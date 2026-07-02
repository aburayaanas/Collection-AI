# Collection AI: Block 07 Model Audit Trail & Provenance Deep-Dive

The **Model Audit Trail & Provenance (Block 07)** serves as the governance and compliance anchor of the Collection Cockpit. In modern banking, AI decision-making can never operate as a "black box." Block 07 provides complete transparency for regulators, internal auditors, and senior credit officers, showing the exact statistical health and legal compliance backing the model's recommendations.

---

## 1. Core Model Performance Metrics (The Mathematics)

To prove to auditors that the AI models are mathematically sound and stable, Block 07 exposes two key statistical quality metrics in real time:

### Population Stability Index (PSI) — Current: `0.08 (Stable)`
*   **What it measures**: PSI measures **model drift**—how much the current population of customer features (inflows, debt burdens, rejections) has shifted compared to the baseline population the model was originally trained on.
*   **Mathematical Formula**:
    
    $$\text{PSI} = \sum \left( (\text{Actual } \% - \text{Expected } \%) \times \ln\left(\frac{\text{Actual } \%}{\text{Expected } \%}\right) \right)$$

*   **Audit Thresholds**:
    *   $\text{PSI} < 0.10$: **Stable** (No population shift. Predictions are highly reliable).
    *   $0.10 \le \text{PSI} \le 0.25$: **Moderate Shift** (Slight drift. Triggers monitoring).
    *   $\text{PSI} > 0.25$: **Severe Shift** (High drift. Triggers an automatic model retraining pipeline because predictions are no longer stable).
*   **Demo Story**: The `PSI 0.08` proves that despite current market shifts, the model's classifications are highly accurate, and the bank does not suffer from data drift.

---

### Gini Coefficient — Current: `0.74`
*   **What it measures**: The Gini coefficient measures the model's **discriminatory power**—its ability to cleanly separate high-risk defaulters (who won't pay) from low-risk borrowers (who will pay).
*   **Statistical Interpretation**: Derived from the Area Under the ROC Curve (AUC):
    
    $$\text{Gini} = 2 \times \text{AUC} - 1$$
    
    *   A Gini of `0.0` is equivalent to random guessing.
    *   A Gini of `1.0` is perfect prediction.
    *   In retail banking credit risk, **any Gini above 0.60 is considered Tier-1/World-Class**. A Gini of **0.74** means our matrix engine has extremely high diagnostic accuracy.

---

## 2. Regulatory Compliance & Accounting Stages

This section bridges data science and bank accounting standards:

*   **IFRS 9 Stage: `Stage 3 (Impaired)`**:
    Under **IFRS 9 (International Financial Reporting Standards)**, bank assets are grouped into three credit quality stages:
    *   *Stage 1*: Performing loans (under 30 days past due). Requires minimal bad-debt provisioning.
    *   *Stage 2*: Underperforming loans (30 to 90 days past due, or showing a significant increase in credit risk). Provisioning rises.
    *   *Stage 3*: Non-performing / Impaired loans (over 90 days past due or active default events). Requires massive capital reserves (bad debt write-off provisions) on the bank's balance sheet.
    *   *Demo Story*: Since this customer is at **147 days past due** (Stage 3), the cockpit highlights the severity of the account, justifying aggressive interventions (like a Field Visit) to recover the capital.
*   **Compliance Framework: `CBJ Circ. 2/2022 & PDPL Art. 14`**:
    *   **CBJ Circular 2/2022 (Central Bank of Jordan)**: Regulates fair treatment of consumers, debt collection ethics, and maximum fee structures. The NBA engine's guardrails are mapped directly to this circular, ensuring no collection actions violate consumer protection laws.
    *   **PDPL Article 14 (Jordan Personal Data Protection Law)**: Guarantees "Algorithmic Transparency." If a customer asks: *"Why was a field collector sent to my house?"*, the bank is legally obligated to explain the decision. The AI Narrative Action Brief generated in Block 08 provides the exact legal explainability required to comply with PDPL Article 14.

---

## 3. Human-in-the-Loop Override Policy

A core safety guardrail of the Collection AI system is: **AI proposes, the Human disposes.**

```
[AI Recommendation: Field Visit]
              │
              ▼
    [Agent Review Screen] ──► [Option: Override NBA Button]
                                       │
                                       ▼
                         [Log CRM Justification Code]
                                       │ (within 2 hours)
                                       ▼
                           [Full Audit Log Entry]
```

*   **The Policy**: The agent is permitted to override the AI's recommendation (e.g., changing a Field Visit to a soft Outgoing Call if the customer has a medical emergency).
*   **The Audit Trail Constraint**: If the agent triggers a manual override, they **must log a valid justification code in the CRM within 2 hours**.
*   **Why**: This maintains operational flexibility and human empathy while preventing compliance leakage and ensuring internal auditors can review every single human override.
