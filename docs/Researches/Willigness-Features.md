<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# \# Role

Act as a Lead Data Scientist specializing in FinTech and Debt Collection AI.

# Context

I am building a "Willingness-to-Pay" (Propensity) model for a bank's debt collection system. This model predicts the *likelihood* that a delinquent customer will make a payment if contacted. This is distinct from an "Ability-to-Pay" model (which measures financial capacity).

# Objective

I need a comprehensive list of State-of-the-Art (SOTA) features and Target Variables used in modern collections models (XGBoost/LightGBM). I need to hand these requirements to a Database Engineering team, so I need clear definitions.

# Research Requirements

Please provide a structured list of features in the following categories:

1. **Interaction \& Engagement Signals:** Beyond simple "call counts," what derived features capture sentiment? (e.g., "Days since last RPC", "SMS open rate proxies", "Promise-to-Pay (PTP) reliability ratio").
2. **Payment History Behavior:** Features that capture patterns, not just totals. (e.g., "Velocity of payments," "Frequency of partial payments," "Time-to-pay after promise").
3. **The "Silent Payer" \& Self-Cure:** How do we identify customers who pay *without* contact? What features predict this behavior? (e.g., "Digital App Login Frequency", "Balance checking behavior").
4. **Target Variable Definition:** How should I define the "Target" (Y=1) to capture both *Explicit Promises* (PTP Kept) and *Implicit Payments* (Silent Payers)? How do industry leaders handle the "No Contact / Paid Anyway" scenario in labeling?

# Output Format

Please present the data in a table with these columns:

* **Feature Name** (Technical naming)
* **Business Rationale** (Why does this predict willingness?)
* **Data Source/Logic** (e.g., "Derived from Transaction Table: Sum of X / Count of Y")
* **Expected Impact** (High/Medium/Low)

The Willingness-to-Pay model uses behavioral signals from interactions, payment patterns, and digital engagement to predict payment likelihood upon contact. Industry SOTA features emphasize derived ratios and temporal patterns over raw counts for XGBoost/LightGBM training.

## Interaction \& Engagement Signals

| Feature Name | Business Rationale | Data Source/Logic | Expected Impact |
| :-- | :-- | :-- | :-- |
| days_since_last_rpc | Recent successful contact signals current engagement and accessibility; longer gaps indicate avoidance or mobility changes predicting lower willingness. [^1][^2] | `SELECT DATEDIFF(CURDATE(), MAX(contact_date)) FROM contact_log WHERE rpc_success = TRUE AND account_id = ?` | High |
| ptp_reliability_ratio_30d | Ratio of kept promises to total promises captures commitment credibility; low ratio signals habitual breakage indicating low future willingness. [^3][^4] | `SELECT SUM(ptp_kept) / COUNT(*) FROM action_history WHERE ptp_made = TRUE AND action_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) AND account_id = ?` | High |
| sms_open_rate_proxy | Proxy via delivery receipts or click-throughs measures responsiveness to low-friction digital channels; high opens predict higher call answer rates. [^5] | `SELECT COUNT(read_receipt) / COUNT(sent_sms) FROM sms_log WHERE sent_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY) AND account_id = ?` | High |
| engagement_duration_trend_30d | Average call duration or IVR completion time trend shows deepening engagement; increasing duration predicts higher conversion. [^6] | `SELECT AVG(duration_sec) OVER (ORDER BY contact_date ROWS 5 PRECEDING) FROM contact_log WHERE channel = 'PHONE' AND account_id = ?` (rolling avg) | Medium |
| objection_frequency_90d | Count/ratio of objections per contact signals resistance; high frequency predicts lower future willingness despite contact. [^7] | `SELECT COUNT(*) / COUNT(contact_id) FROM agent_notes WHERE sentiment = 'NEGATIVE' OR notes LIKE '%objection%' AND note_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)` | High |
| channel_response_variance | Std dev of response rates across channels (SMS, call, email); low variance indicates reliable engagement path predicting higher willingness. [^8] | `SELECT STDDEV(response_rate) FROM (SELECT channel, COUNT(response)/COUNT(sent) AS response_rate FROM multi_channel_log GROUP BY channel) WHERE account_id = ?` | Medium |
| sentiment_score_avg_7d | NLP-derived sentiment from agent notes or IVR transcripts; negative trend predicts avoidance. [^4] | `SELECT AVG(sentiment_score) FROM nlp_notes WHERE note_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND account_id = ?` (use VADER/HuggingFace) | Medium |

## Payment History Behavior

| Feature Name | Business Rationale | Data Source/Logic | Expected Impact |
| :-- | :-- | :-- | :-- |
| payment_velocity_30d | Payments per day in recent window captures momentum; accelerating velocity predicts sustained willingness. [^8][^9] | `SELECT COUNT(payment_id) / DATEDIFF(MAX(payment_date), MIN(payment_date) + 1) FROM payments WHERE payment_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) AND account_id = ?` | High |
| partial_payment_ratio_90d | Ratio of partial vs. full payments signals ongoing engagement despite constraints; high ratio indicates willingness over capacity issues. [^10] | `SELECT SUM(CASE WHEN amount < principal_due THEN 1 ELSE 0 END) / COUNT(*) FROM payments WHERE payment_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)` | High |
| days_to_pay_after_ptp | Avg days from PTP promise to actual payment; short latency predicts high reliability for future promises. [^3][^7] | `SELECT AVG(DATEDIFF(payment_date, ptp_date)) FROM action_history JOIN payments ON payment_date BETWEEN ptp_date AND DATE_ADD(ptp_date, INTERVAL 30 DAY) WHERE account_id = ?` | High |
| payment_day_of_month_preference | Mode/entropy of payment days-of-month reveals salary cycle alignment; predictable patterns predict willingness. [^8] | `SELECT MODE(day_of_month), SHANNON_ENTROPY(day_of_month) FROM payments WHERE payment_date >= DATE_SUB(CURDATE(), INTERVAL 365 DAY)` | Medium |
| bounce_rate_recent_60d | Ratio of bounced payments predicts frustration/avoidance leading to lower future willingness. [^11] | `SELECT COUNT(bounced) / COUNT(payment_attempts) FROM payment_attempts WHERE attempt_date >= DATE_SUB(CURDATE(), INTERVAL 60 DAY)` | High |
| payment_streak_current | Consecutive successful payments without miss; breaking streaks predicts declining willingness. [^9] | `SELECT COUNT(*) FROM (SELECT payment_date FROM payments WHERE account_id = ? ORDER BY payment_date DESC LIMIT 10) WHERE DATEDIFF(payment_date, LAG(payment_date)) <= 31` | Medium |
| amount_promised_vs_paid_ratio | Avg ratio of actual paid to promised amount; close to 1.0 predicts high honor rate. [^4] | `SELECT AVG(actual_amount / promised_amount) FROM action_history WHERE ptp_made = TRUE AND payment_received_30d = TRUE` | High |

## Silent Payer \& Self-Cure Features

| Feature Name | Business Rationale | Data Source/Logic | Expected Impact |
| :-- | :-- | :-- | :-- |
| digital_login_frequency_14d | Frequent app logins without contact signal proactive monitoring and self-resolution intent. [^5][^12] | `SELECT COUNT(DISTINCT login_date) FROM app_logs WHERE login_date >= DATE_SUB(CURDATE(), INTERVAL 14 DAY) AND account_id = ?` | High |
| balance_check_velocity_30d | High frequency of balance inquiries predicts imminent self-payment without intervention. [^12] | `SELECT COUNT(*) / 30 FROM account_activity WHERE activity_type = 'BALANCE_CHECK' AND date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)` | High |
| self_cure_history_flag | Binary/history count of prior self-cures (paid without contact); predicts repeat behavior. [^12] | `SELECT COUNT(*) FROM account_state_history WHERE state_change = 'DELINQUENT_TO_CURRENT' AND no_contact_period >= 5 AND account_id = ?` | High |
| app_notification_open_rate | High opens of payment reminders without contact predicts digital self-pay path. [^5] | `SELECT COUNT(opened) / COUNT(sent) FROM push_notifications WHERE sent_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)` | Medium |
| portal_payment_attempts_30d | Failed/successful portal logins for payment signal intent despite no agent contact. [^9] | `SELECT COUNT(*) FROM portal_logs WHERE action = 'PAYMENT_ATTEMPT' AND date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)` | Medium |
| early_delinquency_flag | In 1-29 DPD bucket with high digital activity; strong self-cure predictor. [^13] | `IF days_past_due BETWEEN 1 AND 29 THEN 1 ELSE 0` from `account_state` | Medium |
| no_contact_pay_ratio_365d | Ratio of payments made without preceding contact; direct silent payer signal. [^12] | `SELECT SUM(CASE WHEN payment_made AND no_contact_30d_preceding THEN 1 ELSE 0 END) / COUNT(payments) FROM payments JOIN contact_log ON ...` | High |

## Target Variable Definition

**Recommended Target (Y=1 Definition)**: Binary label for "Payment Made Within 7 Days of Eligible Contact Window". This captures both explicit (PTP kept) and implicit (silent payers post-contact) behaviors while handling the "No Contact / Paid Anyway" scenario.


| Aspect | Definition | SQL Logic Example | Industry Handling [^6][^12][^14] |
| :-- | :-- | :-- | :-- |
| **Positive Label (Y=1)** | Any payment (full/partial) received within 7 days *after* last successful RPC *OR* PTP kept within 7 days. Includes silent payers if they pay post-contact exposure. | `SELECT CASE WHEN EXISTS (SELECT 1 FROM payments WHERE payment_date BETWEEN last_rpc_date AND DATE_ADD(last_rpc_date, INTERVAL 7 DAY)) OR (ptp_kept AND DATEDIFF(ptp_keep_date, ptp_date) <= 7) THEN 1 ELSE 0 END FROM account_state JOIN action_history` | Leaders like FICO/Experian use 7-14 day windows post-contact; weights PTP_kept higher (e.g., stratified sampling). |
| **Negative Label (Y=0)** | No payment within 7 days post-RPC/PTP *AND* no self-cure transition. Exclude pure "no contact" cases to avoid selection bias. | `SELECT CASE WHEN NOT EXISTS (payments in window) AND ptp_broken = TRUE THEN 1 ELSE 0 END` | Filter out accounts with zero contacts in lookback; use uplift modeling to estimate contact effect. |
| **Window Handling** | 7-day prediction horizon balances signal strength with business cycle (weekly pay cycles). | Use cohort analysis: label based on outcome 7 days after feature snapshot date. | McKinsey/FICO: 5-14 days; validate with time-series CV to avoid leakage. |
| **Silent Payer Adjustment** | Label Y=1 for self-cures within 5 days of delinquency entry *if* digital engagement present (e.g., login). | `SELECT CASE WHEN state_change = 'SELF_CURE' AND digital_activity_score > 0.5 THEN 1 ELSE 0 END` | Propensity uplift models (e.g., two-model approach: treated vs. control cohorts) estimate incremental payment lift. |
| **Class Imbalance** | Expect 20-40% positive rate; use stratified sampling, SMOTE, or class weights in XGBoost. | N/A | XGBoost scale_pos_weight = neg_count / pos_count; monitor precision@top-20%. |

**Implementation Note**: Generate targets via SQL materialized view refreshed daily; snapshot features at T-1 day before outcome window to prevent leakage. Validate with holdout cohorts segmented by delinquency bucket.[^10][^15]
<span style="display:none">[^16][^17][^18][^19][^20][^21][^22][^23][^24][^25][^26][^27][^28][^29][^30]</span>

<div align="center">⁂</div>

[^1]: https://www.tratta.io/blog/improving-right-party-contact-strategies

[^2]: https://datacultr.com/device-financing/right-party-contact-rpc-the-secret-to-higher-collection-success/

[^3]: https://resultscx.com/wp-content/uploads/2023/11/Case-Study_Improving-PTP-Rate-in-Collections_Long-form.pdf

[^4]: https://www.linkedin.com/posts/arunuchil_ai-driven-promise-to-pay-accuracy-a-activity-7389510448544452608-Y0Hp

[^5]: https://ezee.ai/debt-collection/debt-collection-software-for-banks/

[^6]: https://github.com/gbencke/DeepMailing

[^7]: https://www.vodex.ai/blog-posts/how-to-automate-promise-to-pay-ptp-capture-with-voice-ai

[^8]: https://worldbusinessoutlook.com/why-ai-is-the-silent-partner-in-effective-collections/

[^9]: https://ai.respaid.com/ai-learns-debtor-behavior-collections

[^10]: https://blog.equabli.com/9-predictive-analytics-models-to-optimize-debt-collection-strategies/

[^11]: https://patents.google.com/patent/US7191150B1/en

[^12]: https://www.emergeml.com/case-studies-1/self-cure-of-credit-card-accounts-in-collections--

[^13]: https://www.utkarsh.bank.in/uploads/pdf/our-policy/template_ten/Collection_Process.pdf

[^14]: https://credit-and-collections-professionals.com/glossary/propensity-to-pay-ptp/

[^15]: https://www.prem-melville.com/publications/equitant-kdd07.pdf

[^16]: https://www.linkedin.com/pulse/machine-learning-debt-collections-happening-now-chris-maranis

[^17]: https://www.academia.edu/38303397/IRJET_Pay_Later_Loan_Prediction_for_Online_Shopping_Customers

[^18]: https://arxiv.org/html/2412.16333

[^19]: https://fastercapital.com/topics/predictive-modeling-in-debt-collection-analysis.html

[^20]: https://www.impressiondigital.com/blog/propensity-modelling/

[^21]: https://www.ewadirect.com/proceedings/ace/article/view/17404/pdf

[^22]: https://www.marketsizer.io/blog-posts/crm-propensity-model-data-points-for-b2b-saas

[^23]: https://arxiv.org/pdf/2412.16333v1.pdf

[^24]: https://cxl.com/blog/propensity-modeling/

[^25]: https://www.billgosling.com/blog/how-ai-insights-optimizes-promise-to-pay-recovery-rates/

[^26]: https://www.algonew.com/en/ai-powered-decision-engines-the-silent-revolution-in-financial-institutions-debt-collection/

[^27]: https://www.interprose.com/blog/ai-in-collections-from-predictive-analytics-to-personalized-strategies

[^28]: https://bridgeforce.com/insights/transforming-recovery-rates-with-debt-collection-ai-innovation/

[^29]: https://calculatorzilo.com/propensity-to-pay-calculator/

[^30]: https://ai-infrastructure.org/feature-engineering-for-fraud-detection/

