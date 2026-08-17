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

    def get_nba_context_data(self) -> pl.DataFrame:
        """Fetch NBA operational context from PIO_COLL_AI_NBA_CONTEXT_MART.

        This mart is fully isolated from the ML feature marts. It holds
        operational state (account status, contact frequency, outstanding
        balance) that drives guardrail decisions — not model predictions.

        Returns:
            Polars DataFrame with columns:
                CUST_INFO_ID, ACCOUNT_STATUS, TOTAL_DUE,
                SMS_SENT_THIS_WEEK, CALLS_MADE_TODAY.

        Raises:
            Exception: If query execution or data conversion fails.
        """
        logger.info("Fetching NBA context data from PIO_COLL_AI_NBA_CONTEXT_MART...")

        snap_date = get_snap_date(settings.INST_CODE, settings.COUNTRY_CODE)
        if not snap_date:
            raise ValueError("Snapshot date retrieval failed")

        sql = get_query("nba_context")

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, {
                'day_date': snap_date,
                'inst_code': settings.INST_CODE,
                'country_code': settings.COUNTRY_CODE,
            })
            rows = cursor.fetchall()
            cursor.close()

        logger.info(f"Retrieved {len(rows):,} NBA context records")

        schema = {
            "CUST_INFO_ID":               pl.String,
            "ACCOUNT_STATUS":             pl.String,
            "TOTAL_DUE":                  pl.Float64,
            "SMS_SENT_THIS_WEEK":         pl.Int64,
            "CALLS_MADE_TODAY":           pl.Int64,
            "FULL_LEGAL_NAME":            pl.String,
            "CUSTOMER_SEGMENT":           pl.String,
            "NATIONALITY_RESIDENCY":      pl.String,
            "EMPLOYER_NAME":              pl.String,
            "VERIFIED_INCOME_JOD":         pl.Float64,
            "INCOME_LAST_VERIFIED_DATE":  pl.Datetime,
            "AML_LAST_SCREENED_DATE":     pl.Datetime,
            "ACCOUNT_OPEN_DATE":          pl.Datetime,
            "PRODUCTS_HELD":              pl.String,
            "PRIMARY_PHONE":              pl.String,
            "SCORE_DELTA_90D":            pl.Int64,
            "COMPOSITE_RISK_SCORE":       pl.Int64,
            "DAYS_PAST_DUE":              pl.Int64,
            "CLASSIFICATION_PROBABILITIES": pl.Utf8,
            "PAYMENT_REJECTION_FREQ": pl.Int64,
            "CONTACT_AVOIDANCE_INDEX": pl.Float64,
            "TOTAL_EXPOSURE_JOD":         pl.Float64,
            "CURRENT_ARREARS_JOD":        pl.Float64,
            "ACCRUED_INTEREST_JOD":       pl.Float64,
            "LATE_FEES_JOD":              pl.Float64
        }

        df = pl.DataFrame(rows, schema=schema, orient="row")

        # Safe defaults: nulls must never reach the guardrail engine
        df = df.with_columns([
            pl.col("ACCOUNT_STATUS").fill_null("Active"),
            pl.col("TOTAL_DUE").fill_null(0.0),
            pl.col("SMS_SENT_THIS_WEEK").fill_null(0),
            pl.col("CALLS_MADE_TODAY").fill_null(0),
            pl.col("TOTAL_EXPOSURE_JOD").fill_null(0.0),
            pl.col("CURRENT_ARREARS_JOD").fill_null(0.0),
            pl.col("ACCRUED_INTEREST_JOD").fill_null(0.0),
            pl.col("LATE_FEES_JOD").fill_null(0.0),
        ])

        logger.info(f"NBA context DataFrame: {df.shape[0]:,} rows x {df.shape[1]} columns")
        return df

    def get_shap_results(self) -> pl.DataFrame:
        """Fetch SHAP Vector Narratives from the Matrix Results table."""
        logger.info("Fetching SHAP results for Cockpit Payload...")
        snap_date = get_snap_date(settings.INST_CODE, settings.COUNTRY_CODE)
        if not snap_date:
            raise ValueError("Snapshot date retrieval failed")

        sql = """
            SELECT CUST_INFO_ID, 
                   WILL_RISK_DRIVERS, WILL_POSITIVE_DRIVERS,
                   ABIL_RISK_DRIVERS, ABIL_POSITIVE_DRIVERS
            FROM BI_DWH.PIO_COLL_AI_MATRIX_RESULTS
            WHERE DAY_DATE = TO_DATE(:day_date, 'YYYY-MM-DD')
              AND INST_CODE = :inst_code
              AND COUNTRY_CODE = :country_code
        """
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, {
                'day_date': snap_date,
                'inst_code': settings.INST_CODE,
                'country_code': settings.COUNTRY_CODE,
            })
            rows = cursor.fetchall()
            cursor.close()

        schema = {
            "CUST_INFO_ID": pl.String,
            "WILL_RISK_DRIVERS": pl.String,
            "WILL_POSITIVE_DRIVERS": pl.String,
            "ABIL_RISK_DRIVERS": pl.String,
            "ABIL_POSITIVE_DRIVERS": pl.String,
        }
        return pl.DataFrame(rows, schema=schema, orient="row")

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
            "CURRENT_QUADRANT",
            "MODEL_VERSION"
        ]).to_dicts()
        
        # Corrected MERGE SQL statement matching your actual schema
        merge_sql = """
                MERGE INTO BI_DWH.PIO_COLL_AI_MATRIX_RESULTS c
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
                        MODEL_VERSION = :MODEL_VERSION,
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
                        MODEL_VERSION,
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
                        :MODEL_VERSION,
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

    def upsert_nba_results(self, df: pl.DataFrame) -> None:
        """Bulk upsert NBA action recommendations into PIO_COLL_AI_NBA_ACTIONS.

        Persists the output DataFrame produced by ``NBAOrchestrator.process_batch()``
        into the Oracle table that feeds the agent desktop worklist. Uses a
        MERGE so re-running the nightly job is idempotent.

        Args:
            df (pl.DataFrame): Output DataFrame from ``NBAOrchestrator.process_batch()``.
                Must contain columns: ``CUST_INFO_ID``, ``DAY_DATE``,
                ``INST_CODE``, ``COUNTRY_CODE``, ``RECOMMENDED_CHANNEL``,
                ``RECOMMENDED_OFFER``, ``DECISION_REASON``.

        Raises:
            Exception: Re-raised after rollback if the entire batch fails
                at the connection/cursor level. Row-level failures are
                logged as warnings and do not raise.
        """
        logger.info(f"Upserting {df.height:,} NBA action results to database...")

        records = df.select([
            "DAY_DATE",
            "INST_CODE",
            "COUNTRY_CODE",
            "CUST_INFO_ID",
            "RECOMMENDED_CHANNEL",
            "RECOMMENDED_OFFER",
            "DECISION_REASON",
            "AI_PAYLOAD",
            "SCORED_ALTERNATIVES",
        ]).to_dicts()

        merge_sql = """
            MERGE INTO BI_DWH.PIO_COLL_AI_NBA_ACTIONS t
            USING dual ON (
                t.CUST_INFO_ID   = :CUST_INFO_ID AND
                t.DAY_DATE       = TO_DATE(:DAY_DATE, 'YYYY-MM-DD') AND
                t.INST_CODE      = :INST_CODE AND
                t.COUNTRY_CODE   = :COUNTRY_CODE
            )
            WHEN MATCHED THEN
                UPDATE SET
                    RECOMMENDED_CHANNEL = :RECOMMENDED_CHANNEL,
                    RECOMMENDED_OFFER   = :RECOMMENDED_OFFER,
                    DECISION_REASON     = :DECISION_REASON,
                    AI_PAYLOAD          = :AI_PAYLOAD,
                    SCORED_ALTERNATIVES = :SCORED_ALTERNATIVES,
                    AI_NARRATIVE        = 'PENDING',
                    UPDATED_AT          = CURRENT_TIMESTAMP
            WHEN NOT MATCHED THEN
                INSERT (
                    DAY_DATE,
                    INST_CODE,
                    COUNTRY_CODE,
                    CUST_INFO_ID,
                    RECOMMENDED_CHANNEL,
                    RECOMMENDED_OFFER,
                    DECISION_REASON,
                    AI_PAYLOAD,
                    SCORED_ALTERNATIVES,
                    AI_NARRATIVE,
                    CREATED_AT,
                    UPDATED_AT
                )
                VALUES (
                    TO_DATE(:DAY_DATE, 'YYYY-MM-DD'),
                    :INST_CODE,
                    :COUNTRY_CODE,
                    :CUST_INFO_ID,
                    :RECOMMENDED_CHANNEL,
                    :RECOMMENDED_OFFER,
                    :DECISION_REASON,
                    :AI_PAYLOAD,
                    :SCORED_ALTERNATIVES,
                    'PENDING',
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
        """

        with db.get_connection() as conn:
            import oracledb
            cursor = conn.cursor()
            try:
                # CRITICAL: Prevent ORA-01461 / ORA-01704 for large JSON strings
                cursor.setinputsizes(
                    AI_PAYLOAD=oracledb.DB_TYPE_CLOB,
                    SCORED_ALTERNATIVES=oracledb.DB_TYPE_CLOB
                )
                cursor.executemany(merge_sql, records, batcherrors=True)

                errors = cursor.getbatcherrors()
                if errors:
                    logger.warning(
                        f"Encountered {len(errors)} batch errors during NBA upsert"
                    )
                    for error in errors[:10]:
                        logger.warning(f"  Row {error.offset}: {error.message}")

                conn.commit()
                successful = df.height - len(errors)
                logger.info(
                    f"Successfully upserted {successful:,} records "
                    f"to PIO_COLL_AI_NBA_ACTIONS"
                )

            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to upsert NBA results: {e}")
                raise
            finally:
                cursor.close()
