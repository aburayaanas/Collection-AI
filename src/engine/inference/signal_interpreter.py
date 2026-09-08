from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from src.core.config import settings

class SignalType(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    HYPOTHESIS = "HYPOTHESIS"

class BehavioralSignal(BaseModel):
    signal_type: SignalType
    title: str
    description: str
    confidence: Optional[float] = None

class SignalInterpreter:
    """
    Synthesizes raw transactional and communication logs into structured
    behavioral signals (OBSERVED, INFERRED, and HYPOTHESIS).

    Thresholds are rule-based/heuristic by design (docs/backend_issues.md
    Issue 5) — read from ``Settings`` rather than hardcoded, so they can
    be tuned per-institution without a code change. See
    ``SIGNAL_*`` fields in ``src/core/config.py`` for defaults and the
    Configuration app's "Pipeline" tab for how to change them.
    """

    @staticmethod
    def generate_signals(customer_data: Dict[str, Any]) -> List[BehavioralSignal]:
        signals = []

        # Safe extraction (supports both uppercase and lowercase keys)
        rejection_freq = int(customer_data.get("PAYMENT_REJECTION_FREQ") or customer_data.get("payment_rejection_freq") or 0)
        inflow_variance = float(customer_data.get("INFLOW_VARIANCE_30D") or customer_data.get("inflow_variance_30d") or 0.0)
        ability_score = float(customer_data.get("ABILITY_SCORE") or customer_data.get("ability_score") or 0.0)

        broken_ptp = int(customer_data.get("BROKEN_PTP_COUNT_6M") or customer_data.get("broken_ptp_count_6m") or 0)
        days_since_rpc = customer_data.get("DAYS_SINCE_LAST_RPC") or customer_data.get("days_since_rpc")
        days_since_rpc = int(days_since_rpc) if days_since_rpc is not None else 0
        contact_avoidance = float(customer_data.get("CONTACT_AVOIDANCE_INDEX") or customer_data.get("contact_avoidance_index") or 0.0)

        # 1. The Liquidity Crisis Scenario
        # Drop in inflow variance indicates missing salary, combined with rejection freq
        if rejection_freq > 0 and inflow_variance > settings.SIGNAL_LIQUIDITY_INFLOW_VARIANCE_THRESHOLD:
            signals.append(BehavioralSignal(
                signal_type=SignalType.OBSERVED,
                title="Payment Rejections",
                description=f"{rejection_freq} direct debit rejection(s) detected recently.",
                confidence=1.0
            ))

            # Inverse of ability score to determine hypothesis confidence, clamped to the configured range
            raw_hypothesis_conf = max(0.1, 1.0 - ability_score)
            hypothesis_conf = max(
                settings.SIGNAL_LIQUIDITY_CONFIDENCE_MIN,
                min(settings.SIGNAL_LIQUIDITY_CONFIDENCE_MAX, raw_hypothesis_conf),
            )
            signals.append(BehavioralSignal(
                signal_type=SignalType.HYPOTHESIS,
                title="Liquidity Disruption",
                description="Sudden liquidity disruption detected. Suggests possible employer salary delay or termination.",
                confidence=round(hypothesis_conf, 4)
            ))

        # 2. The Evasion Scenario
        # Unanswered outbound calls + high avoidance index
        if (
            (broken_ptp > 0 or days_since_rpc > settings.SIGNAL_EVASION_DAYS_SINCE_RPC_THRESHOLD)
            and contact_avoidance >= settings.SIGNAL_EVASION_CONTACT_AVOIDANCE_THRESHOLD
        ):
            signals.append(BehavioralSignal(
                signal_type=SignalType.OBSERVED,
                title="Contact Failure",
                description="Recent outbound contact attempts remain unanswered or unresolved.",
                confidence=1.0
            ))

            signals.append(BehavioralSignal(
                signal_type=SignalType.INFERRED,
                title="Evasive Pattern",
                description=f"Evasive behavioral pattern activated. Contact avoidance index ({contact_avoidance:.2f}) exceeds threshold.",
                confidence=round(contact_avoidance, 2)
            ))

        return signals
