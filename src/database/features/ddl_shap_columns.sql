-- =============================================================================
-- DDL: Add SHAP explanation columns to PIO_COLL_AI_MATRIX_RESULTS
-- Target: openbi2 DWH, BI_DWH schema
--
-- Column format follows the AML_NEXT_DECISION pattern from
-- PIO_AML_CUSTOMERS (BI_DWH schema, openbi2 db).
--
-- Run ONCE:
--   sqlplus bi_dwh/***@openbi2 @ddl_shap_columns.sql
-- =============================================================================

ALTER TABLE BI_DWH.PIO_COLL_AI_MATRIX_RESULTS
ADD (
    -- Stores the formatted SHAP explanation string (business-friendly).
    -- Format:
    --   "The system scored this customer primarily based on the following factors:
    --    Broken promise ratio (42.9%),
    --    Right-party contact rate (28.7%),
    --    Recent contact attempts (17.0%)."
    SHAP_EXPLANATION    VARCHAR2(4000),

    -- Stores the human-readable feature descriptions (comma-joined).
    -- Format:
    --   "Ratio of broken promises to total promises...,
    --    Right-Party Contact rate...,
    --    Number of contact attempts in the last 30 days..."
    SHAP_DESCRIPTION    VARCHAR2(4000),

    -- Model type that produced this explanation ('WILLINGNESS' or 'ABILITY')
    SHAP_MODEL_TYPE     VARCHAR2(50),

    -- Technical SHAP values string for debugging / audit.
    -- Format: "PTP_BROKEN_RATIO: 42.9%; RPC_RATE: 28.7%; ATTEMPTS_LAST_30D: 17.0%"
    SHAP_RAW_FEATURES   VARCHAR2(4000),

    -- Timestamp when SHAP was computed
    SHAP_COMPUTED_DATE  DATE DEFAULT SYSDATE
);


-- ── Indexes for common access patterns ───────────────────────────────

CREATE INDEX BI_DWH.IDX_COLL_SHAP_CUSNUM
    ON BI_DWH.PIO_COLL_AI_MATRIX_RESULTS (CUST_INFO_ID, SHAP_COMPUTED_DATE);

CREATE INDEX BI_DWH.IDX_COLL_SHAP_MODEL
    ON BI_DWH.PIO_COLL_AI_MATRIX_RESULTS (SHAP_MODEL_TYPE);


-- ── Column comments ──────────────────────────────────────────────────

COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_MATRIX_RESULTS.SHAP_EXPLANATION
    IS 'Business-friendly SHAP explanation (AML_NEXT_DECISION format). '
       'Contains the expanded feature names with percentages.';

COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_MATRIX_RESULTS.SHAP_DESCRIPTION
    IS 'Comma-joined detailed descriptions explaining why each feature '
       'is significant for this customer''s score.';

COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_MATRIX_RESULTS.SHAP_MODEL_TYPE
    IS 'Model type: WILLINGNESS or ABILITY.';

COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_MATRIX_RESULTS.SHAP_RAW_FEATURES
    IS 'Technical SHAP string for audit: "FEATURE: XX.X%; ..." format.';

COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_MATRIX_RESULTS.SHAP_COMPUTED_DATE
    IS 'Timestamp when the SHAP computation was executed.';
