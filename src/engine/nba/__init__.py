"""
NBA Engine — Next Best Action for Collection AI.

This package implements the deterministic compliance layer (guardrails)
and the AI decision engine (bandit) for action selection.

Modules:
    schemas:      Pydantic domain models (CustomerState, ActionSpace, NBAOutput)
    guardrails:   Deterministic rule engine for compliance filtering
    bandit:       Contextual Bandit for optimal (channel, treatment) selection
    orchestrator: Batch controller wiring guardrails + bandit together
"""

from src.engine.nba.schemas import (
    ActionSpace,
    Channel,
    CustomerState,
    NBAOutput,
    Treatment,
)
from src.engine.nba.guardrails import (
    CollectionGuardrails,
    GuardrailResult,
    RuleEngine,
)
from src.engine.nba.bandit import (
    ContextualBandit,
    RewardTracker,
)
from src.engine.nba.orchestrator import NBAOrchestrator

__all__ = [
    "ActionSpace",
    "Channel",
    "CollectionGuardrails",
    "ContextualBandit",
    "CustomerState",
    "GuardrailResult",
    "NBAOrchestrator",
    "NBAOutput",
    "RewardTracker",
    "RuleEngine",
    "Treatment",
]
