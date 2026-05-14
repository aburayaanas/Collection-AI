---
description: 'Pillar 1:  Willingness vs. Ability AI Model Architecture'
---

# 01-constraints-flow

* **Willingness-to-Pay Model (Propensity)**
  * **Purpose:** Predict behavioral intent — likelihood the debtor will make a payment in the next engagement window.
  * **Typical Output:** Probability score; higher = greater likelihood of payment commitment.
  * **Training Feedback:** Promise-to-Pay (PTP) broken/kept, contact frequency responsiveness, engagement depth.

| Feature Category       | Data Source                      | Rationale                                                                                                                      | Note                                                                                                                                            |
| ---------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Contact Responsiveness | NULL                             | Signal of engagementand intent                                                                                                 | Ask Profisionals                                                                                                                                |
| Promise Behavior       | PIO\_PTP\_COLLECTOR              | Direct behavioralsignal of willingness                                                                                         | NULL                                                                                                                                            |
| Engagement Depth       | UNI\_REPOS.PIO\_SMS\_COLLECTOR   | Proxy for attentivenessand motivation                                                                                          | <ul><li>which owner to use uni or pio_collection</li><li>Does this table contains the logic of SMS open rate, email interaction count</li></ul> |
| Payment Initiation     | PIO\_TRANSACTIONS                | Behavioralcommitment signal                                                                                                    | ask gemini. this feature seems to be hard to implement.                                                                                         |
| Temporal Patterns      | Historicaltransactions +calendar | Captures liquiditytiming windows                                                                                               | Hard to implement but usefull.                                                                                                                  |
| Sentiment/Narrative    | PIO\_COLL.PIO\_MEMO\_NOTES\_INFO | <ul><li>Collector notes sentiment (NLP),complaint frequency, dispute flag</li><li>Capturespsychographic intentsignal</li></ul> | NULL                                                                                                                                            |

* **Algorithm Selection:** Gradient Boosting (XGBoost) or LightGBM
  * **Rationale:** Binary/multi-class classification on tabular engagement data; interpretable feature importance is crucial for agent decision-support.
  * **Recommended Python Libraries:**
    * `xgboost`
    * `shap` (for explainability)
    * `optuna` (for hyperparameter tuning)
  * **Typical Performance:** 75–82% AUC on held-out test sets; 6–12 month retraining cycle with concept drift management.

### Willingness-to-Pay Feature Engineering

| Feature Category      | Data Source         | Rationale                           | Notes                     |
| --------------------- | ------------------- | ----------------------------------- | ------------------------- |
| Transactional Entropy | PIO\_TRANSACTIONS   | Proxy for financialinstability      | NULL                      |
| Salary/IncomeInflow   | transactions/salary | Primary liquidityindicator          | confirm from profisionals |
| Cash Velocity         | transactions/salary | Indicates runwayand cashflow stress | confirm from profisionals |
| Account Balance       | PIO\_ACCOUNTS       | Direct liquidityindicator           | NULL                      |
| Debt Service Coverage | PIO\_LOANS/SALARY   | Key affordability metric            | confirm from profisionals |
| Spending Volatility   | PIO\_TRANSACTIONS   | Captures expenseinstability         | NULL                      |
| Bounce/NSFEvents      | PIO\_TRANSACTIONS   | Direct signal ofliquidity stress    | confirm from profisionals |
| Credit Utilization    | PIO\_LOANS          | Proxy for financialstrain           | confirm from profisionals |

### Algorithm selection: LSTM or Hybrid XGBoost-LSTM

* LSTM Rationale:
  \
  Cashflow is inherently sequential; LSTM captures temporal dependencies(e.g., salary seasonality, spending cycles). Studies show LSTM outperforms ARIMA/SARIMAfor medium-term forecasting
* Hybrid Approach:
  \
  Use LSTM for 30-day rolling cashflow forecast → feed aggregatefeatures (e.g., predicted min balance, projected variance) into XGBoost alongside staticfeatures
