"""
Artifact Retention.

Every scoring run writes a brand-new timestamped Parquet cache file and
every training run writes a brand-new timestamped model JSON — neither
ever cleans up after itself (see ``WillingnessScorer.score()`` and
``*Trainer.save_model()``). That is harmless for a handful of manual runs,
but a scheduler firing this pipeline multiple times a day, indefinitely,
accumulates files without bound.

This module prunes old artifacts after each pipeline run, keeping only the
most recent ``RETENTION_KEEP_N`` per family, while never touching whatever
file a ``latest_*.json`` pointer currently references — that safety check
matters more than the count once ``RETENTION_KEEP_N`` is set low.
"""

import json
import logging
from pathlib import Path

from src.core import paths
from src.core.config import settings

logger = logging.getLogger(__name__)

_MODEL_FAMILIES = ("ability_v", "willingness_v")
_CACHE_FAMILIES = ("ability_scores_", "willingness_scores_")


def _pointer_targets() -> set[str]:
    """Filenames the latest_*.json pointers currently reference — never prune these."""
    targets: set[str] = set()
    for pointer_name in ("latest_ability.json", "latest_willingness.json"):
        pointer_path = paths.MODELS_DIR / pointer_name
        if not pointer_path.exists():
            continue
        try:
            data = json.loads(pointer_path.read_text(encoding="utf-8"))
            latest = data.get("latest")
            if latest:
                targets.add(latest)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Retention: could not read pointer {pointer_path}: {e}")
    return targets


def _prune_family(directory: Path, prefix: str, keep_n: int, protected: set[str], log: logging.Logger) -> None:
    candidates = sorted(
        (p for p in directory.glob(f"{prefix}*") if p.is_file() and p.name not in protected),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in candidates[keep_n:]:
        try:
            stale.unlink()
            log.info(f"Retention: removed stale artifact {stale.name}")
        except OSError as e:
            log.warning(f"Retention: could not remove {stale}: {e}")


def cleanup_old_artifacts(log: logging.Logger | None = None) -> None:
    """Prune old model/cache artifacts, keeping the most recent RETENTION_KEEP_N per family."""
    log = log or logger
    keep_n = settings.RETENTION_KEEP_N
    protected = _pointer_targets()

    for prefix in _MODEL_FAMILIES:
        _prune_family(paths.MODELS_DIR, prefix, keep_n, protected, log)

    for prefix in _CACHE_FAMILIES:
        _prune_family(paths.CACHE_DIR, prefix, keep_n, protected, log)
