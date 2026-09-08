# Phase 3 — Contextual Bandit (Reinforcement Learning)

Status: **Planning — not yet implemented.** This document is the source of
truth for assumptions, stack, data model, and design decisions for
replacing the static heuristic in `src/engine/nba/bandit.py` with a real
online-learning contextual bandit. Every claim below was verified directly
against the live system (code + live Oracle DB) on 2026-09-06, not taken
from memory or prior docs alone.

**Revision note (2026-09-06):** the original draft of this document used
Thompson Sampling segmented only by quadrant. That was revised to **LinUCB**
after review: quadrant-only segmentation is a coarse multi-armed bandit,
not a true contextual one — two customers in the same quadrant can have
very different channel responsiveness, and quadrant-only segmentation
can't tell them apart. §3 and §6 below reflect the LinUCB design; §2 was
extended with the additional schema verification LinUCB's feature vector
required.

---

## 1. Objective

Replace `ContextualBandit`'s hardcoded `_score_channel()` heuristic with a
policy that **learns from real outcomes, personalized per customer**, which
channel works best — not just per quadrant — while:

- Never bypassing the existing compliance guardrails (`RuleEngine`) —
  unchanged, still runs first, still hard-blocks excluded/capped channels.
- Never regressing safety below the current heuristic during rollout.
- Requiring zero changes once the DB team's real feedback-population
  procedure exists — we read `PIO_COLL_AI_RL_FEEDBACK` exactly as they
  will populate it; only the *source* of the rows changes (synthetic → real).

---

## 2. Current State — Verified Against the Live System

| Claim | Status | Evidence |
|---|---|---|
| `bandit.py`'s `ContextualBandit` is a pure heuristic (no learning) | **Confirmed** | `_score_channel()` — static point additions/subtractions based on quadrant + evasion/liquidity flags. No persisted state, no DB reads. |
| `RewardTracker` is an unused stub | **Confirmed** | `class RewardTracker: ... pass` — docstring describes Phase 3 intent, body is empty. |
| `PIO_COLL_AI_RL_FEEDBACK` already exists in the DB | **Confirmed** | Live query: table exists in **both** `BI_DWH` and `PIO_COLL` schemas, columns match `docs/DB_Schema.md` exactly, **0 rows**. |
| `docs/To_Do_List.md`'s `PIO_COLL_AI_NBA_FEEDBACK` table | **Stale reference — does not exist.** The real table is `PIO_COLL_AI_RL_FEEDBACK`. Treat the To-Do list as outdated on this point. |
| `PIO_COLL_AI_MATRIX_RESULTS` has `PRIMARY KEY (CUST_INFO_ID)` | **Stale — the DDL in `docs/DB_Schema.md` does not match reality.** Live query shows **no primary key constraint at all** on this table today, and it does carry `DAY_DATE`/`INST_CODE`/`COUNTRY_CODE` (nullable) that the stale DDL snippet omits entirely. Not something this phase fixes; the design below avoids depending on this table. |
| `PIO_COLL_AI_NBA_ACTIONS` real data shape | **Verified 2026-09-06**: 10,000 rows across 2 `DAY_DATE`s (2026-05-18, 2026-08-27), 5,000 each, and **does** retain both (MERGE-based, not truncated). **1,495 rows excluded** (`RECOMMENDED_CHANNEL='None'`, Special Handling — must never get RL_FEEDBACK rows). Of the remaining 8,505: **~75% are Q4**; Q1 has only 29 total rows; some quadrant×channel cells as thin as 2–4 rows. |
| `PIO_CUSTOMERS.AGE` / `PIO_ACCOUNTS.DATE_OPEN` (as literally named in the LinUCB feature request) | **Exist, but are the wrong tables to join.** `BI_DWH.PIO_CUSTOMERS` (500+ columns) and `BI_DWH.PIO_ACCOUNTS` (300+ columns) are raw core-banking source tables keyed by `CUS_NUM`, not `CUST_INFO_ID` — joining them directly would be the first raw-source dependency anywhere in this pipeline (everything else reads only curated `PIO_COLL_AI_*` marts). |
| A cleaner source exists for both | **Confirmed** | `PIO_COLL.PIO_CUSTOMERS_INFO` — the curated, AI-facing customer table already referenced in `schemas.py`'s docstring ("PIO_COLL.PIO_CUSTOMERS_INFO.ID") — has **`AGE` (NUMBER) directly**, keyed by `ID` = `CUST_INFO_ID`. And `PIO_COLL_AI_NBA_CONTEXT_MART` already has **`ACCOUNT_OPEN_DATE`** (already flowing through `get_nba_context_data()` today) — no need to touch `PIO_ACCOUNTS` at all for account tenure. |
| `PIO_COLL_AI_NBA_CONTEXT_MART` / `PIO_COLL_AI_WILLINGNESS_MART` retain history like `NBA_ACTIONS` does | **Not currently true in this dev environment.** Both marts show only **one** `DAY_DATE` (2026-08-27, 5,000 rows each) — `scripts/generate_synthatic_data.py` `TRUNCATE`s them before every seed run. `NBA_ACTIONS`/`MATRIX_RESULTS` don't get truncated (they're MERGE-upserted), which is why they retain both dates. See §5.4 for how this is handled. |
| `PIO_COLL.PIO_CUSTOMERS_INFO.ID` values line up with the AI marts' `CUST_INFO_ID` | **Selectable, but zero overlap in this environment.** `BI_DWH` can `SELECT` from `PIO_COLL.PIO_CUSTOMERS_INFO` (43,391 real rows, real ages like 41/45/51). But its `ID`s are real customer IDs (e.g. `'01855397'`) while the AI marts are seeded by `scripts/generate_synthatic_data.py` with random 8-digit `CUST_INFO_ID`s that don't correspond to any real customer — **0 of 5,000** mart customers match. `AGE` will be `NULL` for every row via this join in dev/test; not a bug, just a consequence of synthetic test data having no relationship to the real customer table. Production `CUST_INFO_ID`s populated by the DB team's real ETL will match correctly. Handled with the same null-fallback convention as `DAYS_SINCE_LAST_RPC` (§5.2): fill with a neutral default (`40`) rather than erroring. |

---

## 3. Decisions

| Decision | Chosen | Rejected / superseded alternative | Why |
|---|---|---|---|
| Algorithm | **LinUCB** — disjoint linear ridge-regression model per channel arm, scored on a per-customer context vector | ~~Thompson Sampling segmented by quadrant~~ (original draft) | Quadrant-only segmentation can't distinguish two customers in the same quadrant with different real responsiveness — that's a multi-armed bandit with 4 buckets, not a *contextual* one. LinUCB personalizes via the full feature vector. Pure linear ridge regression over a small (d≈13) vector runs in tens of milliseconds for 100k+ customers on CPU via vectorized NumPy — no GPU, no new dependency. |
| Context feature vector `x` | 13 dimensions, all from data already verified to exist (§2, §6.2) — no raw source-table joins, no niche/clickstream telemetry | `PIO_CUSTOMERS`/`PIO_ACCOUNTS` raw joins (as literally specified) | Same information (`AGE`, account tenure) is available from `PIO_COLL.PIO_CUSTOMERS_INFO` and the already-integrated `PIO_COLL_AI_NBA_CONTEXT_MART.ACCOUNT_OPEN_DATE` — no new raw-table dependency, no "which account" ambiguity for multi-account customers. |
| Action space | **Channel only** — one linear model per channel (5 arms: SMS, Email, Outgoing Call, Dunning Letter, Field Visit), pruned per-customer by the existing guardrails exactly as today | Channel × Treatment jointly | Unchanged from the original decision — treatment has never varied dynamically; keeping arms at 5 (not up to 20) keeps each arm's training data denser given the sample sizes in §2. |
| Treatment selection | **Unchanged** — stays deterministic via `_select_treatment(quadrant)` | RL-selected treatment | Kept intact per explicit instruction. |
| Rollout safety | **Unchanged** — three-mode `NBA_POLICY_MODE`: `HEURISTIC` (default) / `SHADOW` (LinUCB computes + logs its pick, heuristic still drives `recommended_channel`) / `LIVE` | Ship straight to `LIVE` | Kept intact per explicit instruction; mirrors the Shadow Mode pattern already used for SHAP (`shadow_runner.py`). |
| Synthetic feedback scope | **Unchanged** — real `PIO_COLL_AI_NBA_ACTIONS` rows (grounded) + opt-in `--topup` for thin cells | — | Kept intact per explicit instruction; mechanics adjusted in §5.4 for what LinUCB's context requirement means for top-up rows. |
| Reward attribution | **Unchanged** — always `ACTUAL_CHANNEL_USED`, never `AI_RECOMMENDED_CHANNEL` | — | Kept intact; standard off-policy-contamination avoidance, applies identically whether the arm's model is a Beta posterior or a ridge regression. |
| Cold start | Each arm's `A_a`/`b_a` seeded with **pseudo-observations built from the heuristic score at that quadrant's mean context vector** (§6.3) — the LinUCB analogue of the Beta-prior seeding in the original draft | Zero/uninformative prior (`A_a = λI`, `b_a = 0`) | A cold, uninformed LinUCB would explore near-uniformly among arms at first — exactly the "Cold-Start Safety Hazard" `docs/nba_lifecycle_walkthrough.md` warns against (random Field Visit to a cooperative Q1 customer, random Email to an evasive Q4 one). Seeding preserves the same safety property the original design had, translated to linear-regression terms. |
| Context source for historical feedback rows | **Current mart snapshot**, joined on `(CUST_INFO_ID, INST_CODE, COUNTRY_CODE)` only — **not** an exact `DAY_DATE` match | Exact point-in-time historical context per feedback row | **New assumption, forced by §2's finding.** `NBA_CONTEXT_MART`/`WILLINGNESS_MART` don't currently retain per-`DAY_DATE` history in this environment, so the context *as it truly was* at old decision times isn't reconstructable. Using the latest known context as a proxy is standard practice when true historical snapshots aren't available, and degrades gracefully: if production's marts *do* retain full `DAY_DATE` history (their schema — `SNAPSHOT_DATE` + `DAY_DATE` columns — suggests they're designed to), tightening this join to an exact date match is a one-line change, not a redesign. |

---

## 4. Tech Stack

**No new dependencies**, exactly as before — LinUCB doesn't change this:

| Need | Library | Already present? |
|---|---|---|
| Ridge regression matrices, inversion, vectorized scoring | `numpy` (`np.linalg.inv`, vectorized `@`/`einsum`) | Yes |
| Feature/posterior aggregation from DB rows | `polars` | Yes |
| DB reads/writes | `oracledb` | Yes |
| Schema validation | `pydantic` | Yes (already used throughout `src/engine/nba/schemas.py`) |
| Synthetic data generation | `random` (stdlib) | Matches `scripts/generate_synthatic_data.py` / `scripts/generate_test_data.py` conventions |

No model artifact is trained or saved to `models/`. Each arm's `(A_a, b_a)`
is recomputed from `PIO_COLL_AI_RL_FEEDBACK` (joined to the marts for
context) at the start of each pipeline run — a few thousand rows × 5 arms
× 13-dimensional vectors, trivial on CPU. The database remains the single
source of truth; there is no separate model file to version or go stale.

---

## 5. Data Model

### 5.1 `PIO_COLL_AI_RL_FEEDBACK` (already live — do not alter)

```sql
CREATE TABLE PIO_COLL_AI_RL_FEEDBACK (
    DAY_DATE                DATE            NOT NULL,
    INST_CODE               VARCHAR2(10)    NOT NULL,
    COUNTRY_CODE            VARCHAR2(10)    NOT NULL,
    CUST_INFO_ID            VARCHAR2(50)    NOT NULL,
    AI_RECOMMENDED_CHANNEL  VARCHAR2(50)    NOT NULL,
    AGENT_OVERRIDE_FLAG     NUMBER(1)       NOT NULL,
    OVERRIDE_REASON_CODE    VARCHAR2(100)       NULL,
    ACTUAL_CHANNEL_USED     VARCHAR2(50)    NOT NULL,
    CUSTOMER_OUTCOME        VARCHAR2(50)    NOT NULL,
    BANDIT_REWARD_SCORE     NUMBER(5, 2)        NULL,
    CREATED_AT              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT PK_COLL_AI_RL_FEEDBACK
        PRIMARY KEY (DAY_DATE, INST_CODE, COUNTRY_CODE, CUST_INFO_ID),
    CONSTRAINT CHK_RL_FEEDBACK_OVERRIDE
        CHECK (AGENT_OVERRIDE_FLAG IN (0, 1))
);
```

Confirmed live in both `BI_DWH.PIO_COLL_AI_RL_FEEDBACK` and
`PIO_COLL.PIO_COLL_AI_RL_FEEDBACK`. This phase reads/writes `BI_DWH.*`
exclusively, matching every other table access in `repository.py`.

**`CUSTOMER_OUTCOME` — finalized enum for this phase:**

| Value | Reward (`BANDIT_REWARD_SCORE`) | LinUCB target `r` |
|---|---|---|
| `PAID_IN_FULL` | +1.00 | +1.00 |
| `KEPT_PTP` | +0.70 | +0.70 |
| `RESTRUCTURE_AGREED` | +0.60 | +0.60 |
| `BROKEN_PTP` | -0.50 | -0.50 |
| `IGNORED` | -1.00 | -1.00 |

`RESTRUCTURE_AGREED` is new relative to the 4 examples in `docs/DB_Schema.md`
(explicitly "e.g.", non-exhaustive) — added because it's the exact scenario
`docs/Main_Goal.md` calls out: *"a customer negotiates a Restructuring
Plan... they are 100% Willing, even if they haven't paid a dime yet."* The
same logic applies to reward shaping.

Unlike the Beta-Bernoulli design, LinUCB's ridge regression regresses
directly on the **continuous** reward value above — no binarization needed;
`BANDIT_REWARD_SCORE` *is* the training target `r` for `b_a += r · x`.

### 5.2 Context Feature Vector (`x`) — 13 dimensions

| # | Feature | Source | Notes |
|---|---|---|---|
| 1 | Intercept | constant `1.0` | standard ridge-regression bias term |
| 2 | `TOTAL_DUE` | `PIO_COLL_AI_NBA_CONTEXT_MART` | scaled `/50_000`, clipped `[0,1]` |
| 3 | `DAYS_PAST_DUE` | `PIO_COLL_AI_NBA_CONTEXT_MART` | scaled `/180`, clipped `[0,1]` |
| 4 | `CONTACT_AVOIDANCE_INDEX` | `PIO_COLL_AI_NBA_CONTEXT_MART` | already `[0,1]`, used as-is |
| 5 | `SMS_SENT_THIS_WEEK` | `PIO_COLL_AI_NBA_CONTEXT_MART` | scaled `/3` (reuses `CollectionGuardrails.max_sms_per_week`) |
| 6 | `DAYS_SINCE_LAST_RPC` | `PIO_COLL_AI_WILLINGNESS_MART` | nullable → fill with `180` (never contacted ≈ "a long time"), then scale `/180`, clip `[0,1]` |
| 7 | `PTP_RELIABILITY_RATIO` | `PIO_COLL_AI_WILLINGNESS_MART` | already `[0,1]` |
| 8 | `AGE` | `PIO_COLL.PIO_CUSTOMERS_INFO` | nullable in dev/test (§2 — no ID overlap with synthetic marts) → fill with `40`, then scale `/100`, clip `[0,1]` |
| 9 | `ACCOUNT_TENURE_DAYS` | `PIO_COLL_AI_NBA_CONTEXT_MART.ACCOUNT_OPEN_DATE` (as `snapshot_date − ACCOUNT_OPEN_DATE`) | scaled `/3650` (10y), clipped `[0,1]` |
| 10–13 | Quadrant one-hot (`Q1`,`Q2`,`Q3`,`Q4`) | `PIO_COLL_AI_NBA_ACTIONS.DECISION_REASON` (historical) or `CustomerState.current_quadrant` (live scoring) | exactly one of the four is `1.0` |

Fixed-range scaling (rather than a fitted/persisted `StandardScaler`) is
used deliberately: it needs no additional state to save/version, and the
bounds above are the same ones already used elsewhere in this codebase
(e.g. `max_sms_per_week=3` from `guardrails.py`, the `$50,000` ceiling
mirrors `min_due_for_field_visit`'s order of magnitude). Null-handling for
`DAYS_SINCE_LAST_RPC` reuses the same "fill and proceed" convention already
used in `get_willingness_training_data()`.

### 5.3 Relationship to `PIO_COLL_AI_NBA_ACTIONS`

`PIO_COLL_AI_RL_FEEDBACK` does not store quadrant. The ingestion query
joins to `PIO_COLL_AI_NBA_ACTIONS` on `(DAY_DATE, INST_CODE, COUNTRY_CODE,
CUST_INFO_ID)` — this key **is** exact-date-matched, unlike the mart join in
§5.4, because `NBA_ACTIONS` *does* retain full history (§2) — and extracts
quadrant from `DECISION_REASON` via `REGEXP_SUBSTR(DECISION_REASON,
'Q[0-9]')`.

### 5.4 Context join for historical feedback rows

Per §3's new assumption: numeric context features (§5.2, items 2–9) are
pulled from the **current** `PIO_COLL_AI_NBA_CONTEXT_MART` /
`PIO_COLL_AI_WILLINGNESS_MART` / `PIO_COLL.PIO_CUSTOMERS_INFO` snapshot for
that customer, joined on `(CUST_INFO_ID, INST_CODE, COUNTRY_CODE)` only —
quadrant (§5.3) is the one piece of context still recovered exactly
historically, since `NBA_ACTIONS` retains it per-date.

### 5.5 Synthetic data writes (this phase only)

| Mode | Tables written | Description |
|---|---|---|
| Default | `PIO_COLL_AI_RL_FEEDBACK` only | One feedback row per existing, non-excluded `PIO_COLL_AI_NBA_ACTIONS` row (~8,505 rows). Context for training is read live via the §5.4 join — no extra writes needed for this part. |
| `--topup` (opt-in) | `PIO_COLL_AI_RL_FEEDBACK` **and** `PIO_COLL_AI_NBA_ACTIONS` | For quadrant×channel cells below a configurable sample floor (`RL_MIN_SAMPLES`, default 30), synthesizes additional rows for **real, existing customers** from that quadrant, under **new backdated `DAY_DATE`s** (avoids PK collision). Because context is read from the *current* mart snapshot regardless of `DAY_DATE` (§5.4), top-up rows need no separate fabricated mart data — they reuse the customer's real, current context vector. A matching `NBA_ACTIONS` row is still written per backdated date so quadrant recovery (§5.3) works for every row, real or top-up. Never invents new `CUST_INFO_ID`s. |

---

## 6. Bandit Design (LinUCB)

### 6.1 Arms

One disjoint linear model per channel: SMS, Email, Outgoing Call, Dunning
Letter, Field Visit — **5 arms total** (not per-quadrant; quadrant is now a
feature *inside* each arm's context vector, §5.2). Each arm `a` maintains:

- `A_a` — a `13×13` matrix (ridge-regularized design matrix), initialized `λI`
- `b_a` — a `13`-dimensional vector, initialized `0`

The `RuleEngine` guardrail pruning happens exactly as today, *before* the
bandit sees the customer — a legally-blocked arm for one customer doesn't
affect that arm's model.

### 6.2 Scoring

For an allowed channel `a` and customer context vector `x`:

```
theta_a = A_a^-1 @ b_a
score_a = theta_a^T @ x + alpha * sqrt(x^T @ A_a^-1 @ x)
```

`alpha` (exploration weight, `settings.RL_LINUCB_ALPHA`, default `1.0`)
controls the exploration/exploitation trade-off — standard LinUCB.

**Performance** (per the specification): `A_a^-1` is computed **once per
arm per pipeline run** (5 inversions of a 13×13 matrix — microseconds
total), during `RewardTracker.refresh()`, and cached alongside `theta_a`.
Scoring a customer against a cached `(theta_a, A_a^-1)` is a handful of
dot products — negligible even inside the existing row-by-row
`NBAOrchestrator.process_batch()` loop (no restructuring of that loop's
fault-isolation design is needed; the expensive `O(d^3)` step is the
one-time inversion, not per-customer scoring, which is `O(d^2)`).

### 6.3 Cold-start prior seeding

For each arm `a` (channel), for each quadrant `q`, compute the **mean real
context vector** `x̄_q` for customers currently in that quadrant (from the
live mart data — grounded in real portfolio statistics, not invented
numbers), and the heuristic's implied reward:

```
heuristic_score_q_a = ContextualBandit._score_channel(a, q, has_evasion=False, has_liquidity_crisis=False)  # 0-100
r0_q_a = (heuristic_score_q_a / 100) * 2 - 1   # rescale 0-100 heuristic score to the -1..+1 reward range from §5.1

M = settings.RL_PRIOR_STRENGTH   # default 20 (pseudo-observations per quadrant per arm)

A_a = lambda_reg * I + M * sum_q( x̄_q @ x̄_q^T )
b_a = M * sum_q( r0_q_a * x̄_q )
```

This is the direct LinUCB analogue of the Beta-prior seeding in the
original draft: before any real feedback exists, each arm's fitted `theta_a`
points toward what the heuristic already believed for a typical customer in
each quadrant, and the exploration bonus naturally shrinks as real,
personalized observations accumulate on top — preserving the Cold-Start
Safety Hazard mitigation the team has emphasized throughout this project
without hand-tuning a separate mechanism for it.

### 6.4 Update (once per pipeline run, before scoring)

1. Read `PIO_COLL_AI_RL_FEEDBACK` for the last `settings.RL_LOOKBACK_DAYS`
   (default 90) via `rl_feedback.sql`, joined per §5.3 (quadrant, exact
   date) and §5.4 (numeric context, current snapshot).
2. Build the context vector `x` (§5.2) for every feedback row.
3. For each row, with arm `a = ACTUAL_CHANNEL_USED` and reward `r =
   BANDIT_REWARD_SCORE`:
   ```
   A_a += x @ x^T
   b_a += r * x
   ```
   starting from the seeded `(A_a, b_a)` in §6.3.
4. Invert each `A_a` once, cache `theta_a = A_a^-1 @ b_a` for the batch.
5. Log each arm's real observation count (vs. `RL_MIN_SAMPLES`) for
   observability — not a hard gate; the seeded prior already keeps
   thin arms safe by design (§6.3).

### 6.5 Decision reason (audit trail)

- `HEURISTIC` mode (default, unchanged): `BANDIT:Q1|SOFT_TOUCH|EMAIL|PTP`
- `SHADOW` mode: heuristic still decides `recommended_channel`; the LinUCB
  pick and its score are appended for comparison, e.g.
  `BANDIT:Q1|SOFT_TOUCH|EMAIL|PTP|SHADOW_RL_PICK:SMS(score=0.62)`
- `LIVE` mode: `RL:Q1|LINUCB|EMAIL|PTP`

---

## 7. New / Changed Settings

Added to `Settings` (`src/core/config.py`), `.env.example`, and the
Configuration app's `env_io.py` schema (new "Reinforcement Learning"
section):

| Setting | Default | Purpose |
|---|---|---|
| `NBA_POLICY_MODE` | `HEURISTIC` | `HEURISTIC` / `SHADOW` / `LIVE` — see §3, §6.5 |
| `RL_LOOKBACK_DAYS` | `90` | Feedback window for `A_a`/`b_a` updates |
| `RL_PRIOR_STRENGTH` | `20` | Pseudo-observation weight of the heuristic cold-start prior (§6.3) |
| `RL_LINUCB_ALPHA` | `1.0` | Exploration weight in the UCB score (§6.2) |
| `RL_LINUCB_LAMBDA` | `1.0` | Ridge regularization strength (`A_a` initialization) |
| `RL_MIN_SAMPLES` | `30` | Logging/observability threshold, not a hard gate |

---

## 8. Non-Goals for This Phase (explicitly deferred)

- **Treatment as a learned action** — treatment selection stays exactly
  as today (§3).
- **Real reward-tracking procedure / DB team's DWH view** — out of scope;
  we read whatever lands in `PIO_COLL_AI_RL_FEEDBACK` regardless of who
  populates it (§1).
- **Phase 5 Champion/Challenger A/B routing** (`docs/To_Do_List.md`) —
  `NBA_POLICY_MODE=SHADOW` gives an interim, lower-effort comparison
  mechanism; the full hashing-based control-group split stays a later
  phase.
- **Fixing `PIO_COLL_AI_MATRIX_RESULTS`'s missing primary key** — flagged
  as a factual finding in §2, not addressed here.
- **Full historical point-in-time context reconstruction** — §3/§5.4's
  "current snapshot" assumption is a deliberate simplification, not a
  redesign of the marts.

## 9. Risks / Caveats

- **Sample sparsity**: some arms/quadrants will stay prior-dominated for a
  while under real traffic alone (e.g. Q1 today has 29 total observations)
  — inherent to the portfolio shape found in §2; `--topup` exists to
  exercise/demonstrate learning behavior in testing despite this.
- **Context staleness for historical rows** (§3, §5.4): using current
  context as a proxy for past context is an approximation. If it proves
  too coarse once real DB-team feedback starts arriving, tightening this
  requires the marts to retain `DAY_DATE` history (which their schema
  already supports) — not a redesign of the bandit itself.
- **No DB-level PK/uniqueness on `MATRIX_RESULTS`** (§2) — unrelated to
  this phase's correctness (we don't depend on that table) but worth the
  DB team's attention independently.
- **Feature scaling is fixed-range, not fitted** (§5.2) — reasonable given
  the bounds are grounded in existing business constants, but if the real
  portfolio's distribution shifts substantially (e.g. `TOTAL_DUE` regularly
  exceeds $50,000), the scaling constants in `.env`/`Settings` should be
  revisited; they are not hardcoded magic numbers buried in code.
