"""
Database Repository Layer.

This module provides data access methods for persisting ML predictions
to the Oracle database, including bulk MERGE operations.
"""

import polars as pl

from src.core.logger import get_logger
from src.database.connection import db
from src.database.queries import get_query, get_snap_date
from src.core.config import settings

logger = get_logger(__name__)


class CollectionRepository:
    """
    Repository for Collection AI database operations.
    
    Handles persistence of model predictions and integrated scores
    to the COLLECTION_CUSTOMERS table.
    """
    
    def get_willingness_training_data(self) -> pl.DataFrame:
        """
        Fetch and convert willingness training data with strict schema enforcement.
        
        This method executes the willingness SQL query and converts the results
        to a Polars DataFrame with a strictly defined schema to prevent type
        inference errors on NULL values.
        
        Returns:
            Polars DataFrame with willingness features and strict typing
            
        Raises:
            Exception: If query execution or data conversion fails
        """
        logger.info("Fetching willingness training data from database...")
        
        # Get snapshot date
        snap_date = get_snap_date(settings.INST_CODE, settings.COUNTRY_CODE)
        if not snap_date:
             # Fallback or error - let's log and raise
             logger.error("Could not determine snapshot date for filtering!")
             raise ValueError("Snapshot date retrieval failed")

        logger.info(f"Filtering data for snapshot date: {snap_date}")

        # Execute query
        sql = get_query("willingness")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, {'day_date': snap_date})
            
            # Fetch all rows
            rows = cursor.fetchall()
            cursor.close()
        
        logger.info(f"Retrieved {len(rows):,} records from database")
        
        # Define strict schema mapping (SQL column -> Polars type)
        schema = {
            "CUST_INFO_ID": pl.String,
            # PTP Features (Integers)
            "SNAPSHOT_DATE": pl.String,
            "DAYS_SINCE_LAST_RPC": pl.Int64,
            "PTP_RELIABILITY_RATIO": pl.Float64,
            "PAYMENT_VELOCITY_30D": pl.Int64,
            "PARTIAL_PAYMENT_RATIO": pl.Float64,
            "SELF_CURE_HISTORY_FLAG": pl.Int64,
            "BOUNCE_RATE_60D": pl.Float64,
            "BROKEN_PTP_COUNT_6M": pl.Int64,
            "TARGET_WILLINGNESS": pl.Int64,
        }
        
        # Create DataFrame with strict schema
        df = pl.DataFrame(rows, schema=schema, orient="row")
        
        logger.info(f"Converted to Polars DataFrame: {df.shape[0]:,} rows x {df.shape[1]} columns")
        
        # Post-processing: Fill nulls with 0 for safety (except recency columns which should stay null)
        numeric_cols_to_fill = [
            "DAYS_SINCE_LAST_RPC", "PTP_RELIABILITY_RATIO", "PAYMENT_VELOCITY_30D", "PARTIAL_PAYMENT_RATIO", "SELF_CURE_HISTORY_FLAG", "BOUNCE_RATE_60D", "BROKEN_PTP_COUNT_6M"
        ]
        
        df = df.with_columns([
            pl.col(col).fill_null(0) for col in numeric_cols_to_fill
        ])
        
        logger.info("Applied null-filling for numeric features")
        
        return df
    
    def get_ability_training_data(self) -> pl.DataFrame:
        """
        Fetch and convert ability training data with strict schema enforcement.
        
        This method executes the ability SQL query and converts the results
        to a Polars DataFrame with a strictly defined schema to prevent type
        inference errors on NULL values.
        
        Returns:
            Polars DataFrame with ability features and strict typing
            
        Raises:
            Exception: If query execution or data conversion fails
        """
        logger.info("Fetching ability training data from database...")
        
        # Get snapshot date
        snap_date = get_snap_date(settings.INST_CODE, settings.COUNTRY_CODE)
        if not snap_date:
             raise ValueError("Snapshot date retrieval failed")
             
        logger.info(f"Filtering data for snapshot date: {snap_date}")

        # Execute query
        sql = get_query("ability")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, {'day_date': snap_date})
            
            # Fetch all rows
            rows = cursor.fetchall()
            cursor.close()
        
        logger.info(f"Retrieved {len(rows):,} records from database")
        
        # Define strict schema mapping (SQL column -> Polars type)
        schema = {
            "CUST_INFO_ID": pl.String,
            "SNAPSHOT_DATE": pl.String,
            "INFLOW_VARIANCE_30D": pl.Float64,
            "CASH_RUNWAY_DAYS_ESTIMATED": pl.Float64,
            "SPENDING_VOLATILITY_CV_60D": pl.Float64,
            "DEBT_SERVICE_PROXY_RATIO": pl.Float64,
            "NSF_EVENT_RATE_60D": pl.Float64,
            "ZERO_BALANCE_DAYS_RATIO_30D": pl.Float64,
            "TARGET_ABILITY": pl.Int64
        }
        
        # Create DataFrame with strict schema
        df = pl.DataFrame(rows, schema=schema, orient="row")
        
        logger.info(f"Converted to Polars DataFrame: {df.shape[0]:,} rows x {df.shape[1]} columns")
        
        # Post-processing: Fill nulls with 0 for safety
        numeric_cols_to_fill = [
            "INFLOW_VARIANCE_30D", "CASH_RUNWAY_DAYS_ESTIMATED", "SPENDING_VOLATILITY_CV_60D", "DEBT_SERVICE_PROXY_RATIO", "NSF_EVENT_RATE_60D", "ZERO_BALANCE_DAYS_RATIO_30D"
        ]
        
        df = df.with_columns([
            pl.col(col).fill_null(0) for col in numeric_cols_to_fill if col in df.columns
        ])
        
        logger.info("Applied null-filling for numeric features")
        
        return df
    
    def upsert_matrix_results(self, df: pl.DataFrame) -> None:
        """
        Bulk upsert matrix results into PIO_COLL_AI_MATRIX_RESULTS table.
        
        Uses MERGE statement to update existing records or insert new ones.
        Executes in batches using executemany for performance.
        """
        logger.info(f"Upserting {df.height:,} matrix results to database...")
        
        # Convert DataFrame to list of dictionaries
        records = df.select([
            "DAY_DATE",
            "INST_CODE",
            "COUNTRY_CODE",
            "CUST_INFO_ID",
            "WILLINGNESS_SCORE",
            "ABILITY_SCORE",
            "NBA_PRIORITY",
            "CURRENT_QUADRANT"
        ]).to_dicts()
        
        # Corrected MERGE SQL statement matching your actual schema
        merge_sql = """
                MERGE INTO PIO_COLL_AI_MATRIX_RESULTS c
                USING dual ON (
                    c.DAY_DATE = TO_DATE(:DAY_DATE, 'YYYY-MM-DD') AND
                    c.INST_CODE = :INST_CODE AND
                    c.COUNTRY_CODE = :COUNTRY_CODE AND
                    c.CUST_INFO_ID = :CUST_INFO_ID
                )
                WHEN MATCHED THEN
                    UPDATE SET
                        WILLINGNESS_SCORE = :WILLINGNESS_SCORE,
                        ABILITY_SCORE = :ABILITY_SCORE,
                        PRIORITY_SCORE = :NBA_PRIORITY,
                        CURRENT_QUADRANT = :CURRENT_QUADRANT,
                        LAST_SCORED_AT = CURRENT_TIMESTAMP
                WHEN NOT MATCHED THEN
                    INSERT (
                        DAY_DATE,
                        INST_CODE,
                        COUNTRY_CODE,
                        CUST_INFO_ID, 
                        WILLINGNESS_SCORE, 
                        ABILITY_SCORE, 
                        PRIORITY_SCORE, 
                        CURRENT_QUADRANT, 
                        LAST_SCORED_AT
                    )
                    VALUES (
                        TO_DATE(:DAY_DATE, 'YYYY-MM-DD'),
                        :INST_CODE,
                        :COUNTRY_CODE,
                        :CUST_INFO_ID, 
                        :WILLINGNESS_SCORE, 
                        :ABILITY_SCORE, 
                        :NBA_PRIORITY, 
                        :CURRENT_QUADRANT, 
                        CURRENT_TIMESTAMP
                    )
                """
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Use executemany with batcherrors=True for fault tolerance
                cursor.executemany(merge_sql, records, batcherrors=True)
                
                errors = cursor.getbatcherrors()
                if errors:
                    logger.warning(f"Encountered {len(errors)} batch errors during upsert")
                    for error in errors[:10]:
                        logger.warning(f"  Row {error.offset}: {error.message}")
                
                conn.commit()
                successful = df.height - len(errors)
                logger.info(f"Successfully upserted {successful:,} records to PIO_COLL_AI_MATRIX_RESULTS")
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to upsert matrix results: {e}")
                raise
            finally:
                cursor.close()
