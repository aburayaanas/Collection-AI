# DB Team Questions & NBA Requirements Questionnaire

## General Data & Logic Questions

### Account vs. Customer Logic
- Does the collection system logic rely on the **Account Number** or the **Customer Number (CUS_NUM)**?
- If it relies on the account number, are there specific selection criteria? For example, should we prioritize the most active account or the one with the highest DPD (Days Past Due)?

---

## Table Specific Queries

### PIO_COLL.PIO_PTP_COLLECTOR
- **PTP_STATUS**: Is there a lookup table for this column? What do the specific values represent, and what is their functional scope?
- **PTP_DATE & DAY_DATE**: Is the calculation `PTP_DATE - DAY_DATE` the correct way to determine the number of days between the date the promise was made and the promised payment date? If not, what is the recommended method?

### PIO_COLL.PIO_CONTACT_MANUAL_INFO
- **COMMUNICATION_TYPE**: Is there a lookup table for this column? What are the definitions for each value?
- **UPDATED_DATE**: What specific event or change does this timestamp represent?
- **MODULE_TYPE**: What does this column represent in the context of the system?

### PIO_INWARD_CENTRAL_TRANSFERS
- **Structure**: Is this table granular (one record per transaction) or aggregated?
- **Customer Linking**: We have noticed `CUS_NUM` is often NULL. Should we join this with the `PIO_CUSTOMERS` table to retrieve the correct `CUS_NUM`?
- **Cashflow Analysis**: Does this table provide a complete view of a customer's cashflow for a given period?

### Transaction Analysis
- How can we identify if a customer's transaction was declined specifically due to **insufficient funds** versus other reasons? (This is critical for the `SPENDING_STATS` CTE in the Ability SQL query).

---

## Stakeholder Follow-ups (Abu Hamzeh / Nadier)

- **Account Selection**: Confirmed to use the account with the most DPD.
- **Contact Timing**: The `PIO_CONTACT_MANUAL_INFO` table currently lacks a specific column for the exact call timestamp.
- **Payment Tracking**: How do we identify customers who paid their loans without making a formal promise? Is there a table that stores payment methods, values, and whether the payment was full or partial?
- **Query Validation**: Is joining `PIO_COLL.PIO_ACCOUNT_DEALS_INFO` with the `PTP` tables correct for the Willingness query?

---

## AI Next Best Action (NBA) Requirements

### Context
We have completed the AI Customer Segmentation Matrix (Willingness x Ability). The next phase is the **Next Best Action (NBA) Engine**, which will recommend the optimal channel and negotiation offer for each customer. To avoid incorrect assumptions, we require explicit definitions of the bank's current capabilities, compliance rules, and database tracking.

### Category 1: Communication Channels (The "Action Space")
We need to know which methods the AI is permitted to recommend and how they integrate with the database.
- **Automated Channels**: Which digital channels are currently integrated (e.g., SMS, Email, Push Notifications, WhatsApp, IVR)?
- **Human Channels**: How is a customer routed to a human agent (e.g., Standard Queue, VIP Queue, Legal, Field Visits)?
- **Execution Mechanism**: How should the AI trigger these actions? Should we write recommendations to a daily queue table (e.g., `PIO_COLL_ACTION_QUEUE`) for your servers to consume?

### Category 2: Treatment & Offer Library (The "Negotiation Space")
What specific financial options is the AI allowed to offer to specific segments (e.g., Quadrant 2: "Willing but Broke")?
- **Payment Plans (Restructuring)**: What are the standard installment lengths (e.g., 3, 6, or 12 months)?
- **Settlements (Haircuts)**: Are we allowed to offer principal or interest reductions (e.g., waiving late fees)?
- **Hardship Programs**: Are there flags for "Payment Holidays" or freezes?
- **Eligibility Rules**: Are there strict rules on who receives specific offers (e.g., "Settlements only if DPD > 120")?

### Category 3: Compliance & Contact Guardrails (The "Hard Limits")
What are the hardcoded limits to prevent regulatory breaches or harassment?
- **Anti-Harassment**: Maximum contact frequency (e.g., "Max 2 SMS/week, 1 Call/day").
- **Blackout Periods**: Specific times or days when contact is forbidden (e.g., Fridays, Public Holidays, or 8 PM – 8 AM).
- **Exclusion Segments**: Which statuses must never be contacted (e.g., Bankruptcy, Deceased, VIP, Litigation)? Where are these flags located?

### Category 4: The Feedback Loop (The "Learning Mechanism")
To enable Reinforcement Learning, we must track the outcomes of previous actions.
- **Action Logging**: Which table/column records that an event occurred (e.g., `CONTACT_LOG.STATUS = 'DELIVERED'`)?
- **Offer Acceptance**: How is a customer's response to an offer (Accepted, Rejected, Counter-offered) recorded?
- **Promise Tracking**: Which table definitively tracks if a Promise-To-Pay (PTP) generated from an NBA was kept or broken?

### Category 5: Architecture Output
- **Destination Table**: We propose an output table `PIO_COLL_AI_NBA_ACTIONS` containing `CUST_INFO_ID`, `RECOMMENDED_CHANNEL`, `RECOMMENDED_OFFER`, `CONFIDENCE_SCORE`, and `REASON_CODES`. Does this align with your architecture?

---

### Additional Notes
- **RPC Recency**: `DAYS_SINCE_LAST_RPC` currently only tracks calls; we may need permissions to incorporate other contact methods.
