# Frontend Handover: Addressing Audit Critiques & Visual Alignment

This document outlines the actionable items for the frontend team (`AI_collection_frontend` / `CollectionCockpit.jsx`) based on the architectural audit and critique review.

---

## 1. Executive Summary & Filtering Rationale

The audit raised 9 critique points. We evaluated them to distinguish actual bugs from misunderstandings of synthetic test data:
- **Backend Fixes Completed in `Collection-AI`:**
  - **Critique 1 (Compliance KYC Gate):** LLM system prompt now deterministically suppresses restructuring and forbearance terms when KYC is flagged or expired.
  - **Critique 3 (Timeline Anchor Clock):** Escalation timeline in `EscalationEngine` is now mathematically anchored to the snapshot date `DAY_DATE` (`reference_date`) instead of drifting with `datetime.date.today()`.
  - **Critique 4 (Currency Standard):** Mandated `JOD` across all narrative outputs and calculations; eliminated `$`/`USD`.
  - **Critique 5 (Synthetic Data Arithmetic):** Synthetic data generation boundaries and scores were recalibrated in backend.
  - **Critique 6 (Q2 Quadrant Rationale):** Backend heuristic reasoning now correctly labels Q2 as *"Vulnerable quadrant (Q2). High willingness warrants soft touch / restructuring approach."* instead of "Low risk".
  - **Critique 8 & 9 (LLM Explanations):** LLM prompt now explicitly explains tied scores (policy preference) and clarifies velocity delta vs. absolute risk score.
- **Frontend Action Items Required:**
  - **Critique 2 (IFRS 9 Header Hardcoding):** Must be dynamically driven by `payload.compliance_audit.ifrs9_stage`.
  - **Critique 7 (SHAP Signs & Visual Legend):** Add clear visual distinction and legend for `+ Risk Drivers` (Rose) vs `- Protective Anchors` (Emerald).
  - **Critique 8 (Channel Tie-Breaker Indicator):** Clarify when a recommended channel was selected by policy tie-breaker.

---

## 2. Actionable Changes for `CollectionCockpit.jsx`

### Task 1: Fix Hardcoded IFRS 9 Provisioning Badge in Header
- **File:** `AI_collection_frontend/src/CollectionCockpit.jsx`
- **Location:** Line ~926-929
- **Issue:** The header provisioning badge currently hardcodes `"Stage 3"`, causing a direct contradiction when the customer is at 44 DPD (where `payload.compliance_audit.ifrs9_stage` is `"Stage 2 (Significant Increase in Credit Risk)"`).
- **Target Replacement:**
```jsx
{/* BEFORE (Line ~926-929): */}
<div className="border border-rose-900/50 bg-rose-400/10 rounded px-3 py-1 flex flex-col">
  <span className="text-[9px] uppercase tracking-widest text-rose-400/80 font-mono">IFRS 9 Provisioning</span>
  <span className="text-xs font-semibold font-mono text-rose-400">Stage 3</span>
</div>

{/* AFTER (Dynamic Binding): */}
{(() => {
  const rawStage = payload.compliance_audit?.ifrs9_stage || "Stage 2";
  const stageLabel = rawStage.split('(')[0].trim();
  const isStage3 = rawStage.includes("Stage 3");
  const isStage2 = rawStage.includes("Stage 2");
  
  const containerClass = isStage3
    ? "border-rose-900/50 bg-rose-400/10 text-rose-400"
    : isStage2
    ? "border-amber-900/50 bg-amber-400/10 text-amber-400"
    : "border-emerald-900/50 bg-emerald-400/10 text-emerald-400";

  const labelColor = isStage3
    ? "text-rose-400/80"
    : isStage2
    ? "text-amber-400/80"
    : "text-emerald-400/80";

  return (
    <div className={`border rounded px-3 py-1 flex flex-col ${containerClass}`}>
      <span className={`text-[9px] uppercase tracking-widest font-mono ${labelColor}`}>IFRS 9 Provisioning</span>
      <span className="text-xs font-semibold font-mono">{stageLabel}</span>
    </div>
  );
})()}
```

---

### Task 2: Add Visual Legend to SHAP Driver Visualizer (Block 02)
- **File:** `AI_collection_frontend/src/CollectionCockpit.jsx`
- **Location:** Line ~1055-1065 (inside Block 02, above the Willingness SHAP Drivers)
- **Issue:** Reviewers noted ambiguity regarding what positive and negative percentages signify. While the colors are correct (Rose for risk, Emerald for protective), an explicit legend avoids any misinterpretation.
- **Target Addition:**
Insert this legend directly above the Willingness SHAP weights:
```jsx
{/* SHAP Polar Legend */}
<div className="flex items-center justify-between text-[9px] font-mono mb-3 px-2 py-1.5 rounded border border-slate-800/40 bg-slate-900/40">
  <div className="flex items-center space-x-1.5">
    <span className="h-2 w-2 rounded-full bg-rose-500 inline-block" />
    <span className="text-rose-400 font-semibold">+ Risk Drivers</span>
    <span className="text-slate-500">(Increases default probability)</span>
  </div>
  <div className="flex items-center space-x-1.5">
    <span className="h-2 w-2 rounded-full bg-emerald-500 inline-block" />
    <span className="text-emerald-400 font-semibold">- Protective Anchors</span>
    <span className="text-slate-500">(Mitigates risk)</span>
  </div>
</div>
```

---

### Task 3: Channel Tie-Breaker Badge in Scored Alternatives (Block 04)
- **File:** `AI_collection_frontend/src/CollectionCockpit.jsx`
- **Location:** Around lines 1380-1395 (where `payload.next_best_action.scored_alternatives` are mapped)
- **Issue:** When two channels both have a score of 100 (e.g. Email and Outgoing Call), users ask why one was selected over the other.
- **Target Addition:**
For the selected channel card (`isSelected`), if another alternative shares the same score, show an explanatory badge:
```jsx
{isSelected && payload.next_best_action.scored_alternatives.some(o => o.channel !== alt.channel && o.score === alt.score) && (
  <span className="text-[8px] uppercase tracking-wider px-1 rounded font-bold bg-amber-400/10 border border-amber-900/50 text-amber-400">
    Policy Tie-Breaker
  </span>
)}
```

---

### Task 4: Ensure Mock Payload Consistency (Block 0)
- **File:** `AI_collection_frontend/src/CollectionCockpit.jsx`
- **Location:** `mockPayload` at lines 15-22
- **Action:** If mock data includes Q2 cases, ensure the reasoning string in `mockPayload` uses:
  `"Vulnerable quadrant (Q2). High willingness warrants soft touch / restructuring approach."`
  instead of `"Low risk quadrant (Q2)"`.

---

## 3. Verification Checklist for Frontend Agent
1. [ ] Check browser header: verify the IFRS 9 badge shows `Stage 2` when testing with a 44 DPD customer.
2. [ ] Check Block 02: verify the SHAP legend displays clearly in both Light and Dark mode.
3. [ ] Check Block 04: verify recommended channel clearly shows policy priority when channel scores tie.
4. [ ] Verify no dollar signs (`$`) appear anywhere in the UI; all financial figures use `JOD`.
