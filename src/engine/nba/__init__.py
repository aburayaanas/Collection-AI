"""
NBA Engine — Next Best Action for Collection AI.

This package implements the deterministic compliance layer (guardrails)
and the AI decision engine (bandit) for action selection.

Modules:
    schemas:        Pydantic domain models (CustomerState, ActionSpace, NBAOutput)
    guardrails:     Deterministic rule engine for compliance filtering
    bandit:         Contextual Bandit (HEURISTIC/SHADOW/LIVE) for (channel, treatment) selection
    reward_tracker: Phase 3 LinUCB engine — see docs/phase3_contextual_bandit_rl.md
    orchestrator:   Batch controller wiring guardrails + bandit + reward_tracker together
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
from src.engine.nba.bandit import ContextualBandit
from src.engine.nba.reward_tracker import RewardTracker
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
