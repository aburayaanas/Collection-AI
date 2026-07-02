# SOTA Tier-1 Agent Action Brief

## SECTION 1 — IDENTITY & COMPLIANCE GATE

**KYC Anchor:** Ahmed Aisha Al-Zoubi (CIF-78360649), Jordanian Resident Mass retail · Self-employed customer employed at Self / Trade License (verified), 1 yr 8 mo tenure. 

**KYC Status & Compliance Gate:** The account KYC status is currently marked as "Up to date." However, the income profile of JOD 2,001/mo was last verified 5 months ago. Under bank credit governance, no formal restructuring agreement may be legally executed until re-verification is completed. Downstream forbearance and debt scheduling modifications remain strictly **blocked** pending refresh of the verified income dossier.

**AML & Sanctions Screening:** AML last screened on 2026-03-17 with status "Clear." PEP and Sanctions flags are negative. No administrative flags or PEP escalations are required, leaving the file clear for operational contact.

**Exposure Portfolio:** Cross-product credit exposure consists of one Auto loan and one active Credit card.

**Compliance Warning:** `[COMPLIANCE ALERT]` — No structural compliance alerts are triggered (compliance_warning_flag: false). Any restructuring offer made subsequently is valid and enforceable upon prompt KYC updates.

---

## SECTION 2 — MATRIX STATE & UNCERTAINTY ENVELOPE

**Classification Verdict:** Customer is classified under quadrant **Q4 (High Risk. Severe financial distress and evasive behavior.)** with a composite risk score of **97/100** and is currently **84 days past due (DPD)**. 

**Uncertainty & Posture Strategy:** The model exhibits highly stable primary confidence of **95%** in the Q4 quadrant. The competing quadrant is Q3 (Strategic Defaulter) with a minor probability of **20%**, representing an uncertainty gap of **75 percentage points**. Because the uncertainty gap exceeds 30%, this represents a **low-ambiguity classification** with high model stability. The score velocity indicates rapid deterioration, with the composite risk score accelerating by **+15 points over the last 90 days**.

**Willingness SHAP Drivers:** 
*   **Long-term Promise Reliability** (Primary Driver): Represents **71.87%** of the decision weight driving the classification.
*   **Recent Broken Promises (6M)** (Secondary Factor): Accounts for **22.09%** of the decision weight.
*   **Recent Payment Frequency** (Contributing Factor): Accounts for **5.89%** of the decision weight.
*   *Willingness Protective Factors*: There are no willingness protective factors identified for this profile; negotiation has no historical reliability anchor to utilize.

**Ability SHAP Drivers:**
*   **Payment Rejection Rate** (Primary Driver): Accounts for **38.56%** of the ability decision weight.
*   **Estimated Liquidity Runway** (Primary Driver): Accounts for **31.51%** of the ability decision weight.
*   **Debt Service Burden** (Primary Driver): Accounts for **27.47%** of the ability decision weight.
*   *Ability Protective Factors*: No ability protective factors identified. The customer displays zero residual capacity signals.

**Agent Posture Calibration:** While the primary risk profile is Q4, the residual 20% Q3 probability suggests potential evasive behavior. The agent must probe for deliberate evasion and must not lead with soft empathy before testing willingness. Confirm the current status of the trade license directly with the customer before initiating discussions on payment restructuring.

---

## SECTION 3 — BEHAVIORAL INTELLIGENCE & CHANNEL STRATEGY

**Observed Signals:** `[CONFIRMED]` No observed behavioral signals (e.g., payment rejections, direct debit failures) are explicitly registered in the active transaction logs for this specific customer. 

**Hypothesis Inferences:** `[INFERENCE]` No hypothesis behavioral signals (such as sudden liquidity disruption) are flagged. 

**Channel Strategy Comparison:** 
The contextual bandit engine has recommended **Field Visit (score: 100/100)** as the optimal, high-leverage recovery channel.
*   *Field Visit (Score: 100)*: Prioritized because high-risk Q4 delinquency requires immediate physical/in-person contact to break communication barriers.
*   *Dunning Letter (Score: 90)*: Evaluated as a secondary alternative but discarded as standalone due to low responsive rates on 84 DPD accounts.
*   *Outgoing Call (Score: 80)*: De-prioritized because indirect phone contact has historically failed to secure firm restructuring commitments for high-risk accounts.

**Agent Approach Directive:** In the absence of an active sensitivity or moratorium flag, the agent should maintain a firm, neutral, and obligation-first opening framing during the visit. Focus negotiations purely on securing the minimum cash floor.

---

## SECTION 4 — RECOVERY QUANTIFICATION & ESCALATION CLOCK

**Business Case Summary:** Expected recovery value is **JOD 18,247.08** based on a calibrated recovery probability of **45% (0.45)**, evaluated against a write-off exposure of **JOD 40,549.07**. Pursuing the Next Best Action offers a net recovery advantage of **JOD 18,247.08** over immediate write-off.

**Negotiation Limits:** The human agent's decision boundaries are strictly defined as:
*   **Minimum Acceptable Cash Floor:** JOD 2,780.48 (representing the minimum immediate payment required to halt legal triggers).
*   **Maximum Restructuring Term:** 18 months (Retail standard).
*   **Interest Waiver Authority:** Maximum JOD 77.94 (representing 15% pre-approved waiver limit on accrued interest).
*   **Late Fee Waiver:** 100% pre-approved as a goodwill gesture if the customer signs the restructuring today.

**Operational Escalation Timeline:**

| Node | Label | Target Window & Action |
|---|---|---|
| Current | `PHASE 1 — ACTIVE` | **Field Visit** is active starting today. Action window ends on **2026-05-24** (7 days). |
| Trigger | `PHASE 2 — TRIGGER` | If the Field Visit fails or the minimum floor of **JOD 2,780.48** is not received by **2026-05-24**, the account escalates automatically. Action: **Formal demand letter + legal pre-notification SMS**. Window: days 8–21. |
| Legal | `PHASE 3 — LEGAL` | If Phase 2 produces no payment by day 21, the account triggers immediate **Legal referral + Credit Bureau reporting** and reclassification to **IFRS 9 Stage 3 (Impaired)**. |
| Recovery | `EXIT — DE-ESCALATION` | If the minimum acceptable cash is paid and a restructuring agreement is signed, the account is de-escalated to **Q3 (monitoring)** for a **30-day rescore window**. |

---

## SECTION 5 — MODEL AUDIT TRAIL

Decision governed by `CollectIQ-Matrix-Bandit` v`v3.1.4` (last validated `2026-02-28`, Gini `0.74`, PSI `0.08` — model stability: stable based on PSI threshold of 0.25); IFRS 9 Stage `Stage 2 (Significant Increase in Credit Risk)` classification applies; regulatory framework: `CBJ Circ. 2/2022 & PDPL Art. 14`; human override policy: Agent may override NBA. Must log justification code in CRM within 2 hours of action.
