"""
Input Data Validation Module.

Provides pre-flight checks for DataFrames before they enter training,
scoring, or matrix integration phases. Catches data quality issues
early to prevent silent failures downstream.

Usage:
    from src.core.validation import validate_training_data, validate_scoring_data

    validate_training_data(df, target_col="TARGET_WILLINGNESS", context="Willingness Training")
"""

import logging
from typing import List, Optional

import polars as pl

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────
MIN_ROWS_TRAINING = 50         # absolute minimum to attempt training
MIN_ROWS_SCORING = 1           # at least 1 row to score
MAX_NULL_RATIO = 0.50           # warn if >50% nulls in any feature column
IMBALANCE_FLOOR = 0.02          # error if minority class < 2%
IMBALANCE_WARN = 0.10           # warn  if minority class < 10%
INF_TOLERANCE = 0               # zero infinities allowed


class DataValidationError(Exception):
    """Raised when input data fails a critical validation check."""
    pass


# ── Public API ───────────────────────────────────────────────────────

def validate_training_data(
    df: pl.DataFrame,
    target_col: str,
    feature_cols: Optional[List[str]] = None,
    context: str = "Training",
) -> None:
    """
    Validate a DataFrame before it enters the training pipeline.

    Checks performed:
      1. Not empty
      2. Minimum row count
      3. Target column exists and is binary (0/1)
      4. Class balance is acceptable
      5. No fully-null feature columns
      6. No excessive nulls in any feature
      7. No infinite values
      8. No constant (zero-variance) features

    Args:
        df: Input Polars DataFrame
        target_col: Name of the target column
        feature_cols: Optional explicit list of feature columns.
                      If None, all non-target non-ID columns are used.
        context: Label for log messages (e.g., "Willingness Training")

    Raises:
        DataValidationError: If any critical check fails
    """
    logger.info(f"[{context}] Running input data validation...")

    # ── 1. Empty check ───────────────────────────────────────────
    if df is None or df.height == 0:
        raise DataValidationError(
            f"[{context}] Input DataFrame is empty. "
            f"Check your data source query and date filter."
        )

    logger.info(f"[{context}] Shape: {df.height:,} rows × {df.width} columns")

    # ── 2. Minimum row count ─────────────────────────────────────
    if df.height < MIN_ROWS_TRAINING:
        raise DataValidationError(
            f"[{context}] Only {df.height} rows available "
            f"(minimum {MIN_ROWS_TRAINING} required for training). "
            f"The model will not generalize with this little data."
        )

    # ── 3. Target column exists ──────────────────────────────────
    if target_col not in df.columns:
        raise DataValidationError(
            f"[{context}] Target column '{target_col}' not found. "
            f"Available columns: {df.columns}"
        )

    # ── 4. Target is binary ──────────────────────────────────────
    target_values = df[target_col].drop_nulls().unique().to_list()
    non_binary = [v for v in target_values if v not in (0, 1)]
    if non_binary:
        raise DataValidationError(
            f"[{context}] Target '{target_col}' contains non-binary values: "
            f"{non_binary}. Expected only 0 and 1."
        )

    target_nulls = df[target_col].null_count()
    if target_nulls > 0:
        logger.warning(
            f"[{context}] Target '{target_col}' has {target_nulls} NULL values "
            f"({target_nulls/df.height:.1%}). These rows will be excluded."
        )

    # ── 5. Class balance ─────────────────────────────────────────
    class_counts = df.group_by(target_col).agg(pl.len().alias("count"))
    total = df.height
    for row in class_counts.iter_rows(named=True):
        ratio = row["count"] / total
        if ratio < IMBALANCE_FLOOR:
            raise DataValidationError(
                f"[{context}] Extreme class imbalance: class {row[target_col]} "
                f"has only {row['count']} rows ({ratio:.1%}). "
                f"Minimum threshold is {IMBALANCE_FLOOR:.0%}. "
                f"Consider resampling or adjusting the target definition."
            )
        if ratio < IMBALANCE_WARN:
            logger.warning(
                f"[{context}] ⚠ Class imbalance warning: class {row[target_col]} "
                f"has {row['count']} rows ({ratio:.1%})"
            )

    # ── 6. Identify feature columns ──────────────────────────────
    id_cols = {"CUST_INFO_ID", "ACCOUNT_ID", "SNAPSHOT_DATE"}
    target_cols = {target_col, "IS_WILLING", "IS_STABLE"}
    exclude = id_cols | target_cols

    if feature_cols is None:
        feature_cols = [c for c in df.columns if c not in exclude]

    if len(feature_cols) == 0:
        raise DataValidationError(
            f"[{context}] No feature columns found after excluding "
            f"ID and target columns. Available columns: {df.columns}"
        )

    # ── 7. Fully-null columns ────────────────────────────────────
    fully_null = [
        col for col in feature_cols
        if df[col].null_count() == df.height
    ]
    if fully_null:
        raise DataValidationError(
            f"[{context}] Columns are 100% NULL: {fully_null}. "
            f"These cannot be used as features."
        )

    # ── 8. Excessive nulls ───────────────────────────────────────
    for col in feature_cols:
        null_ratio = df[col].null_count() / df.height
        if null_ratio > MAX_NULL_RATIO:
            logger.warning(
                f"[{context}] ⚠ Column '{col}' has {null_ratio:.1%} NULL values "
                f"(threshold: {MAX_NULL_RATIO:.0%})"
            )

    # ── 9. Infinite values ───────────────────────────────────────
    numeric_cols = [
        col for col in feature_cols
        if df[col].dtype in (pl.Float32, pl.Float64)
    ]
    for col in numeric_cols:
        inf_count = df.filter(pl.col(col).is_infinite()).height
        if inf_count > INF_TOLERANCE:
            logger.warning(
                f"[{context}] ⚠ Column '{col}' has {inf_count} infinite values. "
                f"These will cause NaN in model predictions."
            )

    # ── 10. Constant (zero-variance) features ────────────────────
    constant_cols = [
        col for col in feature_cols
        if df[col].n_unique() <= 1
    ]
    if constant_cols:
        logger.warning(
            f"[{context}] ⚠ Constant features detected (zero variance): "
            f"{constant_cols}. These contribute nothing to the model."
        )

    logger.info(
        f"[{context}] ✅ Validation passed: "
        f"{df.height:,} rows, {len(feature_cols)} features"
    )


def validate_scoring_data(
    df: pl.DataFrame,
    context: str = "Scoring",
) -> None:
    """
    Validate a DataFrame before scoring (lighter checks than training).

    Checks:
      1. Not empty
      2. Has an ID column
      3. No fully-null feature columns

    Args:
        df: Input Polars DataFrame
        context: Label for log messages

    Raises:
        DataValidationError: If any critical check fails
    """
    logger.info(f"[{context}] Running scoring data validation...")

    if df is None or df.height == 0:
        raise DataValidationError(
            f"[{context}] Input DataFrame is empty. Nothing to score."
        )

    # Must have an ID column
    if "CUST_INFO_ID" not in df.columns and "ACCOUNT_ID" not in df.columns:
        raise DataValidationError(
            f"[{context}] No ID column found. "
            f"DataFrame must contain 'CUST_INFO_ID' or 'ACCOUNT_ID'."
        )

    logger.info(
        f"[{context}] ✅ Scoring validation passed: {df.height:,} rows"
    )


def validate_matrix_inputs(
    df: pl.DataFrame,
    required_cols: List[str],
    context: str = "Matrix Integration",
) -> None:
    """
    Validate DataFrame before matrix integration / DB persistence.

    Args:
        df: Merged DataFrame with scores
        required_cols: Columns that must exist
        context: Label for log messages

    Raises:
        DataValidationError: If any critical check fails
    """
    logger.info(f"[{context}] Running matrix input validation...")

    if df is None or df.height == 0:
        raise DataValidationError(f"[{context}] DataFrame is empty.")

    missing = set(required_cols) - set(df.columns)
    if missing:
        raise DataValidationError(
            f"[{context}] Missing required columns: {missing}. "
            f"Available: {df.columns}"
        )

    # Check for duplicate CUST_INFO_IDs
    if "CUST_INFO_ID" in df.columns:
        dupes = df.height - df["CUST_INFO_ID"].n_unique()
        if dupes > 0:
            logger.warning(
                f"[{context}] ⚠ {dupes} duplicate CUST_INFO_ID values detected. "
                f"MERGE may produce unexpected results."
            )

    logger.info(
        f"[{context}] ✅ Matrix validation passed: {df.height:,} rows"
    )
