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
