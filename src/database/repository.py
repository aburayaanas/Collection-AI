"""
Database Repository Layer.

This module provides data access methods for persisting ML predictions
to the Oracle database, including bulk MERGE operations.
"""

import polars as pl

from src.core.logger import get_logger
from src.database.connection import db

logger = get_logger(__name__)


class CollectionRepository:
    """
    Repository for Collection AI database operations.
    
    Handles persistence of model predictions and integrated scores
    to the COLLECTION_CUSTOMERS table.
    """
    
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
