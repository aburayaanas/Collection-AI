"""
Matrix Integration Engine.

This module combines the outputs of Willingness and Ability models,
calculates composite priority scores, assigns customer quadrants, and
persists the final results to the database.
"""

from pathlib import Path

import polars as pl

from src.core.logger import get_logger
from src.database.repository import CollectionRepository
from src.database.queries import get_snap_date
from src.core.config import settings

logger = get_logger(__name__)


class MatrixEngine:
    """
    Integration engine for combining Willingness and Ability model outputs.
    
    Responsibilities:
    1. Load and join Parquet cache files
    2. Calculate NBA_PRIORITY composite score
    3. Assign customers to quadrants
    4. Persist results to database
    """
    
    def __init__(self):
        """Initialize the matrix engine with repository connection."""
        self.repository = CollectionRepository()
        
    def integrate_and_save(self, willingness_path: str, ability_path: str) -> None:
        """
        Integrate willingness and ability scores, then persist to database.
        
        Workflow:
        1. Load both Parquet files
        2. Join on CUST_INFO_ID (outer join with null fill)
        3. Calculate NBA_PRIORITY = (WILLINGNESS * 0.6) + (ABILITY * 0.4)
        4. Assign quadrants based on score thresholds
        5. Persist to database via repository
        
        Args:
            willingness_path: Path to willingness scores Parquet file
            ability_path: Path to ability scores Parquet file
            
        Raises:
            FileNotFoundError: If either Parquet file doesn't exist
        """
        logger.info("Starting matrix integration...")
        
        # Step 1: Load Parquet files
        logger.info(f"Loading willingness scores from: {willingness_path}")
        df_willingness = self._load_parquet(willingness_path)
        
        logger.info(f"Loading ability scores from: {ability_path}")
        df_ability = self._load_parquet(ability_path)
        
        # Step 2: Join on CUST_INFO_ID (outer join)
        logger.info("Joining willingness and ability scores...")
        df_joined = df_willingness.join(
            df_ability, 
            on="CUST_INFO_ID", 
            how="outer"
        )
        
        # Step 3: Fill nulls with 0.0 (safety for customers in only one model)
        df_filled = df_joined.with_columns([
            pl.col("WILLINGNESS_SCORE").fill_null(0.0),
            pl.col("ABILITY_SCORE").fill_null(0.0)
        ])
        
        logger.info(f"Joined dataset size: {df_filled.height:,} customers")
        
        # Step 4: Calculate NBA_PRIORITY (60% willingness, 40% ability)
        logger.info("Calculating NBA_PRIORITY composite score...")
        df_priority = df_filled.with_columns(
            (
                (pl.col("WILLINGNESS_SCORE") * 0.6) + 
                (pl.col("ABILITY_SCORE") * 0.4)
            ).alias("NBA_PRIORITY")
        )
        
        # Step 5: Assign quadrants
        logger.info("Assigning customer quadrants...")
        df_final = self._assign_quadrants(df_priority)
        
        # Log quadrant distribution
        self._log_quadrant_distribution(df_final)
        
        current_day_date = get_snap_date(settings.INST_CODE, settings.COUNTRY_CODE)

        # Append the configuration values to every row in the final DataFrame
        logger.info(f"Appending tenant context: {settings.INST_CODE}, {settings.COUNTRY_CODE}, {current_day_date}")
        
        df_final = df_final.with_columns([
            pl.lit(current_day_date).alias("DAY_DATE"),
            pl.lit(settings.INST_CODE).alias("INST_CODE"),
            pl.lit(settings.COUNTRY_CODE).alias("COUNTRY_CODE")
        ])
        
        # Step 6: Persist to database
        logger.info("Persisting results to database...")
        self.repository.upsert_matrix_results(df_final)
        
        logger.info("Matrix integration completed successfully!")
    
    def _load_parquet(self, path: str) -> pl.DataFrame:
        """
        Load a Parquet file and validate it exists.
        
        Args:
            path: Path to Parquet file
            
        Returns:
            Loaded Polars DataFrame
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        parquet_path = Path(path)
        
        if not parquet_path.exists():
            raise FileNotFoundError(f"Parquet file not found: {path}")
        
        df = pl.read_parquet(path)
        logger.info(f"Loaded {df.height:,} records from {parquet_path.name}")
        
        return df
    
    def _assign_quadrants(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Assign customers to quadrants based on score thresholds.
        
        Quadrant Logic:
        - Q1 (Ideal): Willingness > 0.5 AND Ability > 0.5
        - Q2 (Vulnerable): Willingness > 0.5 AND Ability <= 0.5
        - Q3 (Resistant): Willingness <= 0.5 AND Ability > 0.5
        - Q4 (High Risk): Willingness <= 0.5 AND Ability <= 0.5
        
        Args:
            df: DataFrame with WILLINGNESS_SCORE and ABILITY_SCORE
            
        Returns:
            DataFrame with CURRENT_QUADRANT column added
        """
        df_quadrants = df.with_columns(
            pl.when(
                (pl.col("WILLINGNESS_SCORE") > 0.5) & (pl.col("ABILITY_SCORE") > 0.5)
            ).then(1)  # Q1
            .when(
                (pl.col("WILLINGNESS_SCORE") > 0.5) & (pl.col("ABILITY_SCORE") <= 0.5)
            ).then(2)  # Q2
            .when(
                (pl.col("WILLINGNESS_SCORE") <= 0.5) & (pl.col("ABILITY_SCORE") > 0.5)
            ).then(3)  # Q3
            .otherwise(4)  # Q4
            .alias("CURRENT_QUADRANT")
        )
        
        return df_quadrants
    
    def _log_quadrant_distribution(self, df: pl.DataFrame) -> None:
        """
        Log the distribution of customers across quadrants for observability.
        
        Args:
            df: DataFrame with CURRENT_QUADRANT column
        """
        total = df.height
        
        if total == 0:
            logger.warning("No customers in final dataset!")
            return
        
        # Calculate distribution
        distribution = df.group_by("CURRENT_QUADRANT").agg(
            pl.count().alias("count")
        ).with_columns(
            ((pl.col("count") / total) * 100).round(2).alias("percentage")
        ).sort("CURRENT_QUADRANT")
        
        logger.info("Quadrant Distribution:")
        for row in distribution.iter_rows(named=True):
            quadrant = row["CURRENT_QUADRANT"]
            count = row["count"]
            pct = row["percentage"]
            logger.info(f"  {quadrant}: {count:,} customers ({pct:.2f}%)")
