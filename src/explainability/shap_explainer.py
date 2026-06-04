"""
SHAP-based Model Explanation Engine for Collection AI.

Follows the AML (Smart_AML2025) SHAP architecture with two classes:
- ShapAlertFilter:            Filters to only new/changed alert patterns.
- CollectionShapExplainer:    Per-customer SHAP with formatted explanations.

Output format follows PIO_AML_CUSTOMERS.AML_NEXT_DECISION pattern:
    "Feature_A: 42.9%; Feature_B: 28.7%; Feature_C: 17.0%"

Design Principles:
1. Multiprocessing   – ProcessPoolExecutor with order preserved via row_idx
2. GPU/CPU Auto      – TreeExplainer auto GPU; KernelExplainer CPU fallback
3. Graceful Degrade  – SHAP failures caught and logged, never raised
4. Batch Optimised   – Configurable batch_size for memory safety
"""

import logging
import math
import os
import tempfile
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)

# ── SHAP availability ────────────────────────────────────────────────
try:
    import shap

    SHAP_AVAILABLE = True
    logger.debug(f"SHAP version {shap.__version__} loaded")
except ImportError:
    SHAP_AVAILABLE = False
    logger.warning("SHAP not available. Explainability will be limited.")


# ── GPU detection ─────────────────────────────────────────────────────
def _detect_gpu() -> bool:
    """Detect whether a CUDA-capable GPU is available."""
    try:
        import cupy  # noqa: F401

        cupy.cuda.Device(0).compute_capability
        return True
    except Exception:
        pass
    try:
        import torch

        if torch.cuda.is_available():
            return True
    except Exception:
        pass
    return False


GPU_AVAILABLE = _detect_gpu()


# ── SHAP explainer factory (GPU/CPU auto-detect) ─────────────────────
def get_shap_explainer(model, background_data=None):
    """
    Create SHAP explainer with automatic GPU/CPU detection.

    For XGBoost / tree-based models → shap.TreeExplainer (auto GPU).
    Fallback → shap.KernelExplainer (CPU, universal).
    """
    import xgboost as xgb

    # Try TreeExplainer first (fastest, auto-GPU for XGBoost)
    try:
        if hasattr(model, "get_booster") or isinstance(model, xgb.Booster):
            explainer = shap.TreeExplainer(model)
            logger.info("Using TreeExplainer (auto GPU/CPU)")
            return explainer
    except Exception:
        pass

    try:
        explainer = shap.TreeExplainer(model)
        logger.info("Using TreeExplainer (CPU)")
        return explainer
    except Exception:
        pass

    # Fallback: KernelExplainer (slower, universal)
    if background_data is not None:
        explainer = shap.KernelExplainer(
            model.predict, background_data, nsamples=100
        )
        logger.info("Using KernelExplainer (CPU fallback)")
        return explainer

    raise RuntimeError("Could not create SHAP explainer for this model")


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║  Class 1 — ShapAlertFilter                                          ║
# ╚═══════════════════════════════════════════════════════════════════════╝

class ShapAlertFilter:
    """
    Filters SHAP explanations to only include NEW alert patterns.

    Compares top-N feature keys in newly-computed explanations vs.
    previously-stored ones to determine if the pattern has changed.
    """

    def __init__(self, logger, top_n: int = 3):
        self.top_n = top_n
        self.logger = logger

    def extract_top_keys(self, explanation: str) -> Set[str]:
        """
        Extract the top_n feature keys from an explanation string.

        Expected format: "Feature_A: 40.2%; Feature_B: 30.5%; Feature_C: 29.3%"
        Returns: set of feature keys (e.g. {"Feature_A", "Feature_B", "Feature_C"})
        """
        if not explanation or not isinstance(explanation, str):
            return set()
        pairs = [p.strip() for p in explanation.split(";") if p.strip()]
        top_pairs = pairs[: self.top_n]
        keys = {
            p.split(":")[0].strip() for p in top_pairs if ":" in p
        }
        return keys

    def filter_new_alerts(
        self,
        results: Dict[str, Any],
        previous_data: pl.DataFrame,
    ) -> pl.DataFrame:
        """
        Join new explanations with previous DWH data on CUST_INFO_ID.
        Compare top-N feature keys; only return rows where the
        explanation pattern has genuinely changed.

        Args:
            results: dict with key 'explanations' → new Polars DataFrame
            previous_data: Polars DataFrame from DWH with column
                           SHAP_RAW_FEATURES carrying the old pattern.

        Returns:
            Filtered DataFrame containing only new/changed alerts.
        """
        new_df = results.get("explanations")
        if new_df is None or new_df.is_empty():
            return new_df

        primary_keys = ["CUST_INFO_ID"]

        if previous_data is None or previous_data.is_empty():
            self.logger.info("No previous data — all alerts are new")
            return new_df

        # Cast join keys to string for consistency
        new_cast = new_df.with_columns(
            [pl.col(k).cast(pl.Utf8).alias(k) for k in primary_keys]
        )
        prev_cast = previous_data.with_columns(
            [pl.col(k).cast(pl.Utf8).alias(k) for k in primary_keys]
        )

        # Left join to bring in previous SHAP features
        joined = new_cast.join(
            prev_cast.select(primary_keys + ["SHAP_RAW_FEATURES"]),
            on=primary_keys,
            how="left",
            suffix="_prev",
        )

        # Compare top-N feature keys
        new_col = "reason_cols"
        prev_col = "SHAP_RAW_FEATURES"

        keep_mask = []
        for row in joined.iter_rows(named=True):
            new_keys = self.extract_top_keys(row.get(new_col, ""))
            prev_keys = self.extract_top_keys(row.get(prev_col, ""))
            keep_mask.append(new_keys != prev_keys)

        if not any(keep_mask):
            self.logger.info(
                "All alerts match previous patterns — none are new"
            )
            return new_df.head(0)

        filtered = joined.filter(pl.Series(keep_mask))

        # Drop columns brought in from the previous data
        drop_cols = [
            c
            for c in filtered.columns
            if c.endswith("_prev") or c == prev_col
        ]
        filtered = filtered.drop(
            [c for c in drop_cols if c in filtered.columns]
        )

        self.logger.info(
            f"Filtered: {sum(keep_mask)} new alerts "
            f"out of {len(keep_mask)} total"
        )
        return filtered


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║  Module-level worker for ProcessPoolExecutor                         ║
# ╚═══════════════════════════════════════════════════════════════════════╝

def _shap_batch_worker(
    model_bytes: bytes,
    X_batch: np.ndarray,
    feature_names: List[str],
    row_indices: List[int],
    batch_id: int,
    top_n: int,
    model_type: str,
) -> List[Dict[str, Any]]:
    """
    Pickle-friendly worker executed in a child process.

    Uses XAIMapper to translate technical columns to UI labels and
    business context for LLM narrative generation.
    """
    import json
    import xgboost as xgb
    import shap
    import numpy as np
    from src.explainability.xai_mapper import XAIMapper

    mapper = XAIMapper()

    # ── Reconstruct model in child process ───────────────────────────
    tmp_path = os.path.join(
        tempfile.gettempdir(),
        f"shap_mdl_{os.getpid()}_{batch_id}.ubj",
    )
    try:
        with open(tmp_path, "wb") as f:
            f.write(model_bytes)
        model = xgb.Booster()
        model.load_model(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # ── Create SHAP explainer ────────────────────────────────────────
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_batch)

    # ── Format per row ───────────────────────────────────────────────
    results = []
    for i, row_idx in enumerate(row_indices):
        sv = shap_values[i]
        abs_sv = np.abs(sv)
        total_abs = float(abs_sv.sum())

        if total_abs == 0:
            results.append(
                {
                    "row_idx": row_idx,
                    "risk_drivers": "[]",
                    "positive_drivers": "[]",
                    "batch_id": batch_id,
                }
            )
            continue

        # Top-N features by absolute SHAP value
        sorted_idx = np.argsort(abs_sv)[::-1][:top_n]

        risk_drivers = []
        positive_drivers = []
        
        def get_impact(percentage_val):
            if percentage_val >= 25.0:
                return "Primary Driver"
            elif percentage_val >= 10.0:
                return "Secondary Factor"
            else:
                return "Contributing Factor"

        for idx in sorted_idx:
            feat = feature_names[idx]
            metadata = mapper.get_metadata(feat)
            shap_val = float(sv[idx])
            
            # Calculate percentage impact relative to total variance
            pct = (abs(shap_val) / total_abs) * 100.0 if total_abs > 0 else 0
            
            entry = {
                "feature": metadata.ui_label,
                "impact": get_impact(pct),
                "percentage": round(pct, 2)
            }
            
            if shap_val < 0:
                risk_drivers.append(entry)
            else:
                positive_drivers.append(entry)

        try:
            risk_json = json.dumps(risk_drivers)
        except Exception:
            risk_json = "[]"
            
        try:
            pos_json = json.dumps(positive_drivers)
        except Exception:
            pos_json = "[]"

        results.append(
            {
                "row_idx": row_idx,
                "risk_drivers": risk_json,
                "positive_drivers": pos_json,
                "batch_id": batch_id,
            }
        )

    return results


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║  Class 2 — CollectionShapExplainer                                   ║
# ╚═══════════════════════════════════════════════════════════════════════╝

class CollectionShapExplainer:
    """
    Generates SHAP explanations for scored customers.

    Adds two columns to the input DataFrame:
      - **reason_cols**:  "FEAT_A: 42.9%; FEAT_B: 28.7%; FEAT_C: 17.0%"
      - **reason_desc**:  Comma-joined detailed descriptions of those features.

    Uses multiprocessing for large batches; preserves original record
    order via Polars ``with_row_index()`` (NOT customer ID).

    Usage::

        explainer = CollectionShapExplainer(logger=my_logger)
        df_with_shap = explainer.explain_predictions(
            df, model=booster, model_type="willingness"
        )
    """

    def __init__(
        self,
        logger,
        top_n: int = 3,
        importance_threshold: float = 0.95,
        batch_size: int = 20,
        n_jobs: int = -1,
    ):
        self.logger = logger
        self.top_n = top_n
        self.importance_threshold = importance_threshold
        self.batch_size = batch_size
        self.n_jobs = n_jobs if n_jobs != -1 else min(os.cpu_count() or 4, 8)
        self.use_gpu = GPU_AVAILABLE

        self.logger.info(
            f"CollectionShapExplainer initialised: "
            f"top_n={top_n}, batch_size={batch_size}, "
            f"n_jobs={self.n_jobs}, gpu={self.use_gpu}"
        )

    # ── Model serialisation ──────────────────────────────────────────

    @staticmethod
    def _serialise_model(model) -> bytes:
        """Serialise an XGBoost Booster to raw bytes (for IPC)."""
        tmp = os.path.join(
            tempfile.gettempdir(), f"_xgb_{os.getpid()}.ubj"
        )
        try:
            model.save_model(tmp)
            with open(tmp, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    # ── Public API ───────────────────────────────────────────────────

    def explain_predictions(
        self,
        df: pl.DataFrame,
        model,
        model_type: str = "willingness",
        target_col: str = "prediction",
        id_col: str = "CUST_INFO_ID",
        risk_drivers_col: str = "SHAP_RISK_DRIVERS",
        positive_drivers_col: str = "SHAP_POSITIVE_DRIVERS",
        exclude_cols: Optional[Set[str]] = None,
    ) -> pl.DataFrame:
        """
        For each customer row:

        1. Add ``row_idx`` via ``with_row_index()`` for order preservation.
        2. Identify feature columns (exclude identifiers / targets).
        3. Cast to Float64, fill nulls with 0.
        4. Serialise model for worker processes.
        5. Split into batches → dispatch to ProcessPoolExecutor.
        6. Per row: compute SHAP → sort by |value| → top_n → pct format.
        7. Join results back via ``row_idx`` (NOT customer ID).

        Args:
            df:              Input DataFrame with features.
            model:           Trained XGBoost Booster.
            model_type:      ``'willingness'`` or ``'ability'``.
            target_col:      Name of the prediction column (excluded).
            id_col:          Customer identifier column (excluded).
            reason_cols:     Output column for technical SHAP string.
            descriptive_col: Output column for detailed descriptions.
            exclude_cols:    Additional columns to exclude from features.

        Returns:
            DataFrame with ``reason_cols`` and ``descriptive_col`` added.
        """
        if not SHAP_AVAILABLE:
            self.logger.warning(
                "SHAP not available — returning empty explanations"
            )
            return df.with_columns(
                [
                    pl.lit("[]").alias(risk_drivers_col),
                    pl.lit("[]").alias(positive_drivers_col),
                ]
            )

        self.logger.info(
            f"Starting SHAP explanations for {df.height:,} customers "
            f"({model_type})"
        )

        # 1 ── row index
        df_indexed = df.with_row_index(name="row_idx")

        # 2 ── feature columns
        default_exclude = {
            id_col,
            target_col,
            "IS_WILLING",
            "IS_STABLE",
            "SNAPSHOT_DATE",
            "DAY_DATE",
            "INST_CODE",
            "COUNTRY_CODE",
            "TARGET_WILLINGNESS",
            "TARGET_ABILITY",
            "ACCOUNT_STATUS",
            "TOTAL_DUE",
            "SMS_SENT_THIS_WEEK",
            "CALLS_MADE_TODAY",
            "row_idx",
        }
        if exclude_cols:
            default_exclude.update(exclude_cols)
        feature_names = [
            c for c in df_indexed.columns if c not in default_exclude
        ]

        self.logger.info(
            f"Feature columns ({len(feature_names)}): {feature_names}"
        )

        # 3 ── cast + fill nulls
        df_features = df_indexed.select(
            [
                pl.col(c).cast(pl.Float64).fill_null(0.0)
                for c in feature_names
            ]
        )
        X = df_features.to_numpy().astype(np.float32)
        row_indices = df_indexed["row_idx"].to_list()

        # 4 ── serialise model
        model_bytes = self._serialise_model(model)

        # 5 ── split into batches
        n_total = len(X)
        n_batches = math.ceil(n_total / self.batch_size)
        batches = []
        for b in range(n_batches):
            start = b * self.batch_size
            end = min(start + self.batch_size, n_total)
            batches.append((X[start:end], row_indices[start:end], b))

        self.logger.info(
            f"Dispatching {n_batches} batch(es) to "
            f"{self.n_jobs} worker(s)"
        )

        # 6 ── execute batches
        all_results: List[Dict[str, Any]] = []
        effective_workers = min(self.n_jobs, n_batches)

        if effective_workers <= 1 or n_total <= self.batch_size:
            # Sequential (small dataset or single batch)
            for X_b, idx_b, bid in batches:
                try:
                    batch_res = _shap_batch_worker(
                        model_bytes,
                        X_b,
                        feature_names,
                        idx_b,
                        bid,
                        self.top_n,
                        model_type,
                    )
                    all_results.extend(batch_res)
                except Exception as e:
                    self.logger.error(f"Batch {bid} failed: {e}")
                    self.logger.debug(traceback.format_exc())
        else:
            with ProcessPoolExecutor(
                max_workers=effective_workers
            ) as pool:
                futures = {}
                for X_b, idx_b, bid in batches:
                    fut = pool.submit(
                        _shap_batch_worker,
                        model_bytes,
                        X_b,
                        feature_names,
                        idx_b,
                        bid,
                        self.top_n,
                        model_type,
                    )
                    futures[fut] = bid

                for fut in as_completed(futures):
                    bid = futures[fut]
                    try:
                        batch_res = fut.result()
                        all_results.extend(batch_res)
                        self.logger.debug(
                            f"Batch {bid} done ({len(batch_res)} rows)"
                        )
                    except Exception as e:
                        self.logger.error(f"Batch {bid} failed: {e}")

        # 7 ── sort by row_idx to restore original order
        all_results.sort(key=lambda r: r["row_idx"])

        # 8 ── build result DataFrame
        if all_results:
            results_df = pl.DataFrame(
                {
                    "row_idx": [
                        r["row_idx"] for r in all_results
                    ],
                    risk_drivers_col: [
                        r["risk_drivers"] for r in all_results
                    ],
                    positive_drivers_col: [
                        r["positive_drivers"] for r in all_results
                    ],
                }
            )
        else:
            results_df = pl.DataFrame(
                {
                    "row_idx": pl.Series([], dtype=pl.UInt32),
                    risk_drivers_col: pl.Series([], dtype=pl.Utf8),
                    positive_drivers_col: pl.Series([], dtype=pl.Utf8),
                }
            )

        # 9 ── join back via row_idx
        df_out = df_indexed.join(results_df, on="row_idx", how="left")

        df_out = df_out.with_columns(
            [
                pl.col(risk_drivers_col).fill_null("[]"),
                pl.col(positive_drivers_col).fill_null("[]"),
            ]
        )

        # Drop the helper column
        df_out = df_out.drop("row_idx")

        self.logger.info(
            f"SHAP explanations complete: {len(all_results)} "
            f"explanations for {df.height:,} customers"
        )

        return df_out
