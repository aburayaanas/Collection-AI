"""
Unit tests for the Phase 3 contextual bandit (LinUCB).

See docs/phase3_contextual_bandit_rl.md for the design these tests
guard. These are deliberately fast/offline (no DB, no live Oracle) —
the full pipeline was additionally verified end-to-end against the real
dev DB in all three policy modes; see CHANGELOG.md 2026-09-06.

Covers:
1. Reward mapping (map_outcome) — the single source of truth shared with
   the synthetic feedback generator.
2. Context vector construction — dimensions, scaling, clipping.
3. Cold-start seeding — arms start pointed toward the heuristic's
   preference, not an uninformed prior.
4. ContextualBandit's three policy modes — HEURISTIC is an exact
   regression guard, SHADOW's safety contract (never changes
   recommended_channel), LIVE actually acts on the bandit's pick, and
   graceful fallback when the tracker is unavailable.
5. RewardTracker.seed_and_refresh() actually learns from feedback data
   (a channel with only positive outcomes scores higher than one with
   only negative outcomes, for the same context).
"""

import numpy as np
import polars as pl
import pytest

from src.engine.nba.bandit import ContextualBandit
from src.engine.nba.reward_tracker import (
    FEATURE_DIM,
    OUTCOME_REWARDS,
    RewardTracker,
    build_context_vector,
    map_outcome,
)
from src.engine.nba.schemas import Channel, CustomerState


# ── Reward mapping ───────────────────────────────────────────────────

class TestMapOutcome:
    def test_all_documented_outcomes_map_to_their_reward(self):
        for outcome, expected_reward in OUTCOME_REWARDS.items():
            assert map_outcome(outcome) == expected_reward

    def test_positive_outcomes_are_positive(self):
        for outcome in ("PAID_IN_FULL", "KEPT_PTP", "RESTRUCTURE_AGREED"):
            assert map_outcome(outcome) > 0

    def test_negative_outcomes_are_negative(self):
        for outcome in ("BROKEN_PTP", "IGNORED"):
            assert map_outcome(outcome) < 0

    def test_unknown_outcome_is_neutral_not_an_error(self):
        assert map_outcome("SOMETHING_MADE_UP") == 0.0


# ── Context vector ───────────────────────────────────────────────────

class TestBuildContextVector:
    def _vector(self, **overrides):
        defaults = dict(
            quadrant="Q1", total_due=0.0, days_past_due=0.0,
            contact_avoidance_index=0.0, sms_sent_this_week=0.0,
            days_since_last_rpc=0.0, ptp_reliability_ratio=0.0,
            age=0.0, account_tenure_days=0.0,
        )
        defaults.update(overrides)
        return build_context_vector(**defaults)

    def test_dimension_is_thirteen(self):
        assert self._vector().shape == (FEATURE_DIM,)
        assert FEATURE_DIM == 13

    def test_intercept_is_always_one(self):
        assert self._vector()[0] == 1.0

    def test_quadrant_one_hot_is_exclusive(self):
        for i, q in enumerate(("Q1", "Q2", "Q3", "Q4")):
            x = self._vector(quadrant=q)
            one_hot = x[9:13]
            assert one_hot.sum() == 1.0
            assert one_hot[i] == 1.0

    def test_unrecognised_quadrant_leaves_one_hot_all_zero(self):
        x = self._vector(quadrant="Q99")
        assert x[9:13].sum() == 0.0

    def test_values_are_clipped_to_unit_range(self):
        x = self._vector(total_due=999_999_999, days_past_due=-500)
        assert 0.0 <= x[1] <= 1.0
        assert 0.0 <= x[2] <= 1.0


# ── Cold start ───────────────────────────────────────────────────────

class TestColdStartSeeding:
    def test_seeds_toward_heuristic_preference_for_soft_quadrant(self):
        """Q1 (soft) heuristically prefers Email over Field Visit — the
        seeded LinUCB arms must reflect that before any real feedback."""
        heuristic = ContextualBandit(policy_mode="HEURISTIC")
        tracker = RewardTracker(prior_strength=20, ridge_lambda=1.0, alpha=1.0, min_samples=30)
        tracker.seed_and_refresh(heuristic._score_channel, None, None)

        customer = CustomerState(
            cust_info_id="1", current_quadrant="Q1", account_status="Active",
            total_due=1000.0, sms_sent_this_week=0, calls_made_today=0,
        )
        scores = tracker.score_channels(customer, list(Channel))
        assert scores["Email"] > scores["Field Visit"]

    def test_seeds_toward_heuristic_preference_for_hard_quadrant(self):
        """Q4 (hard) heuristically prefers Field Visit over Email."""
        heuristic = ContextualBandit(policy_mode="HEURISTIC")
        tracker = RewardTracker(prior_strength=20, ridge_lambda=1.0, alpha=1.0, min_samples=30)
        tracker.seed_and_refresh(heuristic._score_channel, None, None)

        customer = CustomerState(
            cust_info_id="2", current_quadrant="Q4", account_status="Active",
            total_due=8000.0, sms_sent_this_week=0, calls_made_today=0,
        )
        scores = tracker.score_channels(customer, list(Channel))
        assert scores["Field Visit"] > scores["Email"]

    def test_score_channels_before_refresh_raises(self):
        tracker = RewardTracker()
        customer = CustomerState(
            cust_info_id="3", current_quadrant="Q1", account_status="Active",
            total_due=0.0,
        )
        with pytest.raises(RuntimeError):
            tracker.score_channels(customer, list(Channel))


# ── Personalization within a quadrant (the reason LinUCB was chosen) ──

class TestPersonalization:
    def test_same_quadrant_different_avoidance_shifts_email_score(self):
        """Two customers in the same quadrant, differing only in
        CONTACT_AVOIDANCE_INDEX, must not score identically — this is
        the exact capability a quadrant-only bandit cannot provide."""
        heuristic = ContextualBandit(policy_mode="HEURISTIC")
        tracker = RewardTracker(prior_strength=20, ridge_lambda=1.0, alpha=1.0, min_samples=30)
        tracker.seed_and_refresh(heuristic._score_channel, None, None)

        low = CustomerState(
            cust_info_id="low", current_quadrant="Q3", account_status="Active",
            total_due=10000.0, contact_avoidance_index=0.05,
        )
        high = CustomerState(
            cust_info_id="high", current_quadrant="Q3", account_status="Active",
            total_due=10000.0, contact_avoidance_index=0.95,
        )
        scores_low = tracker.score_channels(low, list(Channel))
        scores_high = tracker.score_channels(high, list(Channel))
        assert scores_low["Email"] != scores_high["Email"]


# ── RewardTracker learns from feedback ──────────────────────────────

class TestSeedAndRefreshLearnsFromFeedback:
    def test_channel_with_positive_feedback_outscores_one_with_negative(self):
        heuristic = ContextualBandit(policy_mode="HEURISTIC")
        tracker = RewardTracker(prior_strength=5, ridge_lambda=1.0, alpha=0.0, min_samples=30)

        # alpha=0.0 isolates the learned mean (theta.x) from the
        # exploration bonus, so this test only checks what was learned.
        rows = []
        for _ in range(50):
            rows.append({
                "QUADRANT": "Q4", "ACTUAL_CHANNEL_USED": "Email",
                "BANDIT_REWARD_SCORE": 1.0,
                "TOTAL_DUE": 5000.0, "DAYS_PAST_DUE": 30, "CONTACT_AVOIDANCE_INDEX": 0.1,
                "SMS_SENT_THIS_WEEK": 0, "DAYS_SINCE_LAST_RPC": 5, "PTP_RELIABILITY_RATIO": 0.5,
                "AGE": 40, "ACCOUNT_TENURE_DAYS": 500,
            })
            rows.append({
                "QUADRANT": "Q4", "ACTUAL_CHANNEL_USED": "SMS",
                "BANDIT_REWARD_SCORE": -1.0,
                "TOTAL_DUE": 5000.0, "DAYS_PAST_DUE": 30, "CONTACT_AVOIDANCE_INDEX": 0.1,
                "SMS_SENT_THIS_WEEK": 0, "DAYS_SINCE_LAST_RPC": 5, "PTP_RELIABILITY_RATIO": 0.5,
                "AGE": 40, "ACCOUNT_TENURE_DAYS": 500,
            })
        df_feedback = pl.DataFrame(rows)

        tracker.seed_and_refresh(heuristic._score_channel, None, df_feedback)
        assert tracker.sample_count("Email") == 50
        assert tracker.sample_count("SMS") == 50

        customer = CustomerState(
            cust_info_id="x", current_quadrant="Q4", account_status="Active",
            total_due=5000.0, contact_avoidance_index=0.1, days_past_due=30,
            days_since_last_rpc=5, ptp_reliability_ratio=0.5, age=40, account_tenure_days=500,
        )
        scores = tracker.score_channels(customer, [Channel.EMAIL, Channel.SMS])
        assert scores["Email"] > scores["SMS"]


# ── ContextualBandit policy modes ───────────────────────────────────

class _FixedPickRewardTracker:
    """Minimal fake satisfying the duck-typed interface bandit._linucb_pick
    needs, so SHADOW/LIVE behavior can be tested without a real
    RewardTracker or DB access."""

    def __init__(self, preferred_channel: str):
        self.is_ready = True
        self._preferred = preferred_channel

    def score_channels(self, customer, allowed_channels):
        return {
            c.value: (10.0 if c.value == self._preferred else 1.0)
            for c in allowed_channels
        }

    def sample_count(self, channel: str) -> int:
        return 999


class TestContextualBanditPolicyModes:
    CUSTOMER = CustomerState(
        cust_info_id="42", current_quadrant="Q4", account_status="Active",
        total_due=8000.0, sms_sent_this_week=0, calls_made_today=0,
    )

    def test_heuristic_mode_picks_field_visit_for_q4(self):
        """Regression guard: Q4 with no behavioral flags and all channels
        allowed must pick Field Visit — exactly today's pre-Phase-3 heuristic."""
        bandit = ContextualBandit(policy_mode="HEURISTIC")
        out = bandit.get_best_action(self.CUSTOMER, list(Channel))
        assert out.recommended_channel == "Field Visit"
        assert out.decision_reason == "BANDIT:Q4|ESCALATION|FIELD_VISIT|PARTIAL_PAYMENT"

    def test_shadow_mode_never_changes_recommended_channel(self):
        """The core SHADOW safety contract: even when the reward tracker
        strongly prefers a different channel, recommended_channel must
        still be the heuristic's pick."""
        fake_tracker = _FixedPickRewardTracker(preferred_channel="SMS")
        bandit = ContextualBandit(reward_tracker=fake_tracker, policy_mode="SHADOW")
        out = bandit.get_best_action(self.CUSTOMER, list(Channel))
        assert out.recommended_channel == "Field Visit"  # heuristic pick, unchanged
        assert "SHADOW_RL_PICK:SMS" in out.decision_reason

    def test_live_mode_acts_on_reward_tracker_pick(self):
        fake_tracker = _FixedPickRewardTracker(preferred_channel="SMS")
        bandit = ContextualBandit(reward_tracker=fake_tracker, policy_mode="LIVE")
        out = bandit.get_best_action(self.CUSTOMER, list(Channel))
        assert out.recommended_channel == "SMS"
        assert out.decision_reason == "RL:Q4|LINUCB|SMS|PARTIAL_PAYMENT"

    def test_live_mode_falls_back_to_heuristic_without_a_tracker(self):
        bandit = ContextualBandit(reward_tracker=None, policy_mode="LIVE")
        out = bandit.get_best_action(self.CUSTOMER, list(Channel))
        assert out.recommended_channel == "Field Visit"
        assert out.decision_reason == "BANDIT:Q4|ESCALATION|FIELD_VISIT|PARTIAL_PAYMENT"

    def test_treatment_is_identical_across_all_modes(self):
        fake_tracker = _FixedPickRewardTracker(preferred_channel="SMS")
        for mode in ("HEURISTIC", "SHADOW", "LIVE"):
            bandit = ContextualBandit(reward_tracker=fake_tracker, policy_mode=mode)
            out = bandit.get_best_action(self.CUSTOMER, list(Channel))
            assert out.recommended_treatment == "Partial Payment"

    def test_unrecognised_policy_mode_falls_back_to_heuristic(self):
        bandit = ContextualBandit(policy_mode="NOT_A_REAL_MODE")
        assert bandit.policy_mode == "HEURISTIC"
