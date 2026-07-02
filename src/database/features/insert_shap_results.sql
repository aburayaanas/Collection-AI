-- Update separate SHAP columns in PIO_COLL_AI_MATRIX_RESULTS.
-- This prevents Willingness and Ability explanations from overwriting each other.
--
-- Binds:
--   :cust_id          → CUST_INFO_ID
--   :model_type       → Used to route data ('WILLINGNESS' or 'ABILITY')
--   :risk_drivers      → JSON string of negative SHAP factors
--   :positive_drivers  → JSON string of positive SHAP factors
--   :snap_date        → DAY_DATE
--   :inst_code        → INST_CODE
--   :country_code     → COUNTRY_CODE

UPDATE BI_DWH.PIO_COLL_AI_MATRIX_RESULTS
SET
    -- Update Willingness columns ONLY if model_type is WILLINGNESS
    WILL_RISK_DRIVERS = DECODE(:model_type, 'WILLINGNESS', :risk_drivers, WILL_RISK_DRIVERS),
    WILL_POSITIVE_DRIVERS = DECODE(:model_type, 'WILLINGNESS', :positive_drivers, WILL_POSITIVE_DRIVERS),
    
    -- Update Ability columns ONLY if model_type is ABILITY
    ABIL_RISK_DRIVERS = DECODE(:model_type, 'ABILITY', :risk_drivers, ABIL_RISK_DRIVERS),
    ABIL_POSITIVE_DRIVERS = DECODE(:model_type, 'ABILITY', :positive_drivers, ABIL_POSITIVE_DRIVERS),
    
    SHAP_COMPUTED_DATE = SYSDATE
WHERE
    TO_CHAR(CUST_INFO_ID) = TO_CHAR(:cust_id)
    AND TO_CHAR(DAY_DATE, 'YYYY-MM-DD') = TO_CHAR(:snap_date)
    AND TO_CHAR(INST_CODE) = TO_CHAR(:inst_code)
    AND TO_CHAR(COUNTRY_CODE) = TO_CHAR(:country_code)
