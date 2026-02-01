"""
Ability Model Inference Engine.

This module implements the batch scoring pipeline for the Financial Ability Model,
including model loading, null-safe prediction generation, and Parquet caching for downstream processing.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import polars as pl
import xgboost as xgb

from src.core.logger import get_logger

logger = get_logger(__name__)


class AbilityScorer:
    """
    Inference engine for Financial Ability model.
    
    Loads trained models, generates predictions with null-safe preprocessing,
    and caches results to Parquet files for downstream processing.
    """
    
    def __init__(self, model_dir: str = "models", cache_dir: str = "data/cache"):
        """
        Initialize the scorer with model and cache directories.
        
        Args:
            model_dir: Directory containing trained models and pointer file
            cache_dir: Directory to save prediction cache files
            
        Raises:
            FileNotFoundError: If pointer file or model file is not found
        """
        self.model_dir = Path(model_dir)
        self.cache_dir = Path(cache_dir)
        
        # Create cache directory if it doesn't exist
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        logger.info(f"Cache directory ready: {self.cache_dir}")
        
        # Load model using pointer file
        self.model = self._load_latest_model()
        logger.info("AbilityScorer initialized successfully")
    
    def _load_latest_model(self) -> xgb.Booster:
        """
        Load the latest trained model using the pointer file.
        
        Returns:
            Loaded XGBoost Booster model
            
        Raises:
            FileNotFoundError: If pointer file or model file not found
        """
        pointer_file = self.model_dir / "latest_ability.json"
        
        if not pointer_file.exists():
            raise FileNotFoundError(
                f"Pointer file not found: {pointer_file}\n"
                f"Please train a model first by setting MODE=TRAIN"
            )
        
        # Read pointer file to get latest model filename
        with open(pointer_file, "r") as f:
            pointer_data = json.load(f)
        
        model_filename = pointer_data.get("latest")
        if not model_filename:
            raise ValueError(f"Invalid pointer file: missing 'latest' key in {pointer_file}")
        
        model_path = self.model_dir / model_filename
        
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model file not found: {model_path}\n"
                f"Pointer file references: {model_filename}"
            )
        
        # Load XGBoost model
        model = xgb.Booster()
        model.load_model(str(model_path))
        
        logger.info(f"Loaded model: {model_filename}")
        return model
    
    def score(self, df: pl.DataFrame, required_cols: Optional[List[str]] = None) -> str:
        """
        Generate predictions with null-safe preprocessing and cache to Parquet file.
        
        Args:
            df: Polars DataFrame with raw features
            required_cols: List of required column names for validation.
                          If None, skips validation (use for flexibility).
            
        Returns:
            Path to the cached Parquet file as a string
            
        Raises:
            ValueError: If required columns are missing or no valid ID column found
        """
        logger.info(f"Scoring {df.height:,} records...")
        
        # Validate required columns if specified
        if required_cols:
            missing_cols = set(required_cols) - set(df.columns)
            if missing_cols:
                raise ValueError(
                    f"Missing required columns: {missing_cols}\n"
                    f"Available columns: {df.columns}"
                )
        
        # Identify ID column (prefer CUST_INFO_ID, fallback to ACCOUNT_ID)
        id_col = None
        if "CUST_INFO_ID" in df.columns:
            id_col = "CUST_INFO_ID"
        elif "ACCOUNT_ID" in df.columns:
            id_col = "ACCOUNT_ID"
        else:
            raise ValueError(
                "DataFrame must contain either 'CUST_INFO_ID' or 'ACCOUNT_ID' column"
            )
        
        logger.info(f"Using ID column: {id_col}")
        
        # Extract features (exclude ID column and target if present)
        exclude_cols = {id_col, "IS_STABLE"}
        feature_cols = [col for col in df.columns if col not in exclude_cols]
        
        # CRUCIAL: Fill nulls with 0 for XGBoost safety
        logger.info("Preprocessing: Filling null values with 0 for XGBoost compatibility")
        df_filled = df.with_columns([
            pl.col(col).fill_null(0) for col in feature_cols
        ])
        
        # Convert to XGBoost DMatrix
        X = df_filled.select(feature_cols).to_numpy()
        dmatrix = xgb.DMatrix(X, feature_names=feature_cols)
        
        # Generate predictions (probability of IS_STABLE=1)
        logger.info("Generating predictions...")
        predictions = self.model.predict(dmatrix)
        
        # Create result DataFrame with only ID and score
        result_df = pl.DataFrame({
            id_col: df.select(id_col).to_series(),
            "ABILITY_SCORE": predictions
        })
        
        logger.info(f"Predictions generated. Score range: [{predictions.min():.4f}, {predictions.max():.4f}]")
        
        # Cache to Parquet
        cache_filename = f"ability_scores_{datetime.now():%Y%m%d}.parquet"
        cache_path = self.cache_dir / cache_filename
        
        logger.info(f"Caching results to: {cache_path}")
        result_df.write_parquet(cache_path)
        
        logger.info(f"Scoring complete. Cached {result_df.height:,} predictions to Parquet")
        
        return str(cache_path)
    
    def generate_sql_skeleton(self, id_col: str = "CUST_INFO_ID") -> None:
        """
        Print a SQL MERGE skeleton for reference.
        
        This is a helper to show how the cached Parquet data could be
        merged back into the database in a future pipeline stage.
        
        Args:
            id_col: The ID column name used in the merge
        """
        sql_skeleton = f"""
-- SQL MERGE Skeleton (For Reference Only - Not Executed)
-- This shows how to merge the Parquet cache back to a database table

MERGE INTO COLLECTION_SCORES target
USING (
    -- Load from external table or staging table populated from Parquet
    SELECT 
        {id_col},
        ABILITY_SCORE,
        SYSDATE as SCORE_DATE
    FROM ABILITY_SCORES_STAGING
) source
ON (target.{id_col} = source.{id_col})
WHEN MATCHED THEN
    UPDATE SET
        target.ABILITY_SCORE = source.ABILITY_SCORE,
        target.SCORE_DATE = source.SCORE_DATE,
        target.UPDATED_AT = SYSDATE
WHEN NOT MATCHED THEN
    INSERT ({id_col}, ABILITY_SCORE, SCORE_DATE, CREATED_AT)
    VALUES (source.{id_col}, source.ABILITY_SCORE, source.SCORE_DATE, SYSDATE);

COMMIT;

-- Notes:
-- 1. Load Parquet file to ABILITY_SCORES_STAGING table first
-- 2. Adjust column names to match your schema
-- 3. Add any additional metadata columns as needed
        """.strip()
        
        print("\n" + "=" * 80)
        print("SQL MERGE SKELETON")
        print("=" * 80)
        print(sql_skeleton)
        print("=" * 80 + "\n")
        
        logger.info("SQL skeleton printed to console")
