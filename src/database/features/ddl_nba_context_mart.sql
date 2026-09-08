-- =============================================================================
-- DDL: Create PIO_COLL_AI_NBA_CONTEXT_MART
--
-- Purpose: Dedicated mart for NBA operational context columns.
--   Completely isolated from the ML feature marts (Willingness, Ability).
--   The DB team populates this table daily from:
--     - ACCOUNT_STATUS      ← PIO_COLL.PIO_CUSTOMERS_INFO
--     - TOTAL_DUE           ← PIO_ACCOUNT_DEALS_INFO (worst DPD bucket)
--     - SMS_SENT_THIS_WEEK  ← PIO_COLL activity/task tables (rolling 7 days)
--     - CALLS_MADE_TODAY    ← PIO_COLL activity/task tables (calendar day)
--
-- Design Principles:
--   1. No overlap with PIO_COLL_AI_WILLINGNESS_MART or ABILITY_MART.
--   2. Keyed on DAY_DATE + INST_CODE + COUNTRY_CODE + CUST_INFO_ID
--      to match the rest of the AI schema.
--   3. New NBA context needs → add columns here, not to the ML marts.
--
-- Run this ONCE against the production database before deploying.
-- =============================================================================

CREATE TABLE BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART (
    DAY_DATE                DATE            NOT NULL,
    INST_CODE               VARCHAR2(10)    NOT NULL,
    COUNTRY_CODE            VARCHAR2(10)    NOT NULL,
    CUST_INFO_ID            VARCHAR2(50)    NOT NULL,

    -- Customer lifecycle status — drives the exclusion guardrail
    ACCOUNT_STATUS          VARCHAR2(50)    DEFAULT 'Active'  NOT NULL,

    -- Outstanding balance across all delinquent accounts (worst DPD bucket)
    -- Drives field-visit (min 5,000) and dunning-letter (min 500) guardrails
    TOTAL_DUE               NUMBER(15, 2)   DEFAULT 0         NOT NULL,

    -- Rolling 7-day outbound SMS count — enforced against MAX_SMS_PER_WEEK ceiling
    SMS_SENT_THIS_WEEK      NUMBER(3)       DEFAULT 0         NOT NULL,

    -- Outbound call attempts today — enforced against MAX_CALLS_PER_DAY ceiling
    CALLS_MADE_TODAY        NUMBER(3)       DEFAULT 0         NOT NULL,

    -- Block 1 UI: KYC & Customer Identity Overview
    FULL_LEGAL_NAME         VARCHAR2(255)                     NULL,
    CUSTOMER_SEGMENT        VARCHAR2(100)                     NULL,
    NATIONALITY_RESIDENCY   VARCHAR2(100)                     NULL,
    EMPLOYER_NAME           VARCHAR2(255)                     NULL,
    VERIFIED_INCOME_JOD     NUMBER(15, 2)                     NULL,
    INCOME_LAST_VERIFIED_DATE DATE                            NULL,
    AML_LAST_SCREENED_DATE  DATE                              NULL,
    ACCOUNT_OPEN_DATE       DATE                              NULL,
    PRODUCTS_HELD           VARCHAR2(255)                     NULL,
    PRIMARY_PHONE           VARCHAR2(50)                      NULL,

    -- Block 2 UI: Matrix & Quadrant Classification
    SCORE_DELTA_90D         NUMBER(5)                         NULL,
    COMPOSITE_RISK_SCORE    NUMBER(5)                         NULL,
    DAYS_PAST_DUE           NUMBER(5)                         NULL,
    CLASSIFICATION_PROBABILITIES CLOB                         NULL,

    -- Block 3: Behavioral Signal Interpretation
    PAYMENT_REJECTION_FREQ  NUMBER(5)                         NULL,
    CONTACT_AVOIDANCE_INDEX NUMBER(5, 2)                      NULL,

    -- Audit
    CREATED_AT              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UPDATED_AT              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT PK_COLL_AI_NBA_CONTEXT_MART
        PRIMARY KEY (DAY_DATE, INST_CODE, COUNTRY_CODE, CUST_INFO_ID)
);

-- Index for NBA orchestrator lookup by customer + date
CREATE INDEX IDX_NBA_CONTEXT_CUST
    ON BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART (CUST_INFO_ID, DAY_DATE);

COMMENT ON TABLE  BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART
    IS 'Daily NBA operational context per customer. Isolated from ML feature marts. DB team owned.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.DAY_DATE
    IS 'Business snapshot date (YYYY-MM-DD) for which the NBA operational context applies.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.INST_CODE
    IS 'Financial institution / bank identifier code (e.g., 1).';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.COUNTRY_CODE
    IS 'Country ISO code (e.g., 400 for Jordan).';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.CUST_INFO_ID
    IS 'Unique customer identification key (CIF ID).';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.ACCOUNT_STATUS
    IS 'Customer lifecycle status. Values: Active, Deceased, Disease, Legal, Transfer To Remedial. Drives NBA exclusion guardrail.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.TOTAL_DUE
    IS 'Aggregated delinquent balance in JOD across worst DPD bucket. Drives guardrails (Field Visit >= 5000, Dunning >= 500 JOD).';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.SMS_SENT_THIS_WEEK
    IS 'Rolling 7-day outbound SMS count. Enforced against MAX_SMS_PER_WEEK frequency cap.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.CALLS_MADE_TODAY
    IS 'Calendar-day outbound call count. Enforced against MAX_CALLS_PER_DAY frequency cap.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.FULL_LEGAL_NAME
    IS 'Borrower full legal name for KYC display and personalized dunning outreach.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.CUSTOMER_SEGMENT
    IS 'Customer tier / employment classification (e.g., Mass retail / Salaried, SME, Premier).';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.NATIONALITY_RESIDENCY
    IS 'Borrower nationality and legal residency status (e.g., Jordanian / Resident).';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.EMPLOYER_NAME
    IS 'Verified employer name for income source tracing and employer stability assessment.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.VERIFIED_INCOME_JOD
    IS 'Customer verified monthly net income in JOD.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.INCOME_LAST_VERIFIED_DATE
    IS 'Date when income was last re-certified. Age > 12 months triggers KYC refresh warning.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.AML_LAST_SCREENED_DATE
    IS 'Date of most recent AML / PEP / Sanctions screening clearance.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.ACCOUNT_OPEN_DATE
    IS 'Date primary bank account was opened; drives relationship tenure calculation.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.PRODUCTS_HELD
    IS 'Comma-separated active banking products held (Credit card, Personal loan, Mortgage, Savings).';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.PRIMARY_PHONE
    IS 'Primary registered telephone number (masked on UI for data privacy compliance).';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.SCORE_DELTA_90D
    IS '90-day net change in Composite Risk Score. Positive = risk deterioration; Negative = risk improvement.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.COMPOSITE_RISK_SCORE
    IS 'Multi-factor risk index (0-100); higher score denotes higher collection distress.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.DAYS_PAST_DUE
    IS 'Worst days past due (DPD) across all active delinquent accounts.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.CLASSIFICATION_PROBABILITIES
    IS 'JSON CLOB storing primary, competing, and residual matrix quadrant confidences.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.PAYMENT_REJECTION_FREQ
    IS 'Count of bounced checks / direct debit rejections in last 180 days. Triggers liquidity disruption signal.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.CONTACT_AVOIDANCE_INDEX
    IS 'Ratio of unanswered/ignored contact attempts (0.0 to 1.0). At/above 0.60 triggers Evasive Pattern.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.TOTAL_EXPOSURE_JOD
    IS 'Total outstanding principal exposure across all facilities in JOD.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.CURRENT_ARREARS_JOD
    IS 'Immediate past-due arrears balance requiring immediate cash cure in JOD.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.ACCRUED_INTEREST_JOD
    IS 'Total accrued overdue interest and contractual finance charges in JOD.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.LATE_FEES_JOD
    IS 'Cumulative contractual late fees and administrative penalty charges in JOD.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.CREATED_AT
    IS 'Audit timestamp when the row was created.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.UPDATED_AT
    IS 'Audit timestamp when the row was last updated.';

-- =============================================================================
-- PROPOSED MIGRATION: Channel Historical & Estimated Response Rates
--
-- Factual baseline contact/response rates displayed in UI Block 04.
-- Outgoing Calls and Field Visits are ACTUAL historical calculations from CDR/Agent logs.
-- SMS, Email, and Dunning Letters are ESTIMATED benchmark rates.
-- =============================================================================
-- ALTER TABLE BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART ADD (
--     CALL_RESPONSE_RATE             NUMBER(5, 4)  NULL,  -- Actual Right Party Contact (RPC) rate (0.0000 to 1.0000)
--     FIELD_VISIT_RESPONSE_RATE      NUMBER(5, 4)  NULL,  -- Actual successful debtor contact rate in field (0.0000 to 1.0000)
--     SMS_ESTIMATED_RESPONSE_RATE    NUMBER(5, 4)  NULL,  -- Estimated SMS response/delivery rate (0.0000 to 1.0000)
--     EMAIL_ESTIMATED_RESPONSE_RATE  NUMBER(5, 4)  NULL,  -- Estimated Email open/response rate (0.0000 to 1.0000)
--     LETTER_ESTIMATED_RESPONSE_RATE NUMBER(5, 4)  NULL   -- Estimated formal demand letter response rate (0.0000 to 1.0000)
-- );
--
-- COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.CALL_RESPONSE_RATE
--     IS 'ACTUAL historical telephony RPC rate: answered RPC calls / total outbound calls over last 90D (0-1). Factual UI metric.';
-- COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.FIELD_VISIT_RESPONSE_RATE
--     IS 'ACTUAL historical field visit success rate: debtor met & served / total field visits over last 180D (0-1). Factual UI metric.';
-- COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.SMS_ESTIMATED_RESPONSE_RATE
--     IS 'ESTIMATED portfolio benchmark response rate for SMS dunning campaigns (0-1). Factual UI metric.';
-- COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.EMAIL_ESTIMATED_RESPONSE_RATE
--     IS 'ESTIMATED portfolio benchmark open/response rate for digital email dunning (0-1). Factual UI metric.';
-- COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.LETTER_ESTIMATED_RESPONSE_RATE
--     IS 'ESTIMATED portfolio benchmark cure/response rate for registered physical demand letters (0-1). Factual UI metric.';
