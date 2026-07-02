"""
SHAP Phase Orchestration for Collection AI.

Layer 4 of the AML-style architecture.  Provides:
- ``run_shap_phase()``  — single function to run after scoring.
- ``ShadowExplainer``   — class wrapper for backward compatibility.

Shadow Mode Guarantees:
1. SHAP failures never crash the scoring pipeline.
2. No modification of prediction outputs.
3. All errors are logged and suppressed.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import polars as pl
import xgboost as xgb

from src.explainability.shap_explainer import (
    CollectionShapExplainer,
    ShapAlertFilter,
    SHAP_AVAILABLE,
)
from src.database.shap_repository import ShapResultsRepository

logger = logging.getLogger(__name__)


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║  Configuration                                                       ║
# ╚═══════════════════════════════════════════════════════════════════════╝

@dataclass
class ExplainabilityConfig:
    """
    Configuration for SHAP explanation runs.
    """
    enabled: bool = True
    top_n: int = 3
    batch_size: int = 20
    n_jobs: int = -1
    insert_dwh: bool = True
    use_shap_filtering: bool = False   # compare against previous data

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "top_n": self.top_n,
            "batch_size": self.batch_size,
            "n_jobs": self.n_jobs,
            "insert_dwh": self.insert_dwh,
            "use_shap_filtering": self.use_shap_filtering,
        }


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║  Result dataclass                                                    ║
# ╚═══════════════════════════════════════════════════════════════════════╝

@dataclass
class ShadowExplainabilityResult:
    """Result from a shadow explainability run."""
    model_type: str
    model_version: str
    success: bool
    explanations_df: Optional[pl.DataFrame] = None
    dwh_rows_inserted: int = 0
    runtime_seconds: float = 0.0
    error_message: Optional[str] = None


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║  run_shap_phase() — functional entry point (AML pattern)             ║
# ╚═══════════════════════════════════════════════════════════════════════╝

def run_shap_phase(
    scored_data: pl.DataFrame,
    model: xgb.Booster,
    model_type: str,
    model_version: str = "",
    config: Optional[ExplainabilityConfig] = None,
    id_col: str = "CUST_INFO_ID",
) -> ShadowExplainabilityResult:
    """
    Run SHAP explanation phase after scoring.

    This is the top-level entry point, matching the AML architecture.
    It catches ALL exceptions so it never crashes the scoring pipeline.

    Flow:
        1. Generate SHAP explanations via CollectionShapExplainer
        2. (Optional) Filter against historical data via ShapAlertFilter
        3. Insert into PIO_COLL_AI_MATRIX_RESULTS on openbi2

    Args:
        scored_data:   DataFrame with predictions and features.
        model:         The trained XGBoost model used for predictions.
        model_type:    ``'willingness'`` or ``'ability'``.
        model_version: Model version string for audit trail.
        config:        ExplainabilityConfig (uses defaults if None).
        id_col:        Customer identifier column name.

    Returns:
        ShadowExplainabilityResult with success flag and row counts.
    """
    cfg = config or ExplainabilityConfig()
    start = time.time()

    if not cfg.enabled:
        logger.info("[SHAP] Phase disabled — skipping")
        return ShadowExplainabilityResult(
            model_type=model_type,
            model_version=model_version,
            success=True,
        )

    logger.info(
        f"[SHAP] Starting phase for {model_type}: "
        f"{scored_data.height:,} customers, config={cfg.to_dict()}"
    )

    try:
        # ── Step 1: Generate SHAP explanations ───────────────────────
        shap_explainer = CollectionShapExplainer(
            logger=logger,
            top_n=cfg.top_n,
            batch_size=cfg.batch_size,
            n_jobs=cfg.n_jobs,
        )

        explanations_df = shap_explainer.explain_predictions(
            df=scored_data,
            model=model,
            model_type=model_type,
            id_col=id_col,
            risk_drivers_col="SHAP_RISK_DRIVERS",
            positive_drivers_col="SHAP_POSITIVE_DRIVERS",
        )

        logger.info(
            f"[SHAP] Generated explanations for "
            f"{explanations_df.height:,} customers"
        )

        # ── Step 2: (Optional) Filter against previous data ──────────
        if cfg.use_shap_filtering:
            try:
                previous_data = _fetch_previous_shap_data(model_type)
                if previous_data is not None and not previous_data.is_empty():
                    shap_filter = ShapAlertFilter(logger, top_n=cfg.top_n)
                    explanations_df = shap_filter.filter_new_alerts(
                        {"explanations": explanations_df},
                        previous_data,
                    )
                    logger.info(
                        f"[SHAP] After filtering: "
                        f"{explanations_df.height:,} new alerts"
                    )
            except Exception as filter_err:
                logger.warning(
                    f"[SHAP] Alert filtering failed (non-fatal): "
                    f"{filter_err}"
                )

        # ── Step 3: Insert into DWH ──────────────────────────────────
        dwh_rows = 0
        if cfg.insert_dwh and not explanations_df.is_empty():
            try:
                repo = ShapResultsRepository(batch_size=cfg.batch_size)
                dwh_rows = repo.insert_shap_results(
                    explanations_df, model_type
                )
                logger.info(
                    f"[SHAP] Inserted {dwh_rows:,} rows into "
                    f"PIO_COLL_AI_MATRIX_RESULTS"
                )
            except Exception as e:
                logger.error(f"[SHAP] Database insertion failed: {e}")

        elapsed = time.time() - start
        logger.info(
            f"[SHAP] Phase complete for {model_type} in {elapsed:.2f}s: "
            f"explanations={explanations_df.height:,}, "
            f"dwh_rows={dwh_rows}"
        )

        return ShadowExplainabilityResult(
            model_type=model_type,
            model_version=model_version,
            success=True,
            explanations_df=explanations_df,
            dwh_rows_inserted=dwh_rows,
            runtime_seconds=elapsed,
        )

    except Exception as e:
        elapsed = time.time() - start
        err_msg = f"SHAP phase failed: {type(e).__name__}: {e}"
        logger.error(f"[SHAP] {err_msg}", exc_info=True)

        # Shadow mode: return failure, don't raise
        return ShadowExplainabilityResult(
            model_type=model_type,
            model_version=model_version,
            success=False,
            runtime_seconds=elapsed,
            error_message=err_msg,
        )


def _fetch_previous_shap_data(model_type: str) -> Optional[pl.DataFrame]:
    """
    Fetch the most recent SHAP data from DWH for alert filtering.

    Returns None if no previous data exists or on any error.
    """
    from src.database.connection import db

    # Select the appropriate column based on model type
    col_to_check = "WILL_SHAP_EXPLANATION" if model_type.upper() == "WILLINGNESS" else "ABIL_SHAP_EXPLANATION"

    query = (
        f"SELECT CUST_INFO_ID, {col_to_check} "
        "FROM BI_DWH.PIO_COLL_AI_MATRIX_RESULTS "
        f"WHERE {col_to_check} IS NOT NULL"
    )
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()

        if not rows:
            return None

        return pl.DataFrame(
            {
                "CUST_INFO_ID": [r[0] for r in rows],
                "SHAP_RAW_FEATURES": [r[1] for r in rows],
            }
        )
    except Exception as e:
        logger.warning(f"Could not fetch previous SHAP data: {e}")
        return None


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║  ShadowExplainer class — backward-compatible wrapper                 ║
# ╚═══════════════════════════════════════════════════════════════════════╝

class ShadowExplainer:
    """
    Class-based wrapper around ``run_shap_phase()`` for backward
    compatibility with existing code that instantiates ShadowExplainer.
    """

    def __init__(self, config: Optional[ExplainabilityConfig] = None):
        self.config = config or ExplainabilityConfig()
        logger.info(
            f"ShadowExplainer initialised: config={self.config.to_dict()}"
        )

    def explain_model(
        self,
        model: xgb.Booster,
        model_version: str,
        model_type: str,
        df: pl.DataFrame,
        feature_cols: List[str],
        id_col: str = "CUST_INFO_ID",
    ) -> ShadowExplainabilityResult:
        """Delegate to ``run_shap_phase()``."""
        return run_shap_phase(
            scored_data=df,
            model=model,
            model_type=model_type,
            model_version=model_version,
            config=self.config,
            id_col=id_col,
        )
