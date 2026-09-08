-- Phase 3 contextual bandit ingestion query.
-- See docs/phase3_contextual_bandit_rl.md sections 5.2-5.4 for the design.
--
-- Quadrant is recovered from PIO_COLL_AI_NBA_ACTIONS.DECISION_REASON,
-- exact-date-joined (NBA_ACTIONS retains full history via MERGE).
--
-- Numeric context features are read from the CURRENT snapshot of each
-- mart per customer (ROW_NUMBER ... ORDER BY DAY_DATE DESC = 1), not an
-- exact historical date match — PIO_COLL_AI_NBA_CONTEXT_MART and
-- PIO_COLL_AI_WILLINGNESS_MART do not currently retain per-day history in
-- this environment (verified 2026-09-06). This degrades gracefully: if a
-- mart later retains multiple DAY_DATEs per customer, this query already
-- picks the most recent one; tightening it to an exact date match is a
-- one-line change (add "AND ctx.DAY_DATE = f.DAY_DATE" etc.), not a
-- redesign.
--
-- PIO_COLL.PIO_CUSTOMERS_INFO.AGE will be NULL for synthetic test
-- customers (no ID overlap with the synthetic marts, verified 2026-09-06)
-- — expected in dev/test, resolved automatically once production
-- CUST_INFO_IDs are real customer IDs. Null-filled in Python, not here.

SELECT
    f.DAY_DATE,
    f.INST_CODE,
    f.COUNTRY_CODE,
    f.CUST_INFO_ID,
    f.AI_RECOMMENDED_CHANNEL,
    f.AGENT_OVERRIDE_FLAG,
    f.ACTUAL_CHANNEL_USED,
    f.CUSTOMER_OUTCOME,
    f.BANDIT_REWARD_SCORE,
    REGEXP_SUBSTR(a.DECISION_REASON, 'Q[0-9]') AS QUADRANT,
    ctx.TOTAL_DUE,
    ctx.DAYS_PAST_DUE,
    ctx.CONTACT_AVOIDANCE_INDEX,
    ctx.SMS_SENT_THIS_WEEK,
    ctx.ACCOUNT_OPEN_DATE,
    wm.DAYS_SINCE_LAST_RPC,
    wm.PTP_RELIABILITY_RATIO,
    cust.AGE
FROM BI_DWH.PIO_COLL_AI_RL_FEEDBACK f
JOIN BI_DWH.PIO_COLL_AI_NBA_ACTIONS a
    ON  a.DAY_DATE     = f.DAY_DATE
    AND a.INST_CODE    = f.INST_CODE
    AND a.COUNTRY_CODE = f.COUNTRY_CODE
    AND a.CUST_INFO_ID = f.CUST_INFO_ID
LEFT JOIN (
    SELECT
        CUST_INFO_ID, INST_CODE, COUNTRY_CODE,
        TOTAL_DUE, DAYS_PAST_DUE, CONTACT_AVOIDANCE_INDEX,
        SMS_SENT_THIS_WEEK, ACCOUNT_OPEN_DATE,
        ROW_NUMBER() OVER (
            PARTITION BY CUST_INFO_ID, INST_CODE, COUNTRY_CODE
            ORDER BY DAY_DATE DESC
        ) AS RN
    FROM BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART
) ctx
    ON  ctx.CUST_INFO_ID = f.CUST_INFO_ID
    AND ctx.INST_CODE    = f.INST_CODE
    AND ctx.COUNTRY_CODE = f.COUNTRY_CODE
    AND ctx.RN = 1
LEFT JOIN (
    SELECT
        CUST_INFO_ID, DAYS_SINCE_LAST_RPC, PTP_RELIABILITY_RATIO,
        ROW_NUMBER() OVER (
            PARTITION BY CUST_INFO_ID
            ORDER BY DAY_DATE DESC
        ) AS RN
    FROM BI_DWH.PIO_COLL_AI_WILLINGNESS_MART
) wm
    ON  wm.CUST_INFO_ID = f.CUST_INFO_ID
    AND wm.RN = 1
LEFT JOIN (
    SELECT
        ID, AGE,
        ROW_NUMBER() OVER (PARTITION BY ID ORDER BY DAY_DATE DESC) AS RN
    FROM PIO_COLL.PIO_CUSTOMERS_INFO
) cust
    ON  cust.ID = f.CUST_INFO_ID
    AND cust.RN = 1
WHERE f.DAY_DATE     >= TO_DATE(:cutoff_date, 'YYYY-MM-DD')
  AND f.INST_CODE     = :inst_code
  AND f.COUNTRY_CODE  = :country_code
