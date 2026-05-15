-- =============================================================================
-- INSERT: SHAP explanation results into PIO_COLL_AI_MATRIX_RESULTS
-- Target: openbi2 DWH, BI_DWH schema
--
-- Called from src/database/shap_repository.py via executemany.
-- Column mapping (Named Parameters):
--   :cust_id           → CUST_INFO_ID
--   :model_type        → SHAP_MODEL_TYPE
--   :explanation       → SHAP_EXPLANATION
--   :description       → SHAP_DESCRIPTION
--   :raw_features      → SHAP_RAW_FEATURES
--   :snap_date         → DAY_DATE
--   :inst_code         → INST_CODE
--   :country_code      → COUNTRY_CODE

UPDATE BI_DWH.PIO_COLL_AI_MATRIX_RESULTS
SET
    SHAP_MODEL_TYPE    = :model_type,
    SHAP_EXPLANATION   = :explanation,
    SHAP_DESCRIPTION   = :description,
    SHAP_RAW_FEATURES  = :raw_features,
    SHAP_COMPUTED_DATE = SYSDATE
WHERE
    CUST_INFO_ID = :cust_id
    AND TRUNC(DAY_DATE) = TO_DATE(:snap_date, 'YYYY-MM-DD')
    AND INST_CODE = :inst_code
    AND COUNTRY_CODE = :country_code
