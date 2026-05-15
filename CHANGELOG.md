# Changelog

All notable changes to the Collection AI project will be documented in this file.

---

## [Unreleased] — 2026-05-15

### Added — NBA Engine Wiring (Phase 2 Complete)
- `src/database/features/ddl_willingness_mart_nba_columns.sql`: ALTER TABLE script adding 4 NBA context columns to `PIO_COLL_AI_WILLINGNESS_MART` (`ACCOUNT_STATUS`, `TOTAL_DUE`, `SMS_SENT_THIS_WEEK`, `CALLS_MADE_TODAY`).
- `src/database/features/ddl_nba_actions.sql`: CREATE TABLE DDL for `BI_DWH.PIO_COLL_AI_NBA_ACTIONS` with PK and customer lookup index.
- `src/database/repository.py`: New `upsert_nba_results()` — bulk MERGE into `PIO_COLL_AI_NBA_ACTIONS` using `executemany` + `batcherrors=True`.

### Changed — NBA Engine Wiring
- `src/engine/matrix.py`: `integrate_and_save()` now returns `pl.DataFrame` instead of `None`, piping data directly into the NBA step without a DB re-read.
- `src/main.py`: `run_matrix_integration()` updated to return the matrix DataFrame; new `run_nba_steps()` added as Step E in the SCORE/FULL pipeline, isolated in its own `try/except`.
- `src/database/features/willingness.sql`: Added 4 NBA context columns to the SELECT.
- `src/database/repository.py`: `get_willingness_training_data()` schema extended with the 4 NBA context columns.
- `scripts/generate_synthatic_data.py`: Seed script updated to generate logically sane NBA context values. `TOTAL_DUE` correlated with debt-stress signals; `ACCOUNT_STATUS` uses a realistic 85%/15% Active/Excluded distribution; `SMS`/`CALLS` weighted toward low values.

---

## [Unreleased] — 2026-05-14

### Added — NBA Engine Foundation (Phase 2)
- `src/engine/nba/schemas.py`: Pydantic domain models (`CustomerState`, `ActionSpace`, `NBAOutput`). Frozen models for thread-safety in batch processing.
- `src/engine/nba/guardrails.py`: Deterministic `RuleEngine` with two-stage filtering:
    - **Filter 1 (Exclusion):** Immediate halt for Deceased, Legal, Disease, Transfer To Remedial.
    - **Filter 2 (Pruning):** Dynamic channel removal based on regulatory ceilings (SMS/call frequency, minimum-due thresholds).
- `src/engine/nba/bandit.py`: `ContextualBandit` heuristic decision engine:
    - Soft-touch policy (cheapest channel) for Q1/Q2.
    - Escalation policy (most aggressive channel) for Q3/Q4.
    - Per-quadrant treatment mapping: Q1→PTP, Q2→Scheduling, Q3→PTP, Q4→Partial Payment.
    - `RewardTracker` stub reserved for Phase 3 online RL integration.
- `src/engine/nba/orchestrator.py`: Central batch controller wiring guardrails + bandit:
    - `process_single_customer()`: Validates input → Guardrails → Bandit → `NBAOutput`.
    - `process_batch()`: Row-by-row safe iteration; one bad row never crashes the batch.
    - Returns a DataFrame matching `PIO_COLL_AI_NBA_ACTIONS` schema, ready for DB upsert.
- `src/engine/nba/__init__.py`: Clean public API exposing all 4 module classes.
- `CHANGELOG.md`: Created to track daily development progress.

### Changed — Phase 2 Foundation
- `src/engine/nba/schemas.py`: Added `noqa: F401` hints for linter compatibility during development.
