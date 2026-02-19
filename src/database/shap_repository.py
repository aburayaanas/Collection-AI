"""
SHAP Results DWH Repository.

Handles persistence of SHAP explanation results into
PIO_COLL_AI_MATRIX_RESULTS on the openbi2 Data Warehouse.

Follows the AML bulk-insert pattern with constraint-violation handling.
"""

import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any

import polars as pl

from src.core.logger import get_logger
from src.database.connection import db
from src.explainability.feature_name_expansion import format_shap_explanation
from src.database.queries import get_snap_date
from src.core.config import settings

logger = get_logger(__name__)

# Load the SQL template once
_SQL_DIR = Path(__file__).resolve().parent / "features"


def _load_sql(filename: str) -> str:
    """Read a .sql file from the features directory."""
    path = _SQL_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class ShapResultsRepository:
    """
    Repository for persisting SHAP explanation outputs to the DWH.

    Target table: PIO_COLL_AI_MATRIX_RESULTS  (openbi2, BI_DWH schema)

    SHAP columns (created by ddl_shap_columns.sql):
        SHAP_EXPLANATION   VARCHAR2(4000)  – Business-friendly text
        SHAP_DESCRIPTION   VARCHAR2(4000)  – Detailed feature descriptions
        SHAP_MODEL_TYPE    VARCHAR2(50)    – 'WILLINGNESS' or 'ABILITY'
        SHAP_RAW_FEATURES  VARCHAR2(4000)  – Technical "FEAT: XX.X%; ..." string
        SHAP_COMPUTED_DATE DATE            – Computation timestamp
    """

    def __init__(self, batch_size: int = 500):
        """
        Args:
            batch_size: Number of rows per executemany batch.
        """
        self.batch_size = batch_size
        self._update_sql = _load_sql("insert_shap_results.sql")

    # ── Public API ───────────────────────────────────────────────────

    def insert_shap_results(
        self,
        df: pl.DataFrame,
        model_type: str,
    ) -> int:
        """
        Update SHAP explanation results on PIO_COLL_AI_MATRIX_RESULTS.

        The DataFrame must have at least these columns:
            - CUST_INFO_ID
            - reason_cols   (technical string: "FEAT: XX.X%; ...")
            - reason_desc   (detailed descriptions)

        The method converts ``reason_cols`` to the business-friendly
        ``SHAP_EXPLANATION`` via ``format_shap_explanation()`` (Layer 2).

        Args:
            df:         Polars DataFrame with SHAP results.
            model_type: 'willingness' or 'ability'.

        Returns:
            Number of successfully updated rows.
        """
        if df.is_empty():
            logger.warning("Empty DataFrame — nothing to insert.")
            return 0

        # De-duplicate on customer identifier
        unique_df = df.unique(subset=["CUST_INFO_ID"])

        total_rows = unique_df.height
        logger.info(
            f"Inserting {total_rows:,} SHAP results "
            f"(model_type={model_type}) into PIO_COLL_AI_MATRIX_RESULTS ..."
        )

        # Get snapshot date and org codes
        snap_date = get_snap_date(settings.INST_CODE, settings.COUNTRY_CODE)
        if not snap_date:
             logger.error("Could not determine snapshot date for SHAP update!")
             return 0
             
        # Safe type conversion for binding
        try:
            inst_code_val = int(settings.INST_CODE)
        except (ValueError, TypeError):
            inst_code_val = settings.INST_CODE
            
        try:
            country_code_val = int(settings.COUNTRY_CODE)
        except (ValueError, TypeError):
            country_code_val = settings.COUNTRY_CODE

        # Build list of dictionaries matching the named bind variables in the SQL:
        #   :cust_id
        #   :model_type
        #   :explanation
        #   :description
        #   :raw_features
        #   :snap_date
        #   :inst_code
        #   :country_code
        records: List[Dict[str, Any]] = []
        for row in unique_df.iter_rows(named=True):
            cust_id = row["CUST_INFO_ID"]
            raw_features = row.get("reason_cols", "")
            description = row.get("reason_desc", "")

            # Generate business-friendly explanation
            explanation = format_shap_explanation(
                raw_features, model_type=model_type
            )

            records.append({
                "cust_id": cust_id,
                "model_type": model_type.upper(),
                "explanation": explanation,
                "description": description,
                "raw_features": raw_features,
                "snap_date": snap_date,
                "inst_code": inst_code_val,
                "country_code": country_code_val,
            })

        # Execute in batches
        total_success = 0
        total_errors = 0

        with db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                for start in range(0, len(records), self.batch_size):
                    batch = records[start : start + self.batch_size]

                    cursor.executemany(
                        self._update_sql, batch, batcherrors=True
                    )

                    errors = cursor.getbatcherrors()
                    batch_ok = len(batch) - len(errors)
                    total_success += batch_ok
                    total_errors += len(errors)

                    if errors:
                        logger.warning(
                            f"Batch [{start}:{start + len(batch)}]: "
                            f"{len(errors)} error(s)"
                        )
                        for err in errors[:5]:
                            logger.warning(
                                f"  Row {err.offset}: {err.message}"
                            )

                conn.commit()

                logger.info(
                    f"SHAP insertion complete: "
                    f"{total_success:,} ok / {total_errors:,} failed "
                    f"(of {total_rows:,} total)"
                )

            except Exception as e:
                conn.rollback()
                logger.error(f"SHAP insertion failed: {e}")
                raise
            finally:
                cursor.close()

        return total_success
