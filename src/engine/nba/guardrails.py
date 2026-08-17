"""
NBA Engine — Deterministic Compliance Guardrails.

This module implements the hard regulatory and business constraints
that MUST be applied before any ML-based action selection (Bandit).
No recommendation may bypass these filters.

Architecture:
    CustomerState ──► RuleEngine.evaluate() ──► GuardrailResult
                          │
                          ├── Filter 1: Exclusion check (Deceased, Legal, …)
                          └── Filter 2: Channel ceiling pruning (SMS cap, call cap, …)

The output is a reduced action space representing the legally
permissible channels for a specific customer on a specific day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, List, Optional

from src.core.logger import get_logger
from src.engine.nba.schemas import (
    AccountStatus,
    Channel,
    CustomerState,
    NBAOutput,
    Treatment,
)

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Configuration — Dynamic Compliance Limits
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CollectionGuardrails:
    """Dynamic compliance limits for outbound collection actions.

    These values are typically sourced from the central bank's
    consumer protection guidelines and the institution's internal
    collection policy. They can be overridden per-institution via
    environment variables or a configuration table.

    Attributes:
        max_sms_per_week (int): Maximum SMS messages allowed per
            customer per rolling 7-day window. Exceeding this
            threshold constitutes regulatory harassment.
        max_calls_per_day (int): Maximum outbound call attempts per
            customer per calendar day. Central bank mandate.
        min_due_for_field_visit (float): Minimum outstanding balance
            to justify the cost and intrusiveness of a field visit.
            Below this threshold, field visits are not cost-effective
            and may be considered disproportionate.
        min_due_for_dunning_letter (float): Minimum balance to
            trigger a formal dunning letter. Letters carry legal
            implications and should not be sent for trivial amounts.
    """

    max_sms_per_week: int = 3
    max_calls_per_day: int = 1
    min_due_for_field_visit: float = 5_000.0
    min_due_for_dunning_letter: float = 500.0


# ═══════════════════════════════════════════════════════════════════════
#  Excluded Statuses — Immediate Halt Set
# ═══════════════════════════════════════════════════════════════════════

EXCLUDED_STATUSES: Final[frozenset[str]] = frozenset({
    AccountStatus.DECEASED.value,
    AccountStatus.DISEASE.value,
    AccountStatus.LEGAL.value,
    AccountStatus.TRANSFER_TO_REMEDIAL.value,
})
"""Account statuses that trigger immediate exclusion from all
standard collection actions. These customers must be routed to
specialized handling teams and MUST NOT receive automated outreach."""


# ═══════════════════════════════════════════════════════════════════════
#  Guardrail Result — Output of the Rule Engine
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class GuardrailResult:
    """Outcome of the compliance filter pipeline.

    Attributes:
        is_excluded (bool): True if the customer is excluded from
            all standard collection channels. When True, the Bandit
            MUST NOT run; use the pre-built NBAOutput instead.
        allowed_channels (List[Channel]): The dynamically pruned
            list of channels that remain legally permissible for
            this customer today. Empty list if excluded.
        exclusion_output (Optional[NBAOutput]): Pre-built output
            for excluded customers. None if the customer is eligible
            for standard treatment.
        applied_rules (List[str]): Audit trail of every rule that
            fired during evaluation. Logged and persisted for
            regulatory review.
    """

    is_excluded: bool
    allowed_channels: List[Channel] = field(default_factory=list)
    exclusion_output: Optional[NBAOutput] = None
    applied_rules: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
#  Rule Engine — Deterministic Compliance Filter
# ═══════════════════════════════════════════════════════════════════════

class RuleEngine:
    """Applies deterministic compliance filters to a customer state.

    The engine runs two sequential filter stages:

    1. **Exclusion Check** — Certain account statuses (Deceased,
       Disease, Legal, Transfer To Remedial) immediately halt all
       collection activity and produce a Special Handling output.

    2. **Channel Ceiling Pruning** — For eligible customers, each
       channel is tested against regulatory limits. Channels that
       violate a ceiling are removed from the action space.

    The output is a ``GuardrailResult`` containing the reduced set
    of permissible channels and a full audit trail of fired rules.

    Usage:
        >>> engine = RuleEngine()
        >>> result = engine.evaluate(customer_state)
        >>> if result.is_excluded:
        ...     persist(result.exclusion_output)
        ... else:
        ...     bandit_input = result.allowed_channels

    Attributes:
        config (CollectionGuardrails): The compliance limits used
            for channel ceiling evaluation. Injected at construction
            to support per-institution overrides.
    """

    def __init__(self, config: Optional[CollectionGuardrails] = None) -> None:
        """Initialize the Rule Engine with compliance configuration.

        Args:
            config (Optional[CollectionGuardrails]): Compliance limits.
                Defaults to standard bank policy if not provided.
                Injected via constructor to enable per-institution
                overrides and testability.
        """
        self.config: Final[CollectionGuardrails] = config or CollectionGuardrails()
        logger.info(
            f"RuleEngine initialized | "
            f"SMS cap={self.config.max_sms_per_week}/wk, "
            f"Call cap={self.config.max_calls_per_day}/day, "
            f"Field visit floor={self.config.min_due_for_field_visit:,.0f}, "
            f"Dunning floor={self.config.min_due_for_dunning_letter:,.0f}"
        )

    # ── Public API ───────────────────────────────────────────────────

    def evaluate(self, customer: CustomerState) -> GuardrailResult:
        """Run the full compliance filter pipeline for a single customer.

        Applies filters sequentially: exclusion check first, then
        channel ceiling pruning. Short-circuits on exclusion.

        Args:
            customer (CustomerState): Immutable snapshot of the
                customer's current state. Must be fully populated;
                missing fields will raise Pydantic validation errors
                at construction time.

        Returns:
            GuardrailResult: Contains the pruned channel list, an
                optional pre-built exclusion output, and the full
                audit trail of fired rules.
        """
        logger.debug(
            f"Evaluating guardrails for {customer.cust_info_id} | "
            f"status={customer.account_status}, "
            f"quadrant={customer.current_quadrant}, "
            f"due={customer.total_due:,.2f}"
        )

        # ── Filter 1: Exclusion Check ────────────────────────────────
        exclusion_result = self._check_exclusions(customer)
        if exclusion_result is not None:
            return exclusion_result

        # ── Filter 2: Channel Ceiling Pruning ────────────────────────
        return self._prune_channels(customer)

    # ── Filter 1: Exclusion Check ────────────────────────────────────

    def _check_exclusions(
        self, customer: CustomerState
    ) -> Optional[GuardrailResult]:
        """Check if the customer must be excluded from all standard actions.

        Args:
            customer (CustomerState): The customer state to evaluate.

        Returns:
            Optional[GuardrailResult]: A fully-built exclusion result
                if the customer is excluded, or None if the customer
                passes the exclusion check and should proceed to
                channel pruning.
        """
        if customer.account_status not in EXCLUDED_STATUSES:
            return None

        reason = f"EXCLUDED:{customer.account_status.upper().replace(' ', '_')}"

        logger.debug(
            f"Customer {customer.cust_info_id} excluded | "
            f"status='{customer.account_status}' -> {reason}"
        )

        output = NBAOutput(
            cust_info_id=customer.cust_info_id,
            recommended_channel="None",
            recommended_treatment=Treatment.SPECIAL_HANDLING.value,
            decision_reason=reason,
        )

        return GuardrailResult(
            is_excluded=True,
            allowed_channels=[],
            exclusion_output=output,
            applied_rules=[reason],
        )

    # ── Filter 2: Channel Ceiling Pruning ────────────────────────────

    def _prune_channels(self, customer: CustomerState) -> GuardrailResult:
        """Dynamically prune channels that violate compliance ceilings.

        Each channel is independently tested against the relevant
        ceiling. A channel is removed if any of its constraints are
        violated. The surviving channels form the legal action space
        for the downstream Bandit.

        Args:
            customer (CustomerState): The customer state to evaluate.
                Must have passed the exclusion check.

        Returns:
            GuardrailResult: Contains the reduced channel list and
                the audit trail of every rule that fired.
        """
        allowed: List[Channel] = []
        fired_rules: List[str] = []

        for channel in Channel:
            blocked, rule = self._evaluate_channel(channel, customer)
            if blocked:
                fired_rules.append(rule)
                logger.debug(
                    f"  {channel.value} blocked for "
                    f"{customer.cust_info_id}: {rule}"
                )
            else:
                allowed.append(channel)

        logger.debug(
            f"Customer {customer.cust_info_id} | "
            f"allowed={[c.value for c in allowed]} | "
            f"rules_fired={len(fired_rules)}"
        )

        return GuardrailResult(
            is_excluded=False,
            allowed_channels=allowed,
            exclusion_output=None,
            applied_rules=fired_rules,
        )

    def _evaluate_channel(
        self, channel: Channel, customer: CustomerState
    ) -> tuple[bool, str]:
        """Test a single channel against its compliance constraints.

        Args:
            channel (Channel): The channel to evaluate.
            customer (CustomerState): The customer's current state.

        Returns:
            tuple[bool, str]: A (is_blocked, rule_description) pair.
                is_blocked is True if the channel violates a ceiling.
                rule_description is a human-readable audit string
                (empty if not blocked).
        """
        if channel == Channel.SMS:
            if customer.sms_sent_this_week >= self.config.max_sms_per_week:
                return True, (
                    f"CEILING:SMS_WEEKLY|"
                    f"sent={customer.sms_sent_this_week}/"
                    f"max={self.config.max_sms_per_week}"
                )

        elif channel == Channel.OUTGOING_CALL:
            if customer.calls_made_today >= self.config.max_calls_per_day:
                return True, (
                    f"CEILING:CALL_DAILY|"
                    f"made={customer.calls_made_today}/"
                    f"max={self.config.max_calls_per_day}"
                )

        elif channel == Channel.FIELD_VISIT:
            if customer.total_due < self.config.min_due_for_field_visit:
                return True, (
                    f"CEILING:FIELD_VISIT_MIN_DUE|"
                    f"due={customer.total_due:,.2f}/"
                    f"min={self.config.min_due_for_field_visit:,.2f}"
                )

        elif channel == Channel.DUNNING_LETTER:
            if customer.total_due < self.config.min_due_for_dunning_letter:
                return True, (
                    f"CEILING:DUNNING_MIN_DUE|"
                    f"due={customer.total_due:,.2f}/"
                    f"min={self.config.min_due_for_dunning_letter:,.2f}"
                )

        # EMAIL has no ceiling — always allowed for eligible customers
        return False, ""


# ═══════════════════════════════════════════════════════════════════════
#  Financial Guardrails — Block 5 boundaries calculation
# ═══════════════════════════════════════════════════════════════════════

class FinancialGuardrails:
    """Calculates strict negotiation boundaries and expected financial recovery for Collection Cockpit."""

    @staticmethod
    def calculate_boundaries(customer_data: dict, hypothesis_signal: bool) -> dict:
        """Calculate negotiation limits and empathetic sensitivity flags.

        Args:
            customer_data (dict): Raw or normalized customer attributes.
            hypothesis_signal (bool): True if 'Liquidity Disruption' or similar crisis detected.

        Returns:
            dict: Structured negotiation boundaries and sensitivity guidelines.
        """
        # Support case-insensitive key extraction
        normalised = {k.lower(): v for k, v in customer_data.items()}

        current_arrears = float(normalised.get("current_arrears_jod") or normalised.get("total_due") or 0.0)
        accrued_interest = float(normalised.get("accrued_interest_jod") or 0.0)
        segment = str(normalised.get("customer_segment") or normalised.get("segment") or "Mass retail")

        # minimum_acceptable_cash: 30% of CURRENT_ARREARS_JOD
        minimum_acceptable_cash = round(current_arrears * 0.30, 2)

        # max_restructuring_term_months: Based on segment (e.g., 18 months for Retail, 24 months for Wealth)
        if "wealth" in segment.lower():
            max_restructuring_term_months = 24
        else:
            max_restructuring_term_months = 18

        # interest_waiver_authority: 15% of ACCRUED_INTEREST_JOD without senior approval
        interest_waiver_authority = round(accrued_interest * 0.15, 2)

        # late_fee_waiver: 100% pre-approved
        late_fee_waiver = "100% pre-approved"

        # Sensitivity Flag Check
        sensitivity_flag = None
        if hypothesis_signal:
            sensitivity_flag = "Liquidity-crisis hypothesis warrants an empathetic, solution-first approach. Agent authorized to offer 30-day full payment moratorium without escalation."

        return {
            "minimum_acceptable_cash": minimum_acceptable_cash,
            "max_restructuring_term_months": max_restructuring_term_months,
            "interest_waiver_authority": interest_waiver_authority,
            "late_fee_waiver": late_fee_waiver,
            "sensitivity_flag": sensitivity_flag,
        }

