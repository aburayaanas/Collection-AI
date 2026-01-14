---
description: 'Pillar 2: Next Best Action (NBA) Engine Logic'
---

# 03-constraints-flow

### Architecture Decision: Hybrid Rule-RL Approach

The industry uses three architectural patterns:

<table><thead><tr><th valign="top">Pattern</th><th valign="top">Mechanism</th><th width="139.6666259765625" valign="top">Strengths</th><th valign="top">Weaknesses</th><th valign="top">Notes</th></tr></thead><tbody><tr><td valign="top">Pure Rule Engine(Drools)</td><td valign="top">Deterministic rules: IF(Risk=High) THENAction=Call</td><td valign="top">Explainable,auditabl, fastdeployment</td><td valign="top">Brittle; cannot optimize multi-step sequences; high manualrule tuning.</td><td valign="top">We might not use it, usally this is used by the rule based engine already built by the company.</td></tr><tr><td valign="top">Pure ReinforcementLearning(DQN/DDPG)</td><td valign="top">Agent learns optimal policyend-to-end via trial-and-error</td><td valign="top">Discovers non-obviousstrategies; auto-adapts</td><td valign="top">Delayed rewards (paymentarrives 10+ days after action);sample inefficient; difficult toenforce compliance constraints</td><td valign="top">RL is needed in such systems beacuse its an optimization problem, but we prefer to use clasical ML first e.g. XGBoost</td></tr><tr><td valign="top">Hybrid (ContextualBandits + RuleGuard Rails)</td><td valign="top">RL selects action; ruleengine enforcesconstraints (FDCPA,frequency caps, channelrules)</td><td valign="top">Best of both: fastlearning + safety</td><td valign="top">Requires careful constraintdesign; monitoring complexity</td><td valign="top">usallly we will take this approch</td></tr></tbody></table>

### Recommendation: Hybrid Multi-Armed Bandit (MAB) + Contextual Bandit + Rule Engine

Rationale:

1.Real-world collections have hard constraints: FDCPA compliance (maximum contactfrequency, time-of-day rules, right-party contact verification).

2.Delayed reward problem: Payment happens 10–30 days post-action, making end-to-endRL training unstable.

3.Imitation Learning bridges the gap: Learn from historical collections policies (agentpolicies), then use offline RL to marginally improve.



### Recommended RL Framework: Contextual Bandits

Core Algorithm: LinUCB (Linear Upper Confidence Bound) or Thompson Sampling

#### Why Not DQN?

* DQN requires millions of samples and suffers from non-stationarity in collections (portfoliocomposition changes, seasonal effects).
* Collections actions have sparse, delayed feedback: agent calls today; payment signalarrives in 10–30 days (or never).
* DQN's experience replay and two-network architecture add latency unfit for real-timescoring.



### Why Contextual Bandits?

* Each customer context (willingness, affordability, delinquency bucket, channel) maps to anaction (Call, SMS, Letter, Escalate, Skip).
* Bandit algorithms (UCB, Thompson Sampling) balance exploration vs. exploitation in astateless decision frame.
* Regret bounds are theoretically sound and empirically validated.
