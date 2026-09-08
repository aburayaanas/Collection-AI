"""
Probability calibration for the Willingness/Ability XGBoost models.

Deep gradient-boosted trees routinely push predicted probabilities to the
extremes (exact ~0.0 or ~1.0) even when the true underlying confidence is
far more moderate — a well-documented failure mode for tree ensembles
(Niculescu-Mizil & Caruana, 2005, "Predicting Good Probabilities With
Supervised Learning"). Left uncalibrated, this is exactly what produces
the "0/100 or 99/100" scores reported in docs/backend_issues.md Issue 3:
the raw XGBoost probability genuinely is 0.0001 or 0.9999, and
multiplying by 100 for display (src/explainability/xai_aggregator.py)
just shows that faithfully. The saturation happens upstream, at
inference — so that's where the fix belongs, not in the display layer.

The fix is out-of-fold (OOF) isotonic calibration, fit on the TRAINING
fold only, in three steps:

  1. K-fold cross-validate the *already-tuned* hyperparameters across the
     training fold, predicting each fold's held-out rows with a model
     that never saw them — a genuinely out-of-sample prediction.
  2. Fit an IsotonicRegression mapping OOF raw probability -> true label
     across the whole training fold. Isotonic (not Platt/sigmoid) is
     used deliberately: it is non-parametric and can correct the
     arbitrary monotonic distortion boosted trees produce, whereas Platt
     scaling assumes a specific sigmoid-shaped miscalibration that
     doesn't match this failure mode.
  3. The production model is still trained on the FULL training fold,
     unchanged — no training data is sacrificed to calibration, and the
     untouched TEST fold remains available for an honest before/after
     calibration-quality check (Brier score + Expected Calibration
     Error), so the fix's effect is measured, not assumed.

The calibrator is persisted as a small companion artifact next to the
model JSON; scorer.py applies it after model.predict() so every
downstream consumer (Matrix, NBA, Cockpit, LLM narrative) sees calibrated
probabilities without any change to their own code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import joblib
import numpy as np
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import StratifiedKFold

from src.core.logger import get_logger

logger = get_logger(__name__)

N_CALIBRATION_FOLDS = 5
CALIBRATION_RANDOM_STATE = 42
ECE_N_BINS = 10


def compute_oof_predictions(
    params: Dict[str, Any],
    X_train: np.ndarray,
    y_train: np.ndarray,
    feature_names: List[str],
    num_boost_round: int = 100,
    n_splits: int = N_CALIBRATION_FOLDS,
) -> np.ndarray:
    """Out-of-fold raw probability predictions for every row in X_train.

    Each prediction comes from a model trained WITHOUT that row — a
    genuinely out-of-sample prediction, safe to fit a calibrator against
    without leaking information back into the model that produced it.
    Reuses the already-tuned hyperparameters/num_boost_round as-is; this
    is purely about generating an honest calibration signal, not a
    second round of hyperparameter search.
    """
    oof = np.zeros(len(y_train), dtype=np.float64)
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=CALIBRATION_RANDOM_STATE)

    for fold_idx, (fit_idx, hold_idx) in enumerate(skf.split(X_train, y_train), start=1):
        d_fit = xgb.DMatrix(X_train[fit_idx], label=y_train[fit_idx], feature_names=feature_names)
        d_hold = xgb.DMatrix(X_train[hold_idx], feature_names=feature_names)

        fold_model = xgb.train(params=params, dtrain=d_fit, num_boost_round=num_boost_round, verbose_eval=False)
        oof[hold_idx] = fold_model.predict(d_hold)
        logger.debug(f"Calibration fold {fold_idx}/{n_splits}: {len(hold_idx)} OOF predictions generated.")

    return oof


def fit_isotonic_calibrator(oof_predictions: np.ndarray, y_train: np.ndarray) -> IsotonicRegression:
    """Fits the mapping raw_probability -> calibrated_probability."""
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(oof_predictions, y_train)
    return calibrator


def expected_calibration_error(y_true: np.ndarray, probs: np.ndarray, n_bins: int = ECE_N_BINS) -> float:
    """Standard Expected Calibration Error.

    Bins predictions by confidence and averages
    |mean predicted probability - actual positive rate| per bin, weighted
    by bin size. 0.0 = perfectly calibrated; this is the metric that
    directly detects the "always near 0 or 1" saturation pattern, since
    a saturated model's high-confidence bins will show a large gap
    between predicted confidence and actual outcome rate.
    """
    y_true = np.asarray(y_true)
    probs = np.asarray(probs)
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (probs >= lo) & (probs < hi) if hi < 1.0 else (probs >= lo) & (probs <= hi)
        if not np.any(mask):
            continue
        bin_confidence = probs[mask].mean()
        bin_accuracy = y_true[mask].mean()
        ece += (mask.sum() / n) * abs(bin_confidence - bin_accuracy)
    return float(ece)


def evaluate_calibration(y_true: np.ndarray, raw_probs: np.ndarray, calibrated_probs: np.ndarray) -> Dict[str, float]:
    """Brier score + ECE, before and after calibration, on the same held-out labels."""
    return {
        "brier_raw": float(brier_score_loss(y_true, raw_probs)),
        "brier_calibrated": float(brier_score_loss(y_true, calibrated_probs)),
        "ece_raw": expected_calibration_error(y_true, raw_probs),
        "ece_calibrated": expected_calibration_error(y_true, calibrated_probs),
    }


def save_calibrator(calibrator: IsotonicRegression, path: Path) -> None:
    joblib.dump(calibrator, path)


def load_calibrator(path: Path) -> IsotonicRegression:
    return joblib.load(path)
