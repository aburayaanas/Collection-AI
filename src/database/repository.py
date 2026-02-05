"""
Database Repository Layer.

This module provides data access methods for persisting ML predictions
to the Oracle database, including bulk MERGE operations.
"""

import polars as pl

from src.core.logger import get_logger
from src.database.connection import db
from src.database.queries import get_query

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
        
        # Execute query
        sql = get_query("willingness")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            
            # Fetch all rows
            rows = cursor.fetchall()
            cursor.close()
        
        logger.info(f"Retrieved {len(rows):,} records from database")
        
        # Define strict schema mapping (SQL column -> Polars type)
        schema = {
            "CUST_INFO_ID": pl.String,
            # PTP Features (Integers)
            "TOTAL_PTP_COUNT": pl.Int64,
            "PTP_BROKEN_COUNT": pl.Int64,
            "PTP_KEPT_COUNT": pl.Int64,
            # PTP Features (Floats)
            "PTP_BROKEN_RATIO": pl.Float64,
            "DAYS_SINCE_LAST_BROKEN_PTP": pl.Float64,  # Nullable recency
            # Contact Features (Integers)
            "TOTAL_ATTEMPTS_LIFETIME": pl.Int64,
            "SUCCESSFUL_CONTACTS": pl.Int64,
            "SMS_DELIVERED_COUNT": pl.Int64,
            "CALL_ANSWERED_COUNT": pl.Int64,
            # Contact Features (Floats)
            "RPC_RATE": pl.Float64,
            "DAYS_SINCE_LAST_RPC": pl.Float64,  # Nullable recency
            # Deal & Payment Features (Floats)
            "TOTAL_PAYMENT_AMT": pl.Float64,
            "TOTAL_OVERDUE_AMT": pl.Float64,
        }
        
        # Create DataFrame with strict schema
        df = pl.DataFrame(rows, schema=schema, orient="row")
        
        logger.info(f"Converted to Polars DataFrame: {df.shape[0]:,} rows x {df.shape[1]} columns")
        
        # Post-processing: Fill nulls with 0 for safety (except recency columns which should stay null)
        numeric_cols_to_fill = [
            "TOTAL_PTP_COUNT", "PTP_BROKEN_COUNT", "PTP_KEPT_COUNT",
            "PTP_BROKEN_RATIO", "TOTAL_ATTEMPTS_LIFETIME", "SUCCESSFUL_CONTACTS",
            "RPC_RATE", "SMS_DELIVERED_COUNT", "CALL_ANSWERED_COUNT",
            "TOTAL_PAYMENT_AMT", "TOTAL_OVERDUE_AMT"
        ]
        
        df = df.with_columns([
            pl.col(col).fill_null(0) for col in numeric_cols_to_fill
        ])
        
        # Recency columns can stay null (they represent "never happened" when null)
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
        
        # Execute query
        sql = get_query("ability")
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            
            # Fetch all rows
            rows = cursor.fetchall()
            cursor.close()
        
        logger.info(f"Retrieved {len(rows):,} records from database")
        
        # Define strict schema mapping (SQL column -> Polars type)
        schema = {
            "CUST_INFO_ID": pl.String,
            # Income & Liquidity Features
            "AVG_MONTHLY_INCOME": pl.Float64,
            "INCOME_VOLATILITY": pl.Float64,
            "CURRENT_BALANCE": pl.Float64,
            # Spending & Stability Features
            "TOTAL_OUTFLOW_6M": pl.Float64,
            "SPENDING_VOLATILITY": pl.Float64,
            "ENTROPY_CATEGORY_COUNT": pl.Int64,
            # Financial Stress Features
            "NSF_COUNT": pl.Int64,
            "FIXED_OBLIGATIONS": pl.Float64,
            "UTILIZATION_RATE": pl.Float64,
            # Calculated Features
            "DBR_RATIO": pl.Float64,
            "CASH_RUNWAY_MONTHS": pl.Float64,
        }
        
        # Create DataFrame with strict schema
        df = pl.DataFrame(rows, schema=schema, orient="row")
        
        logger.info(f"Converted to Polars DataFrame: {df.shape[0]:,} rows x {df.shape[1]} columns")
        
        # Post-processing: Fill nulls with 0 for safety
        numeric_cols_to_fill = [
            "AVG_MONTHLY_INCOME", "INCOME_VOLATILITY", "CURRENT_BALANCE",
            "TOTAL_OUTFLOW_6M", "SPENDING_VOLATILITY", "ENTROPY_CATEGORY_COUNT",
            "NSF_COUNT", "FIXED_OBLIGATIONS", "UTILIZATION_RATE",
            "DBR_RATIO", "CASH_RUNWAY_MONTHS"
        ]
        
        df = df.with_columns([
            pl.col(col).fill_null(0) for col in numeric_cols_to_fill if col in df.columns
        ])
        
        logger.info("Applied null-filling for numeric features")
        
        return df
    
    def upsert_matrix_results(self, df: pl.DataFrame) -> None:
        """
        Bulk upsert matrix results into COLLECTION_CUSTOMERS table.
        
        Uses MERGE statement to update existing records or insert new ones.
        Executes in batches using executemany for performance.
        
        Args:
            df: DataFrame with columns:
                - CUST_INFO_ID
                - WILLINGNESS_SCORE
                - ABILITY_SCORE
                - NBA_PRIORITY
                - CURRENT_QUADRANT
                
        Raises:
            Exception: If database operation fails
        """
        logger.info(f"Upserting {df.height:,} matrix results to database...")
        
        # Convert DataFrame to list of dictionaries
        records = df.select([
            "CUST_INFO_ID",
            "WILLINGNESS_SCORE",
            "ABILITY_SCORE",
            "NBA_PRIORITY",
            "CURRENT_QUADRANT"
        ]).to_dicts()
        
        # MERGE SQL statement
        merge_sql = """
        MERGE INTO COLLECTION_CUSTOMERS c
        USING dual ON (c.account_id = :CUST_INFO_ID)
        WHEN MATCHED THEN
            UPDATE SET
                willingness_score = :WILLINGNESS_SCORE,
                ability_score = :ABILITY_SCORE,
                priority_score = :NBA_PRIORITY,
                current_quadrant = :CURRENT_QUADRANT,
                last_scored_at = SYSDATE
        WHEN NOT MATCHED THEN
            INSERT (
                account_id, 
                willingness_score, 
                ability_score, 
                priority_score, 
                current_quadrant, 
                last_scored_at
            )
            VALUES (
                :CUST_INFO_ID, 
                :WILLINGNESS_SCORE, 
                :ABILITY_SCORE, 
                :NBA_PRIORITY, 
                :CURRENT_QUADRANT, 
                SYSDATE
            )
        """
        
        # Execute bulk upsert
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                # Use executemany with batcherrors=True for fault tolerance
                cursor.executemany(merge_sql, records, batcherrors=True)
                
                # Check for batch errors
                errors = cursor.getbatcherrors()
                if errors:
                    logger.warning(f"Encountered {len(errors)} batch errors during upsert")
                    for error in errors[:10]:  # Log first 10 errors
                        logger.warning(f"  Row {error.offset}: {error.message}")
                
                # Commit transaction
                conn.commit()
                
                successful = df.height - len(errors)
                logger.info(f"Successfully upserted {successful:,} records")
                
                if errors:
                    logger.warning(f"Failed to upsert {len(errors):,} records")
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to upsert matrix results: {e}")
                raise
            finally:
                cursor.close()
