# Collection AI - Banking Collection Batch Job

Production-ready ML system for predicting customer **Willingness** and **Ability** to pay in banking collection environments.

## Overview

Collection AI is a batch processing system that combines two XGBoost models to prioritize collections strategy:
1.  **Willingness to Pay** - Likelihood of keeping payment promises/self-curing.
2.  **Ability to Pay** - Financial capacity/liquidity to make payments.

High-level output is a **Matrix Quadrant** (1-4) and a **Priority Score** stored in the database.

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
DB_USER=your_username
DB_PASSWORD=your_password
DB_DSN=host:port/service_name

# App Settings
MODE=FULL             # TRAIN, SCORE, or FULL (Recommended)
MODEL_TYPE=WILLINGNESS # Not used in FULL mode
DEBUG=True
```

### 3. Run the Pipeline
```bash
# Run the complete Training -> Scoring -> Matrix pipeline
python -m src.main
```

---

## System Architecture

### 1. Data Marts (Oracle)

| Table | Purpose | Key Features | Target Variable |
|-------|---------|--------------|-----------------|
| `PIO_COLL_AI_WILLINGNESS_MART` | Willingness Model Data | RPC Recency, PTP Reliability, Payment Velocity | `TARGET_WILLINGNESS` |
| `PIO_COLL_AI_ABILITY_MART` | Ability Model Data | Cash Runway, Spending Volatility, NSF Rate | `TARGET_ABILITY` |

### 2. Execution Pipeline (`src.main`)

When running in `MODE=FULL`, the system executes:

1.  **Train Willingness Model**
    *   Fetches data from `PIO_COLL_AI_WILLINGNESS_MART`.
    *   Trains XGBoost Classifier (binary:logistic).
    *   Excludes `TARGET_WILLINGNESS` (Label) and `SNAPSHOT_DATE` from features.
    *   Saves artifact: `models/willingness_v{timestamp}.json`.

2.  **Train Ability Model**
    *   Fetches data from `PIO_COLL_AI_ABILITY_MART`.
    *   Trains XGBoost Classifier.
    *   Excludes `TARGET_ABILITY` (Label) and `SNAPSHOT_DATE` from features.
    *   Saves artifact: `models/ability_v{timestamp}.json`.

3.  **Score Willingness**
    *   Loads latest Willingness model.
    *   Generates `WILLINGNESS_SCORE` (0-1).
    *   Caches to `data/cache/willingness_scores_{date}.parquet`.

4.  **Score Ability**
    *   Loads latest Ability model.
    *   Generates `ABILITY_SCORE` (0-1).
    *   Caches to `data/cache/ability_scores_{date}.parquet`.

5.  **Matrix Integration**
    *   Joins Parquet caches on `CUST_INFO_ID`.
    *   Calculates `PRIORITY_SCORE` (0.6 * Willingness + 0.4 * Ability).
    *   Assigns **Quadrants (1-4)**.
    *   **Persists** results to `PIO_COLL_AI_MATRIX_RESULTS` table via MERGE.

### 3. Quadrant Logic & Strategy:

| Quadrant | Name | Logic | Profile Description | Standard Collection Action |
|----------|------|-------|---------------------|----------------------------|
| **1** | **Ideal (Self-Cure)** | Willingness > 0.5 <br> Ability > 0.5 | **"I want to pay, and I have the money."** <br> These customers are highly engaged and financially stable. They likely just forgot or had a temporary bank glitch. | **Light Touch**: Send an automated SMS or Email reminder with a payment link. Do not waste expensive human call center agents on them. |
| **2** | **Vulnerable (Hardship)** | Willingness > 0.5 <br> Ability ≤ 0.5 | **"I want to pay, but I am broke."** <br> These customers answer the phone and make promises, but their bank accounts are empty (high NSF, low cash runway). | **Restructure/Empathy**: Do not demand the full balance; they physically cannot pay it. Offer a 12-month payment plan, debt restructuring, or a hardship program. |
| **3** | **Resistant (Strategic)** | Willingness ≤ 0.5 <br> Ability > 0.5 | **"I have the money, but I refuse to pay you."** <br> These are "Ghost" or "Liar" profiles. They ignore calls or break promises, but your data shows their salary is hitting their account perfectly. | **Firm Escalation**: Assign to your most experienced, firmest human collectors. Use formal legal threats, credit bureau reporting warnings, or immediate escalation. |
| **4** | **High Risk (Lost Cause)** | Willingness ≤ 0.5 <br> Ability ≤ 0.5 | **"I have no money, and I'm hiding."** <br> They are entirely unresponsive and financially distressed. | **Skip / Sell**: Do not waste effort. Send to a third-party collection agency, initiate deep legal action (garnishment), or write off the debt. |

### 4. Output Table (`PIO_COLL_AI_MATRIX_RESULTS`)

| Column | Type | Description |
|--------|------|-------------|
| `WILLINGNESS_SCORE` | NUMBER | Model probability of willingness. |
| `ABILITY_SCORE` | NUMBER | Model probability of ability. |
| `PRIORITY_SCORE` | NUMBER | Composite score for sorting worklists. |
| `CURRENT_QUADRANT` | VARCHAR | **1**: Ideal, **2**: Vulnerable, **3**: Resistant, **4**: High Risk. |

---

## Project Structure

```
Collection-AI/
├── .env                    # Secrets & Config
├── src/
│   ├── main.py            # Pipeline Orchestrator
│   ├── core/              # Config, Logging, Error Handling
│   ├── database/          # Oracle Repo & SQL Feature Files
│   ├── models/            # XGBoost Trainers & Scorers
│   │   ├── willingness/
│   │   └── ability/
│   └── engine/
│       └── matrix.py      # Logic for combining scores & quadrants
├── models/                # Saved JSON models & pointer files
└── data/cache/            # Intermediate Parquet files
```

## MLflow Integration

Track experiments, metrics, and parameters:
```bash
mlflow ui
```
*   **Metrics**: AUC, Precision, Recall, LogLoss.
*   **Parameters**: XGBoost hyperparameters (depth, eta, etc.) tuned via Optuna.

## Troubleshooting

*   **Feature Mismatch Error**: Ensure `SNAPSHOT_DATE` and Target columns are excluded from `feature_cols` in `trainer.py` and `scorer.py`.
*   **ImportError**: Run as a module from root: `python -m src.main`.
*   **Database Error**: Check `repository.py` schema definitions match actual DB columns.