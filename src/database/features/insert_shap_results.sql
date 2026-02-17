-- =============================================================================
-- INSERT: SHAP explanation results into PIO_COLL_AI_MATRIX_RESULTS
-- Target: openbi2 DWH, BI_DWH schema
--
-- Called from src/database/shap_repository.py via executemany.
-- Column mapping:
--   :1 → CUST_INFO_ID       (customer identifier)
--   :2 → SHAP_MODEL_TYPE    ('WILLINGNESS' or 'ABILITY')
--   :3 → SHAP_EXPLANATION   (business-friendly formatted text)
--   :4 → SHAP_DESCRIPTION   (detailed feature descriptions)
--   :5 → SHAP_RAW_FEATURES  (technical "FEAT: XX.X%; ..." string)
--   SYSDATE auto-filled for SHAP_COMPUTED_DATE
-- =============================================================================

UPDATE BI_DWH.PIO_COLL_AI_MATRIX_RESULTS
SET
    SHAP_MODEL_TYPE    = :2,
    SHAP_EXPLANATION   = :3,
    SHAP_DESCRIPTION   = :4,
    SHAP_RAW_FEATURES  = :5,
    SHAP_COMPUTED_DATE = SYSDATE
WHERE
    CUST_INFO_ID = :1
