import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr

from src.core import paths

class Settings(BaseSettings):
    # --- Application Info ---
    APP_NAME: str = "CollectionAI_Batch"
    VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, description="Set to True for verbose logging")

    # --- Oracle Database Config ---
    # We use SecretStr to hide passwords from logs automatically.
    # Defaulted to blank (not required) rather than Field(...): the
    # Configuration app must be able to import Settings and launch on a
    # brand-new install, before any credentials have been entered, so it
    # can be the thing that collects them in the first place. Anything
    # that actually needs a live connection (db.initialize_pool) checks
    # for blank credentials itself and fails there with a clear message.
    DB_USER: str = Field(default="", description="Oracle Username")
    DB_PASSWORD: SecretStr = Field(default=SecretStr(""), description="Oracle Password")
    DB_DSN: str = Field(default="", description="DSN string")
    
    DB_MIN_POOL: int = Field(default=2, ge=1)
    DB_MAX_POOL: int = Field(default=5, ge=2)

    INST_CODE: str = Field(default="1")
    COUNTRY_CODE: str = Field(default="400")
    
    BATCH_SIZE: int = 1000 
    
    # --- Execution Mode ---
    MODE: str = Field(default="FULL", description="Execution mode: TRAIN, SCORE, or FULL")
    MODEL_SCOPE: str = Field(default="BOTH", description="Scope of models to run: WILLINGNESS, ABILITY, or BOTH")
    SHAP_SCOPE: str = Field(default="BOTH", description="Scope of SHAP explanations: WILLINGNESS, ABILITY, BOTH, or NONE")
    MODEL_TYPE: str = Field(default="WILLINGNESS", description="Legacy field, use MODEL_SCOPE instead")
    
    # --- Model Thresholds ---
    WILLINGNESS_THRESHOLD: float = 0.7
    ABILITY_THRESHOLD: float = 0.5

    # --- Snapshot Date Override (TESTING ONLY) ---
    # Leave unset (None) in production: get_snap_date() will call the real
    # Oracle SNAP_DATE() function. Setting this pins every pipeline run to
    # a fixed business date — only ever meant for local/dev testing against
    # a database whose SNAP_DATE() function isn't wired up yet.
    SNAP_DATE_OVERRIDE: str | None = Field(
        default=None,
        description="YYYY-MM-DD. TESTING ONLY — pins the pipeline's business date. Leave blank in production.",
    )

    # --- Artifact Retention ---
    RETENTION_KEEP_N: int = Field(
        default=10,
        ge=1,
        description="Number of most-recent model/cache artifacts to keep per model type before pruning older ones.",
    )

    # --- NBA Phase 3: Contextual Bandit (LinUCB) ---
    # See docs/phase3_contextual_bandit_rl.md for the full design.
    NBA_POLICY_MODE: str = Field(
        default="HEURISTIC",
        description="HEURISTIC (today's static scoring, default) / SHADOW (LinUCB computes+logs its pick but heuristic still acts) / LIVE (LinUCB drives the recommendation).",
    )
    RL_LOOKBACK_DAYS: int = Field(
        default=90, ge=1,
        description="How many days of PIO_COLL_AI_RL_FEEDBACK to read when rebuilding the bandit's arms each run.",
    )
    RL_PRIOR_STRENGTH: int = Field(
        default=20, ge=0,
        description="Pseudo-observation weight of the heuristic-derived cold-start prior for each LinUCB arm.",
    )
    RL_LINUCB_ALPHA: float = Field(
        default=1.0, ge=0.0,
        description="LinUCB exploration weight: score = theta.x + alpha * sqrt(x.A_inv.x).",
    )
    RL_LINUCB_LAMBDA: float = Field(
        default=1.0, gt=0.0,
        description="Ridge regularization strength for each arm's A matrix (A = lambda*I + ...).",
    )
    RL_MIN_SAMPLES: int = Field(
        default=30, ge=0,
        description="Observability threshold: arms below this many real observations are logged as still prior-dominated (not a hard gate).",
    )

    # --- Behavioral Signal Thresholds (docs/backend_issues.md Issue 5) ---
    # SignalInterpreter's rule-based scenario detectors. Externalized from
    # hardcoded constants so business/risk teams can tune them without a
    # code change or redeploy. Defaults match the values these replaced,
    # so leaving them unset changes nothing.
    SIGNAL_LIQUIDITY_INFLOW_VARIANCE_THRESHOLD: float = Field(
        default=500.0,
        description="INFLOW_VARIANCE_30D above this (combined with a payment rejection) triggers the Liquidity Disruption hypothesis.",
    )
    SIGNAL_LIQUIDITY_CONFIDENCE_MIN: float = Field(
        default=0.55, ge=0.0, le=1.0,
        description="Lower clamp for the Liquidity Disruption hypothesis confidence.",
    )
    SIGNAL_LIQUIDITY_CONFIDENCE_MAX: float = Field(
        default=0.75, ge=0.0, le=1.0,
        description="Upper clamp for the Liquidity Disruption hypothesis confidence.",
    )
    SIGNAL_EVASION_DAYS_SINCE_RPC_THRESHOLD: int = Field(
        default=30, ge=0,
        description="DAYS_SINCE_LAST_RPC above this (with a broken PTP or high avoidance) contributes to the Evasive Pattern signal.",
    )
    SIGNAL_EVASION_CONTACT_AVOIDANCE_THRESHOLD: float = Field(
        default=0.6, ge=0.0, le=1.0,
        description="CONTACT_AVOIDANCE_INDEX at/above this triggers the Contact Failure / Evasive Pattern signals.",
    )

    # --- Escalation Timeline (docs/backend_issues.md Issue 4) ---
    # EscalationEngine.generate_timeline()'s phase windows. Externalized
    # from hardcoded day-counts so they can be tuned per-institution.
    # Defaults match the values these replaced.
    ESCALATION_PHASE1_DAYS: int = Field(
        default=7, ge=1,
        description="Length of Phase 1 (active NBA channel) in days before Phase 2 can trigger.",
    )
    ESCALATION_PHASE2_END_DAY: int = Field(
        default=21, ge=1,
        description="Day (from today) at which Phase 2 ends and Phase 3 (legal referral) can trigger.",
    )
    ESCALATION_LEGAL_INELIGIBLE_PRODUCTS: str = Field(
        default="",
        description="Comma-separated product names (matched case-insensitively as substrings of PRODUCTS_HELD) for which a formal demand letter must NOT be offered in Phase 2. Blank means no restriction — no such business rule is documented yet (docs/backend_issues.md Issue 4); populate once the compliance/legal team defines one.",
    )

    # --- LLM Narrative Config (Local — LM Studio fallback) ---
    LLM_BASE_URL: str = Field(default="http://localhost:1234/v1", description="Base URL for local LLM server (e.g., LM Studio)")
    LLM_MODEL_NAME: str = Field(default="your-local-model-name-here", description="Name of the model loaded in LM Studio")
    LLM_API_KEY: SecretStr = Field(default=SecretStr("lm-studio"), description="API Key for the LLM server")

    # --- OpenAI API Config (Executive Demo / Cloud toggle) ---
    USE_OPENAI_API: bool = Field(default=False, description="If True, routes LLM calls to OpenAI instead of local LM Studio")
    OPENAI_API_KEY: SecretStr = Field(default=SecretStr(""), description="OpenAI API Key (sk-...)")
    OPENAI_MODEL_NAME: str = Field(default="gpt-4o", description="OpenAI model to use (e.g., gpt-4o)")

    # Writable app-data root (models/, data/cache/, logs/, mlruns/ all live
    # under this). ProgramData when frozen, repo root in dev — see
    # src/core/paths.py. Kept as a plain str field (not Path) so it still
    # serializes/compares the way existing code expects.
    BASE_DIR: str = str(paths.APP_DIR)

    model_config = SettingsConfigDict(
        env_file=str(paths.ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()


def reload_settings() -> Settings:
    """
    Re-read .env from disk and refresh the ``settings`` singleton in place.

    Needed because ``settings`` is imported by reference all over the
    codebase (``from src.core.config import settings``). A long-lived
    process — the scheduler service — must pick up edits the Configuration
    exe makes to .env without a full restart, so every scheduled pipeline
    run calls this first instead of trusting values loaded once at process
    start.
    """
    fresh = Settings()
    for field_name in Settings.model_fields:
        setattr(settings, field_name, getattr(fresh, field_name))
    return settings


def get_secret_value(setting: SecretStr) -> str:
    return setting.get_secret_value()