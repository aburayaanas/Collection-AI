"""
NBA Engine — Phase 3 Contextual Bandit (LinUCB) Reward Tracker.

See docs/phase3_contextual_bandit_rl.md for the full design record —
verified facts, the decisions behind LinUCB over Thompson Sampling, the
13-dimensional feature vector, cold-start seeding, and known risks. This
module is the implementation of that document's sections 5-6.

This module owns three things:

  - ``map_outcome()`` — the single source of truth mapping
    ``CUSTOMER_OUTCOME`` to a reward. Shared by the real ingestion path
    (``RewardTracker.seed_and_refresh``) and the synthetic feedback
    generator (``scripts/generate_synthetic_rl_feedback.py``) so the two
    can never disagree about what a given outcome is worth.
  - ``build_context_vector()`` / ``context_vector_from_customer()`` — build
    the 13-dim LinUCB feature vector identically whether the caller is
    live-scoring a ``CustomerState`` or replaying a historical feedback row.
  - ``RewardTracker`` — the LinUCB engine: seeds cold-start priors from the
    existing heuristic, updates each channel's disjoint linear model from
    historical feedback, and caches the one-time-per-run matrix inversion
    so per-customer scoring stays cheap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import polars as pl

from src.core.logger import get_logger
from src.engine.nba.schemas import Channel, CustomerState

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Reward mapping — docs/phase3_contextual_bandit_rl.md section 5.1
# ═══════════════════════════════════════════════════════════════════════

OUTCOME_REWARDS: Dict[str, float] = {
    "PAID_IN_FULL": 1.00,
    "KEPT_PTP": 0.70,
    "RESTRUCTURE_AGREED": 0.60,
    "BROKEN_PTP": -0.50,
    "IGNORED": -1.00,
}


def map_outcome(customer_outcome: str) -> float:
    """Maps a CUSTOMER_OUTCOME string to its LinUCB reward target.

    Unknown outcomes log a warning and return 0.0 (neutral) rather than
    raising — one malformed feedback row must never crash bandit
    initialization for the whole batch.
    """
    reward = OUTCOME_REWARDS.get(customer_outcome)
    if reward is None:
        logger.warning(f"Unknown CUSTOMER_OUTCOME '{customer_outcome}' — treating as neutral (0.0).")
        return 0.0
    return reward


# ═══════════════════════════════════════════════════════════════════════
#  Context vector — docs/phase3_contextual_bandit_rl.md section 5.2
# ═══════════════════════════════════════════════════════════════════════

QUADRANTS: Tuple[str, ...] = ("Q1", "Q2", "Q3", "Q4")

FEATURE_NAMES: Tuple[str, ...] = (
    "intercept",
    "total_due",
    "days_past_due",
    "contact_avoidance_index",
    "sms_sent_this_week",
    "days_since_last_rpc",
    "ptp_reliability_ratio",
    "age",
    "account_tenure_days",
    "quadrant_q1",
    "quadrant_q2",
    "quadrant_q3",
    "quadrant_q4",
)
FEATURE_DIM: int = len(FEATURE_NAMES)  # 13


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def build_context_vector(
    quadrant: str,
    total_due: float,
    days_past_due: float,
    contact_avoidance_index: float,
    sms_sent_this_week: float,
    days_since_last_rpc: float,
    ptp_reliability_ratio: float,
    age: float,
    account_tenure_days: float,
) -> np.ndarray:
    """Builds the 13-dim LinUCB context vector `x`.

    Fixed-range scaling (not a fitted/persisted scaler) — the bounds are
    the same business constants already used elsewhere in this codebase
    (e.g. the SMS weekly cap from guardrails.py). See docs sec 5.2 for the
    rationale on each bound.
    """
    x = np.zeros(FEATURE_DIM, dtype=np.float64)
    x[0] = 1.0  # intercept
    x[1] = _clip01(total_due / 50_000.0)
    x[2] = _clip01(days_past_due / 180.0)
    x[3] = _clip01(contact_avoidance_index)
    x[4] = _clip01(sms_sent_this_week / 3.0)
    x[5] = _clip01(days_since_last_rpc / 180.0)
    x[6] = _clip01(ptp_reliability_ratio)
    x[7] = _clip01(age / 100.0)
    x[8] = _clip01(account_tenure_days / 3650.0)
    if quadrant in QUADRANTS:
        x[9 + QUADRANTS.index(quadrant)] = 1.0
    return x


def context_vector_from_customer(customer: CustomerState) -> np.ndarray:
    """Builds `x` from a live CustomerState at scoring time (SHADOW/LIVE mode)."""
    return build_context_vector(
        quadrant=customer.current_quadrant,
        total_due=customer.total_due,
        days_past_due=customer.days_past_due,
        contact_avoidance_index=customer.contact_avoidance_index,
        sms_sent_this_week=customer.sms_sent_this_week,
        days_since_last_rpc=customer.days_since_last_rpc,
        ptp_reliability_ratio=customer.ptp_reliability_ratio,
        age=customer.age,
        account_tenure_days=customer.account_tenure_days,
    )


def _context_vector_from_feedback_row(row: dict) -> np.ndarray:
    """Builds `x` from one row of RewardTracker's feedback DataFrame
    (CollectionRepository.get_rl_feedback_data() — column names uppercase)."""
    return build_context_vector(
        quadrant=row.get("QUADRANT") or "Q4",
        total_due=row.get("TOTAL_DUE") or 0.0,
        days_past_due=row.get("DAYS_PAST_DUE") or 0.0,
        contact_avoidance_index=row.get("CONTACT_AVOIDANCE_INDEX") or 0.0,
        sms_sent_this_week=row.get("SMS_SENT_THIS_WEEK") or 0.0,
        days_since_last_rpc=row.get("DAYS_SINCE_LAST_RPC") or 180.0,
        ptp_reliability_ratio=row.get("PTP_RELIABILITY_RATIO") or 0.0,
        age=row.get("AGE") or 40.0,
        account_tenure_days=row.get("ACCOUNT_TENURE_DAYS") or 0.0,
    )


def _context_vector_from_batch_row(row: dict) -> np.ndarray:
    """Builds `x` from one row of the current scoring batch DataFrame
    (uppercase columns as produced by main.py's run_nba_steps), used only
    for cold-start quadrant-mean seeding (docs sec 6.3)."""
    return build_context_vector(
        quadrant=row.get("CURRENT_QUADRANT") or "Q4",
        total_due=row.get("TOTAL_DUE") or 0.0,
        days_past_due=row.get("DAYS_PAST_DUE") or 0.0,
        contact_avoidance_index=row.get("CONTACT_AVOIDANCE_INDEX") or 0.0,
        sms_sent_this_week=row.get("SMS_SENT_THIS_WEEK") or 0.0,
        days_since_last_rpc=row.get("DAYS_SINCE_LAST_RPC") or 180.0,
        ptp_reliability_ratio=row.get("PTP_RELIABILITY_RATIO") or 0.0,
        age=row.get("AGE") or 40.0,
        account_tenure_days=row.get("ACCOUNT_TENURE_DAYS") or 0.0,
    )


# ═══════════════════════════════════════════════════════════════════════
#  LinUCB Arm — docs/phase3_contextual_bandit_rl.md section 6.1
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class _Arm:
    """One channel's disjoint linear ridge-regression model.

    `A` and `b` accumulate the cold-start prior plus every historical
    feedback observation. `A_inv`/`theta` are cached exactly once per
    `seed_and_refresh()` call via `finalize()` — the expensive O(d^3)
    inversion happens once per arm per pipeline run, never per customer.
    """

    channel: str
    A: np.ndarray
    b: np.ndarray
    n_real_observations: int = 0
    A_inv: Optional[np.ndarray] = field(default=None, repr=False)
    theta: Optional[np.ndarray] = field(default=None, repr=False)

    def finalize(self) -> None:
        self.A_inv = np.linalg.inv(self.A)
        self.theta = self.A_inv @ self.b


# Type of ContextualBandit._score_channel, injected to avoid a circular
# import between bandit.py and this module (bandit.py imports
# RewardTracker; RewardTracker must not import bandit.py).
HeuristicScorer = Callable[[Channel, str, bool, bool], Tuple[int, str]]


# ═══════════════════════════════════════════════════════════════════════
#  RewardTracker
# ═══════════════════════════════════════════════════════════════════════

class RewardTracker:
    """LinUCB contextual bandit reward tracker.

    Usage (once per pipeline run, before scoring the batch)::

        tracker = RewardTracker(
            prior_strength=settings.RL_PRIOR_STRENGTH,
            ridge_lambda=settings.RL_LINUCB_LAMBDA,
            alpha=settings.RL_LINUCB_ALPHA,
            min_samples=settings.RL_MIN_SAMPLES,
        )
        tracker.seed_and_refresh(bandit._score_channel, df_batch, df_feedback)
        ...
        scores = tracker.score_channels(customer, allowed_channels)
    """

    def __init__(
        self,
        prior_strength: float = 20.0,
        ridge_lambda: float = 1.0,
        alpha: float = 1.0,
        min_samples: int = 30,
    ) -> None:
        self.prior_strength = prior_strength
        self.ridge_lambda = ridge_lambda
        self.alpha = alpha
        self.min_samples = min_samples
        self._arms: Dict[str, _Arm] = {}
        self._ready: bool = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ── Cold start (docs sec 6.3) ───────────────────────────────────

    @staticmethod
    def _quadrant_mean_vectors(df_batch: Optional[pl.DataFrame]) -> Dict[str, np.ndarray]:
        """Mean real context vector per quadrant, from the current scoring
        batch — grounded in real portfolio statistics, not invented
        numbers, and always available (unlike historical feedback, which
        starts at zero rows on day one)."""
        means: Dict[str, np.ndarray] = {}

        def _neutral(q: str) -> np.ndarray:
            x = np.zeros(FEATURE_DIM)
            x[0] = 1.0
            x[9 + QUADRANTS.index(q)] = 1.0
            return x

        if df_batch is None or df_batch.height == 0 or "CURRENT_QUADRANT" not in df_batch.columns:
            return {q: _neutral(q) for q in QUADRANTS}

        for q in QUADRANTS:
            sub = df_batch.filter(pl.col("CURRENT_QUADRANT") == q)
            if sub.height == 0:
                means[q] = _neutral(q)
                continue
            row = {col: sub[col].mean() for col in sub.columns if col in (
                "TOTAL_DUE", "DAYS_PAST_DUE", "CONTACT_AVOIDANCE_INDEX",
                "SMS_SENT_THIS_WEEK", "DAYS_SINCE_LAST_RPC",
                "PTP_RELIABILITY_RATIO", "AGE", "ACCOUNT_TENURE_DAYS",
            )}
            row["CURRENT_QUADRANT"] = q
            means[q] = _context_vector_from_batch_row(row)
        return means

    def _seed_arms(
        self,
        heuristic_scorer: HeuristicScorer,
        quadrant_means: Dict[str, np.ndarray],
    ) -> Dict[str, _Arm]:
        """Seeds each channel's (A, b) from the heuristic's implied reward
        at each quadrant's mean context vector — the LinUCB analogue of
        Beta-prior seeding: before any real feedback, theta_a already
        points toward what the heuristic believed, so LIVE/SHADOW mode
        never starts from uninformed, unsafe random exploration."""
        arms: Dict[str, _Arm] = {}
        for channel in Channel:
            A = self.ridge_lambda * np.eye(FEATURE_DIM)
            b = np.zeros(FEATURE_DIM)
            for quadrant, x_bar in quadrant_means.items():
                heuristic_score, _ = heuristic_scorer(channel, quadrant, False, False)
                r0 = (heuristic_score / 100.0) * 2.0 - 1.0  # 0..100 -> -1..+1 (docs sec 6.3)
                A = A + self.prior_strength * np.outer(x_bar, x_bar)
                b = b + self.prior_strength * r0 * x_bar
            arms[channel.value] = _Arm(channel=channel.value, A=A, b=b)
        return arms

    # ── Update (docs sec 6.4) ────────────────────────────────────────

    def seed_and_refresh(
        self,
        heuristic_scorer: HeuristicScorer,
        df_batch: Optional[pl.DataFrame],
        df_feedback: Optional[pl.DataFrame],
    ) -> None:
        """Rebuilds every arm from scratch: heuristic cold-start prior
        plus every feedback row's (x, r) update. Called once per pipeline
        run — never incrementally — matching how WillingnessScorer/
        AbilityScorer load their model fresh each run.
        """
        quadrant_means = self._quadrant_mean_vectors(df_batch)
        arms = self._seed_arms(heuristic_scorer, quadrant_means)

        n_rows = 0 if df_feedback is None else df_feedback.height
        skipped_unknown_channel = 0
        for row in ([] if df_feedback is None else df_feedback.iter_rows(named=True)):
            channel = row.get("ACTUAL_CHANNEL_USED")
            arm = arms.get(channel)
            if arm is None:
                skipped_unknown_channel += 1
                continue
            reward = row.get("BANDIT_REWARD_SCORE")
            if reward is None:
                continue
            x = _context_vector_from_feedback_row(row)
            arm.A = arm.A + np.outer(x, x)
            arm.b = arm.b + reward * x
            arm.n_real_observations += 1

        for arm in arms.values():
            arm.finalize()  # the one-time-per-run O(d^3) inversion

        self._arms = arms
        self._ready = True

        if skipped_unknown_channel:
            logger.warning(f"Skipped {skipped_unknown_channel} feedback row(s) with an unrecognized channel.")
        for channel, arm in arms.items():
            status = "seasoned" if arm.n_real_observations >= self.min_samples else "prior-dominated"
            logger.info(
                f"LinUCB arm '{channel}': {arm.n_real_observations} real observation(s) "
                f"({status}, min_samples={self.min_samples})"
            )
        logger.info(f"RewardTracker refreshed from {n_rows:,} feedback row(s) across {len(arms)} arms.")

    # ── Scoring (docs sec 6.2) ───────────────────────────────────────

    def score_channels(
        self,
        customer: CustomerState,
        allowed_channels: List[Channel],
    ) -> Dict[str, float]:
        """UCB score (mean + exploration bonus) per allowed channel.

        Uses the cached `theta`/`A_inv` from the last `seed_and_refresh()`
        — no matrix inversion happens here, just cheap dot products, so
        this is safe to call once per customer in the existing row-by-row
        orchestrator loop without restructuring it.
        """
        if not self._ready:
            raise RuntimeError("RewardTracker.score_channels() called before seed_and_refresh().")

        x = context_vector_from_customer(customer)
        scores: Dict[str, float] = {}
        for channel in allowed_channels:
            arm = self._arms.get(channel.value)
            if arm is None or arm.theta is None or arm.A_inv is None:
                continue
            mean_score = float(arm.theta @ x)
            bonus = self.alpha * math.sqrt(max(0.0, float(x @ arm.A_inv @ x)))
            scores[channel.value] = mean_score + bonus
        return scores

    def sample_count(self, channel: str) -> int:
        """Observability helper: how many real observations backed this arm."""
        arm = self._arms.get(channel)
        return arm.n_real_observations if arm else 0
