-- =============================================================================
-- DDL: Create PIO_COLL_AI_NBA_ACTIONS
--
-- Purpose: Stores the Next Best Action (NBA) recommendation for each
--   customer per business day. Consumed by the agent desktop worklist
--   to guide collector outreach.
--
-- Run this ONCE against the production database before deploying the
-- NBA pipeline for the first time.
-- =============================================================================

CREATE TABLE BI_DWH.PIO_COLL_AI_NBA_ACTIONS (
    DAY_DATE            DATE            NOT NULL,
    INST_CODE           VARCHAR2(10)    NOT NULL,
    COUNTRY_CODE        VARCHAR2(10)    NOT NULL,
    CUST_INFO_ID        VARCHAR2(50)    NOT NULL,
    RECOMMENDED_CHANNEL VARCHAR2(100)   NOT NULL,   -- e.g. 'Email', 'SMS', 'Outgoing Call'
    RECOMMENDED_OFFER   VARCHAR2(200)   NOT NULL,   -- e.g. 'PTP', 'Scheduling and Structuring'
    DECISION_REASON     VARCHAR2(500)   NOT NULL,   -- Audit trail, e.g. 'BANDIT:Q1|SOFT_TOUCH|EMAIL|PTP'
    CREATED_AT          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UPDATED_AT          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP NOT NULL,
    --
    CONSTRAINT PK_COLL_AI_NBA_ACTIONS
        PRIMARY KEY (DAY_DATE, INST_CODE, COUNTRY_CODE, CUST_INFO_ID)
);

-- Index for agent desktop lookup by customer
CREATE INDEX IDX_NBA_ACTIONS_CUST
    ON BI_DWH.PIO_COLL_AI_NBA_ACTIONS (CUST_INFO_ID, DAY_DATE);

COMMENT ON TABLE  BI_DWH.PIO_COLL_AI_NBA_ACTIONS                    IS 'Daily NBA recommendations produced by the Collection AI Phase 2 engine.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_ACTIONS.DAY_DATE           IS 'Business date (SNAP_DATE) for which the recommendation applies.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_ACTIONS.RECOMMENDED_CHANNEL IS 'Outbound channel selected by the Bandit or compliance guardrail.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_ACTIONS.RECOMMENDED_OFFER  IS 'Treatment/offer selected (PTP, Scheduling, Partial Payment, Special Handling).';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_NBA_ACTIONS.DECISION_REASON    IS 'Structured audit trail: BANDIT:<Q>|<POLICY>|<CHANNEL>|<TREATMENT> or EXCLUDED:<STATUS>.';
