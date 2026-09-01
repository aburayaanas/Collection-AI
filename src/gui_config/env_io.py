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
