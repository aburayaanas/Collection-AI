"""
Ability Model Training Pipeline.

This module implements the complete training workflow for the Financial Ability Model,
including target engineering, hyperparameter optimization with Optuna, model training
with XGBoost, and experiment tracking with MLflow.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import polars as pl
import xgboost as xgb
import optuna
import mlflow
import mlflow.xgboost
from sklearn.metrics import roc_auc_score, precision_score, recall_score

from src.core.logger import get_logger

logger = get_logger(__name__)


class AbilityTrainer:
    """
    Training pipeline for the Financial Ability model.
    
    Orchestrates target engineering, hyperparameter tuning, model training,
    and artifact management with MLflow experiment tracking.
    """
    
    def __init__(self, model_dir: str = "models"):
        """
        Initialize the trainer.
        
        Args:
            model_dir: Directory to save trained models (default: "models")
        """
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True, parents=True)
        self.model = None
        self.best_params = None
        
    def train(self, df: pl.DataFrame) -> None:
        """
        Execute the complete training pipeline.
        
        This orchestrates the entire workflow:
        1. Engineer target variable
        2. Optimize hyperparameters
        3. Train final model
        4. Save artifacts
        
        Args:
            df: Raw feature DataFrame from the database query
            
        Raises:
            ValueError: If required columns are missing
        """
        logger.info("Starting Ability Model training pipeline...")
        
        with mlflow.start_run(run_name=f"ability_training_{datetime.now():%Y%m%d_%H%M%S}"):
            # Step 1: Engineer target variable
            df_labeled = self.engineer_target(df)
            logger.info(f"Target engineering complete. Dataset size: {df_labeled.height:,} rows")
            
            # Prepare features and target
            # Exclude non-feature columns and target
            exclude_cols = {"IS_STABLE", "CUST_INFO_ID", "SNAPSHOT_DATE", "TARGET_ABILITY"}
            feature_cols = [col for col in df_labeled.columns if col not in exclude_cols]
            
            logger.info(f"Training with {len(feature_cols)} features: {feature_cols}")
            X = df_labeled.select(feature_cols).to_numpy()
            y = df_labeled.select("IS_STABLE").to_numpy().ravel()
            
            # Create DMatrix for XGBoost
            dtrain = xgb.DMatrix(X, label=y, feature_names=feature_cols)
            
            # Step 2: Optimize hyperparameters
            logger.info("Starting hyperparameter optimization with Optuna...")
            self.best_params = self.optimize_hyperparameters(dtrain)
            logger.info(f"Best hyperparameters found: {self.best_params}")
            
            # Step 3: Train final model
            logger.info("Training final model with optimized hyperparameters...")
            self.model = self.train_final_model(dtrain, self.best_params)
            
            # Step 4: Save model artifacts
            logger.info("Saving model artifacts...")
            self.save_model(self.model)
            
        logger.info("Training pipeline completed successfully!")
    
    def engineer_target(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Engineer the target variable IS_STABLE from pre-calculated database feature.
        
        Target Logic:
        - IS_STABLE = TARGET_ABILITY (pre-calculated feature from DB)
        
        Args:
            df: Raw DataFrame with financial behavior columns
            
        Returns:
            DataFrame with engineered IS_STABLE column
            
        Raises:
            ValueError: If required columns are missing
        """
        required_cols = {"TARGET_ABILITY"}
        missing_cols = required_cols - set(df.columns)
        
        if missing_cols:
            raise ValueError(
                f"Missing required columns for target engineering: {missing_cols}. "
                f"Available columns: {df.columns}"
            )
        
        logger.info("Engineering target variable IS_STABLE...")
        
        # Create binary target based on pre-calculated feature
        # Ensure strict integer type (0 or 1)
        df_labeled = df.with_columns(
            pl.col("TARGET_ABILITY").cast(pl.Int64).alias("IS_STABLE")
        )
        
        # Log class distribution
        class_dist = df_labeled.group_by("IS_STABLE").count()
        logger.info(f"Target distribution:\n{class_dist}")
        
        # Calculate and log class balance
        stable_count = df_labeled.filter(pl.col("IS_STABLE") == 1).height
        total_count = df_labeled.height
        stable_ratio = stable_count / total_count if total_count > 0 else 0
        
        logger.info(f"Stable customers: {stable_count:,} ({stable_ratio:.2%})")
        mlflow.log_metric("target_stable_ratio", stable_ratio)
        mlflow.log_metric("total_samples", total_count)
        
        return df_labeled
    
    def optimize_hyperparameters(self, dtrain: xgb.DMatrix) -> Dict[str, Any]:
        """
        Optimize XGBoost hyperparameters using Optuna to maximize AUC.
        
        Search Space:
        - eta (learning rate): 0.01 to 0.3
        - max_depth: 3 to 8
        - subsample: 0.6 to 1.0
        - colsample_bytree: 0.6 to 1.0
        
        Args:
            dtrain: XGBoost DMatrix with training data
            
        Returns:
            Dictionary of best hyperparameters
        """
        def objective(trial: optuna.Trial) -> float:
            """Optuna objective function to maximize AUC."""
            params = {
                "objective": "binary:logistic",
                "eval_metric": "auc",
                "eta": trial.suggest_float("eta", 0.01, 0.3, log=True),
                "max_depth": trial.suggest_int("max_depth", 3, 8),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "tree_method": "hist",
                "seed": 42,
            }
            
            # Perform 3-fold cross-validation
            cv_results = xgb.cv(
                params=params,
                dtrain=dtrain,
                num_boost_round=100,
                nfold=3,
                early_stopping_rounds=10,
                verbose_eval=False,
                seed=42,
            )
            
            # Return the best AUC from CV (maximize)
            return cv_results["test-auc-mean"].max()
        
        # Create and run Optuna study
        study = optuna.create_study(
            direction="maximize",  # Maximize AUC
            study_name="ability_hpo",
            sampler=optuna.samplers.TPESampler(seed=42),
        )
        
        study.optimize(objective, n_trials=30, show_progress_bar=True)
        
        # Get best parameters
        best_params = {
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "tree_method": "hist",
            "seed": 42,
            **study.best_params,
        }
        
        # Log to MLflow
        mlflow.log_params(best_params)
        mlflow.log_metric("best_cv_auc", study.best_value)
        mlflow.log_metric("n_trials", len(study.trials))
        
        logger.info(f"Optimization complete. Best CV AUC: {study.best_value:.4f}")
        
        return best_params
    
    def train_final_model(self, dtrain: xgb.DMatrix, best_params: Dict[str, Any]) -> xgb.Booster:
        """
        Train the final XGBoost model on the full dataset.
        
        Args:
            dtrain: XGBoost DMatrix with full training data
            best_params: Optimized hyperparameters from Optuna
            
        Returns:
            Trained XGBoost Booster model
        """
        # Train the model with best parameters
        model = xgb.train(
            params=best_params,
            dtrain=dtrain,
            num_boost_round=100,
            verbose_eval=10,
        )
        
        # Generate predictions for evaluation
        y_pred_proba = model.predict(dtrain)
        y_pred = (y_pred_proba > 0.5).astype(int)
        y_true = dtrain.get_label()
        
        # Calculate metrics
        auc = roc_auc_score(y_true, y_pred_proba)
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        
        # Log metrics to MLflow
        mlflow.log_metric("auc", auc)
        mlflow.log_metric("precision", precision)
        mlflow.log_metric("recall", recall)
        
        logger.info(f"Training metrics - AUC: {auc:.4f}, Precision: {precision:.4f}, Recall: {recall:.4f}")
        
        # Log model to MLflow
        mlflow.xgboost.log_model(
            model,
            artifact_path="model",
            registered_model_name="AbilityModel",
        )
        
        return model
    
    def save_model(self, model: xgb.Booster) -> None:
        """
        Save the trained model locally with versioning.
        
        Creates:
        1. Versioned model file: ability_v{YYYYMMDD_HHMMSS}.json
        2. Pointer file: latest_ability.json with reference to newest version
        
        Args:
            model: Trained XGBoost Booster model
        """
        # Generate versioned filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_filename = f"ability_v{timestamp}.json"
        model_path = self.model_dir / model_filename
        
        # Save model
        model.save_model(str(model_path))
        logger.info(f"Model saved to: {model_path}")
        
        # Update pointer file
        pointer_file = self.model_dir / "latest_ability.json"
        pointer_data = {"latest": model_filename}
        
        with open(pointer_file, "w") as f:
            json.dump(pointer_data, f, indent=2)
        
        logger.info(f"Pointer file updated: {pointer_file}")
        
        # Log artifact path to MLflow
        mlflow.log_param("local_model_path", str(model_path))
        mlflow.log_artifact(str(model_path))
