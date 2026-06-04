# Collection AI: Block 05 Forbearance & Recovery Simulator Deep-Dive

The **Forbearance & Recovery Simulator (Block 05)** is a real-time negotiation engine built into the Collection Cockpit. It empowers collection agents to simulate restructuring terms dynamically while on the phone with a customer, balancing the bank's recovery yields against the customer's immediate cash constraints.

---

## 1. The Inputs (Operational Controls)

The simulator provides the agent with four primary dials to customize the restructuring proposal:

*   **`MIN CASH FLOOR` (JOD Input)**: The immediate down-payment the customer must make today to establish and active the restructuring agreement.
*   **`RESTRUCTURING TERM` (Months Slider)**: The length of the new amortization schedule (ranging from 6 to 60 months). The system standard baseline is set to **18 Months**.
*   **`INTEREST WAIVER` (% Slider)**: The percentage of outstanding interest the bank is pre-authorized to waive (ranging from 0% to 100%) to encourage customer compliance.
*   **`LATE FEE WAIVER` (Dynamic Policy Label)**: The percentage of late fees waived, pre-authorized deterministically by the customer's risk profile (e.g., `100% pre-approved` for distressed Q2/Q4 accounts).

---

## 2. The Core Mathematical Equations

The simulator runs an interactive, sensitivity-driven calculation loop. Every time an agent updates a slider, the engine executes five sequential mathematical rules:

```
[Cash Floor Input] ──► rawTargetRecovery
                           │
[Term Slider]      ──► simulatedProbability (1.5% penalty per month > 18)
                           │
[Waiver Slider]    ──► waiverFactor (0.4% value haircut per 1% waived)
                           │
                           ▼
                    simulatedRecovery ──► simulatedNetAdvantage vs. Write-off
```

### Rule 1: The Cash Floor Advantage
Increasing the down-payment (Cash Floor) increases the immediate day-one recovery volume. The cash-adjusted base recovery target is calculated as:

$$\text{rawTargetRecovery} = \text{baseRecovery} + (\text{cashFloor} - \text{baseMinimumCash})$$

*Where:*
*   `baseRecovery`: The model's baseline predicted recovery amount (e.g., JOD 25,000).
*   `baseMinimumCash`: The minimum acceptable down-payment authorized by the credit policy.

---

### Rule 2: The Term Decay Penalty (Probability Curve)
Extending the repayment term lowers the customer's monthly payment (improving short-term ability), but **mathematically increases re-default risk over time** (long-term default volatility). The model applies a linear decay penalty of **1.5% for every month beyond the 18-month policy baseline**:

$$\text{extraMonths} = \max(0, \text{termMonths} - 18)$$

$$\text{probPenalty} = \text{extraMonths} \times 0.015$$

$$\text{simulatedProbability} = \max(0.01, \text{baseProb} - \text{probPenalty})$$

*Example:* If the base recovery probability is `75%` (`0.75`) and the agent extends the term to `24 months` (6 extra months):
$$\text{probPenalty} = 6 \times 0.015 = 0.09 \ (9\%)$$
$$\text{simulatedProbability} = 0.75 - 0.09 = 0.66 \ (66.0\%)$$

---

### Rule 3: The Interest Waiver Haircut (Waiver Factor)
Waiving outstanding interest increases customer willingness to sign, but directly reduces the ultimate collections yield. The model applies a **0.4% value haircut for every 1% of interest waived**:

$$\text{waiverFactor} = 1 - (\text{interestWaiver} \times 0.004)$$

*Example:* If the agent waives `50%` of the interest:
$$\text{waiverFactor} = 1 - (50 \times 0.004) = 1 - 0.20 = 0.80 \ (20\% \text{ haircut on yield})$$

---

### Rule 4: Simulated Expected Recovery
The final expected recovery value is computed by multiplying the cash-adjusted target by the probability ratio and the interest waiver factor:

$$\text{probRatio} = \frac{\text{simulatedProbability}}{\text{baseProb}}$$

$$\text{simulatedRecovery} = \text{rawTargetRecovery} \times \text{probRatio} \times \text{waiverFactor}$$

---

### Rule 5: Net Advantage vs. Write-off Exposure
The engine compares the final simulated recovery against the absolute **Write-off Exposure** (the total outstanding debt written off if the customer is abandoned):

$$\text{simulatedNetAdvantage} = \text{simulatedRecovery} - \text{writeOffExposure}$$

*Interpretation:*
*   **Net Deficit (e.g. JOD -9,128.41)**: The expected recovery is less than the total outstanding exposure. The bank will take a net accounting loss, but recovering JOD 27K is far better than losing all JOD 36K!
*   **Net Advantage (Green / Positive)**: The recovery exceeds the loss threshold, representing a net win for the bank's balance sheet relative to standard default expectations.

---

## 3. The Business Logic: "Why" we did it this way

In traditional banking, restructuring negotiations are rigid and blind. An agent offers a standard plan (e.g., 24 months, 10% down-payment). If the customer refuses, the account progresses to litigation.

The **Block 05 Simulator** changes this dynamic completely:
1.  **Optimizes the "Liquidity Sweet-Spot"**:
    It allows the agent to visually discover the balance between a lower monthly installment (which increases willingness) and the long-term re-default risk (the term penalty). 
2.  **Empowers Frontline Negotiation**:
    If a customer says *"I cannot pay a down-payment of JOD 1,368"*, the agent can type in `500` and instantly watch the **Simulated Expected Recovery** and **Net Advantage** recalculate. The agent can adjust the Term or Interest Waiver sliders to compensate, finding a middle ground that maintains bank value while accommodating the customer's cash flow.
3.  **Active Moratorium Rules Gating**:
    The dynamic note at the bottom of the card is driven by the backend signal interpreter. If a `Liquidity Disruption` hypothesis is active (e.g., salary delay), the engine dynamically displays an empathetic authorization note allowing a **30-day payment moratorium** without administrative escalation, preventing relationship decay during a short-term cash squeeze.
