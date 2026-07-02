-- =======================================================
-- MART TABLES

SELECT * FROM PIO_COLL_AI_WILLINGNESS_MART;
SELECT * FROM PIO_COLL_AI_ABILITY_MART;
SELECT * FROM PIO_COLL_AI_NBA_CONTEXT_MART;

-- =======================================================
-- =======================================================
-- RESULTS TABLES

SELECT * FROM PIO_COLL_AI_MATRIX_RESULTS;
SELECT * FROM PIO_COLL_AI_NBA_ACTIONS;
-- =======================================================
-- =======================================================
-- CLEARING TABLES

DELETE FROM PIO_COLL_AI_WILLINGNESS_MART;
DELETE FROM PIO_COLL_AI_ABILITY_MART;
DELETE FROM PIO_COLL_AI_NBA_CONTEXT_MART;

DELETE FROM PIO_COLL_AI_MATRIX_RESULTS;
DELETE FROM PIO_COLL_AI_NBA_ACTIONS;
-- =======================================================
-- =======================================================
-- CLEARING outputTABLES

-- 1. Empty the Next-Best-Action recommendations
TRUNCATE TABLE BI_DWH.PIO_COLL_AI_NBA_ACTIONS;

-- 2. Empty the demographic/compliance mart
TRUNCATE TABLE BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART;

-- 3. Empty the core ML willingness/ability results
TRUNCATE TABLE BI_DWH.PIO_COLL_AI_MATRIX_RESULTS;
-- =======================================================

