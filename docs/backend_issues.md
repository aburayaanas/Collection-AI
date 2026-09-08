# Backend Issues & Proposed Adjustments

**Source Review Reference:** `docs/issues.md` (AI_collection_frontend)
**Date:** September 6, 2026
**Target Repository:** `Collection-AI` (Backend)

---

## 1. Issue 3: Extreme Willingness / Ability Model Scores (0/100 or 99/100)

### Current Architecture & Finding

- **Inference Pipeline:**
  - In `src/models_engine/willingness/scorer.py` and `src/models_engine/ability/scorer.py`, `xgb.DMatrix` is fed to `model.predict(dmatrix)`.
  - In `src/explainability/xai_aggregator.py` (lines 194-198), raw scores (`0.0` to `1.0`) are multiplied directly by 100: `int(float(raw_score) * 100)`.
- **Root Cause Analysis:**
  1. **Objective Function & Sigmoid Saturation:** In `trainer.py`, the training objective is `binary:logistic`. When a tree-based gradient boosted model has large feature weights or uncalibrated leaves (e.g., `max_depth` up to 10, deep trees), predicted probabilities saturate at exact extremes: $P \to 0.0$ or $P \to 1.0$.
  2. **Uncalibrated Probabilities:** Neither Platt scaling nor Isotonic regression calibration (`CalibratedClassifierCV`) is applied post-training.
  3. **High Feature Cardinality / Separability:** Features like `BOUNCE_RATE_60D = 1.0` or `BROKEN_PTP_COUNT_6M > 3` cause the XGBoost trees to output extreme log-odds margins ($z > 6$ or $z < -6$), converting via logistic sigmoid into $0.0001$ or $0.9999$.

### Proposed Backend Solution

- **Calibrate Model Probabilities:** Apply probability calibration (Platt scaling / Sigmoidal or Isotonic calibration) on held-out validation folds before saving the model booster, or:
- **Temperature / Logit Smoothing:** Implement probability smoothing / clipping or calibrate scores using ranking percentiles if scores are expected to represent a continuous risk index rather than a binary threshold.

---

## 2. Issue 4: Block 06 Escalation Generation Flow Assessment

### Current Architecture & Finding

- **Source File:** `src/engine/nba/escalation.py` (`EscalationEngine.generate_timeline`)
- **How it Works:**
  - **Inputs:** `days_past_due`, `current_quadrant`, `selected_nba`, `minimum_acceptable_cash`.
  - **Phase 1:** Sets window from `today` to `today + 7 days` with action `selected_nba`.
  - **Phase 2:** Hardcoded condition: `"Triggered if {nba_action} fails or minimum {min_cash} not received by {target_date}. Action: Formal demand letter + legal pre-notification SMS. Window: days 8-21."`
  - **Phase 3:** Fixed string: `"Triggered if Phase 2 produces no payment by day 21. Action: Legal referral + credit bureau reporting. Reclassify to Stage 3 per IFRS 9."`
  - **Exit Path:** Dynamic quadrant reclassification lookup (Q4 -> Q2; Q3/Q2 -> Q1; other -> Q0).
- **Update Frequency:**
  - Calculated **per-customer** during batch/single NBA execution (`src/engine/nba/orchestrator.py`), then stored statically in `AI_PAYLOAD` in `PIO_COLL_AI_NBA_ACTIONS`.
  - It does **not** update dynamically in real time based on intermediate collector call logs unless the batch pipeline or snapshot runs again.
- **Assumptions:**
  - Phase 1 is always 7 days.
  - Phase 2 is always days 8–21.
  - Phase 3 is always day 21+ legal referral.
  - Does not check whether legal referral is already in progress or if product type allows formal demand letters.

---

## 3. Issue 5: Block 03 Behavioral Signals Generation Check

### Current Architecture & Finding

- **Source File:** `src/engine/inference/signal_interpreter.py` (`SignalInterpreter.generate_signals`)
- **How it Works:**
  - **Liquidity Scenario:**
    ```python
    if rejection_freq > 0 and inflow_variance > 500.0:
        # Appends OBSERVED "Payment Rejections"
        # Appends HYPOTHESIS "Liquidity Disruption" with confidence = clamp(0.55, 0.75, 1.0 - ability_score)
    ```
  - **Evasion Scenario:**
    ```python
    if (broken_ptp > 0 or days_since_rpc > 30) and contact_avoidance >= 0.6:
        # Appends OBSERVED "Contact Failure"
        # Appends INFERRED "Evasive Pattern" with confidence = contact_avoidance
    ```
- **Finding:**
  - The logic is **rule-based / heuristic**, not a black-box ML model.
  - Several hardcoded numerical constants are used (`inflow_variance > 500.0`, `contact_avoidance >= 0.6`, `days_since_rpc > 30`, arbitrary confidence clamp `[0.55, 0.75]`).
  - These signals are stored inside `AI_PAYLOAD["behavioral_signals"]`.

---

## 4. Issue 6: Block 08 Section 2 Score Velocity Contradiction (LLM Direction Inversion)

### Problem Description

- For customer `66498973`, the UI shows `+47 pts` (Deterioration) or `+47 pts` (Improvement), but the LLM states the exact opposite in Section 2.
- **Root Cause in `src/explainability/llm_system_prompt.md`:**
  - Current prompt line 32 simply states:
    `- Score Velocity: 90-day score delta (score_delta_90d).`
  - In risk scoring:
    - If `score` is a **Risk Score** (higher = riskier): `+47` means **deterioration** (worse risk), while `-47` means **improvement** (less risk).
    - In standard credit scoring (e.g. FICO): `+47` means **improvement** (higher score = better).
  - Because `llm_system_prompt.md` does not specify the polarity/definition of `score_delta_90d`, the LLM hallucinates or inverts the meaning (assuming higher score = improved creditworthiness).

### Proposed Backend Solution

- In `src/explainability/llm_system_prompt.md`, explicitly define the polarity rule:
  ```markdown
  - **Score Velocity Definition (`score_delta_90d`):** 
    - A positive delta (e.g., `+X` points) represents **RISK DETERIORATION** (the customer has become higher risk).
    - A negative delta (e.g., `-X` points) represents **RISK IMPROVEMENT** (the customer has become lower risk / more cooperative).
    - You must explicitly state whether the delta represents deterioration or improvement matching this exact rule.
  ```

---

## 5. Issue 7: Block 08 Section 2 Feature Importance / SHAP Explanation Clarity

### Problem Description

- SHAP drivers in Section 2 are currently output in a dense academic format (e.g., `Recent Broken Promises (6M) (49.48% decision weight)`), which does not clearly convey to collection officers whether the feature is hurting or helping the customer's case.

### Proposed Backend Solution

- In `src/explainability/llm_system_prompt.md` under `SECTION 2 — MATRIX STATE & UNCERTAINTY ENVELOPE`, refine the SHAP instruction:
  ```markdown
  - **Willingness & Ability SHAP Drivers:** 
    - For Risk Drivers (Negative impact on customer health / increasing risk): Clearly explain how they aggravate delinquency (e.g., "Driven primarily by frequent broken promises (+49.5%), which severely reduces willingness").
    - For Protective Anchors (Positive impact / reducing risk): Clearly explain how they mitigate risk (e.g., "Anchored positively by recent payment frequency (-6.0%), which demonstrates residual intent to pay").
    - Use clear business language: explain what the feature means in practice rather than just reciting feature names and raw percentages.
  ```
