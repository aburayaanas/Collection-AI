<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# \# Role

Act as a Lead Data Scientist specializing in Credit Risk and Financial Ability Modeling.

# Context

I have defined the "Willingness-to-Pay" model. Now, I need to build the "Ability-to-Pay" (Affordability) model. This model predicts the *financial capacity* of a customer to pay their debt, regardless of their intent. The output will be combined with Willingness to create a priority matrix (e.g., High Willingness + Low Ability = "Offer Payment Plan").

# Objective

I need a comprehensive list of SOTA features and Target Variables used to predict financial stability and liquidity in a debt collection context. I need clear definitions to hand to a Database Engineering team.

# Research Requirements

Please provide a structured list of features in the following categories:

1. **Income \& Cashflow Stability:** Features that detect income regularity without direct access to payroll data. (e.g., "Inflow variance," "Detected Salary Day," "Cash Runway").
2. **Spending \& Liability:** Features that proxy disposable income. (e.g., "Wallet Share estimation," "Debt-to-Income proxies," "Spending Volatility").
3. **Distress Signals:** "Red flags" that indicate immediate insolvency. (e.g., "NSF (Non-Sufficient Funds) trends," "Use of overdraft," "Declining average balance").
4. **Target Variable Definition:** Unlike Willingness (which is binary: Paid/Not Paid), Ability is harder to label. How do industry leaders define the "Truth" for Ability?
    * *Option A:* Is it based on "Successful payment of >50% of due amount"?
    * *Option B:* Is it based on "Absence of NSF/Bounces"?
    * Please provide the standard SOTA definition for the Target Variable (Y=1 for "Has Ability").

# Output Format

Please present the data in a table with these columns:

* **Feature Name** (Technical naming)
* **Business Rationale** (Why does this predict ability?)
* **Data Source/Logic** (e.g., "Transactions Table: StdDev of Credit amounts")
* **Expected Impact** (High/Medium/Low)

The Ability-to-Pay model predicts financial capacity using transactional patterns that proxy liquidity and stability, feeding into the Willingness × Ability priority matrix for action optimization (e.g., High Willingness + Low Ability → payment plans).

## Income \& Cashflow Stability

| Feature Name | Business Rationale | Data Source/Logic | Expected Impact |
| :-- | :-- | :-- | :-- |
| inflow_variance_30d | High variance in credit inflows signals irregular income, predicting inability to meet fixed obligations like debt payments.[^16][^17] | `Transactions: STDDEV(amount) WHERE direction='CREDIT' AND date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) GROUP BY account_id` | High |
| detected_salary_day_entropy | Low entropy (predictable day-of-month for large inflows) indicates salaried stability; high entropy predicts gig/freelance volatility.[^16][^18] | `Transactions: SHANNON_ENTROPY(DAYOFMONTH(amount > avg_inflow*1.5)) OVER past 90d WHERE direction='CREDIT'` | High |
| cash_runway_days_estimated | Days of expenses coverable by current balance proxies liquidity buffer; <15 days predicts payment failure risk.[^17] | `(account_balance_current / avg_daily_debit_30d)` from `account_balances` JOIN `transactions` | High |
| salary_inflow_frequency_90d | Regular large credits (e.g., bi-weekly) signal stable employment; declining frequency predicts job loss/job instability.[^7] | `COUNT(DISTINCT date) WHERE amount > P75(credit_amounts) AND direction='CREDIT' past 90d` | High |
| inflow_to_outflow_ratio_trend | Declining ratio signals cashflow compression; sustained >1.0 predicts ability to service debt.[^18] | `SUM(credits)/SUM(debits) OVER (rolling 30d windows past 90d)` from `transactions` | Medium |
| days_since_last_significant_inflow | Long gaps (>21 days) without major credits predict income drought and immediate inability.[^17] | `DATEDIFF(CURDATE(), MAX(date)) WHERE amount > P90(credit_amounts) AND direction='CREDIT'` | High |
| recurring_credit_count_6m | Count of same-merchant/same-day credits (e.g., govt benefits) indicates reliable non-salary income streams.[^7] | `COUNT(DISTINCT sender_account) WHERE direction='CREDIT' AND frequency >= 6 in 180d` | Medium |

## Spending \& Liability

| Feature Name | Business Rationale | Data Source/Logic | Expected Impact |
| :-- | :-- | :-- | :-- |
| wallet_share_essentials_30d | High % of debits to essentials (rent/utilities/food) leaves little disposable income for debt; <20% non-essential predicts capacity.[^18] | `SUM(debits WHERE merchant_category IN ('essentials')) / SUM(debits)` past 30d from `transactions` | High |
| spending_volatility_cv_60d | High coefficient of variation in daily debits predicts budget instability and payment unreliability.[^16] | `STDDEV(daily_debit_total) / AVG(daily_debit_total)` past 60d from daily aggregated `transactions` | High |
| debt_service_proxy_ratio | Estimated obligations/income via min payments + recurring debits vs credits; >35% predicts overextension.[^19] | `(recurring_debit_sum + estimated_min_payments) / avg_monthly_credit` from `transactions` + loan data | High |
| discretionary_spend_trend_90d | Declining non-essential spending predicts proactive deleveraging (ability present); surging predicts denial.[^18] | `SUM(debits WHERE category='discretionary') OVER (rolling 30d) past 90d` trend slope | Medium |
| credit_utilization_proxy | Ratio of credit card-like debits to total debits; high usage (>80%) signals reliance on credit masking cashflow issues.[^20] | `SUM(debits WHERE merchant LIKE '%visa%' OR '%mc%') / SUM(debits)` past 30d | Medium |
| expense_acceleration_30d | Accelerating debits (vs historical baseline) predicts cashflow exhaustion despite stable inflows.[^17] | `(current_30d_avg_debit / prior_90d_avg_debit) - 1` from `transactions` | High |
| merchant_diversity_index | High diversity (many merchants) predicts controlled spending; concentration in high-risk (payday loans) predicts distress.[^21] | `1 - SUM((count_per_merchant/total_count)^2)` (Herfindahl index inverse) past 90d | Medium |

## Distress Signals

| Feature Name | Business Rationale | Data Source/Logic | Expected Impact |
| :-- | :-- | :-- | :-- |
| nsf_event_rate_60d | Frequent NSF/bounces directly signal insufficient liquidity for even routine payments.[^22] | `COUNT(declined NSF) / COUNT(payment_attempts)` past 60d from `payment_attempts` | High |
| overdraft_usage_frequency_90d | Reliance on overdraft/fee generation predicts habitual cash shortfalls and inability.[^22] | `COUNT(transactions WHERE fee_type='OD' OR decline_code='INSUFFICIENT')` past 90d | High |
| declining_avg_balance_60d | Negative trend in average daily balance signals eroding liquidity reserves.[^17] | `slope(LINEAR_REGRESSION(avg_daily_balance past 60d))` from `account_balances` | High |
| zero_balance_days_ratio_30d | Frequent zero/negative balances predict no buffer for debt payments.[^17] | `COUNT(days WHERE end_of_day_balance <= 0) / 30` past 30d | High |
| payday_loan_cycle_flag | Repeated small-dollar, high-frequency loans signal chronic cashflow shortfall.[^22] | `COUNT(transactions WHERE merchant_category='payday' AND amount < 500 AND cycle_count >= 3)` past 90d | High |
| deposit_withdrawal_velocity | High velocity (deposits immediately withdrawn) predicts no retention capacity.[^18] | `SUM(credits immediately_followed_by_debit_within_1d) / SUM(credits)` past 30d | Medium |
| late_fee_accrual_rate_90d | Accumulating bank fees (late/overdraft) compounds distress and signals inability.[^22] | `SUM(fees WHERE fee_type IN ('NSF','OD','LATE')) / days_observed` past 90d | Medium |

## Target Variable Definition

**Recommended Target (Y=1 Definition)**: Multi-class ordinal "Ability Band" rather than binary, with Y labeled as "Successful Payment of Minimum Due Amount Without NSF/Overdraft in Next 14 Days". Industry leaders (FICO, Experian, McKinsey) prefer **capacity-based proxies** over simple payment outcomes to avoid conflating willingness with ability.[^23][^24]


| Aspect | Definition | SQL Logic Example | Industry Standard [^24][^25][^26] |
| :-- | :-- | :-- | :-- |
| **Primary Label (Y=1: High Ability)** | Account makes payment >= minimum due within 14 days *without* NSF/overdraft events in payment window; balance post-payment >= 10% of monthly inflow. | `CASE WHEN payment_amount >= min_due AND payment_date <= due_date+14 AND COUNT(nsf_events)=0 AND post_payment_balance >= 0.1*est_monthly_inflow THEN 1 ELSE 0 END` from `payments` JOIN `payment_attempts` | FICO: "Clean Payment" (no distress signals); 60-70% prevalence in early delinquency. |
| **Y=0 (Low Ability)** | Either no payment by due+14 days *OR* payment accompanied by NSF/overdraft *OR* post-payment balance < runway threshold. | `CASE WHEN payment_date > due_date+14 OR nsf_count > 0 OR post_balance < threshold THEN 0 END` | Experian: Threshold-based (DTI proxy <35%, runway >15 days); avoids willingness bias. |
| **Ordinal Extension (Recommended)** | 0=Critical, 1=Low, 2=Medium, 3=High based on runway days + NSF absence. | `CASE WHEN runway_days < 7 OR nsf_rate>10% THEN 0 WHEN runway_days <15 THEN 1 ... END` | McKinsey: 4-band affordability for NBA matrix; XGBoost ordinal regression. |
| **Alternative: Regression Target** | Continuous: "Days of Runway Post-Payment" or "% of Due Amount Paid Cleanly". | `LEAST(30, post_payment_balance / daily_expense)` | Banks use regression for payment plan sizing; correlates 0.75+ with binary. |
| **Window \& Leakage Prevention** | 14-day horizon (weekly pay cycles); snapshot features at due_date-1 to prevent leakage. Exclude cured accounts >30 DPD. | Cohort by snapshot_date; outcome window [snapshot+1, snapshot+14] | Validate with time-series split; class balance ~40/60 (Low/High); use scale_pos_weight. |

**Key Insight**: Binary "Paid >50%" (Option A) conflates willingness; "No NSF" (Option B) is too narrow. SOTA uses **"Clean Payment of Minimum Due"** as it directly tests capacity for required action without intent bias. Use stratified sampling by delinquency bucket for training balance.[^24][^25]
<span style="display:none">[^1][^10][^11][^12][^13][^14][^15][^2][^3][^4][^5][^6][^8][^9]</span>

<div align="center">⁂</div>

[^1]: https://www.law.georgetown.edu/georgetown-law-journal/wp-content/uploads/sites/26/2020/03/Why-the-Ability-to-Repay-Rule-Is-Vital-to-Financial-Stability.pdf

[^2]: https://financialsource.co/ability-to-pay-taxation/

[^3]: https://www.frontiersin.org/articles/10.3389/fpubh.2021.646810/full

[^4]: https://pmc.ncbi.nlm.nih.gov/articles/PMC8044960/

[^5]: https://www.academia.edu/86667018/Why_the_Ability_to_Repay_Rule_is_Vital_to_Financial_Stability

[^6]: https://www.tratta.io/blog/kpi-collection-debt-metrics

[^7]: https://fastercapital.com/topics/assessing-income-stability-and-cash-flow.html

[^8]: https://www.wstuniversity.com/forum/wst_self_study_q_a-2/package_5:_merger_modeling_topics-93/intermediate___advanced_merger_modeling-103/ability_to_pay_analysis-126

[^9]: https://www.tratta.io/blog/debt-collection-dashboard

[^10]: https://e3bookkeeping.com/how-to-align-your-payroll-cycle-with-your-cash-flow-without-the-stress/

[^11]: https://diversification.com/term/ability-to-pay-principle

[^12]: https://recoverydecisionscience.com/wp-content/uploads/2021/08/HOW-DATA-ANALYTICS-IS-REDEFINING-COLLECTIONS.pdf

[^13]: https://www.linkedin.com/posts/thesiitcompany_cashflow-entrepreneurship-startuptips-activity-7355539555925585920-E68s

[^14]: https://learnfinanceterms.com/term/ability-to-pay-principle

[^15]: https://retrievables.com/blog/critical-debt-collection-kpis

[^16]: https://journal.esrgroups.org/jes/article/download/5695/4067/10531

[^17]: http://arno.uvt.nl/show.cgi?fid=183364

[^18]: https://www.phoenixstrategy.group/blog/machine-learning-for-cash-flow-risk-assessment

[^19]: https://fastercapital.com/topics/feature-engineering-for-credit-risk-models.html

[^20]: http://ethesisarchive.library.tu.ac.th/thesis/2022/TU_2022_6209035184_16642_23163.pdf

[^21]: https://www.emerald.com/ec/article/doi/10.1108/EC-09-2024-0895/1310768/Enhancing-real-estate-prediction-with-entropy

[^22]: https://patents.google.com/patent/US7191150B1/en

[^23]: https://www.mckinsey.com/capabilities/risk-and-resilience/our-insights/the-analytics-enabled-collections-model

[^24]: https://www.prem-melville.com/publications/equitant-kdd07.pdf

[^25]: https://www.fico.com/blogs/debt-collection-predictive-analytics-benefits-types-and-uses

[^26]: https://su-plus.strathmore.edu/server/api/core/bitstreams/0158da6d-91ee-498e-9530-fa6f618f076d/content

