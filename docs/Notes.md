# Database Schema & Data Dictionary

## Matrix Results Table

The final output table where Willingness and Ability scores are combined.

```sql
CREATE TABLE PIO_COLL_AI_MATRIX_RESULTS (
    CUST_INFO_ID        VARCHAR2(400) NOT NULL,
    WILLINGNESS_SCORE   NUMBER(5,4)   DEFAULT 0,
    ABILITY_SCORE       NUMBER(5,4)   DEFAULT 0,
    PRIORITY_SCORE      NUMBER(5,4)   DEFAULT 0,
    CURRENT_QUADRANT    VARCHAR2(2)   NOT NULL, -- E.g., '1', '2'
    LAST_SCORED_AT      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT PK_PIO_COLL_MATRIX PRIMARY KEY (CUST_INFO_ID)
);

COMMENT ON TABLE PIO_COLL_AI_MATRIX_RESULTS IS 'AI Team: Final output of the Willingness x Ability pipeline.';
COMMENT ON COLUMN PIO_COLL_AI_MATRIX_RESULTS.CURRENT_QUADRANT IS '1: Ideal, 2: Vulnerable, 3: Resistant, 4: High Risk';
```

---

## Ability Data Mart (`PIO_COLL_AI_ABILITY_MART`)

Data Mart serving the Ability-to-Pay (Financial Capacity) Model.
**Architecture:** Point-in-time snapshot design.

```sql
CREATE TABLE PIO_COLL_AI_ABILITY_MART (
    -- 1. IDENTIFIERS & TEMPORAL KEYS
    CUST_INFO_ID                  VARCHAR2(400)  NOT NULL,
    SNAPSHOT_DATE                 DATE           NOT NULL,
    
    -- 2. INCOME & CASHFLOW STABILITY
    INFLOW_VARIANCE_30D           NUMBER(15,2)  DEFAULT 0,    -- StdDev of credits
    CASH_RUNWAY_DAYS_ESTIMATED    NUMBER(10,2)  DEFAULT 0,    -- Balance / Daily Spend
    
    -- 3. SPENDING & LIABILITY
    SPENDING_VOLATILITY_CV_60D    NUMBER(5,4)   DEFAULT 0,    -- Coeff of Variation of debits
    DEBT_SERVICE_PROXY_RATIO      NUMBER(5,4)   DEFAULT 0,    -- Obligations / Income
    
    -- 4. DISTRESS SIGNALS (The "Red Flags")
    NSF_EVENT_RATE_60D            NUMBER(5,4)   DEFAULT 0,    -- Bounces / Total Attempts
    ZERO_BALANCE_DAYS_RATIO_30D   NUMBER(5,4)   DEFAULT 0,    -- Days at $0 / 30
    
    -- 5. THE TARGET VARIABLE (Ground Truth for Training)
    TARGET_ABILITY                NUMBER(1,0)   DEFAULT 0, 

    -- 6. SYSTEM METADATA
    CREATED_AT                    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT PK_PIO_COLL_AI_ABILITY PRIMARY KEY (CUST_INFO_ID, SNAPSHOT_DATE)
);
```

### Ability Data Dictionary

| Column | Description | ETL Logic (DB Team) |
|--------|-------------|---------------------|
| `SNAPSHOT_DATE` | Date the ETL ran | Insert system date (e.g., `TRUNC(SYSDATE)`) |
| `INFLOW_VARIANCE_30D` | StdDev of credit inflows (30d) | StdDev of all CREDIT transaction amounts over last 30 days. Exclude internal transfers. |
| `CASH_RUNWAY_DAYS_ESTIMATED` | Days until zero balance | Current Balance / Avg Daily Debit (spending) over last 30 days. |
| `SPENDING_VOLATILITY_CV_60D` | Spending Coeff. of Variation | StdDev of daily spending / Avg daily spending over last 60 days. |
| `DEBT_SERVICE_PROXY_RATIO` | Obligations / Income | Sum of fixed monthly loan/debt installments / Avg monthly income. |
| `NSF_EVENT_RATE_60D` | Bounced payment ratio | Count of NSF declines / Total payment attempts in last 60 days. |
| `ZERO_BALANCE_DAYS_RATIO_30D` | Days at $0 ratio | Count of days ending with balance <= 0 / 30. |
| `TARGET_ABILITY` | **LABEL** (Ground Truth) | **1** if payment >= Min_Due AND Zero NSF in 14 days AFTER snapshot. Else **0**. |

---

## Willingness Data Mart (`PIO_COLL_AI_WILLINGNESS_MART`)

Data Mart serving the Willingness-to-Pay XGBoost Model.
**Architecture:** Point-in-time snapshot design.

```sql
CREATE TABLE PIO_COLL_AI_WILLINGNESS_MART (
    -- 1. IDENTIFIERS & TEMPORAL KEYS
    CUST_INFO_ID              VARCHAR2(400)  NOT NULL,
    SNAPSHOT_DATE             DATE           NOT NULL,
    
    -- 2. INTERACTION & ENGAGEMENT (The "Reachability" features)
    DAYS_SINCE_LAST_RPC       NUMBER(10,0),               -- Can be NULL if never reached
    PTP_RELIABILITY_RATIO     NUMBER(5,4)   DEFAULT 0,    -- Kept PTPs / Total PTPs
    
    -- 3. PAYMENT BEHAVIOR (The "Momentum" features)
    PAYMENT_VELOCITY_30D      NUMBER(10,0)  DEFAULT 0,    -- Count of distinct payments
    PARTIAL_PAYMENT_RATIO     NUMBER(5,4)   DEFAULT 0,    -- Count(Pay < Due) / Total Payments
    SELF_CURE_HISTORY_FLAG    NUMBER(1,0)   DEFAULT 0,    -- 1 = Paid last cycle with 0 contact
    
    -- 4. RISK & DISTRESS (The "Friction" features)
    BOUNCE_RATE_60D           NUMBER(5,4)   DEFAULT 0,    -- Bounces / Total Attempts
    BROKEN_PTP_COUNT_6M       NUMBER(10,0)  DEFAULT 0,
    
    -- 5. THE TARGET VARIABLE (Ground Truth for Training)
    TARGET_WILLINGNESS        NUMBER(1,0)   DEFAULT 0, 

    -- 6. SYSTEM METADATA
    CREATED_AT                TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    
    -- COMPOSITE PRIMARY KEY
    CONSTRAINT PK_AI_WILLINGNESS_MART PRIMARY KEY (CUST_INFO_ID, SNAPSHOT_DATE)
);
```

### Willingness Data Dictionary

| Column | Description | ETL Logic (DB Team) |
|--------|-------------|---------------------|
| `SNAPSHOT_DATE` | Date the ETL ran | Insert system date (e.g., `TRUNC(SYSDATE)`). |
| `DAYS_SINCE_LAST_RPC` | Days since last Right Party Contact | Days between today and most recent RPC. NULL if never. |
| `PTP_RELIABILITY_RATIO` | Promise Keeping Ratio | `Sum(Kept_PTP) / Sum(All_PTP)`. |
| `PAYMENT_VELOCITY_30D` | Payment Frequency | Count of debt repayment transactions in last 30 days. |
| `PARTIAL_PAYMENT_RATIO` | Partial Payment Ratio | `Count(Payments < Min_Due) / Count(Total_Payments)` over last 90 days. |
| `SELF_CURE_HISTORY_FLAG` | Self-Cure Indicator | **1** if payment made in last 30d without prior contact. Else **0**. |
| `BOUNCE_RATE_60D` | NSF Rate | `Count(NSF) / Count(Total_Attempts)` over last 60 days. |
| `TARGET_WILLINGNESS` | **LABEL** (Ground Truth) | **1** if Silent Pay OR Promise Kept OR Restructure in 7 days AFTER snapshot. Else **0**. |