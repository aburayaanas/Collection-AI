"""
Reads and writes the shared .env file that both the Service exe (via
pydantic Settings, see src/core/config.py) and any manual
``python -m src.main`` run consume.

Every save rewrites the entire file atomically (temp file + os.replace)
from a known field schema, rather than patching individual lines in
place — simpler to reason about, and a scheduler process mid-poll of
.env's mtime (see src/scheduler/service.py) never observes a half
written file.
"""

from typing import Any, Dict, List, NamedTuple, Optional

from dotenv import dotenv_values

from src.core import paths


class Field(NamedTuple):
    key: str
    label: str
    section: str
    kind: str  # "str" | "int" | "float" | "bool" | "secret" | "choice"
    help_text: str
    choices: Optional[List[str]] = None
    default: str = ""


# Every .env value the pipeline reads (src/core/config.py Settings), grouped
# by the tab it appears under in the Configuration app. Keeping this list as
# the single source of truth is what satisfies "include all configurations."
FIELD_SCHEMA: List[Field] = [
    # --- Application ---
    Field("APP_NAME", "Application Name", "Application", "str", "Identifies this deployment in logs.", default="CollectionAI_Batch"),
    Field("VERSION", "Version", "Application", "str", "Informational version tag.", default="1.0.0"),
    Field("DEBUG", "Debug Logging", "Application", "bool", "Verbose (DEBUG-level) logging.", default="False"),

    # --- Database ---
    Field("DB_USER", "DB Username", "Database", "str", "Oracle username."),
    Field("DB_PASSWORD", "DB Password", "Database", "secret", "Oracle password."),
    Field("DB_DSN", "DB DSN", "Database", "str", "host:port/service_name"),
    Field("DB_MIN_POOL", "Min Pool Size", "Database", "int", "Minimum pooled connections.", default="2"),
    Field("DB_MAX_POOL", "Max Pool Size", "Database", "int", "Maximum pooled connections.", default="5"),
    Field("INST_CODE", "Institution Code", "Database", "str", "", default="1"),
    Field("COUNTRY_CODE", "Country Code", "Database", "str", "", default="400"),

    # --- Pipeline ---
    Field("MODE", "Default Mode", "Pipeline", "choice", "Used by manual runs; scheduled jobs set their own mode.", ["TRAIN", "SCORE", "FULL"], default="FULL"),
    Field("MODEL_SCOPE", "Default Model Scope", "Pipeline", "choice", "", ["WILLINGNESS", "ABILITY", "BOTH"], default="BOTH"),
    Field("SHAP_SCOPE", "Default SHAP Scope", "Pipeline", "choice", "", ["WILLINGNESS", "ABILITY", "BOTH", "NONE"], default="BOTH"),
    Field("BATCH_SIZE", "Batch Size", "Pipeline", "int", "", default="1000"),
    Field("WILLINGNESS_THRESHOLD", "Willingness Threshold", "Pipeline", "float", "Quadrant cutoff (0-1).", default="0.7"),
    Field("ABILITY_THRESHOLD", "Ability Threshold", "Pipeline", "float", "Quadrant cutoff (0-1).", default="0.5"),
    Field("RETENTION_KEEP_N", "Artifact Retention Count", "Pipeline", "int", "How many recent model/cache files to keep before pruning.", default="10"),
    Field("SNAP_DATE_OVERRIDE", "Snap Date Override", "Pipeline", "str", "TESTING ONLY — pins the business date (YYYY-MM-DD). Leave BLANK in production.", default=""),

    # --- Behavioral Signal Thresholds (docs/backend_issues.md Issue 5) ---
    Field("SIGNAL_LIQUIDITY_INFLOW_VARIANCE_THRESHOLD", "Liquidity: Inflow Variance Threshold", "Pipeline", "float", "INFLOW_VARIANCE_30D above this (+ a payment rejection) triggers the Liquidity Disruption hypothesis.", default="500.0"),
    Field("SIGNAL_LIQUIDITY_CONFIDENCE_MIN", "Liquidity: Confidence Floor", "Pipeline", "float", "Lower clamp for the Liquidity Disruption hypothesis confidence (0-1).", default="0.55"),
    Field("SIGNAL_LIQUIDITY_CONFIDENCE_MAX", "Liquidity: Confidence Ceiling", "Pipeline", "float", "Upper clamp for the Liquidity Disruption hypothesis confidence (0-1).", default="0.75"),
    Field("SIGNAL_EVASION_DAYS_SINCE_RPC_THRESHOLD", "Evasion: Days Since Contact Threshold", "Pipeline", "int", "DAYS_SINCE_LAST_RPC above this (+ high avoidance) contributes to the Evasive Pattern signal.", default="30"),
    Field("SIGNAL_EVASION_CONTACT_AVOIDANCE_THRESHOLD", "Evasion: Contact Avoidance Threshold", "Pipeline", "float", "CONTACT_AVOIDANCE_INDEX at/above this triggers the Contact Failure / Evasive Pattern signals (0-1).", default="0.6"),

    # --- Escalation Timeline (docs/backend_issues.md Issue 4) ---
    Field("ESCALATION_PHASE1_DAYS", "Escalation: Phase 1 Length (days)", "Pipeline", "int", "Length of the active-channel window before Phase 2 can trigger.", default="7"),
    Field("ESCALATION_PHASE2_END_DAY", "Escalation: Phase 2 End Day", "Pipeline", "int", "Day (from today) Phase 2 ends and Phase 3 (legal referral) can trigger.", default="21"),
    Field("ESCALATION_LEGAL_INELIGIBLE_PRODUCTS", "Escalation: Demand-Letter-Ineligible Products", "Pipeline", "str", "Comma-separated products for which a formal demand letter must not be offered. Blank = no restriction (no rule documented yet).", default=""),

    # --- Reinforcement Learning (Phase 3 contextual bandit) ---
    # See docs/phase3_contextual_bandit_rl.md.
    Field("NBA_POLICY_MODE", "NBA Policy Mode", "Reinforcement Learning", "choice", "HEURISTIC = today's static scoring (safe default). SHADOW = LinUCB computes+logs its pick but the heuristic still acts. LIVE = LinUCB drives the recommendation.", ["HEURISTIC", "SHADOW", "LIVE"], default="HEURISTIC"),
    Field("RL_LOOKBACK_DAYS", "Feedback Lookback (days)", "Reinforcement Learning", "int", "How many days of PIO_COLL_AI_RL_FEEDBACK to read when rebuilding the bandit's arms each run.", default="90"),
    Field("RL_PRIOR_STRENGTH", "Cold-Start Prior Strength", "Reinforcement Learning", "int", "Pseudo-observation weight of the heuristic-derived cold-start prior for each arm.", default="20"),
    Field("RL_LINUCB_ALPHA", "LinUCB Exploration Weight (alpha)", "Reinforcement Learning", "float", "Higher = more exploration of under-sampled channels. Tune down if LIVE mode over-concentrates on one channel.", default="1.0"),
    Field("RL_LINUCB_LAMBDA", "LinUCB Ridge Regularization (lambda)", "Reinforcement Learning", "float", "Ridge regularization strength for each arm's design matrix.", default="1.0"),
    Field("RL_MIN_SAMPLES", "Min Samples Before 'Seasoned'", "Reinforcement Learning", "int", "Observability threshold only — arms below this are logged as still prior-dominated, not blocked.", default="30"),

    # --- Narrative API ---
    Field("LLM_BASE_URL", "LLM Base URL", "Narrative API", "str", "Local LM Studio server URL.", default="http://localhost:1234/v1"),
    Field("LLM_MODEL_NAME", "LLM Model Name", "Narrative API", "str", ""),
    Field("LLM_API_KEY", "LLM API Key", "Narrative API", "secret", "", default="lm-studio"),
    Field("USE_OPENAI_API", "Use OpenAI Instead", "Narrative API", "bool", "Route narrative generation to OpenAI instead of the local LLM.", default="False"),
    Field("OPENAI_API_KEY", "OpenAI API Key", "Narrative API", "secret", ""),
    Field("OPENAI_MODEL_NAME", "OpenAI Model", "Narrative API", "str", "", default="gpt-4o"),
]

FIELDS_BY_KEY: Dict[str, Field] = {f.key: f for f in FIELD_SCHEMA}
SECTIONS: List[str] = list(dict.fromkeys(f.section for f in FIELD_SCHEMA))


def read_env() -> Dict[str, str]:
    """Current .env values merged with schema defaults for anything missing/blank."""
    on_disk: Dict[str, str] = {}
    if paths.ENV_PATH.exists():
        on_disk = {k: (v or "") for k, v in dotenv_values(paths.ENV_PATH).items()}

    values: Dict[str, str] = {}
    for f in FIELD_SCHEMA:
        values[f.key] = on_disk.get(f.key, f.default)
    # Preserve anything already in .env that isn't in our schema.
    for k, v in on_disk.items():
        values.setdefault(k, v or "")
    return values


def _format_value(v: Any) -> str:
    s = "" if v is None else str(v)
    if any(c in s for c in " #\"'"):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def write_env(values: Dict[str, Any]) -> None:
    """Rewrite the entire .env file from `values`, atomically."""
    lines = [
        "# Managed by the Collection AI Configuration app.",
        "# Values are grouped by section; edit via the app rather than by hand where possible.",
        "",
    ]
    current_section: Optional[str] = None
    for f in FIELD_SCHEMA:
        if f.section != current_section:
            lines.append(f"# --- {f.section} ---")
            current_section = f.section
        lines.append(f"{f.key}={_format_value(values.get(f.key, f.default))}")

    known_keys = set(FIELDS_BY_KEY)
    extras = {k: v for k, v in values.items() if k not in known_keys}
    if extras:
        lines.append("")
        lines.append("# --- Other ---")
        for k, v in extras.items():
            lines.append(f"{k}={_format_value(v)}")

    content = "\n".join(lines) + "\n"
    tmp_path = paths.ENV_PATH.with_suffix(".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(paths.ENV_PATH)
