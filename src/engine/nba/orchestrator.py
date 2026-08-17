"""
NBA Engine — Batch Orchestrator.

This module is the central controller for the Next Best Action pipeline.
It wires together the compliance guardrails and the contextual bandit,
processing a full Polars DataFrame batch produced by Phase 1 (Matrix
Engine) and returning a recommendation DataFrame ready for DB persistence.

Pipeline per customer:

    raw dict row
        │
        ▼
    CustomerState (Pydantic validation)
        │
        ▼
    RuleEngine.evaluate()
        ├── is_excluded=True  → NBAOutput (Special Handling, no channel)
        └── is_excluded=False
                │
                ├── allowed_channels=[]  → NBAOutput (Wait, no channel)
                └── allowed_channels=[…] → ContextualBandit.get_best_action()
                                                │
                                                ▼
                                           NBAOutput (channel + treatment)
        │
        ▼
    Accumulated into pl.DataFrame (DB schema for PIO_COLL_AI_NBA_ACTIONS)

Fault Isolation:
    A single malformed row (bad data type, missing field, etc.) logs
    an ERROR and writes a sentinel ``NBAOutput`` with
    decision_reason="ERROR:PROCESSING_FAILED" for that customer.
    The batch continues uninterrupted.
"""

from __future__ import annotations

import traceback
from dataclasses import asdict  # noqa: F401
from typing import Any, List

import polars as pl
from pydantic import ValidationError  # noqa: F401

from src.core.logger import get_logger
from src.engine.nba.bandit import ContextualBandit
from src.engine.nba.guardrails import RuleEngine
from src.engine.nba.schemas import Channel, CustomerState, NBAOutput, Treatment # noqa: F401
from src.explainability.xai_aggregator import CockpitAggregator
from src.core.config import settings

logger = get_logger(__name__)


# ── Sentinel constants ────────────────────────────────────────────────

_CHANNEL_NONE: str = "None"
_REASON_CAP_REACHED: str = "CHANNEL_FREQUENCY_CAP_REACHED"
_REASON_ERROR: str = "ERROR:PROCESSING_FAILED"

# DB column names for the output table PIO_COLL_AI_NBA_ACTIONS.
# Kept as constants so a schema rename only touches one place.
_COL_CUST_ID: str = "CUST_INFO_ID"
_COL_CHANNEL: str = "RECOMMENDED_CHANNEL"
_COL_OFFER: str = "RECOMMENDED_OFFER"
_COL_REASON: str = "DECISION_REASON"


class NBAOrchestrator:
    """Central controller that wires guardrails and bandit together.

    Accepts both single-customer dicts (for real-time scoring) and
    full Polars DataFrames (for the nightly batch job), returning
    results in the target DB schema.

    Attributes:
        rule_engine (RuleEngine): Deterministic compliance filter.
            Instantiated once and reused across the entire batch
            for performance.
        bandit (ContextualBandit): Heuristic decision engine.
            Instantiated once; stateless per evaluation call.

    Example — single customer::

        orchestrator = NBAOrchestrator()
        output = orchestrator.process_single_customer({
            "cust_info_id": "123",
            "current_quadrant": "Q1",
            "account_status": "Active",
            "total_due": 1500.0,
            "sms_sent_this_week": 1,
            "calls_made_today": 0,
        })

    Example — full batch::

        df_results = orchestrator.process_batch(df_phase1_output)
        repo.upsert_nba_actions(df_results)
    """

    def __init__(self) -> None:
        """Initialise the orchestrator with its two sub-components.

        Both sub-components use default configurations. To override
        compliance limits (e.g. per-institution SMS caps), instantiate
        ``RuleEngine`` separately and pass it in via composition once
        the codebase grows to support multi-tenancy.
        """
        self.rule_engine = RuleEngine()
        self.bandit = ContextualBandit()
        logger.info("NBAOrchestrator ready.")

    # ── Public API ────────────────────────────────────────────────────

    def process_single_customer(self, raw_data: dict[str, Any]) -> NBAOutput:
        """Run the full NBA pipeline for a single customer.

        Validates the raw input, applies compliance guardrails, and
        delegates to the bandit for action selection. Every exit path
        produces a valid ``NBAOutput`` — the caller never needs to
        handle ``None``.

        Args:
            raw_data (dict[str, Any]): A dictionary containing the
                fields required by ``CustomerState``. Typically one
                row from a Polars DataFrame obtained via
                ``.iter_rows(named=True)``. Required keys:
                ``cust_info_id``, ``current_quadrant``,
                ``account_status``, ``total_due``,
                ``sms_sent_this_week``, ``calls_made_today``.

        Returns:
            NBAOutput: A fully validated recommendation record.
                Always returned — never raises. Error cases are
                captured in ``decision_reason``.

        Decision tree:

        - **ValidationError** → sentinel output with
          ``decision_reason="ERROR:PROCESSING_FAILED"``.
        - **Excluded customer** → channel=``"None"``,
          treatment=``"Special Handling"``,
          reason=``"EXCLUDED:<STATUS>"``.
        - **All channels capped** → channel=``"None"``,
          treatment=``"Wait"``,
          reason=``"CHANNEL_FREQUENCY_CAP_REACHED"``.
        - **Channels available** → bandit-selected output with
          structured ``decision_reason``.
        """
        cust_id: str = raw_data.get("cust_info_id", "UNKNOWN")

        # ── Step 1: Validate input ───────────────────────────────────
        try:
            from src.engine.inference.signal_interpreter import SignalInterpreter
            raw_data["behavioral_signals"] = SignalInterpreter.generate_signals(raw_data)
            customer = CustomerState(**raw_data)
        except ValidationError as exc:
            logger.error(
                f"Validation failed for customer '{cust_id}': {exc}. "
                f"Raw data: {raw_data}"
            )
            return self._error_output(cust_id, exc)

        # ── Step 2: Apply guardrails ─────────────────────────────────
        try:
            guardrail_result = self.rule_engine.evaluate(customer)
        except Exception as exc:
            logger.error(
                f"RuleEngine raised an unexpected error for "
                f"'{customer.cust_info_id}': {exc}\n{traceback.format_exc()}"
            )
            return self._error_output(customer.cust_info_id, exc)

        # ── Step 3a: Excluded customer ───────────────────────────────
        if guardrail_result.is_excluded:
            # exclusion_output is always populated when is_excluded=True
            return guardrail_result.exclusion_output  # type: ignore[return-value]

        # ── Step 3b: All channels capped ─────────────────────────────
        if not guardrail_result.allowed_channels:
            logger.info(
                f"All channels capped for {customer.cust_info_id}. "
                f"Rules fired: {guardrail_result.applied_rules}"
            )
            return NBAOutput(
                cust_info_id=customer.cust_info_id,
                recommended_channel=_CHANNEL_NONE,
                recommended_treatment=Treatment.PTP.value,  # lightest treatment as placeholder
                decision_reason=_REASON_CAP_REACHED,
            )

        # ── Step 3c: Delegate to bandit ──────────────────────────────
        try:
            return self.bandit.get_best_action(
                customer=customer,
                allowed_channels=guardrail_result.allowed_channels,
            )
        except Exception as exc:
            logger.error(
                f"Bandit raised an unexpected error for "
                f"'{customer.cust_info_id}': {exc}\n{traceback.format_exc()}"
            )
            return self._error_output(customer.cust_info_id, exc)

    def process_batch(self, df: pl.DataFrame) -> pl.DataFrame:
        """Run the full NBA pipeline for a Polars DataFrame batch.

        This is the **main entry point for the nightly pipeline**.
        It iterates row-by-row (safer than vectorization for complex
        Python object orchestration), accumulates ``NBAOutput``
        records, and returns a DataFrame matching the DB schema for
        ``PIO_COLL_AI_NBA_ACTIONS``.

        One bad row will never crash the batch — it produces a
        sentinel error row and processing continues.

        Args:
            df (pl.DataFrame): Input DataFrame from Phase 1. Expected
                columns: ``CUST_INFO_ID``, ``CURRENT_QUADRANT``,
                ``ACCOUNT_STATUS``, ``TOTAL_DUE``,
                ``SMS_SENT_THIS_WEEK``, ``CALLS_MADE_TODAY``.
                Column names are normalised to lowercase before
                being passed to ``CustomerState``.

        Returns:
            pl.DataFrame: Result DataFrame with the following schema,
                ready for direct upsert into ``PIO_COLL_AI_NBA_ACTIONS``:

                | Column                | Type   |
                |-----------------------|--------|
                | CUST_INFO_ID          | Utf8   |
                | RECOMMENDED_CHANNEL   | Utf8   |
                | RECOMMENDED_OFFER     | Utf8   |
                | DECISION_REASON       | Utf8   |

        Raises:
            ValueError: If the input DataFrame is ``None`` or empty.
        """
        if df is None or df.height == 0:
            raise ValueError(
                "process_batch received an empty or None DataFrame. "
                "Ensure Phase 1 scoring has produced output before "
                "calling the NBA pipeline."
            )

        logger.info(
            f"NBA batch processing started | "
            f"rows={df.height:,}, columns={df.columns}"
        )

        results: List[dict[str, str]] = []
        error_count: int = 0

        for row in df.iter_rows(named=True):
            # Normalise column names to lowercase so CustomerState
            # field names match regardless of DB column casing.
            normalised = {k.lower(): v for k, v in row.items()}
            output = self.process_single_customer(normalised)

            # Generate Cockpit Payload for Lazy-Loading LLM
            ai_payload = CockpitAggregator.generate_payload_string(
                cust_info_id=output.cust_info_id,
                country_code=settings.COUNTRY_CODE,
                inst_code=settings.INST_CODE,
                day_date=str(row.get("DAY_DATE", "UNKNOWN")),
                quadrant=str(row.get("CURRENT_QUADRANT", "UNKNOWN")),
                will_risk=row.get("WILL_RISK_DRIVERS"),
                will_pos=row.get("WILL_POSITIVE_DRIVERS"),
                abil_risk=row.get("ABIL_RISK_DRIVERS"),
                abil_pos=row.get("ABIL_POSITIVE_DRIVERS"),
                nba_channel=output.recommended_channel,
                nba_treatment=output.recommended_treatment,
                scored_alternatives=[a.model_dump() for a in getattr(output, "scored_alternatives", [])],
                raw_record=row
            )
            import json
            scored_alts_json = json.dumps([a.model_dump() for a in getattr(output, "scored_alternatives", [])])

            results.append({
                _COL_CUST_ID:  output.cust_info_id,
                _COL_CHANNEL:  output.recommended_channel,
                _COL_OFFER:    output.recommended_treatment,
                _COL_REASON:   output.decision_reason,
                "AI_PAYLOAD":  ai_payload,
                "SCORED_ALTERNATIVES": scored_alts_json,
            })

            if output.decision_reason.startswith("ERROR:"):
                error_count += 1

        result_df = pl.DataFrame(
            results,
            schema={
                _COL_CUST_ID: pl.Utf8,
                _COL_CHANNEL: pl.Utf8,
                _COL_OFFER:   pl.Utf8,
                _COL_REASON:  pl.Utf8,
                "AI_PAYLOAD": pl.Utf8,
                "SCORED_ALTERNATIVES": pl.Utf8,
            },
        )

        success_count = df.height - error_count
        logger.info(
            f"NBA batch complete | "
            f"total={df.height:,}, "
            f"success={success_count:,}, "
            f"errors={error_count:,}"
        )
        if error_count > 0:
            logger.warning(
                f"{error_count} row(s) could not be processed. "
                f"Review ERROR rows in {_COL_REASON} column."
            )

        return result_df

    # ── Private Helpers ───────────────────────────────────────────────

    @staticmethod
    def _error_output(cust_id: str, exc: Exception) -> NBAOutput:
        """Produce a sentinel NBAOutput for rows that fail processing.

        Ensures the batch DataFrame always has a record for every
        input customer, even when processing fails. The error detail
        is embedded in ``decision_reason`` for downstream triage.

        Args:
            cust_id (str): Customer identifier, used as the DB key.
                May be ``"UNKNOWN"`` if the ID itself was missing.
            exc (Exception): The exception that caused the failure.
                Its type name is appended to the reason code.

        Returns:
            NBAOutput: Sentinel output with channel=``"None"``,
                treatment=``"Special Handling"``, and
                ``decision_reason="ERROR:PROCESSING_FAILED:<ExcType>"``.
        """
        return NBAOutput(
            cust_info_id=cust_id,
            recommended_channel=_CHANNEL_NONE,
            recommended_treatment=Treatment.SPECIAL_HANDLING.value,
            decision_reason=f"{_REASON_ERROR}:{type(exc).__name__}",
        )
