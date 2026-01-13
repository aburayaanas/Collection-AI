# 01-constraints-flow

#### Pillar 1: Willingness vs. Ability AI Model Architecture

Willingness-to-Pay Model (Propensity)\
Purpose\
: Predict behavioral intent—likelihood debtor will make a payment in the nextengagement window\
Typical Output\
: Probability score; higher = greater likelihood of payment commitment\
Training Feedback\
: Promise-to-Pay (PTP) broken/kept, contact frequency responsiveness,engagement depth

| Feature Category       | Data Source                      | Rationale                                                                                                                      | Note                                                                                                                                            |
| ---------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Contact Responsiveness | NULL                             | Signal of engagementand intent                                                                                                 | Ask Profisionals                                                                                                                                |
| Promise Behavior       | PIO\_PTP\_COLLECTOR              | Direct behavioralsignal of willingness                                                                                         | NULL                                                                                                                                            |
| Engagement Depth       | UNI\_REPOS.PIO\_SMS\_COLLECTOR   | Proxy for attentivenessand motivation                                                                                          | <ul><li>which owner to use uni or pio_collection</li><li>Does this table contains the logic of SMS open rate, email interaction count</li></ul> |
| Payment Initiation     | PIO\_TRANSACTIONS                | Behavioralcommitment signal                                                                                                    | ask gemini. this feature seems to be hard to implement.                                                                                         |
| Temporal Patterns      | Historicaltransactions +calendar | Captures liquiditytiming windows                                                                                               | Hard to implement but usefull.                                                                                                                  |
| Sentiment/Narrative    | PIO\_COLL.PIO\_MEMO\_NOTES\_INFO | <ul><li>Collector notes sentiment (NLP),complaint frequency, dispute flag</li><li>Capturespsychographic intentsignal</li></ul> | NULL                                                                                                                                            |

Algorithm Selection: Gradient Boosting (XGBoost) or LightGBM\
Rationale: Binary/multi-class classification on tabular engagement data; interpretable featureimportance crucial for agent decision-support\
Recommended Python Libraries:\
xgboost\
,\
shap\
(for explainability),\
optuna\
(hyperparametertuning)\
Typical Performance: 75–82% AUC on held-out test sets; 6–12 month retraining cycle withconcept drift management

