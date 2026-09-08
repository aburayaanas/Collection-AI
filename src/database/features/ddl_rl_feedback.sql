-- =============================================================================
-- DDL: Create PIO_COLL_AI_RL_FEEDBACK
--
-- Purpose: Captures the final agent action and customer outcome for each
--   NBA recommendation, used to train the Phase 3 contextual bandit
--   (see docs/phase3_contextual_bandit_rl.md). This table already exists
--   live (verified 2026-09-06, both BI_DWH and PIO_COLL schemas) — this
--   script exists so the schema is reproducible/documented like every
--   other table in this folder, not because it needs to be run again.
--
-- Populated today by scripts/generate_synthetic_rl_feedback.py against
-- real PIO_COLL_AI_NBA_ACTIONS rows. Once the DB team's real outcome-
-- tracking procedure exists, it can write to this exact same table with
-- zero pipeline changes required.
-- =============================================================================

CREATE TABLE BI_DWH.PIO_COLL_AI_RL_FEEDBACK (
    DAY_DATE                DATE            NOT NULL,
    INST_CODE               VARCHAR2(10)    NOT NULL,
    COUNTRY_CODE            VARCHAR2(10)    NOT NULL,
    CUST_INFO_ID            VARCHAR2(50)    NOT NULL,
    AI_RECOMMENDED_CHANNEL  VARCHAR2(50)    NOT NULL,   -- what PIO_COLL_AI_NBA_ACTIONS.RECOMMENDED_CHANNEL said
    AGENT_OVERRIDE_FLAG     NUMBER(1)       NOT NULL,   -- 1 if the agent used a different channel than recommended
    OVERRIDE_REASON_CODE    VARCHAR2(100)       NULL,   -- e.g. 'AGENT_JUDGMENT', 'CUSTOMER_REQUEST', 'FORCE_MAJEURE'
    ACTUAL_CHANNEL_USED     VARCHAR2(50)    NOT NULL,   -- the channel actually pulled - the bandit learns from THIS, not the recommendation
    CUSTOMER_OUTCOME        VARCHAR2(50)    NOT NULL,   -- PAID_IN_FULL / KEPT_PTP / RESTRUCTURE_AGREED / BROKEN_PTP / IGNORED
    BANDIT_REWARD_SCORE     NUMBER(5, 2)        NULL,   -- -1.00 .. +1.00, see map_outcome() in src/engine/nba/reward_tracker.py
    CREATED_AT              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP NOT NULL,
    --
    CONSTRAINT PK_COLL_AI_RL_FEEDBACK
        PRIMARY KEY (DAY_DATE, INST_CODE, COUNTRY_CODE, CUST_INFO_ID),
    CONSTRAINT CHK_RL_FEEDBACK_OVERRIDE
        CHECK (AGENT_OVERRIDE_FLAG IN (0, 1))
);

COMMENT ON TABLE  BI_DWH.PIO_COLL_AI_RL_FEEDBACK                        IS 'Agent action + customer outcome per NBA recommendation, feeding the Phase 3 contextual bandit.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_RL_FEEDBACK.ACTUAL_CHANNEL_USED    IS 'The channel actually pulled — reward is always attributed here, never to AI_RECOMMENDED_CHANNEL, to avoid off-policy contamination.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_RL_FEEDBACK.CUSTOMER_OUTCOME       IS 'PAID_IN_FULL | KEPT_PTP | RESTRUCTURE_AGREED | BROKEN_PTP | IGNORED.';
COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_RL_FEEDBACK.BANDIT_REWARD_SCORE    IS 'Reward mapped from CUSTOMER_OUTCOME; the LinUCB training target r for b_a += r * x.';
