-- =============================================================================
-- DDL: Add MODEL_VERSION column to PIO_COLL_AI_MATRIX_RESULTS
--
-- Purpose: Track which model version produced each score, enabling:
--   1. Audit trail — regulators can trace any score to a specific model
--   2. Rollback — identify records scored by a bad model version
--   3. Champion-Challenger — compare performance across model versions
--
-- Run this ONCE against the production database before deploying the update.
-- =============================================================================

ALTER TABLE BI_DWH.PIO_COLL_AI_MATRIX_RESULTS
ADD (
    MODEL_VERSION VARCHAR2(100)   -- e.g., 'willingness_v20260220_164400'
);

-- Optional: backfill existing rows
-- UPDATE BI_DWH.PIO_COLL_AI_MATRIX_RESULTS
-- SET MODEL_VERSION = 'pre_versioning'
-- WHERE MODEL_VERSION IS NULL;

COMMENT ON COLUMN BI_DWH.PIO_COLL_AI_MATRIX_RESULTS.MODEL_VERSION IS
    'Model filename version that produced this score (e.g., willingness_v20260220_164400)';
