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
            ├── _select_treatment(quadrant)   → Treatment heuristic
            └── _select_channel(allowed, quadrant) → Channel policy
            │
            ▼
        NBAOutput  →  downstream DB persistence

Design Philosophy:
    The current implementation is a **Heuristic Baseline** — a
    deterministic policy that encodes expert domain knowledge about
    customer quadrant behaviour. This baseline serves two purposes:

    1. **Immediate value:** Produces sensible recommendations from
       day one, before any feedback data is collected.

    2. **RL scaffolding:** The architecture is deliberately structured
       to be replaced by a true contextual bandit (e.g., LinUCB or
       Thompson Sampling) once the ``RewardTracker`` accumulates
       sufficient interaction history (typically 30–90 days of
       scored customers with outcome labels).

Isolation Guarantee:
    This module is fully decoupled from ``guardrails.py``. It only
    knows about the schemas from ``.schemas`` and the pre-filtered
    ``allowed_channels`` list it receives. It has no knowledge of
    what was removed or why.
"""

from __future__ import annotations

from typing import Final, List

from src.core.logger import get_logger
from src.engine.nba.schemas import Channel, CustomerState, NBAOutput, Treatment

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Channel Cost Hierarchy — Aggressiveness Index
# ═══════════════════════════════════════════════════════════════════════

# Maps each channel to an integer "cost score". Lower = cheaper and
# less intrusive; higher = more expensive and more aggressive.
# Used by _select_channel to implement the Q1/Q2 (soft) vs Q3/Q4
# (hard) selection policy without nested conditionals.
CHANNEL_COST: Final[dict[Channel, int]] = {
    Channel.EMAIL:          1,
    Channel.SMS:            2,
    Channel.OUTGOING_CALL:  3,
    Channel.DUNNING_LETTER: 4,
    Channel.FIELD_VISIT:    5,
}

# Quadrants that receive a "soft-touch" (cheapest) channel approach.
SOFT_QUADRANTS: Final[frozenset[str]] = frozenset({"Q1", "Q2"})

# Quadrants that receive an "escalation" (most aggressive) approach.
HARD_QUADRANTS: Final[frozenset[str]] = frozenset({"Q3", "Q4"})


# ═══════════════════════════════════════════════════════════════════════
#  RewardTracker — Phase 3 Stub
# ═══════════════════════════════════════════════════════════════════════

class RewardTracker:
    """Stub for the Phase 3 feedback loop and online learning system.

    **Current State:** Empty placeholder. Do not use in production yet.

    **Future Responsibility (Phase 3):**
    This class will be responsible for closing the Reinforcement
    Learning loop. Once the NBA pipeline has been running for 30–90
    days, it will:

    - Ingest action-outcome pairs from the DWH
      (e.g., ``CUST_INFO_ID``, ``recommended_channel``,
      ``recommended_treatment``, ``outcome_flag`` where 1 = payment
      received / PTP kept, 0 = no engagement).
    - Maintain per-arm (channel × treatment × quadrant) success-rate
      estimates using Thompson Sampling or LinUCB.
    - Expose an ``get_arm_weights(quadrant)`` method that the
      ``ContextualBandit`` will call instead of the static heuristic,
      allowing the system to shift recommendations towards actions
      that empirically generate the highest collection rate.
    - Support cold-start via the current heuristic baseline as a
      prior, so the bandit starts with informed beliefs rather than
      uniform priors.

    **Integration Point:**
    ``ContextualBandit.__init__`` accepts an optional
    ``RewardTracker`` instance. When Phase 3 is implemented, wire it
    in there — no other code changes will be required.
    """

    pass


# ═══════════════════════════════════════════════════════════════════════
#  Contextual Bandit — Core Decision Engine
# ═══════════════════════════════════════════════════════════════════════

class ContextualBandit:
    """Selects the optimal (channel, treatment) pair for a given customer.

    Implements a **Scoring Heuristic Baseline policy** using domain knowledge
    about customer quadrant behaviour and behavioral signals.
    """

    def __init__(
        self, reward_tracker: RewardTracker | None = None
    ) -> None:
        self.reward_tracker: RewardTracker | None = reward_tracker
        logger.info(
            "ContextualBandit initialised | "
            f"soft_quadrants={sorted(SOFT_QUADRANTS)}, "
            f"hard_quadrants={sorted(HARD_QUADRANTS)} | "
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
            f"quadrant={quadrant}, "
            f"allowed_channels={[c.value for c in allowed_channels]}"
        )

        treatment = self._select_treatment(quadrant)
        
        from src.engine.nba.schemas import ScoredAlternative
        scored_alternatives: List[ScoredAlternative] = []
        best_channel = "None"
        best_score = -1
        best_reason = ""

        # Extract behavioral flags
        has_evasion = any(s.title in ("Contact Failure", "Evasive Pattern") for s in customer.behavioral_signals)
        has_liquidity_crisis = any(s.title in ("Payment Rejections", "Liquidity Disruption") for s in customer.behavioral_signals)

        for channel in allowed_channels:
            score, reasoning = self._score_channel(channel, quadrant, has_evasion, has_liquidity_crisis)
            if score > best_score:
                best_score = score
                best_channel = channel.value
                best_reason = reasoning

        # Build ScoredAlternative list
        for channel in allowed_channels:
            score, reasoning = self._score_channel(channel, quadrant, has_evasion, has_liquidity_crisis)
            is_selected = (channel.value == best_channel)
            scored_alternatives.append(ScoredAlternative(
                channel=channel.value,
                score=score,
                is_selected=is_selected,
                reasoning=reasoning
            ))

        # Sort by score descending
        scored_alternatives.sort(key=lambda x: x.score, reverse=True)

        reason_code = self._build_reason_code(quadrant, best_channel, treatment)

        logger.debug(
            f"Bandit decision for {customer.cust_info_id}: "
            f"channel={best_channel!r}, treatment={treatment!r} | {reason_code}"
        )

        return NBAOutput(
            cust_info_id=customer.cust_info_id,
            recommended_channel=best_channel,
            recommended_treatment=treatment,
            reason_code=reason_code,
            scored_alternatives=scored_alternatives
        )

    def _score_channel(self, channel: Channel, quadrant: str, has_evasion: bool, has_liquidity_crisis: bool) -> tuple[int, str]:
        """Heuristic scoring for each channel."""
        cost_idx = CHANNEL_COST[channel]  # 1 to 5
        base_score = 50
        reasoning = ""

        if quadrant in SOFT_QUADRANTS:
            # Prefer cheaper channels (Email, SMS)
            base_score += (6 - cost_idx) * 10
            reasoning = f"Low risk quadrant ({quadrant}). Soft touch approach preferred."
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

    # ── Treatment Selection ──────────────────────────────────────────

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

    # ── Reason Code Builder ──────────────────────────────────────────

    def _build_reason_code(
        self, quadrant: str, channel: str, treatment: str
    ) -> str:
        policy_label = "SOFT_TOUCH" if quadrant in SOFT_QUADRANTS else "ESCALATION"
        channel_label = channel.upper().replace(" ", "_") if channel != "None" else "NO_CHANNEL"
        treatment_label = treatment.upper().replace(" ", "_")
        return f"BANDIT:{quadrant}|{policy_label}|{channel_label}|{treatment_label}"
