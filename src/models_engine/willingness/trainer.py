"""
Willingness Model Training Pipeline.

This module implements the complete training workflow for the Willingness Model,
including target engineering, hyperparameter optimization with Optuna, model training
with XGBoost, and experiment tracking with MLflow.

Evaluation follows production best practices:
- 80/20 stratified train/test split
- Optuna CV runs on training fold ONLY
- Final model trained on training fold ONLY
- All reported metrics computed on held-out test fold
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple

import numpy as np
import polars as pl
import xgboost as xgb
import optuna
import mlflow
import mlflow.xgboost
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score

from src.core.logger import get_logger

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────
TEST_SIZE = 0.20
RANDOM_STATE = 42
MIN_SAMPLES_PER_CLASS = 100
IMBALANCE_WARNING_THRESHOLD = 0.05   # warn if minority class < 5%
OVERFIT_GAP_THRESHOLD = 0.10         # warn if train_auc - test_auc > 10pp


class WillingnessTrainer:
    """
    Training pipeline for the Willingness to Pay model.

    Orchestrates target engineering, data splitting, hyperparameter tuning,
    model training, and artifact management with MLflow experiment tracking.

    Evaluation protocol:
        1. Stratified 80/20 split on TARGET_WILLINGNESS
        2. Optuna 3-fold CV on the training fold (80%)
        3. Final model trained on the training fold (80%)
        4. AUC / Precision / Recall / F1 reported on the test fold (20%)
    """

    def __init__(self, model_dir: str = "models"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True, parents=True)
        self.model = None
        self.best_params = None

    # ── Public entry point ───────────────────────────────────────────

    def train(self, df: pl.DataFrame) -> None:
        """Execute the complete training pipeline."""
        logger.info("Starting Willingness Model training pipeline...")

        with mlflow.start_run(run_name=f"willingness_training_{datetime.now():%Y%m%d_%H%M%S}"):
            # Step 1: Engineer target variable
            df_labeled = self.engineer_target(df)
            logger.info(f"Target engineering complete. Dataset size: {df_labeled.height:,} rows")

            # Step 2: Prepare features
            # NBA context columns live in this mart for the DB team's convenience
            # but are NOT behavioral predictors — exclude them from XGBoost features.
            exclude_cols = {
                "IS_WILLING", "CUST_INFO_ID", "SNAPSHOT_DATE", "TARGET_WILLINGNESS",
                # NBA operational state columns (non-predictive for willingness)
                "ACCOUNT_STATUS", "TOTAL_DUE", "SMS_SENT_THIS_WEEK", "CALLS_MADE_TODAY",
            }
            feature_cols = [col for col in df_labeled.columns if col not in exclude_cols]

            logger.info(f"Training with {len(feature_cols)} features: {feature_cols}")
            X = df_labeled.select(feature_cols).to_numpy()
            y = df_labeled.select("TARGET_WILLINGNESS").to_numpy().ravel()

            # Step 3: Stratified Train/Test Split
            X_train, X_test, y_train, y_test = self._stratified_split(X, y)

            # Step 4: Validate data quality
            self._validate_data_quality(y_train, y_test)

            # Step 5: Create DMatrices
            dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=feature_cols)
            dtest = xgb.DMatrix(X_test, label=y_test, feature_names=feature_cols)

            # Step 6: Optimize hyperparameters (on TRAINING fold only)
            logger.info("Starting hyperparameter optimization with Optuna (on training fold)...")
            self.best_params = self.optimize_hyperparameters(dtrain)
            logger.info(f"Best hyperparameters found: {self.best_params}")

            # Step 7: Train final model (on TRAINING fold only)
            logger.info("Training final model with optimized hyperparameters...")
            self.model = self.train_final_model(dtrain, dtest, self.best_params)

            # Step 8: Save model artifacts
            logger.info("Saving model artifacts...")
            self.save_model(self.model)

        logger.info("Training pipeline completed successfully!")

    # ── Target Engineering ───────────────────────────────────────────

    def engineer_target(self, df: pl.DataFrame) -> pl.DataFrame:
        """Engineer the target variable IS_WILLING from raw behavioral data."""
        required_cols = {"TARGET_WILLINGNESS"}
        missing_cols = required_cols - set(df.columns)

        if missing_cols:
            raise ValueError(
                f"Missing required columns for target engineering: {missing_cols}. "
                f"Available columns: {df.columns}"
            )

        logger.info("Engineering target variable IS_WILLING...")

        df_labeled = df.with_columns(
            pl.col("TARGET_WILLINGNESS").cast(pl.Int64).alias("IS_WILLING")
        )

        # Log class distribution
        class_dist = df_labeled.group_by("IS_WILLING").count()
        logger.info(f"Target distribution:\n{class_dist}")

        willing_count = df_labeled.filter(pl.col("IS_WILLING") == 1).height
        total_count = df_labeled.height
        willing_ratio = willing_count / total_count if total_count > 0 else 0

        logger.info(f"Willing customers: {willing_count:,} ({willing_ratio:.2%})")
        mlflow.log_metric("target_willing_ratio", willing_ratio)
        mlflow.log_metric("total_samples", total_count)

        return df_labeled

    # ── Stratified Split ─────────────────────────────────────────────

    def _stratified_split(
        self, X: np.ndarray, y: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Perform stratified train/test split preserving class proportions.

        Returns:
            (X_train, X_test, y_train, y_test)
        """
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE,
            stratify=y,
        )

        logger.info(
            f"Stratified split: "
            f"Train={len(y_train):,} ({1-TEST_SIZE:.0%}), "
            f"Test={len(y_test):,} ({TEST_SIZE:.0%})"
        )

        # Log split sizes
        mlflow.log_param("train_size", len(y_train))
        mlflow.log_param("test_size", len(y_test))
        mlflow.log_param("split_ratio", f"{1-TEST_SIZE:.0%}/{TEST_SIZE:.0%}")
        mlflow.log_param("random_state", RANDOM_STATE)

        return X_train, X_test, y_train, y_test

    # ── Data Quality Validation ──────────────────────────────────────

    def _validate_data_quality(self, y_train: np.ndarray, y_test: np.ndarray) -> None:
        """Run pre-training data quality checks."""
        for label, y in [("train", y_train), ("test", y_test)]:
            unique, counts = np.unique(y, return_counts=True)
            class_counts = dict(zip(unique.astype(int), counts))
            minority_count = min(counts)
            minority_ratio = minority_count / len(y)

            logger.info(f"  {label} class distribution: {class_counts}")

            if minority_count < MIN_SAMPLES_PER_CLASS:
                logger.warning(
                    f"⚠ {label} set has only {minority_count} samples in minority class "
                    f"(minimum recommended: {MIN_SAMPLES_PER_CLASS})"
                )

            if minority_ratio < IMBALANCE_WARNING_THRESHOLD:
                logger.warning(
                    f"⚠ {label} set is highly imbalanced: "
                    f"minority class is {minority_ratio:.1%} of total"
                )
                mlflow.log_metric(f"{label}_minority_ratio", minority_ratio)

    # ── Hyperparameter Optimization ──────────────────────────────────

    def optimize_hyperparameters(self, dtrain: xgb.DMatrix) -> Dict[str, Any]:
        """Optimize XGBoost hyperparameters using Optuna with CV on TRAINING fold."""
        def objective(trial: optuna.Trial) -> float:
            params = {
                "objective": "binary:logistic",
                "eval_metric": "logloss",
                "eta": trial.suggest_float("eta", 0.01, 0.3, log=True),
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "tree_method": "hist",
                "seed": RANDOM_STATE,
            }

            cv_results = xgb.cv(
                params=params,
                dtrain=dtrain,
                num_boost_round=100,
                nfold=3,
                early_stopping_rounds=10,
                verbose_eval=False,
                seed=RANDOM_STATE,
            )

            return cv_results["test-logloss-mean"].min()

        study = optuna.create_study(
            direction="minimize",
            study_name="willingness_hpo",
            sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE),
        )

        study.optimize(objective, n_trials=30, show_progress_bar=True)

        best_params = {
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "tree_method": "hist",
            "seed": RANDOM_STATE,
            **study.best_params,
        }

        mlflow.log_params(best_params)
        mlflow.log_metric("best_cv_logloss", study.best_value)
        mlflow.log_metric("n_trials", len(study.trials))

        logger.info(f"Optimization complete. Best CV logloss: {study.best_value:.4f}")

        return best_params

    # ── Final Model Training ─────────────────────────────────────────

    def train_final_model(
        self,
        dtrain: xgb.DMatrix,
        dtest: xgb.DMatrix,
        best_params: Dict[str, Any],
    ) -> xgb.Booster:
        """
        Train the final XGBoost model on the TRAINING fold.
        Evaluate on the held-out TEST fold.
        """
        model = xgb.train(
            params=best_params,
            dtrain=dtrain,
            num_boost_round=100,
            verbose_eval=10,
        )

        # ── Evaluate on TRAINING fold (for overfit detection only) ────
        y_train_proba = model.predict(dtrain)
        y_train_true = dtrain.get_label()
        train_auc = roc_auc_score(y_train_true, y_train_proba)

        # ── Evaluate on HELD-OUT TEST fold (the real metrics) ─────────
        y_test_proba = model.predict(dtest)
        y_test_pred = (y_test_proba > 0.5).astype(int)
        y_test_true = dtest.get_label()

        test_auc = roc_auc_score(y_test_true, y_test_proba)
        test_precision = precision_score(y_test_true, y_test_pred, zero_division=0)
        test_recall = recall_score(y_test_true, y_test_pred, zero_division=0)
        test_f1 = f1_score(y_test_true, y_test_pred, zero_division=0)

        # ── Log metrics ──────────────────────────────────────────────
        mlflow.log_metric("train_auc", train_auc)
        mlflow.log_metric("test_auc", test_auc)
        mlflow.log_metric("test_precision", test_precision)
        mlflow.log_metric("test_recall", test_recall)
        mlflow.log_metric("test_f1", test_f1)

        logger.info(
            f"Training metrics (overfit check) — Train AUC: {train_auc:.4f}"
        )
        logger.info(
            f"Held-out test metrics — "
            f"AUC: {test_auc:.4f}, "
            f"Precision: {test_precision:.4f}, "
            f"Recall: {test_recall:.4f}, "
            f"F1: {test_f1:.4f}"
        )

        # ── Overfit detection ────────────────────────────────────────
        gap = train_auc - test_auc
        mlflow.log_metric("overfit_gap", gap)
        if gap > OVERFIT_GAP_THRESHOLD:
            logger.warning(
                f"⚠ Potential overfitting detected! "
                f"Train AUC ({train_auc:.4f}) - Test AUC ({test_auc:.4f}) = {gap:.4f} "
                f"(threshold: {OVERFIT_GAP_THRESHOLD})"
            )

        # ── Log model to MLflow ──────────────────────────────────────
        mlflow.xgboost.log_model(
            model,
            artifact_path="model",
            registered_model_name="WillingnessModel",
        )

        return model

    # ── Model Persistence ────────────────────────────────────────────

    def save_model(self, model: xgb.Booster) -> None:
        """Save the trained model locally with versioning."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_filename = f"willingness_v{timestamp}.json"
        model_path = self.model_dir / model_filename

        model.save_model(str(model_path))
        logger.info(f"Model saved to: {model_path}")

        pointer_file = self.model_dir / "latest_willingness.json"
        pointer_data = {"latest": model_filename}

        with open(pointer_file, "w") as f:
            json.dump(pointer_data, f, indent=2)

        logger.info(f"Pointer file updated: {pointer_file}")

        mlflow.log_param("local_model_path", str(model_path))
        mlflow.log_artifact(str(model_path))
