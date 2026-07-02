-- =============================================================================
-- DDL: Add NBA context columns to PIO_COLL_AI_WILLINGNESS_MART
--
-- Purpose: These 4 columns are the customer-level context the NBA guardrail
--   engine needs. In production the DB team populates them daily via their
--   procedures. The defaults ensure existing rows remain valid after the ALTER.
--
-- Run this ONCE against the database before re-running the seed script
-- and deploying the updated pipeline.
-- =============================================================================

ALTER TABLE PIO_COLL_AI_WILLINGNESS_MART
    ADD ACCOUNT_STATUS      VARCHAR2(50)    DEFAULT 'Active'  NOT NULL;

ALTER TABLE PIO_COLL_AI_WILLINGNESS_MART
    ADD TOTAL_DUE           NUMBER(15, 2)   DEFAULT 0         NOT NULL;

ALTER TABLE PIO_COLL_AI_WILLINGNESS_MART
    ADD SMS_SENT_THIS_WEEK  NUMBER(3)       DEFAULT 0         NOT NULL;

ALTER TABLE PIO_COLL_AI_WILLINGNESS_MART
    ADD CALLS_MADE_TODAY    NUMBER(3)       DEFAULT 0         NOT NULL;

-- Column comments for the DB team handover document
COMMENT ON COLUMN PIO_COLL_AI_WILLINGNESS_MART.ACCOUNT_STATUS
    IS 'Customer lifecycle status from PIO_COLL.PIO_CUSTOMERS_INFO. Drives NBA exclusion guardrail.';

COMMENT ON COLUMN PIO_COLL_AI_WILLINGNESS_MART.TOTAL_DUE
    IS 'Total outstanding balance across delinquent accounts (most-DPD). Drives field-visit / dunning thresholds.';

COMMENT ON COLUMN PIO_COLL_AI_WILLINGNESS_MART.SMS_SENT_THIS_WEEK
    IS 'Rolling 7-day SMS count from PIO_COLL activity tables. Enforced against MAX_SMS_PER_WEEK ceiling.';

COMMENT ON COLUMN PIO_COLL_AI_WILLINGNESS_MART.CALLS_MADE_TODAY
    IS 'Outbound call count today from PIO_COLL activity tables. Enforced against MAX_CALLS_PER_DAY ceiling.';
