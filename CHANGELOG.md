# Changelog

All notable changes to the Collection AI project will be documented in this file.

---

## [Unreleased] — 2026-09-07

### Fixed — Audit Critique Corrections (Data & Logic Consistency)

- **Escalation Timeline Snapshot Anchoring:** `src/engine/nba/escalation.py` (`EscalationEngine.generate_timeline()`) now accepts an optional `reference_date` parameter, and `src/explainability/xai_aggregator.py` passes the customer record's `DAY_DATE`. Escalation phases (0-7 days, 8-21 days) are now mathematically anchored to the snapshot date rather than drifting with `datetime.date.today()`, ensuring historical consistency and backtesting accuracy.
- **Q2 Channel Heuristic Rationale:** `src/engine/nba/bandit.py` (`ContextualBandit._score_channel()`) previously labeled both Q1 and Q2 as `"Low risk quadrant ({quadrant}). Soft touch approach preferred."`. Q2 represents Vulnerable / Distressed borrowers (Low Ability / High Willingness). Updated Q2's rationale to: `"Vulnerable quadrant (Q2). High willingness warrants soft touch / restructuring approach."`.
- **LLM System Prompt Governance Guardrails:** `src/explainability/llm_system_prompt.md` updated with:
  1. Strict KYC compliance lock override: when KYC/income is expired or flagged, Section 2 posture and Section 4 restructuring terms are explicitly suppressed/locked.
  2. Currency Mandate: enforce JOD across all narrative sections (no `$`, `USD`, or unvalidated symbols).
  3. Channel Tie-Breaker Explanation: explicit instructions for narrating tied channel scores (e.g. Email 100 vs Outgoing Call 100) via policy priority (cost efficiency & soft-touch digital precedence) rather than claiming numerical superiority.
  4. Composite Risk Score Velocity Nuance: clear guidance on narrating high risk scores with negative deltas (improving trajectory within high-risk territory).
- **Bandit Escalation Policy Tie-Breaker:** In `src/engine/nba/bandit.py` (`_heuristic_pick()`), resolved ties dynamically based on quadrant type: soft quadrants (Q1/Q2) favor non-intrusive/cheaper digital outreach (`score > best_score`), while escalation quadrants (Q3/Q4) favor escalated/physical intervention (`score >= best_score`). Prevents telephone calling from improperly superseding Field Visits in Q4 when contact evasion is active.
- **Demo Showcase Customers Calibration & Pre-Caching:** Created `scripts/clean_demo_showcase_customers.py` to align all three primary demo customers (`48618400` Q1, `10617433` Q2, `10017292` Q4) in Oracle `PIO_COLL_AI_NBA_CONTEXT_MART`, `WILLINGNESS_MART`, `ABILITY_MART`, and `NBA_ACTIONS`. Cleaned string encoding, calibrated behavioral indices (Q1: 0.04 avoidance/0 rejections; Q2: 0.12 avoidance/2 rejections/2450 inflow variance; Q4: 0.88 avoidance/4 rejections/3800 inflow variance), and pre-cached complete audited 5-section executive narratives in `AI_NARRATIVE` for instant 0ms demo rendering.
- Added unit tests in `tests/test_backend_issues_fixes.py` covering timeline reference date anchoring and Q2 bandit rationale.

---

## [Unreleased] — 2026-09-06 (later)

### Fixed — Backend Issues Reported by the Frontend Team (`docs/backend_issues.md`)

- **Issue 3 (extreme 0/100 or 99/100 Willingness/Ability scores):** Verified the severity directly against real cached scores before fixing — **92.9%** of a real willingness scoring run was below 0.01. Root cause confirmed: raw, uncalibrated XGBoost `binary:logistic` probabilities genuinely saturate near 0/1; `xai_aggregator.py`'s `int(score * 100)` was just displaying that faithfully, so the fix belongs upstream at inference, not in the display layer. Added `src/models_engine/calibration.py`: 5-fold out-of-fold isotonic regression calibration, fit on the training fold only (never touching the held-out test fold), with Brier score + Expected Calibration Error logged to MLflow before/after so the fix's effect is measured, not assumed. Both `WillingnessTrainer`/`AbilityTrainer` now fit and persist a calibrator alongside the model (`<name>_calibrator_v<timestamp>.pkl`, referenced from the `latest_*.json` pointer file); both `WillingnessScorer`/`AbilityScorer` load and apply it, with a graceful, clearly-logged fallback to raw probabilities for any model trained before this fix. Verified end-to-end against the real dev DB: ECE improved from 0.0206 → 0.0024 for the Ability model on a real held-out test fold (~8.5x). Note: this dev/test environment's synthetic training labels are a deterministic function of the training features (`scripts/generate_synthatic_data.py`), so population-level score saturation doesn't visibly change here even though calibration is measurably correct — real, noisy production behavioral data is where this fix's effect will actually be visible in the score distribution.
- **Issue 4 (escalation timeline hardcoding):** `src/engine/nba/escalation.py`'s phase day-windows (7 / 8-21 / 21+) are now `ESCALATION_PHASE1_DAYS`/`ESCALATION_PHASE2_END_DAY` settings instead of magic numbers. Fixed the concrete bug found while investigating: `CockpitAggregator` calls `generate_timeline()` unconditionally for every customer, including ones already in `Legal`/`Transfer To Remedial` status — so those customers' own AI_PAYLOAD said they would be "referred to legal" as a *future* trigger despite already being there. `generate_timeline()` now takes `account_status` and short-circuits to a status-accurate timeline for those two statuses. Also added a configurable, opt-in `ESCALATION_LEGAL_INELIGIBLE_PRODUCTS` product-eligibility gate for Phase 2's demand letter (default blank — no such business rule is documented yet; this builds the correct extension point rather than fabricating one). Verified against a real `Legal`-status customer's persisted `AI_PAYLOAD` in the dev DB.
- **Issue 5 (hardcoded behavioral signal thresholds):** `SignalInterpreter`'s four magic numbers (`inflow_variance > 500.0`, `contact_avoidance >= 0.6`, `days_since_rpc > 30`, confidence clamp `[0.55, 0.75]`) are now `SIGNAL_*` settings, defaults unchanged, surfaced in the Configuration app's Pipeline tab like every other tunable in this codebase.
- **Issues 6 & 7 (LLM prompt polarity + SHAP clarity):** `src/explainability/llm_system_prompt.md` Section 2 now explicitly defines `score_delta_90d`'s polarity (positive = risk deterioration, negative = risk improvement — the composite-risk-score convention, opposite of FICO-style credit scores) so the LLM can't hallucinate the inverse, and gives the SHAP driver instructions concrete before/after phrasing for Risk Drivers vs. Protective Anchors instead of dense feature-name-and-percentage recitation.
- Added `tests/test_backend_issues_fixes.py` (16 tests) covering all of the above except 6/7 (prompt text, not executable behavior).
- Also fixed in passing: `mlruns/0/meta.yaml` (MLflow's default experiment metadata) was missing from the local tracking store, blocking every `mlflow.start_run()` call — pre-existing local environment corruption unrelated to this work, regenerated to unblock verification training runs.

---

## [Unreleased] — 2026-09-06

### Added — Phase 3: Contextual Bandit (LinUCB)

Full design record in `docs/phase3_contextual_bandit_rl.md`, verified against the live system (code + live Oracle DB) before implementation, including two corrections to prior docs found during that verification: `docs/To_Do_List.md`'s `PIO_COLL_AI_NBA_FEEDBACK` reference is stale (the real table is `PIO_COLL_AI_RL_FEEDBACK`), and `docs/DB_Schema.md`'s `PIO_COLL_AI_MATRIX_RESULTS` DDL is stale (no primary key exists on the live table).

- `src/engine/nba/reward_tracker.py` (new): LinUCB contextual bandit — one disjoint linear ridge-regression model per channel arm, scored on a 13-dimensional per-customer context vector (`TOTAL_DUE`, `DAYS_PAST_DUE`, `CONTACT_AVOIDANCE_INDEX`, `SMS_SENT_THIS_WEEK`, `DAYS_SINCE_LAST_RPC`, `PTP_RELIABILITY_RATIO`, `AGE`, account tenure, quadrant one-hot). Cold-start priors are seeded from the existing heuristic's implied reward at each quadrant's real mean context vector, not a blank/uninformative prior — preserving the Cold-Start Safety Hazard mitigation the team had already flagged for this phase. `map_outcome()` is the single reward-mapping source of truth shared with the synthetic generator.
- `src/engine/nba/bandit.py`: `ContextualBandit` now runs one of three policies via `NBA_POLICY_MODE` — `HEURISTIC` (default, byte-for-byte unchanged), `SHADOW` (LinUCB computes and logs its pick in `DECISION_REASON`/`SCORED_ALTERNATIVES`, heuristic still acts), `LIVE` (LinUCB drives `RECOMMENDED_CHANNEL`). Treatment selection is unchanged in every mode. Any `RewardTracker` failure degrades to the heuristic for that customer/run rather than failing the batch.
- `src/engine/nba/orchestrator.py`: builds and refreshes the `RewardTracker` once per `process_batch()` call (skipped entirely in `HEURISTIC` mode).
- `src/database/features/rl_feedback.sql`, `ddl_rl_feedback.sql`; `CollectionRepository.get_rl_feedback_data()`: reads `PIO_COLL_AI_RL_FEEDBACK` joined to `PIO_COLL_AI_NBA_ACTIONS` (quadrant, exact-date) and the ML marts (numeric context, current-snapshot join — see docs sec 5.4 for why).
- `src/database/features/nba_context.sql`, `CollectionRepository.get_nba_context_data()`, `src/main.py`: extended to also supply `AGE` (from `PIO_COLL.PIO_CUSTOMERS_INFO`, not the raw core-banking `PIO_CUSTOMERS` table) and `ACCOUNT_TENURE_DAYS` (derived from the already-integrated `ACCOUNT_OPEN_DATE`) for live scoring.
- `src/engine/nba/schemas.py`: `CustomerState` gained 6 optional Phase 3 context fields with neutral defaults — additive, non-breaking for existing callers.
- `scripts/generate_synthetic_rl_feedback.py` (new): populates `PIO_COLL_AI_RL_FEEDBACK` from real, non-excluded `PIO_COLL_AI_NBA_ACTIONS` rows, with outcome probabilities that vary by quadrant *and* by each customer's real `CONTACT_AVOIDANCE_INDEX` — not a flat per-quadrant table — so the generated data actually exercises LinUCB's personalization within a quadrant. `--topup` tops up thin quadrant×channel cells using real customers under new backdated dates; `--dry-run` previews without writing.
- New settings: `NBA_POLICY_MODE`, `RL_LOOKBACK_DAYS`, `RL_PRIOR_STRENGTH`, `RL_LINUCB_ALPHA`, `RL_LINUCB_LAMBDA`, `RL_MIN_SAMPLES`.

**Verified against the real dev DB, not just unit-tested:** ran the full `TRAIN→SCORE→MATRIX→NBA` pipeline end-to-end in all three policy modes. Confirmed personalization works (two same-quadrant customers differing only in `CONTACT_AVOIDANCE_INDEX` get different LinUCB channel scores). Confirmed `SHADOW` mode's safety contract holds (100% of actioned rows carried the shadow annotation; `RECOMMENDED_CHANNEL` never touched). Confirmed `LIVE` mode actually changes `RECOMMENDED_CHANNEL` in the DB.

**Finding from that test, not yet resolved:** with the current synthetic feedback and `RL_LINUCB_ALPHA=1.0`, LIVE mode converges heavily toward `Dunning Letter` (~98% of actioned customers) — its exploration bonus (fewest real observations: 75 vs. 2,005 for Outgoing Call) combined with a less-negative learned mean than the other aggressive channels wins the UCB argmax almost everywhere it's guardrail-legal. This is mathematically correct UCB behavior given the current data, not a bug, but not a distribution anyone should want live yet — needs alpha tuning and/or more balanced real feedback before any real `LIVE` rollout. Exactly the scenario `SHADOW` mode exists to catch first.

---

## [Unreleased] — 2026-08-31

### Added — Scheduler Service, Configuration App, and PyInstaller Packaging

- `src/scheduler/`: New package — `jobstore.py` (multiple-times-a-day schedule persistence, each entry with its own `MODE`/`MODEL_SCOPE`/`SHAP_SCOPE`), `service.py` (APScheduler `BackgroundScheduler` with config/schedule hot-reload polling and a "run now" flag), `executor.py` (runs one pipeline job, records status), `win_service.py` (pywin32 Windows Service wrapper with install/start/stop/debug verbs and crash auto-restart via `sc failure`).
- `src/gui_config/`: New CustomTkinter Configuration app (`app.py`) covering every `.env` value across Application/Database/Pipeline/Narrative API tabs, plus Schedule (add/edit/delete jobs, per-job Run Now), Service (install/start/stop with UAC elevation), and Logs (live tail) tabs. `.env` writes are atomic (temp file + replace).
- `src/core/paths.py`: Centralizes app-data vs. bundled-resource path resolution so both executables agree on one writable location (`%PROGRAMDATA%\CollectionAI` when frozen) regardless of install folder or a Windows Service's `System32` working directory.
- `src/core/retention.py`: Prunes old model/cache artifacts after each run (scoring/training previously wrote a new timestamped file forever with no cleanup), protecting whatever the `latest_*.json` pointers currently reference.
- `packaging/collectionai_service.spec`, `packaging/collectionai_config.spec`, `scripts/build_exes.ps1`: PyInstaller build configuration for the two executables. Verified end-to-end: both launch standalone, the Service exe correctly creates its app-data directory under `%PROGRAMDATA%` and starts the scheduler when frozen.

### Fixed — Production-readiness issues found while building the above

- `src/database/queries.py`: Removed a hardcoded `2026-05-18` snapshot-date override that silently bypassed the real Oracle `SNAP_DATE()` call in every run. Replaced with an explicit, opt-in `SNAP_DATE_OVERRIDE` setting (blank by default) surfaced with a clear production warning in both `.env.example` and the Configuration app.
- `src/core/config.py`: `DB_USER`/`DB_PASSWORD`/`DB_DSN` are no longer required at import time — they defaulted to `Field(...)`, which meant *any* process importing `Settings` (including the Configuration app meant to collect these values on first install) crashed before a fresh install could even be configured. `src/database/connection.py` now checks for blank credentials itself and raises a clear, actionable error at connection time instead.
- `src/core/config.py`: Added `reload_settings()` so the long-lived scheduler process picks up `.env` edits without a restart (previously `settings` was a load-once singleton).
- Path anchoring: `src/core/logger.py`, `src/api/narrative_service.py`, `src/engine/matrix.py`, and `src/main.py`'s model/cache directory arguments all previously used CWD-relative paths (`"models"`, `"data/cache"`, `Path(__file__)`-derived logs dir) that break under a frozen exe / Windows Service whose working directory is `System32`. Now resolved via `src/core/paths.py`.



### Enhanced — Bulletproof Narrative API & Caching Layer

- `src/api/narrative_service.py`:
  - Implemented strict Zero-Error-Caching policy ensuring errors and failures never overwrite `PENDING` states in the database.
  - Added smart cache validation to detect and auto-regenerate previously corrupted or truncated narrative entries.
  - Added support for `force_regenerate=True` query parameter to allow manual re-generation on demand.
  - Robust handling of reasoning models, markdown code fences, and empty content fallbacks.
- `src/explainability/llm_system_prompt.md`: Streamlined system prompt to eliminate scratchpad token bloat, enforce markdown output, and prevent models from emitting incomplete/broken JSON.
- `CollectionCockpit.jsx`: Updated frontend narrative generation trigger to utilize `force_regenerate=true` and cleanly surface server/LLM failures in the UI error banner.

---

## [Unreleased] — 2026-08-16

### Fixed — Narrative Service LLM Handling

- `src/api/narrative_service.py`: Increased `max_tokens` to 3,000 to give local reasoning models (such as Qwen3/DeepSeek) ample headroom to complete internal thinking. Added fallback support for `reasoning_content` if `content` is empty, and added a safeguard preventing empty narrative strings from being saved to the database.

---

## [Unreleased] — 2026-08-12

### Added — QA Release Notes Documentation

- `docs/release notes/Collection_AI_Table_and_Procedure_Descriptions.xlsx`: Generated a professional corporate-formatted Excel catalog mapping all 6 major database tables and the 4 primary PL/SQL procedures (along with their registered `PIO_LABELS` IDs) used in the Collection AI system. Includes full English and Arabic descriptions, schema ownership, and system roles to finalize QA release requirements.

---

## [Unreleased] — 2026-08-06

### Changed — Database Schema Alignment

- Renamed the column `REASON_CODE` to `DECISION_REASON` (and `reason_code` variables to `decision_reason`) across the NBA engine (`schemas.py`, `orchestrator.py`, `bandit.py`, `guardrails.py`), database repository (`repository.py`), execution script (`main.py`), and related DDL and documentation. This aligns the naming standard with database design guidelines since the column stores structured decision text rather than numeric lookup codes.

---

## [Unreleased] — 2026-07-02

### Changed — Frontend Connection

- `CollectionCockpit.jsx`: Replaced hardcoded `localhost:8000` URLs with dynamic `window.location.hostname` URLs. This allows the frontend to dynamically connect back to the hosting developer's machine's backend API from other devices on the local network (such as the manager's computer).

---

## [Unreleased] — 2026-06-04

### Added — Database Marts Reference Documentation

- `docs/table_marts_summary.md`: A comprehensive schema dictionary detailing fully qualified column paths (e.g. `PIO_COLL_AI_WILLINGNESS_MART.CUST_INFO_ID`), English object name expansions, Arabic translations, data types, nullability, and database comments (describing AI calculation logic and DB procedures) for all key data marts (`PIO_COLL_AI_WILLINGNESS_MART`, `PIO_COLL_AI_ABILITY_MART`, `PIO_COLL_AI_NBA_CONTEXT_MART`) and output tables.
- `Collection_AI_Input_Marts_Mapping_Checklist.xlsx`: Fully populated the Excel mapping checklist template with sheets for `PIO_COLL_AI_WILLINGNESS_MART`, `PIO_COLL_AI_ABILITY_MART`, and `PIO_COLL_AI_NBA_CONTEXT_MART`, using standard Left-to-Right (LTR) column orientation, custom headers, data types, nullability (M/O), and descriptive English/Arabic comments.
- `Collection_AI_Output_Tables_Mapping_Checklist.xlsx`: Created and populated a new Excel workbook for the output and decision tables (`PIO_COLL_AI_MATRIX_RESULTS` and `PIO_COLL_AI_NBA_ACTIONS`) with standard LTR column layout, custom headers, data types, nullability (M/O), and English/Arabic comments.
- `docs/DB_Schema.md`: Added the DDL schema script and data dictionary for the new reinforcement learning feedback table `PIO_COLL_AI_RL_FEEDBACK`.

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
