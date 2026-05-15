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
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.ACCOUNT_STATUS
    IS 'Customer lifecycle status. Values: Active, Deceased, Disease, Legal, Transfer To Remedial.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.TOTAL_DUE
    IS 'Total outstanding balance. Drives field-visit (>=5000) and dunning (>=500) guardrails.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.SMS_SENT_THIS_WEEK
    IS 'Rolling 7-day SMS count. Guardrail blocks SMS when >= MAX_SMS_PER_WEEK (default: 3).';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART.CALLS_MADE_TODAY
    IS 'Calendar-day outbound call count. Guardrail blocks calls when >= MAX_CALLS_PER_DAY (default: 1).';
