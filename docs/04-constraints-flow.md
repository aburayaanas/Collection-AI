---
description: 'Pillar 3: Feedback Loop & Data Schema'
---

# 04-constraints-flow

### Collections State Machine (FSM)

Every account flows through a well-defined state machine. Each state encodes currentdelinquency status and collections strategy eligibility.



### Action History & Outcome Labels

Action History Table\
(immutable log):



CREATE TABLE action\_history ( action\_id BIGINT PRIMARY KEY AUTO\_INCREMENT, account\_id INT, action\_date DATETIME, action\_type VARCHAR(50), -- CALL, SMS, LETTER, ESCALATE, SKIP

```
-- Context at Time of Action
delinquency_days INT,
willingness_score_at_action DECIMAL(5,4),
affordability_score_at_action DECIMAL(5,4),

-- Action Details
channel VARCHAR(50),  -- PHONE, SMS, EMAIL, USPS, ESCALATION
assigned_agent_id INT,
duration_seconds INT, -- For CALL actions

-- Immediate Outcome (Captured 0–1 Days)
rpc_success BOOLEAN,
customer_answered BOOLEAN,
agent_notes TEXT,
sentiment_label VARCHAR(20), -- POSITIVE, NEUTRAL, NEGATIVE (NLP-derived)

-- Short-term Outcome (Captured 2–7 Days)
promised_to_pay BOOLEAN,
promised_amount DECIMAL(15,2),
promised_date DATE,

-- Long-term Outcome (Captured 30 Days)
ptp_kept BOOLEAN,
ptp_keep_date DATETIME,
payment_received_30d BOOLEAN,
payment_amount_30d DECIMAL(15,2),
payment_date_30d DATETIME,

-- Feedback for RL Model
ltv_immediate DECIMAL(10,2),  -- Immediate proxy reward
ltv_30day DECIMAL(10,2),      -- 30-day actual recovery

created_at DATETIME
```

Outcome Labels (Key Targets for Model Training):



| Label            | Definition                                                                     | Source                                                | Prediction Target                                                  |
| ---------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------- | ------------------------------------------------------------------ |
| PTP\_Broken      | Customer promised payment, then failed to pay within promised date + 5 days    | action\_history.ptp\_kept = FALSE                     | Predicts willingness volatility; fine-tunes engagement strategy    |
| PTP\_Kept        | Customer honored promised payment                                              | action\_history.ptp\_kept = TRUE                      | Indicates successful negotiation; increases agent confidence score |
| RPC\_Success     | Right-party contact confirmed                                                  | action\_history.rpc\_success = TRUE                   | Indicates contact data quality; enables RPC-gated actions          |
| Payment\_30d     | Any payment received within 30 days of action                                  | action\_history.payment\_received\_30d = TRUE         | Primary RL reward signal; maps to recovery metrics                 |
| Self\_Cure       | Account transitions from delinquent → current without collections intervention | Derived from state transitions                        | Identifies self-cure segment; prevents unnecessary treatment       |
| Propensity\_Roll | Account ages into next delinquency bucket despite intervention                 | Derived from account\_state.current\_state transition | Indicates treatment failure; triggers escalation                   |
