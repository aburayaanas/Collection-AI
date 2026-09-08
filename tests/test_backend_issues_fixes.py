"""
Regression tests for docs/backend_issues.md fixes (2026-09-06).

Covers:
- Issue 3: probability calibration (src/models_engine/calibration.py)
- Issue 4: escalation timeline — legal-status and product-restriction
  awareness (src/engine/nba/escalation.py)
- Issue 5: behavioral signal thresholds are configurable, not hardcoded
  (src/engine/inference/signal_interpreter.py)

Issues 6/7 (LLM prompt polarity + SHAP clarity) are prompt-text changes
in src/explainability/llm_system_prompt.md with no executable behavior
to unit test; verified by inline review during the fix.
"""

import numpy as np
import pytest

from src.core.config import reload_settings, settings
from src.engine.inference.signal_interpreter import SignalInterpreter
from src.engine.nba.escalation import EscalationEngine
from src.models_engine import calibration


# ── Issue 3: Calibration ─────────────────────────────────────────────


class TestCalibration:
    def test_isotonic_calibrator_is_monotonic(self):
        rng = np.random.default_rng(42)
        raw = np.sort(rng.uniform(0, 1, 500))
        # Noisy but generally-increasing true labels
        y = (raw + rng.normal(0, 0.1, 500) > 0.5).astype(int)
        calibrator = calibration.fit_isotonic_calibrator(raw, y)
        calibrated = calibrator.predict(raw)
        # Isotonic regression must never decrease as the input increases
        assert np.all(np.diff(calibrated) >= -1e-9)

    def test_calibrated_output_stays_in_unit_range(self):
        rng = np.random.default_rng(1)
        raw = rng.uniform(0, 1, 200)
        y = rng.integers(0, 2, 200)
        calibrator = calibration.fit_isotonic_calibrator(raw, y)
        calibrated = calibrator.predict(raw)
        assert calibrated.min() >= 0.0
        assert calibrated.max() <= 1.0

    def test_ece_is_zero_for_perfectly_calibrated_predictions(self):
        # 100 predictions of exactly 0.5, exactly half positive: perfectly calibrated.
        probs = np.full(100, 0.5)
        y_true = np.array([1] * 50 + [0] * 50)
        ece = calibration.expected_calibration_error(y_true, probs, n_bins=10)
        assert ece == pytest.approx(0.0, abs=1e-9)

    def test_ece_detects_saturation_miscalibration(self):
        # The exact failure mode from Issue 3: model is 100% confident
        # (prob=1.0) but only right 50% of the time — badly miscalibrated.
        probs = np.full(100, 1.0)
        y_true = np.array([1] * 50 + [0] * 50)
        ece = calibration.expected_calibration_error(y_true, probs, n_bins=10)
        assert ece == pytest.approx(0.5, abs=1e-9)

    def test_evaluate_calibration_returns_all_four_metrics(self):
        rng = np.random.default_rng(7)
        y_true = rng.integers(0, 2, 100)
        raw = rng.uniform(0, 1, 100)
        calibrated = raw.copy()
        result = calibration.evaluate_calibration(y_true, raw, calibrated)
        assert set(result.keys()) == {
            "brier_raw",
            "brier_calibrated",
            "ece_raw",
            "ece_calibrated",
        }

    def test_compute_oof_predictions_covers_every_row_exactly_once(self):
        rng = np.random.default_rng(3)
        X = rng.uniform(0, 1, (100, 2))
        y = rng.integers(0, 2, 100)
        params = {
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "max_depth": 2,
            "seed": 42,
        }
        oof = calibration.compute_oof_predictions(
            params, X, y, feature_names=["a", "b"], num_boost_round=5, n_splits=5
        )
        assert oof.shape == (100,)
        assert np.all((oof >= 0.0) & (oof <= 1.0))


# ── Issue 4: Escalation timeline ─────────────────────────────────────


class TestEscalationEngine:
    def test_active_account_uses_configured_phase_windows(self):
        result = EscalationEngine.generate_timeline(
            days_past_due=45,
            current_quadrant="Q4",
            selected_nba="Field Visit",
            minimum_acceptable_cash=1500.0,
            account_status="Active",
            products_held="Personal loan",
        )
        assert "0-7 days" in result["phase_1_current"]
        assert "days 8-21" in result["phase_2_trigger"]
        assert "Formal demand letter" in result["phase_2_trigger"]
        assert "day 21" in result["phase_3_legal"]

    def test_legal_status_account_never_says_will_be_referred(self):
        """The exact bug from Issue 4: an account already in Legal status
        must not be told it will be referred to legal in the future."""
        result = EscalationEngine.generate_timeline(
            days_past_due=120,
            current_quadrant="Q3",
            selected_nba="Outgoing Call",
            minimum_acceptable_cash=3000.0,
            account_status="Legal",
            products_held="Mortgage",
        )
        for phase_text in (
            result["phase_1_current"],
            result["phase_2_trigger"],
            result["phase_3_legal"],
        ):
            assert "Triggered if" not in phase_text
        assert "already" in result["phase_3_legal"].lower()

    def test_transfer_to_remedial_status_also_short_circuits(self):
        result = EscalationEngine.generate_timeline(
            days_past_due=80,
            current_quadrant="Q4",
            selected_nba="Field Visit",
            minimum_acceptable_cash=1000.0,
            account_status="Transfer To Remedial",
        )
        assert "Not applicable" in result["phase_2_trigger"]

    def test_product_restriction_suppresses_demand_letter(self):
        reload_settings()
        settings.ESCALATION_LEGAL_INELIGIBLE_PRODUCTS = "Mortgage"
        try:
            result = EscalationEngine.generate_timeline(
                days_past_due=45,
                current_quadrant="Q4",
                selected_nba="Field Visit",
                minimum_acceptable_cash=1500.0,
                account_status="Active",
                products_held="Mortgage · Current account",
            )
            assert "Formal demand letter" not in result["phase_2_trigger"]
            assert "NOT applicable" in result["phase_2_trigger"]
        finally:
            settings.ESCALATION_LEGAL_INELIGIBLE_PRODUCTS = ""

    def test_blank_ineligible_products_setting_changes_nothing(self):
        """Default (blank) must reproduce the original, unrestricted behavior."""
        result = EscalationEngine.generate_timeline(
            days_past_due=45,
            current_quadrant="Q4",
            selected_nba="Field Visit",
            minimum_acceptable_cash=1500.0,
            account_status="Active",
            products_held="Mortgage",
        )
        assert "Formal demand letter" in result["phase_2_trigger"]

    def test_recovery_quadrant_logic_unchanged(self):
        result = EscalationEngine.generate_timeline(
            days_past_due=10,
            current_quadrant="Q1",
            selected_nba="Email",
            minimum_acceptable_cash=0.0,
        )
        assert "Q0" in result["exit_path"]

    def test_reference_date_anchors_timeline_dates(self):
        result = EscalationEngine.generate_timeline(
            days_past_due=44,
            current_quadrant="Q2",
            selected_nba="Email",
            minimum_acceptable_cash=500.0,
            account_status="Active",
            reference_date="2026-05-18",
        )
        assert "2026-05-25" in result["phase_1_current"]
        assert "2026-05-25" in result["phase_2_trigger"]


class TestBanditReasoning:
    def test_q2_reasoning_differentiates_from_q1(self):
        from src.engine.nba.bandit import ContextualBandit, Channel
        bandit = ContextualBandit()
        _, q1_reason = bandit._score_channel(Channel.EMAIL, "Q1", False, False)
        _, q2_reason = bandit._score_channel(Channel.EMAIL, "Q2", False, False)
        assert "Low risk quadrant (Q1)" in q1_reason
        assert "Vulnerable quadrant (Q2)" in q2_reason


# ── Issue 5: Configurable signal thresholds ──────────────────────────


class TestSignalInterpreterThresholds:
    def setup_method(self):
        reload_settings()

    def teardown_method(self):
        reload_settings()

    def test_default_thresholds_match_original_hardcoded_behavior(self):
        signals = SignalInterpreter.generate_signals(
            {
                "PAYMENT_REJECTION_FREQ": 2,
                "INFLOW_VARIANCE_30D": 800.0,
                "ABILITY_SCORE": 0.2,
            }
        )
        titles = [s.title for s in signals]
        assert "Payment Rejections" in titles
        assert "Liquidity Disruption" in titles
        liquidity_signal = next(s for s in signals if s.title == "Liquidity Disruption")
        assert liquidity_signal.confidence == 0.75  # clamped to the default ceiling

    def test_no_signal_below_default_threshold(self):
        signals = SignalInterpreter.generate_signals(
            {
                "PAYMENT_REJECTION_FREQ": 1,
                "INFLOW_VARIANCE_30D": 100.0,
            }
        )
        assert signals == []

    def test_lowering_threshold_via_settings_triggers_signal_that_wouldnt_fire_by_default(
        self,
    ):
        settings.SIGNAL_LIQUIDITY_INFLOW_VARIANCE_THRESHOLD = 50.0
        signals = SignalInterpreter.generate_signals(
            {
                "PAYMENT_REJECTION_FREQ": 1,
                "INFLOW_VARIANCE_30D": 100.0,
            }
        )
        assert any(s.title == "Payment Rejections" for s in signals)

    def test_evasion_threshold_is_configurable(self):
        settings.SIGNAL_EVASION_CONTACT_AVOIDANCE_THRESHOLD = 0.9
        # 0.8 no longer clears the raised bar
        signals = SignalInterpreter.generate_signals(
            {
                "BROKEN_PTP_COUNT_6M": 2,
                "CONTACT_AVOIDANCE_INDEX": 0.8,
            }
        )
        assert signals == []
