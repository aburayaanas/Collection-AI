"""
NBA Engine — Domain Schemas.

Pydantic models that define the contract between the Rule Engine,
the Bandit, and the downstream database persistence layer.

All models are immutable (frozen) to guarantee thread-safety in
batch scoring and to prevent accidental mutation during pipeline
traversal.
"""

from __future__ import annotations

from enum import Enum
from typing import Final, List, Literal, Optional, Any   # noqa: F401

from pydantic import BaseModel, Field, field_validator  # noqa: F401


# ═══════════════════════════════════════════════════════════════════════
#  Enumerations — Channel & Treatment Taxonomy
# ═══════════════════════════════════════════════════════════════════════

class Channel(str, Enum):
    """Available outbound communication channels.

    Each value maps 1:1 to the bank's PIO_COMMUNICATE_TYPE lookup table.
    Ordering reflects escalation intensity (lowest → highest).
    """

    SMS = "SMS"
    EMAIL = "Email"
    OUTGOING_CALL = "Outgoing Call"
    DUNNING_LETTER = "Dunning Letter"
    FIELD_VISIT = "Field Visit"


class Treatment(str, Enum):
    """Treatments the bank can offer to a delinquent customer.

    Ordering reflects concession depth (lightest → heaviest).
    """

    PTP = "PTP"
    SCHEDULING = "Scheduling and Structuring"
    PARTIAL_PAYMENT = "Partial Payment"
    SPECIAL_HANDLING = "Special Handling"


class AccountStatus(str, Enum):
    """Account statuses that trigger special-handling exclusions.

    Values sourced from PIO_COLL.PIO_CUSTOMERS_INFO status lookups.
    """

    ACTIVE = "Active"
    DECEASED = "Deceased"
    DISEASE = "Disease"
    LEGAL = "Legal"
    TRANSFER_TO_REMEDIAL = "Transfer To Remedial"


# ═══════════════════════════════════════════════════════════════════════
#  Customer State — Input to the Rule Engine
# ═══════════════════════════════════════════════════════════════════════

class CustomerState(BaseModel):
    """Snapshot of a customer's current state at scoring time.

    This model is the single source of truth consumed by both the
    deterministic guardrails and the downstream Bandit.

    Attributes:
        cust_info_id (str): Unique customer identifier from
            PIO_COLL.PIO_CUSTOMERS_INFO.ID. Used as the join key
            across all collection tables.
        current_quadrant (Literal["Q1", "Q2", "Q3", "Q4"]): The
            Willingness × Ability quadrant assigned by the Matrix
            Engine. Drives strategy selection downstream.
        account_status (str): Current account lifecycle status.
            Certain values (Deceased, Legal, etc.) trigger immediate
            exclusion from standard collection actions.
        total_due (float): Outstanding balance across all delinquent
            accounts (most-DPD account takes priority). Used to
            gate expensive channels like Field Visit.
        sms_sent_this_week (int): Rolling 7-day SMS count for this
            customer. Enforced against MAX_SMS_PER_WEEK ceiling to
            comply with communication regulations.
        calls_made_today (int): Outbound call attempts made today.
            Enforced against MAX_CALLS_PER_DAY ceiling to prevent
            harassment and comply with central bank guidelines.
        behavioral_signals (List[Any]): List of generated behavioral signals.

    Raises:
        ValueError: If total_due is negative or contact counts are
            negative.
    """

    model_config = {"frozen": True}

    cust_info_id: str = Field(
        ...,
        min_length=1,
        description="Unique customer identifier (PIO_CUSTOMERS_INFO.ID).",
    )
    current_quadrant: Literal["Q1", "Q2", "Q3", "Q4"] = Field(
        ...,
        description="Willingness × Ability quadrant from Matrix Engine.",
    )
    account_status: str = Field(
        ...,
        description="Account lifecycle status from PIO_CUSTOMERS_INFO.",
    )
    total_due: float = Field(
        ...,
        ge=0.0,
        description="Total outstanding balance across delinquent accounts.",
    )
    sms_sent_this_week: int = Field(
        default=0,
        ge=0,
        description="Rolling 7-day SMS count for regulatory ceiling enforcement.",
    )
    calls_made_today: int = Field(
        default=0,
        ge=0,
        description="Outbound call count today for anti-harassment ceiling.",
    )
    behavioral_signals: List[Any] = Field(
        default_factory=list,
        description="List of behavioral signals from the Inference Engine.",
    )

    # ── Phase 3: LinUCB context vector inputs ──────────────────────────
    # Optional with neutral defaults so existing callers (guardrails,
    # manual single-customer tests) that don't supply these keep working
    # unchanged. See docs/phase3_contextual_bandit_rl.md sec 5.2.
    days_past_due: int = Field(default=0, ge=0, description="From PIO_COLL_AI_NBA_CONTEXT_MART.")
    contact_avoidance_index: float = Field(default=0.0, ge=0.0, le=1.0, description="From PIO_COLL_AI_NBA_CONTEXT_MART.")
    days_since_last_rpc: int = Field(default=180, ge=0, description="From PIO_COLL_AI_WILLINGNESS_MART. Defaults to 180 (never contacted).")
    ptp_reliability_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="From PIO_COLL_AI_WILLINGNESS_MART.")
    age: int = Field(default=40, ge=0, description="From PIO_COLL.PIO_CUSTOMERS_INFO. Defaults to 40 (neutral) when unresolved.")
    account_tenure_days: int = Field(default=0, ge=0, description="Days since PIO_COLL_AI_NBA_CONTEXT_MART.ACCOUNT_OPEN_DATE.")

    # ── Channel Response Rates (Factual baseline metrics from CONTEXT_MART) ──
    call_response_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Actual RPC rate from PIO_COLL_AI_NBA_CONTEXT_MART.")
    field_visit_response_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Actual field contact rate from PIO_COLL_AI_NBA_CONTEXT_MART.")
    sms_estimated_response_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Estimated SMS rate from PIO_COLL_AI_NBA_CONTEXT_MART.")
    email_estimated_response_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Estimated Email rate from PIO_COLL_AI_NBA_CONTEXT_MART.")
    letter_estimated_response_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Estimated Letter rate from PIO_COLL_AI_NBA_CONTEXT_MART.")


# ═══════════════════════════════════════════════════════════════════════
#  Action Space — Static Bank Capabilities
# ═══════════════════════════════════════════════════════════════════════

class ActionSpace(BaseModel):
    """Defines the complete set of actions the bank can take.

    This is a static configuration object, loaded once at pipeline
    start. The RuleEngine dynamically prunes it per-customer based
    on compliance constraints.

    Attributes:
        channels (List[Channel]): All outbound channels the bank
            is licensed to use. Ordered by escalation intensity.
        treatments (List[Treatment]): All treatments available.
            Excludes Special Handling (auto-injected by guardrails).
    """

    model_config = {"frozen": True}

    channels: List[Channel] = Field(
        default=[
            Channel.SMS,
            Channel.EMAIL,
            Channel.OUTGOING_CALL,
            Channel.DUNNING_LETTER,
            Channel.FIELD_VISIT,
        ],
        description="Licensed outbound communication channels.",
    )
    treatments: List[Treatment] = Field(
        default=[
            Treatment.PTP,
            Treatment.SCHEDULING,
            Treatment.PARTIAL_PAYMENT,
        ],
        description="Available treatments (excludes Special Handling).",
    )


# ═══════════════════════════════════════════════════════════════════════
#  NBA Output — Final DB Payload
# ═══════════════════════════════════════════════════════════════════════

class ScoredAlternative(BaseModel):
    """Represents a scored channel alternative evaluated by the Bandit."""
    channel: str
    score: int = Field(ge=0, le=100)
    is_selected: bool
    reasoning: str
    response_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Actual or estimated channel response rate.")
    response_rate_type: Optional[str] = Field(default=None, description="'ACTUAL' or 'ESTIMATED'.")


class NBAOutput(BaseModel):
    """Final recommendation payload persisted to the database.

    One record per customer per scoring run. Consumed by the
    downstream agent desktop and reporting dashboards.

    Attributes:
        cust_info_id (str): Customer identifier for the DB join key.
        recommended_channel (str): The single best channel selected
            by the Bandit (or guardrail override). Maps to
            PIO_COMMUNICATE_TYPE.
        recommended_treatment (str): The treatment to apply. Maps to
            PIO_ACTIVITY_DEF action sequences.
        decision_reason (str): Human-readable audit text explaining why
            this action was recommended (e.g., "EXCLUDED:LEGAL",
            "BANDIT:Q1_SMS_PTP"). Used for regulatory reporting
            and model governance.
        scored_alternatives (List[ScoredAlternative]): Ranked list of all
            evaluated communication channels with their confidence scores.
    """

    model_config = {"frozen": True}

    cust_info_id: str = Field(
        ...,
        min_length=1,
        description="Customer identifier for DB persistence.",
    )
    recommended_channel: str = Field(
        ...,
        description="Selected outbound channel (or 'None' for exclusions).",
    )
    recommended_treatment: str = Field(
        ...,
        description="Selected treatment action.",
    )
    decision_reason: str = Field(
        ...,
        description="Audit-trail text for regulatory reporting.",
    )
    scored_alternatives: List[ScoredAlternative] = Field(
        default_factory=list,
        description="Ranked list of evaluated communication channels.",
    )
