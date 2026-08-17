# Collection AI - Banking Collection Batch Job

Production-ready ML system for predicting customer **Willingness** and **Ability** to pay, and prescribing the **Next Best Action (NBA)** for each customer in banking collection environments.

## Overview

Collection AI is a batch processing system that combines two XGBoost models to prioritize collections strategy, then routes each customer to the right outreach channel and treatment via a compliance-aware AI decision engine:

1. **Willingness to Pay** — Likelihood of keeping payment promises / self-curing.
2. **Ability to Pay** — Financial capacity / liquidity to make payments.
3. **Next Best Action (NBA)** — Selects the optimal (channel, treatment) pair per customer, subject to regulatory guardrails.

High-level output is a **Matrix Quadrant (Q1–Q4)**, a **Priority Score**, and a **Recommended Action** — all stored in the database and consumed by the agent desktop worklist.

---

## Quick Start

### 1. Setup Environment

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration (`.env`)

```bash
# Database Credentials
DB_USER=BI_DWH
DB_PASSWORD=BI_DWH
DB_DSN=host:port/service_name

# App Settings
MODE=FULL             # TRAIN, SCORE, or FULL
MODEL_SCOPE=BOTH      # WILLINGNESS, ABILITY, or BOTH
SHAP_SCOPE=BOTH       # WILLINGNESS, ABILITY, BOTH, or NONE
DEBUG=True
BATCH_SIZE=1000

# Score Thresholds (used for Quadrant assignment)
WILLINGNESS_THRESHOLD=0.65
ABILITY_THRESHOLD=0.5
```

### 3. Seed the Database (First Run / Development Only)

Before running the pipeline for the first time in a development environment, seed the mart tables with synthetic data:

```bash
python scripts/generate_synthatic_data.py
```

> In **production**, the DB team populates the mart tables via their scheduled procedures. You do not run this script in production.

### 4. Run the Pipeline

```bash
# Run the complete Training -> Scoring -> Matrix -> NBA pipeline
python -m src.main
```

### 5. Run the Real-Time Narrative API (Lazy-Loading LLM)

This API lazy-loads 2-to-3 sentence executive summaries for collection officers in real-time by pulling the pre-processed `AI_PAYLOAD` from the database, running it through a local LLM, caching the output in `AI_NARRATIVE`, and returning it.

#### Prerequisites:

1. **LM Studio Setup**:
   - Download and run [LM Studio](https://lmstudio.ai/).
   - Download a local LLM (e.g., Llama 3, Mistral, or Qwen).
   - Start the **Local Inference Server** on port `1234` (the default).
   - Ensure the server is running and a model is loaded.
2. **Environment Variables**:
   Update your `.env` file with your local model configuration:
   ```bash
   LLM_BASE_URL="http://localhost:1234/v1"
   LLM_MODEL_NAME="your-local-model-name-here" # e.g. "meta-llama-3-8b-instruct"
   LLM_API_KEY="lm-studio"
   ```

#### Start the API Server:

Use `uvicorn` to start the FastAPI server:

```bash
.\.venv\Scripts\python.exe -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

#### Test the LLM Generation:

Open your browser or run a `curl` request to fetch a narrative. The endpoint expects the customer ID, country code, institution code, and snapshot date as query parameters:

```bash
curl -X GET "http://localhost:8000/customer/123/narrative?country_code=400&inst_code=1&day_date=2026-05-17"
```

- **First Call**: Fetches the payload, invokes the local LLM using the strict guardrails in `llm_system_prompt.md`, caches the result back in Oracle as a `CLOB`, and returns `status: "GENERATED"`.
- **Subsequent Calls**: Instantaneous, pulling directly from the cached database field, returning `status: "CACHED"`.

---

## System Architecture

### 1. Data Marts (Oracle)

The system reads exclusively from mart tables maintained by the DB team. As a data science team, we are fully isolated from the underlying source system complexity.

| Table                            | Purpose                                  | Key Columns                                                                                                              | Target Variable        |
| -------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------------------- |
| `PIO_COLL_AI_WILLINGNESS_MART` | Willingness model features + NBA context | RPC Recency, PTP Reliability, Payment Velocity,**ACCOUNT_STATUS, TOTAL_DUE, SMS_SENT_THIS_WEEK, CALLS_MADE_TODAY** | `TARGET_WILLINGNESS` |
| `PIO_COLL_AI_ABILITY_MART`     | Ability model features                   | Cash Runway, Spending Volatility, NSF Rate                                                                               | `TARGET_ABILITY`     |

> **Note for DB team:** The `PIO_COLL_AI_WILLINGNESS_MART` table was extended with 4 NBA context columns. See `src/database/features/ddl_willingness_mart_nba_columns.sql` for the ALTER TABLE script.

### 2. Execution Pipeline (`src.main`)

When running in `MODE=FULL`, the system executes 5 sequential steps:

#### Step A — Train Willingness Model

- Fetches data from `PIO_COLL_AI_WILLINGNESS_MART`.
- Trains XGBoost Classifier (binary:logistic) with Optuna hyperparameter tuning.
- Excludes `TARGET_WILLINGNESS` and `SNAPSHOT_DATE` from features.
- Saves artifact: `models/willingness_v{timestamp}.json`.

#### Step B — Train Ability Model

- Fetches data from `PIO_COLL_AI_ABILITY_MART`.
- Trains XGBoost Classifier with Optuna hyperparameter tuning.
- Excludes `TARGET_ABILITY` and `SNAPSHOT_DATE` from features.
- Saves artifact: `models/ability_v{timestamp}.json`.

#### Step C — Score & Matrix Integration

- Loads latest models, generates `WILLINGNESS_SCORE` and `ABILITY_SCORE` (0–1).
- Caches scores to `data/cache/*.parquet`.
- Joins both caches on `CUST_INFO_ID`.
- Calculates `NBA_PRIORITY = (WILLINGNESS * 0.6) + (ABILITY * 0.4)`.
- Assigns **Quadrants (Q1–Q4)**.
- Persists results to `BI_DWH.PIO_COLL_AI_MATRIX_RESULTS` via MERGE.

#### Step D — SHAP Explainability

- Runs SHAP for configured scopes (`SHAP_SCOPE`).
- Inserts top-3 feature contributions per customer to the DWH.

#### Step E — NBA Engine *(Phase 2)*

- Takes the Matrix output DataFrame directly (no extra DB read).
- **Guardrails** (`RuleEngine`): Deterministically filters the allowed channel set per customer — exclusion check (Deceased, Legal, etc.) then channel-ceiling pruning (SMS cap, call cap, minimum-due thresholds).
- **Bandit** (`ContextualBandit`): Selects the optimal channel + treatment from the allowed set using a quadrant-based heuristic policy.
- Persists recommendations to `BI_DWH.PIO_COLL_AI_NBA_ACTIONS` via MERGE.

> **Fault isolation:** A failure in Step E never corrupts the already-committed Matrix results. Each step has its own error boundary.

### 3. Quadrant Logic & Collection Strategy

| Quadrant     | Name                             | Logic                                 | Profile                                      | NBA Action                                                                  |
| ------------ | -------------------------------- | ------------------------------------- | -------------------------------------------- | --------------------------------------------------------------------------- |
| **Q1** | **Ideal (Self-Cure)**      | Willingness > 0.5 AND Ability > 0.5   | *"I want to pay, and I have the money."*   | **Light Touch**: Cheapest channel (Email/SMS) + PTP commitment.       |
| **Q2** | **Vulnerable (Hardship)**  | Willingness > 0.5 AND Ability ≤ 0.5  | *"I want to pay, but I am broke."*         | **Restructure**: Cheapest channel + Scheduling/Restructuring plan.    |
| **Q3** | **Resistant (Strategic)**  | Willingness ≤ 0.5 AND Ability > 0.5  | *"I have the money, but I refuse to pay."* | **Firm Escalation**: Most aggressive available channel + PTP.         |
| **Q4** | **High Risk (Lost Cause)** | Willingness ≤ 0.5 AND Ability ≤ 0.5 | *"No money, and I'm hiding."*              | **Hard Escalation**: Most aggressive channel + Partial Payment offer. |

### 4. NBA Channels & Treatments

**Channels (ordered by aggressiveness):**
Email → SMS → Outgoing Call → Dunning Letter → Field Visit

**Treatments:**
PTP (Promise to Pay) | Scheduling and Structuring | Partial Payment | Special Handling

**Guardrail Ceilings (default config):**

| Rule                           | Default |
| ------------------------------ | ------- |
| Max SMS per rolling 7 days     | 3       |
| Max outbound calls per day     | 1       |
| Minimum due for Dunning Letter | 500     |
| Minimum due for Field Visit    | 5,000   |

### 5. Output Tables (Oracle)

#### `BI_DWH.PIO_COLL_AI_MATRIX_RESULTS`

| Column                | Description                                                    |
| --------------------- | -------------------------------------------------------------- |
| `WILLINGNESS_SCORE` | Model probability of willingness (0–1).                       |
| `ABILITY_SCORE`     | Model probability of ability (0–1).                           |
| `PRIORITY_SCORE`    | Composite score for sorting worklists.                         |
| `CURRENT_QUADRANT`  | Q1: Ideal, Q2: Vulnerable, Q3: Resistant, Q4: High Risk.       |
| `MODEL_VERSION`     | Pointer to the model artifact files used for this scoring run. |

#### `BI_DWH.PIO_COLL_AI_NBA_ACTIONS` *(Phase 2)*

| Column                  | Description                                                        |
| ----------------------- | ------------------------------------------------------------------ |
| `RECOMMENDED_CHANNEL` | Selected outreach channel (e.g.,`Email`, `Outgoing Call`).     |
| `RECOMMENDED_OFFER`   | Selected treatment (e.g.,`PTP`, `Scheduling and Structuring`). |
| `DECISION_REASON`     | Structured audit trail (e.g.,`BANDIT:Q1\|SOFT_TOUCH\|EMAIL\|PTP`).  |

---

## Project Structure

```
Collection-AI/
├── .env                          # Secrets & Config
├── CHANGELOG.md                  # Daily development log
├── scripts/
│   └── generate_synthatic_data.py  # Dev-only: seed mart tables with synthetic data
├── src/
│   ├── main.py                   # Pipeline Orchestrator (5-step)
│   ├── core/                     # Config, Logging, Error Taxonomy, Validation
│   ├── database/
│   │   ├── connection.py         # Oracle connection pool
│   │   ├── repository.py         # Data access (upsert_matrix_results, upsert_nba_results)
│   │   ├── queries.py            # SQL file loader + snap_date resolver
│   │   └── features/             # SQL feature files & DDL scripts
│   │       ├── willingness.sql
│   │       ├── ability.sql
│   │       ├── ddl_nba_actions.sql               # CREATE TABLE for NBA output
│   │       └── ddl_willingness_mart_nba_columns.sql  # ALTER TABLE for NBA context columns
│   ├── models_engine/
│   │   ├── willingness/          # Trainer & Scorer
│   │   └── ability/              # Trainer & Scorer
│   ├── engine/
│   │   ├── matrix.py             # Score joining, quadrant assignment
│   │   └── nba/                  # Phase 2 — NBA Engine
│   │       ├── schemas.py        # Pydantic models (CustomerState, NBAOutput)
│   │       ├── guardrails.py     # Deterministic compliance rule engine
│   │       ├── bandit.py         # Contextual Bandit decision engine
│   │       └── orchestrator.py   # Batch controller wiring guardrails + bandit
│   └── explainability/           # SHAP shadow runner
├── models/                       # Saved JSON model artifacts & pointer files
└── data/cache/                   # Intermediate Parquet files (scoring cache)
```

---

## MLflow Integration

Track experiments, metrics, and model parameters:

```bash
mlflow ui
```

- **Metrics tracked**: AUC, Precision, Recall, LogLoss.
- **Parameters tracked**: XGBoost hyperparameters (depth, eta, etc.) tuned via Optuna.

---

## DDL Scripts (Run Once Per Environment)

Before first production deployment, execute these against the Oracle DB in order:

```bash
# 1. Create NBA actions output table
src/database/features/ddl_nba_actions.sql

# 2. Add NBA context columns to the willingness mart
src/database/features/ddl_willingness_mart_nba_columns.sql
```

---

## Troubleshooting

- **`ModuleNotFoundError: No module named 'src'`**: Run the main pipeline as a module from root: `python -m src.main`. For standalone scripts in `scripts/`, the `sys.path` injection at the top of each script handles this automatically.
- **Feature Mismatch Error**: Ensure `SNAPSHOT_DATE` and Target columns are excluded from `feature_cols` in `trainer.py` and `scorer.py`.
- **Database Error**: Check `repository.py` schema definitions match actual DB columns. If you added new mart columns, re-run the corresponding DDL script.
- **NBA Phase skipped**: Requires `MODE=SCORE` or `MODE=FULL`. NBA runs after Matrix Integration — if Matrix fails, NBA is also skipped (by design).
- **NBA Guardrails not firing**: Verify `ACCOUNT_STATUS`, `TOTAL_DUE`, `SMS_SENT_THIS_WEEK`, and `CALLS_MADE_TODAY` are populated in `PIO_COLL_AI_WILLINGNESS_MART` by the DB team procedures.
