# Collection AI - Banking Collection Batch Job

Production-ready ML system for predicting customer willingness and ability to pay in banking collection environments.

## Overview

Collection AI is a batch processing system that uses XGBoost models to score customers on two key dimensions:
- **Willingness to Pay** - Likelihood of keeping payment promises
- **Ability to Pay** - Financial capacity to make payments

The system supports two modes:
- **TRAIN** - Build and optimize ML models with hyperparameter tuning
- **SCORE** - Apply trained models to generate predictions for collections teams

## Quick Start

### 1. Setup Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Database & Settings

Edit `.env` file:

```bash
# Database Credentials
DB_USER=your_username
DB_PASSWORD=your_password
DB_DSN=host:port/service_name

# Execution Mode
MODE=SCORE  # Change to TRAIN for model training

# App Settings
DEBUG=True
BATCH_SIZE=1000

# Model Thresholds
WILLINGNESS_THRESHOLD=0.65
ABILITY_THRESHOLD=0.5
```

### 3. Run the Job

```bash
# From project root
python -m src.main
```

## Training Models

### Step 1: Set Training Mode

Update `.env`:
```bash
MODE=TRAIN
```

### Step 2: Run Training

```bash
python -m src.main
```

The training pipeline will:
1. Fetch raw data from database
2. Engineer target variable (`IS_WILLING`)
3. Optimize hyperparameters with Optuna (30 trials, 3-fold CV)
4. Train final XGBoost model
5. Log everything to MLflow
6. Save versioned model to `models/`

### Step 3: View Experiment Results

```bash
mlflow ui
```

Open browser to `http://localhost:5000` to view:
- All training runs and metrics (AUC, Precision, Recall)
- Hyperparameter comparisons
- Model artifacts

### Training Output

```
models/
├── willingness_v20260131_170523.json  # Versioned model
└── latest_willingness.json            # Pointer to latest {"latest": "willingness_v..."}
```

## Scoring (Inference)

### Step 1: Set Scoring Mode

Update `.env`:
```bash
MODE=SCORE
```

### Step 2: Run Batch Scoring

```bash
python -m src.main
```

**What Happens:**
1. Loads data from database
2. Loads latest trained model using pointer file
3. Generates predictions (XGBoost)
4. Caches results to `data/cache/willingness_scores_{YYYYMMDD}.parquet`
5. Prints SQL skeleton for database merge

### Scoring Output

```
data/cache/
└── willingness_scores_20260131.parquet  # ID + WILLINGNESS_SCORE only
```

**Parquet Schema:**
- `CUST_INFO_ID` or `ACCOUNT_ID` - Customer identifier
- `WILLINGNESS_SCORE` - Prediction probability (0.0-1.0)

### Next Steps (Manual)

The scorer caches predictions to Parquet. To load them into the database:

1. **Load Parquet to staging table** (external table or bulk insert)
2. **Execute MERGE** using the SQL skeleton printed by the scorer
3. **Verify** results in `COLLECTION_SCORES` table

## Project Structure

```
Collection-AI/
├── .env                    # Configuration (gitignored)
├── src/
│   ├── main.py            # Entry point - routes TRAIN/SCORE modes
│   ├── core/
│   │   ├── config.py      # Settings (loads from .env)
│   │   ├── logger.py      # Logging setup
│   │   └── taxonomy.py    # Error advisor
│   ├── database/
│   │   ├── connection.py  # Oracle connection pool (singleton)
│   │   ├── queries.py     # Query execution helpers
│   │   ├── repository.py  # Data persistence layer
│   │   └── features/      # SQL feature queries
│   │       ├── willingness.sql
│   │       └── ability.sql
│   ├── models/
│   │   ├── willingness/
│   │   │   ├── trainer.py # Willingness training pipeline
│   │   │   └── scorer.py  # Willingness inference engine
│   │   └── ability/
│   │       ├── trainer.py # Ability training pipeline
│   │       └── scorer.py  # Ability inference engine
│   └── engine/
│       └── matrix.py      # Score integration and quadrant assignment
├── models/                # Saved model artifacts
├── data/cache/            # Parquet prediction cache
└── mlruns/               # MLflow experiment tracking
```

## Key Technologies

| Component | Technology | Why? |
|-----------|-----------|------|
| **Data Processing** | Polars | 5-10x faster than pandas |
| **ML Engine** | XGBoost | Industry-standard gradient boosting |
| **Optimization** | Optuna | Efficient hyperparameter tuning |
| **Experiment Tracking** | MLflow | Reproducibility & model registry |
| **Database** | Oracle (oracledb) | Enterprise connection pooling |

## System Flow

### Complete Pipeline Overview

```
1. DATA EXTRACTION
   ├─ Fetch features: willingness.sql
   ├─ Fetch features: ability.sql
   └─ Load into Polars DataFrames

2. MODEL TRAINING (MODE=TRAIN)
   ├─ Willingness Model
   │  ├─ Target: IS_WILLING (payment behavior)
   │  ├─ Optuna: Minimize logloss
   │  └─ Save: models/willingness_v{timestamp}.json
   │
   └─ Ability Model
      ├─ Target: IS_STABLE (financial health)
      ├─ Optuna: Maximize AUC
      └─ Save: models/ability_v{timestamp}.json

3. BATCH SCORING (MODE=SCORE)
   ├─ Willingness Scorer
   │  ├─ Load: latest_willingness.json
   │  ├─ Predict: WILLINGNESS_SCORE
   │  └─ Cache: data/cache/willingness_scores_{date}.parquet
   │
   └─ Ability Scorer
      ├─ Load: latest_ability.json
      ├─ Predict: ABILITY_SCORE (with null fill)
      └─ Cache: data/cache/ability_scores_{date}.parquet

4. MATRIX INTEGRATION
   ├─ Join: Willingness + Ability (outer join, fill nulls with 0.0)
   ├─ Calculate: NBA_PRIORITY = (WILLINGNESS * 0.6) + (ABILITY * 0.4)
   ├─ Assign: CURRENT_QUADRANT (Q1/Q2/Q3/Q4)
   ├─ Log: Quadrant distribution
   └─ Persist: Bulk MERGE to COLLECTION_CUSTOMERS table
```

### Training Pipeline Details (`MODE=TRAIN`)

**Willingness Model:**
1. Data Extraction: Execute `willingness.sql`
2. Target Engineering: `IS_WILLING = 1 if (PTP_KEPT_COUNT > 0 OR TOTAL_PAYMENT_AMT > 0) else 0`
3. Optimization: Minimize logloss with Optuna (30 trials, 3-fold CV)
4. Search Space: eta (0.01-0.3), max_depth (3-10), subsample (0.5-1.0)
5. Training: XGBoost with best params
6. MLflow: Log params, metrics (AUC, Precision, Recall), model
7. Save: `models/willingness_v{YYYYMMDD_HHMMSS}.json` + pointer file

**Ability Model:**
1. Data Extraction: Execute `ability.sql`
2. Target Engineering: `IS_STABLE = 1 if (NSF_COUNT == 0 AND CASH_RUNWAY_MONTHS > 0.5 AND UTILIZATION_RATE < 1.0) else 0`
3. Optimization: Maximize AUC with Optuna (30 trials, 3-fold CV)
4. Search Space: eta (0.01-0.3), max_depth (3-8), subsample (0.6-1.0), colsample_bytree (0.6-1.0)
5. Training: XGBoost with best params
6. MLflow: Log params, metrics (AUC, Precision, Recall), model
7. Save: `models/ability_v{YYYYMMDD_HHMMSS}.json` + pointer file

### Scoring Pipeline Details (`MODE=SCORE`)

**1. Individual Model Scoring:**
- Each model (Willingness, Ability) generates predictions independently
- Results cached to Parquet: `data/cache/{model}_scores_{date}.parquet`
- Schema: `CUST_INFO_ID` + `{MODEL}_SCORE`

**2. Matrix Integration:**
- Load both Parquet files
- Outer join on `CUST_INFO_ID` (customers may exist in one model only)
- Fill missing scores with 0.0 for safety
- Calculate composite priority: `NBA_PRIORITY = (WILLINGNESS * 0.6) + (ABILITY * 0.4)`

**3. Quadrant Assignment:**
- Q1 (Ideal): Willingness > 0.5 AND Ability > 0.5
- Q2 (Vulnerable): Willingness > 0.5 AND Ability <= 0.5
- Q3 (Resistant): Willingness <= 0.5 AND Ability > 0.5
- Q4 (High Risk): Willingness <= 0.5 AND Ability <= 0.5

**4. Database Persistence:**
- Bulk MERGE operation to `COLLECTION_CUSTOMERS` table
- Updates: `willingness_score`, `ability_score`, `priority_score`, `current_quadrant`, `last_scored_at`
- Fault tolerant: Uses `executemany` with `batcherrors=True`

### Key Design Decisions

**Null Handling:** When a customer exists in only one model output, missing scores are filled with 0.0 to prevent calculation errors and ensure all customers are scored.

**Weighting Rationale:** NBA_PRIORITY uses 60% Willingness + 40% Ability because willingness is more actionable (behavioral change) while ability reflects structural constraints.

**Database Strategy:** All database operations use dynamically loaded SQL scripts rather than hardcoded queries for flexibility and maintainability.

## Troubleshooting

### Import Error: `ModuleNotFoundError: No module named 'src'`

**Solution**: Always run from project root using module syntax:
```bash
# Correct
python -m src.main

# Wrong
python src/main.py
```

### Database Connection Failed

Check `.env` credentials and DSN format:
```bash
DB_DSN=host:port/service_name  # Example: 192.168.1.10:1521/ORCL
```

### MLflow UI Not Starting

```bash
# Check if port 5000 is available
mlflow ui --port 5001
```

## Development Notes

- **Singleton Pattern**: Database connection uses singleton (`src.database.connection.db`)
- **Type Hints**: Full type annotations for better IDE support
- **Logging**: Structured logging via `src.core.logger`
- **Error Handling**: Custom `ErrorAdvisor` for diagnostic messages
- **SOLID Principles**: Clean separation of concerns

## License

Internal banking use only.