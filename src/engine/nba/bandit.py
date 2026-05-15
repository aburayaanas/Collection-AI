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

    Implements a **Heuristic Baseline policy** using domain knowledge
    about customer quadrant behaviour:

    - **Q1** (High Willingness, High Ability): Customer wants to pay
      and can. Use the cheapest nudge — a gentle reminder suffices.
      Offer a PTP to formalise the commitment.

    - **Q2** (High Willingness, Low Ability): Customer wants to pay
      but genuinely cannot. Use a soft channel. Offer a Scheduling
      or Restructuring plan to make payment feasible.

    - **Q3** (Low Willingness, High Ability): Customer can pay but
      is disengaged or resistant. Escalate channel aggressiveness
      to create urgency. Offer a PTP to re-establish commitment.

    - **Q4** (Low Willingness, Low Ability): Highest risk. Escalate
      to the most aggressive available channel. Offer a Partial
      Payment as a realistic near-term target.

    Attributes:
        reward_tracker (RewardTracker | None): Optional Phase 3
            feedback component. Currently unused; reserved for the
            online RL implementation.

    Example:
        >>> bandit = ContextualBandit()
        >>> output = bandit.get_best_action(customer, allowed_channels)
        >>> print(output.recommended_channel, output.recommended_treatment)
        Email PTP
    """

    def __init__(
        self, reward_tracker: RewardTracker | None = None
    ) -> None:
        """Initialise the bandit with the channel cost hierarchy.

        Args:
            reward_tracker (RewardTracker | None): Optional Phase 3
                feedback tracker. Pass ``None`` (default) to use the
                pure heuristic baseline. When Phase 3 is ready,
                inject a populated ``RewardTracker`` instance here
                without changing any downstream code.
        """
        self.reward_tracker: RewardTracker | None = reward_tracker

        # Ordered lists are derived once at init for O(1) lookups at
        # scoring time — avoids re-sorting on every customer.
        self._channels_cheapest_first: Final[list[Channel]] = sorted(
            CHANNEL_COST, key=lambda c: CHANNEL_COST[c]
        )
        self._channels_costliest_first: Final[list[Channel]] = sorted(
            CHANNEL_COST, key=lambda c: CHANNEL_COST[c], reverse=True
        )

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
        """Select the optimal (channel, treatment) pair for a customer.

        This is the single public entry point for the bandit. It
        orchestrates treatment and channel selection and assembles
        the final ``NBAOutput`` with a structured audit reason code.

        Args:
            customer (CustomerState): The customer's current state.
                Used to read ``current_quadrant`` and
                ``cust_info_id``. Must have passed guardrail
                evaluation before being passed here.
            allowed_channels (List[Channel]): The legally-permissible
                channels returned by ``RuleEngine.evaluate()``. The
                bandit MUST NOT add channels back; it can only choose
                from this pre-filtered list.

        Returns:
            NBAOutput: A fully validated, immutable recommendation
                payload ready for DB persistence. ``recommended_channel``
                will be ``"None"`` if ``allowed_channels`` is empty.

        Raises:
            ValueError: If ``customer.current_quadrant`` is not one of
                Q1–Q4 (enforced upstream by Pydantic, but re-validated
                here for defence-in-depth).
        """
        quadrant = customer.current_quadrant

        logger.debug(
            f"Bandit evaluating {customer.cust_info_id} | "
            f"quadrant={quadrant}, "
            f"allowed_channels={[c.value for c in allowed_channels]}"
        )

        treatment = self._select_treatment(quadrant)
        channel = self._select_channel(allowed_channels, quadrant)

        reason_code = self._build_reason_code(quadrant, channel, treatment)

        logger.debug(
            f"Bandit decision for {customer.cust_info_id}: "
            f"channel={channel!r}, treatment={treatment!r} | {reason_code}"
        )

        return NBAOutput(
            cust_info_id=customer.cust_info_id,
            recommended_channel=channel,
            recommended_treatment=treatment,
            reason_code=reason_code,
        )

    # ── Treatment Selection ──────────────────────────────────────────

    def _select_treatment(self, quadrant: str) -> str:
        """Map a customer quadrant to the most appropriate treatment.

        The mapping encodes expert collection strategy knowledge.
        Q1 and Q3 receive PTP (the lighter commitment); Q2 receives
        a Scheduling plan (financial relief); Q4 receives a Partial
        Payment offer (realistic for high-risk customers).

        Args:
            quadrant (str): One of "Q1", "Q2", "Q3", "Q4".

        Returns:
            str: The ``Treatment`` enum value string to include in
                the ``NBAOutput`` payload.

        Raises:
            ValueError: If ``quadrant`` is not a recognised value.
                Under normal operation this cannot occur because
                ``CustomerState`` is Pydantic-validated upstream.
        """
        mapping: Final[dict[str, Treatment]] = {
            "Q1": Treatment.PTP,
            "Q2": Treatment.SCHEDULING,
            "Q3": Treatment.PTP,
            "Q4": Treatment.PARTIAL_PAYMENT,
        }

        if quadrant not in mapping:
            raise ValueError(
                f"Unrecognised quadrant '{quadrant}'. "
                f"Expected one of {list(mapping.keys())}."
            )

        selected = mapping[quadrant]
        logger.debug(f"Treatment selected: {selected.value} (quadrant={quadrant})")
        return selected.value

    # ── Channel Selection ────────────────────────────────────────────

    def _select_channel(
        self, allowed_channels: List[Channel], quadrant: str
    ) -> str:
        """Select the optimal channel from the legally-allowed list.

        Applies a two-policy approach based on the customer's quadrant:

        - **Soft policy** (Q1, Q2): Select the **cheapest / least
          intrusive** channel. These customers are already engaged or
          willing, so a gentle nudge is sufficient and avoids
          unnecessary escalation costs.

        - **Hard policy** (Q3, Q4): Select the **most aggressive**
          channel available. These customers require stronger prompts
          to generate a response. The guardrails have already ensured
          this escalation is legally and regulatorily permissible.

        Args:
            allowed_channels (List[Channel]): The pre-filtered list
                from ``RuleEngine``. This method must never add
                channels that are not in this list.
            quadrant (str): One of "Q1", "Q2", "Q3", "Q4". Determines
                which selection policy to apply.

        Returns:
            str: The ``Channel`` enum value string, or ``"None"`` if
                ``allowed_channels`` is empty (no contact today).
        """
        if not allowed_channels:
            logger.warning(
                f"No allowed channels for quadrant={quadrant}. "
                f"Returning 'None' — no outreach today."
            )
            return "None"

        # Build a lookup set for O(1) membership check
        allowed_set: frozenset[Channel] = frozenset(allowed_channels)

        if quadrant in SOFT_QUADRANTS:
            # Pick cheapest channel from the ordered list
            for channel in self._channels_cheapest_first:
                if channel in allowed_set:
                    logger.debug(
                        f"Soft policy ({quadrant}): "
                        f"cheapest available = {channel.value}"
                    )
                    return channel.value

        if quadrant in HARD_QUADRANTS:
            # Pick most aggressive channel from the ordered list
            for channel in self._channels_costliest_first:
                if channel in allowed_set:
                    logger.debug(
                        f"Hard policy ({quadrant}): "
                        f"most aggressive available = {channel.value}"
                    )
                    return channel.value

        # Fallback: should be unreachable with valid quadrant values
        raise ValueError(
            f"Unrecognised quadrant '{quadrant}'. "
            f"Cannot apply channel selection policy."
        )

    # ── Reason Code Builder ──────────────────────────────────────────

    def _build_reason_code(
        self, quadrant: str, channel: str, treatment: str
    ) -> str:
        """Construct a structured audit reason code for the decision.

        Format: ``BANDIT:<quadrant>|<policy>|<channel>|<treatment>``

        Examples:
            ``BANDIT:Q1|SOFT_TOUCH|Email|PTP``
            ``BANDIT:Q4|ESCALATION|Field Visit|Partial Payment``
            ``BANDIT:Q2|SOFT_TOUCH|NO_CHANNEL|Scheduling and Structuring``

        Args:
            quadrant (str): Customer quadrant (Q1–Q4).
            channel (str): Selected channel value or ``"None"``.
            treatment (str): Selected treatment value.

        Returns:
            str: A pipe-delimited audit string suitable for storage in
                ``NBAOutput.reason_code`` and regulatory reporting.
        """
        policy_label = "SOFT_TOUCH" if quadrant in SOFT_QUADRANTS else "ESCALATION"
        channel_label = channel.upper().replace(" ", "_") if channel != "None" else "NO_CHANNEL"
        treatment_label = treatment.upper().replace(" ", "_")

        reason = (
            f"BANDIT:{quadrant}|{policy_label}|{channel_label}|{treatment_label}"
        )
        return reason
