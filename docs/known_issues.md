# Known Issues & Synchronization Guide

## 1. SNAP_DATE Mismatch (Sync Error)
**Status:** Resolved for Development
**Root Cause:** The pipeline relies on a consistent `DAY_DATE` across three operations: Matrix results insertion, SHAP updates, and NBA results. In production, this date is provided by the Oracle `SNAP_DATE` function. During development, if this function returns a stale date (e.g., from 2025), but the system date is 2026, the `UPDATE` and `JOIN` operations will match 0 rows.

### Mandatory Production Checklist
When moving to production, the following hardcoded "DEV mode" overrides **MUST** be reverted:

| Component | File Path | Action Required |
| :--- | :--- | :--- |
| **Logic Root** | `src/database/queries.py` | Uncomment the Oracle `SNAP_DATE` SQL call and remove the `datetime.now()` override. |
| **Matrix Producer** | `src/engine/matrix.py` | Ensure `current_day_date` calls `get_snap_date()` (do not use hardcoded strings). |
| **SHAP Consumer** | `src/database/shap_repository.py` | Ensure `snap_date` calls `get_snap_date()` for the `UPDATE` filter. |
| **NBA Consumer** | `src/main.py` | The NBA step extracts `day_date` from the matrix results. Ensure the matrix results have the correct production date. |
| **Seed Script** | `scripts/generate_synthatic_data.py` | For local testing, this script must match whatever date `get_snap_date()` is returning. |

---

## 2. Windows File System Conflicts
**Status:** Fixed
**Issue:** `os.rename()` fails on Windows if the destination `.bak` file already exists.
**Fix:** Use `os.replace()` in `src/models_engine/willingness/scorer.py` and `src/models_engine/ability/scorer.py`.

## 3. SHAP Feature Mismatch
**Status:** Fixed
**Issue:** Adding NBA Context columns (Strings like 'Active') to the Mart tables causes SHAP to crash when it tries to cast those strings to numeric features.
**Fix:** Update `default_exclude` in `src/explainability/shap_explainer.py` to include `INST_CODE`, `COUNTRY_CODE`, `DAY_DATE`, and all NBA operational columns.

## 4. SHAP Column Overwrite & Type Mismatch
**Status:** Fixed
**Issue:** 
1.  **Overwrites:** Originally, both Willingness and Ability models updated the same `SHAP_EXPLANATION` column, causing the second model (Ability) to overwrite the first.
2.  **Naming Mismatch:** The code was explicitly overriding SHAP column names with `reason_cols` instead of the expected `SHAP_EXPLANATION`, leading to `NULL` updates.
3.  **Oracle Type Strictness:** Silent failure (0 rows updated) occurred when Python sent `int` binds for `INST_CODE` or `COUNTRY_CODE` against Oracle `VARCHAR2` columns, or due to timestamp discrepancies.

**Fix:**
- Updated DDL to use separate columns: `WILL_SHAP_...` and `ABIL_SHAP_...`.
- Synchronized `shadow_runner.py` and `shap_explainer.py` to use `SHAP_EXPLANATION` and `SHAP_DESCRIPTION` consistently.
- Implemented aggressive `TO_CHAR()` casting in `src/database/features/insert_shap_results.sql` to force string-matching in the `WHERE` clause and bypass Oracle type-matching failures.

## 5. Oracle Date Parsing (Polars Type Mismatch)
**Status:** Fixed
**Issue:** Oracle `DATE` fields are parsed by `oracledb` as Python `datetime.datetime` objects. Defining them as `pl.Date` in Polars schema mapping raises a silent conversion exception, causing the `main.py` ingestion loop to fall back on an empty context dataframe (which populates all new UI KYC fields with "Unknown").
**Fix:** Map Oracle date-only fields as `pl.Datetime` in `CollectionRepository.get_nba_context_data()` schema definitions and update the empty fallback schemas accordingly to keep them aligned.

## 6. Empty Behavioral Signals due to Missing Mart Joins (Core Logic)
**Status:** Fixed
**Issue:** Behavioral signal interpretation rules require ML-specific features (`INFLOW_VARIANCE_30D`, `DAYS_SINCE_LAST_RPC`, `BROKEN_PTP_COUNT_6M`). Because the NBA data preparation joined only the Matrix and NBA Context tables, these ML features were missing (`None` / `0`), causing the **Liquidity Crisis** and **Evasion** scenario checks to evaluate to `False` and return empty lists `[]`.
**Fix:** Explicitly retrieve and left-join raw Willingness and Ability features from their respective database marts on `CUST_INFO_ID` into the orchestrator's leading DataFrame during `run_nba_steps` in [main.py](file:///c:/Users/abura/.vscode/workspace/Collection-AI/src/main.py).

## 7. Windows Multiprocessing Entrypoint Spawning Loop (DB Lock ORA-00054)
**Status:** Fixed
**Issue:** The SHAP phase spawns a multiprocessing `ProcessPoolExecutor` with `-n_jobs -1`. On Windows, the subprocess `spawn` method re-imports the original entrypoint script (`run_pipeline.py`). If this file lacks an `if __name__ == "__main__":` guard, all spawned child processes recursively trigger the entire pipeline from scratch, truncating database tables concurrently and raising `ORA-00054: resource busy` exceptions.
**Fix:** Enclose all pipeline initiation, database seeding, and execution statements within a proper `if __name__ == "__main__":` guard in [run_pipeline.py](file:///C:/Users/abura/.gemini/antigravity/scratch/run_pipeline.py).

