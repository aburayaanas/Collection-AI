"""
Willingness Model Inference Engine.

This module implements the batch scoring pipeline for the Willingness Model,
including model loading, prediction generation, and Parquet caching for downstream processing.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List

import polars as pl
import xgboost as xgb

from src.core.logger import get_logger

logger = get_logger(__name__)


class WillingnessScorer:
    """
    Inference engine for Willingness to Pay model.
    
    Loads trained models, generates predictions, and caches results
    to Parquet files for downstream processing.
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
        logger.info("WillingnessScorer initialized successfully")
    
    def _load_latest_model(self) -> xgb.Booster:
        """
        Load the latest trained model using the pointer file.
        
        Returns:
            Loaded XGBoost Booster model
            
        Raises:
            FileNotFoundError: If pointer file or model file not found
        """
        pointer_file = self.model_dir / "latest_willingness.json"
        
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
    
    def score(self, df: pl.DataFrame, required_cols: List[str] = None) -> str:
        """
        Generate predictions and cache to Parquet file.
        
        Args:
            df: Polars DataFrame with raw features
            required_cols: List of required column names for validation.
                          If None, skips validation (use for flexibility).
            
        Returns:
            Path to the cached Parquet file as a string
            
        Raises:
            ValueError: If required columns are missing
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
        exclude_cols = {id_col, "IS_WILLING", "SNAPSHOT_DATE", "TARGET_WILLINGNESS"}
        feature_cols = [col for col in df.columns if col not in exclude_cols]
        
        # Convert to XGBoost DMatrix
        X = df.select(feature_cols).to_numpy()
        dmatrix = xgb.DMatrix(X, feature_names=feature_cols)
        
        # Generate predictions
        logger.info("Generating predictions...")
        predictions = self.model.predict(dmatrix)
        
        # Create result DataFrame with only ID and score
        result_df = pl.DataFrame({
            id_col: df.select(id_col).to_series(),
            "WILLINGNESS_SCORE": predictions
        })
        
        logger.info(f"Predictions generated. Score range: [{predictions.min():.4f}, {predictions.max():.4f}]")
        
        # Cache to Parquet (include time to prevent same-day overwrites)
        cache_filename = f"willingness_scores_{datetime.now():%Y%m%d_%H%M%S}.parquet"
        cache_path = self.cache_dir / cache_filename
        
        # Also maintain a "latest" symlink-style file for downstream consumers
        latest_path = self.cache_dir / f"willingness_scores_{datetime.now():%Y%m%d}.parquet"
        if latest_path.exists():
            backup_path = latest_path.with_suffix(".parquet.bak")
            logger.warning(f"Existing cache found. Backing up to: {backup_path.name}")
            latest_path.rename(backup_path)
        
        logger.info(f"Caching results to: {cache_path}")
        result_df.write_parquet(cache_path)
        
        # Write the "daily" file that matrix integration expects
        result_df.write_parquet(latest_path)
        
        logger.info(f"Scoring complete. Cached {result_df.height:,} predictions to Parquet")
        
        return str(cache_path)
