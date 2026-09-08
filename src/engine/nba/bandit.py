"""
NBA Engine — Contextual Bandit Decision Engine.

This module implements the AI decision layer that selects the optimal
(channel, treatment) pair for each customer from the legally-allowed
action space produced by the guardrail ``RuleEngine``.

Architecture:
    GuardrailResult.allowed_channels
            │
            ▼
    ContextualBandit.get_best_action(customer, allowed_channels)
            │
            ├── _select_treatment(quadrant)        → Treatment heuristic (unchanged, all modes)
            ├── _heuristic_pick(...)                → today's static scoring
            └── _linucb_pick(...)                   → RewardTracker (Phase 3)
            │
            ▼
        NBAOutput  →  downstream DB persistence

Design Philosophy — Phase 3 status:
    Channel selection now runs one of three policies, controlled by
    ``settings.NBA_POLICY_MODE`` (see docs/phase3_contextual_bandit_rl.md):

    - ``HEURISTIC`` (default): the original static, deterministic policy
      below — unchanged, byte-for-byte, from before Phase 3.
    - ``SHADOW``: the heuristic still decides ``recommended_channel``
      (safe — nothing acts on the bandit's pick yet), but the LinUCB
      pick and its score are computed and logged in the audit trail for
      comparison.
    - ``LIVE``: the LinUCB pick (``RewardTracker``) drives
      ``recommended_channel`` directly.

    Treatment selection is unchanged in every mode — it has never been
    part of the learned action space (docs sec 3).

    If a reward tracker isn't supplied, isn't ready, or scoring raises for
    any reason, every mode falls back to the heuristic for that customer
    rather than failing the batch — the same fault-isolation guarantee
    already used everywhere else in the NBA engine.

Isolation Guarantee:
    This module is fully decoupled from ``guardrails.py``. It only
    knows about the schemas from ``.schemas`` and the pre-filtered
    ``allowed_channels`` list it receives. It has no knowledge of
    what was removed or why.
"""

from __future__ import annotations

from typing import Final, List, Optional

from src.core.logger import get_logger
from src.engine.nba.schemas import (
    Channel,
    CustomerState,
    NBAOutput,
    ScoredAlternative,
    Treatment,
)

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Channel Cost Hierarchy — Aggressiveness Index
# ═══════════════════════════════════════════════════════════════════════

# Maps each channel to an integer "cost score". Lower = cheaper and
# less intrusive; higher = more expensive and more aggressive.
# Used by _select_channel to implement the Q1/Q2 (soft) vs Q3/Q4
# (hard) selection policy without nested conditionals.
CHANNEL_COST: Final[dict[Channel, int]] = {
    Channel.EMAIL: 1,
    Channel.SMS: 2,
    Channel.OUTGOING_CALL: 3,
    Channel.DUNNING_LETTER: 4,
    Channel.FIELD_VISIT: 5,
}

# Quadrants that receive a "soft-touch" (cheapest) channel approach.
SOFT_QUADRANTS: Final[frozenset[str]] = frozenset({"Q1", "Q2"})

# Quadrants that receive an "escalation" (most aggressive) approach.
HARD_QUADRANTS: Final[frozenset[str]] = frozenset({"Q3", "Q4"})

VALID_POLICY_MODES: Final[frozenset[str]] = frozenset({"HEURISTIC", "SHADOW", "LIVE"})


# ═══════════════════════════════════════════════════════════════════════
#  Contextual Bandit — Core Decision Engine
# ═══════════════════════════════════════════════════════════════════════


class ContextualBandit:
    """Selects the optimal (channel, treatment) pair for a given customer.

    See the module docstring for the three ``policy_mode`` behaviors.
    ``reward_tracker`` is a ``src.engine.nba.reward_tracker.RewardTracker``
    (typed loosely here — see below — to avoid a hard import-time
    dependency for callers that only ever use HEURISTIC mode, e.g. unit
    tests and the CLI's plain heuristic path).
    """

    def __init__(
        self,
        reward_tracker: Optional[object] = None,
        policy_mode: str = "HEURISTIC",
    ) -> None:
        policy_mode = (policy_mode or "HEURISTIC").upper()
        if policy_mode not in VALID_POLICY_MODES:
            logger.warning(
                f"Unrecognised NBA_POLICY_MODE '{policy_mode}' — falling back to HEURISTIC."
            )
            policy_mode = "HEURISTIC"

        self.reward_tracker = reward_tracker
        self.policy_mode = policy_mode
        logger.info(
            "ContextualBandit initialised | "
            f"soft_quadrants={sorted(SOFT_QUADRANTS)}, "
            f"hard_quadrants={sorted(HARD_QUADRANTS)} | "
            f"policy_mode={policy_mode} | "
            f"reward_tracker={'active' if reward_tracker else 'disabled (heuristic mode)'}"
        )

    # ── Public API ───────────────────────────────────────────────────

    def get_best_action(
        self,
        customer: CustomerState,
        allowed_channels: List[Channel],
    ) -> NBAOutput:
        quadrant = customer.current_quadrant

        logger.debug(
            f"Bandit evaluating {customer.cust_info_id} | "
            f"quadrant={quadrant}, mode={self.policy_mode}, "
            f"allowed_channels={[c.value for c in allowed_channels]}"
        )

        treatment = self._select_treatment(quadrant)
        heuristic_channel, heuristic_alternatives = self._heuristic_pick(
            customer, allowed_channels
        )

        if self.policy_mode == "HEURISTIC" or not allowed_channels:
            return self._build_output(
                customer,
                heuristic_channel,
                treatment,
                heuristic_alternatives,
                decision_reason=self._build_decision_reason(
                    quadrant, heuristic_channel, treatment
                ),
            )

        linucb_result = self._linucb_pick(customer, allowed_channels)

        if linucb_result is None:
            # RewardTracker unavailable/not ready/errored — degrade to the
            # heuristic for this customer rather than fail the batch.
            return self._build_output(
                customer,
                heuristic_channel,
                treatment,
                heuristic_alternatives,
                decision_reason=self._build_decision_reason(
                    quadrant, heuristic_channel, treatment
                ),
            )

        linucb_channel, linucb_score, linucb_alternatives = linucb_result

        if self.policy_mode == "SHADOW":
            decision_reason = (
                f"{self._build_decision_reason(quadrant, heuristic_channel, treatment)}"
                f"|SHADOW_RL_PICK:{linucb_channel.upper().replace(' ', '_')}"
                f"(score={linucb_score:.2f})"
            )
            return self._build_output(
                customer,
                heuristic_channel,
                treatment,
                heuristic_alternatives,
                decision_reason,
            )

        # LIVE
        return self._build_output(
            customer,
            linucb_channel,
            treatment,
            linucb_alternatives,
            decision_reason=self._build_rl_decision_reason(
                quadrant, linucb_channel, treatment
            ),
        )

    # ── Heuristic policy (HEURISTIC mode, and SHADOW's acting policy) ──

    def _heuristic_pick(
        self,
        customer: CustomerState,
        allowed_channels: List[Channel],
    ) -> tuple[str, List[ScoredAlternative]]:
        """Today's static scoring — unchanged since before Phase 3."""
        quadrant = customer.current_quadrant
        best_channel = "None"
        best_score = -1

        # Extract behavioral flags
        has_evasion = any(
            s.title in ("Contact Failure", "Evasive Pattern")
            for s in customer.behavioral_signals
        )
        has_liquidity_crisis = any(
            s.title in ("Payment Rejections", "Liquidity Disruption")
            for s in customer.behavioral_signals
        )

        scored_alternatives: List[ScoredAlternative] = []
        for channel in allowed_channels:
            score, reasoning = self._score_channel(
                channel, quadrant, has_evasion, has_liquidity_crisis
            )
            is_better = (
                score > best_score
                if quadrant in SOFT_QUADRANTS
                else score >= best_score
            )
            if is_better:
                best_score = score
                best_channel = channel.value
            scored_alternatives.append(
                ScoredAlternative(
                    channel=channel.value,
                    score=score,
                    is_selected=False,
                    reasoning=reasoning,
                )
            )

        for alt in scored_alternatives:
            if alt.channel == best_channel:
                alt.is_selected = True

        scored_alternatives.sort(key=lambda a: a.score, reverse=True)
        return best_channel, scored_alternatives

    def _score_channel(
        self,
        channel: Channel,
        quadrant: str,
        has_evasion: bool,
        has_liquidity_crisis: bool,
    ) -> tuple[int, str]:
        """Heuristic scoring for each channel.

        Also used, unmodified, as the cold-start prior source for the
        LinUCB RewardTracker (docs sec 6.3) — RewardTracker.seed_and_refresh()
        is handed this method as a callable so its cold-start beliefs
        start wherever this heuristic already believes.
        """
        cost_idx = CHANNEL_COST[channel]  # 1 to 5
        base_score = 50
        reasoning = ""

        if quadrant in SOFT_QUADRANTS:
            # Prefer cheaper channels (Email, SMS)
            base_score += (6 - cost_idx) * 10
            if quadrant == "Q1":
                reasoning = (
                    f"Low risk quadrant ({quadrant}). Soft touch approach preferred."
                )
            else:
                reasoning = (
                    f"Vulnerable quadrant ({quadrant}). High willingness warrants soft touch / restructuring approach."
                )
            if channel == Channel.FIELD_VISIT:
                base_score -= 40
                reasoning = f"Field visit is overly aggressive for {quadrant}."
        else:
            # Prefer aggressive channels (Field Visit, Letter, Call)
            base_score += cost_idx * 10
            reasoning = f"High risk quadrant ({quadrant}). Escalation required."

        if has_evasion:
            if channel in (Channel.SMS, Channel.EMAIL):
                base_score -= 30
                reasoning = "Message read-rate dropped/unanswered calls. Likely deliberate avoidance."
            elif channel == Channel.FIELD_VISIT:
                base_score += 35
                reasoning = "High contact avoidance detected. Physical presence breaks evasion pattern."

        if has_liquidity_crisis:
            if channel == Channel.OUTGOING_CALL:
                base_score += 20
                reasoning = "Liquidity crisis detected. Direct conversation needed to negotiate restructuring."

        # Ensure bounds
        final_score = max(0, min(100, base_score))
        return final_score, reasoning

    # ── LinUCB policy (SHADOW comparison, LIVE acting policy) ──────────

    def _linucb_pick(
        self,
        customer: CustomerState,
        allowed_channels: List[Channel],
    ) -> Optional[tuple[str, float, List[ScoredAlternative]]]:
        """Returns (best_channel, best_raw_score, scored_alternatives) or
        None if the RewardTracker is unavailable/not ready/errors — the
        caller degrades to the heuristic in that case."""
        if self.reward_tracker is None or not getattr(
            self.reward_tracker, "is_ready", False
        ):
            return None

        try:
            raw_scores = self.reward_tracker.score_channels(customer, allowed_channels)
        except Exception as exc:
            logger.error(
                f"RewardTracker.score_channels failed for {customer.cust_info_id}: {exc}. Falling back to heuristic."
            )
            return None

        if not raw_scores:
            return None

        best_channel = max(raw_scores, key=raw_scores.get)
        best_raw_score = raw_scores[best_channel]

        # Rescale to ScoredAlternative's 0-100 contract, min-max within
        # this customer's evaluated set (LinUCB's raw UCB scores are
        # unbounded reals, unlike the heuristic's already-0-100 scale).
        values = list(raw_scores.values())
        lo, hi = min(values), max(values)
        spread = hi - lo

        scored_alternatives: List[ScoredAlternative] = []
        for channel_value, raw in raw_scores.items():
            score_100 = 50 if spread == 0 else round(100 * (raw - lo) / spread)
            scored_alternatives.append(
                ScoredAlternative(
                    channel=channel_value,
                    score=int(max(0, min(100, score_100))),
                    is_selected=(channel_value == best_channel),
                    reasoning=f"LinUCB score={raw:.3f} (n={self.reward_tracker.sample_count(channel_value)} real obs.)",
                )
            )
        scored_alternatives.sort(key=lambda a: a.score, reverse=True)

        return best_channel, best_raw_score, scored_alternatives

    # ── Treatment Selection (unchanged in every mode) ──────────────────

    def _select_treatment(self, quadrant: str) -> str:
        mapping: dict[str, Treatment] = {
            "Q1": Treatment.PTP,
            "Q2": Treatment.SCHEDULING,
            "Q3": Treatment.PTP,
            "Q4": Treatment.PARTIAL_PAYMENT,
        }
        if quadrant not in mapping:
            raise ValueError(f"Unrecognised quadrant '{quadrant}'.")
        return mapping[quadrant].value

    # ── Output / Decision Reason Builders ──────────────────────────────

    def _build_output(
        self,
        customer: CustomerState,
        channel: str,
        treatment: str,
        scored_alternatives: List[ScoredAlternative],
        decision_reason: str,
    ) -> NBAOutput:
        logger.debug(
            f"Bandit decision for {customer.cust_info_id}: "
            f"channel={channel!r}, treatment={treatment!r} | {decision_reason}"
        )
        return NBAOutput(
            cust_info_id=customer.cust_info_id,
            recommended_channel=channel,
            recommended_treatment=treatment,
            decision_reason=decision_reason,
            scored_alternatives=scored_alternatives,
        )

    def _build_decision_reason(
        self, quadrant: str, channel: str, treatment: str
    ) -> str:
        policy_label = "SOFT_TOUCH" if quadrant in SOFT_QUADRANTS else "ESCALATION"
        channel_label = (
            channel.upper().replace(" ", "_") if channel != "None" else "NO_CHANNEL"
        )
        treatment_label = treatment.upper().replace(" ", "_")
        return f"BANDIT:{quadrant}|{policy_label}|{channel_label}|{treatment_label}"

    def _build_rl_decision_reason(
        self, quadrant: str, channel: str, treatment: str
    ) -> str:
        channel_label = (
            channel.upper().replace(" ", "_") if channel != "None" else "NO_CHANNEL"
        )
        treatment_label = treatment.upper().replace(" ", "_")
        return f"RL:{quadrant}|LINUCB|{channel_label}|{treatment_label}"
