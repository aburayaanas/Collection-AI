---
description: 'Pillar 4: Benchmarks & Real-World Architecture'
---

# 05-constraints-flow

### Validated Performance Improvements

| Metric                        | Source                     | Improvement                     | Context                                                  |
| ----------------------------- | -------------------------- | ------------------------------- | -------------------------------------------------------- |
| Collections Recovery          | McKinsey (2024)            | +10% vs. baseline               | Gen AI + advanced segmentation                           |
| Operational Efficiency        | McKinsey (2024)            | -40% opex reduction             | Full collections workflow automation                     |
| Customer Satisfaction         | McKinsey (2024)            | +30% satisfaction scores        | Personalized, timely outreach                            |
| Behavioral Scoring Impact     | Industry Report (2025)     | +40% higher liquidation results | AI-driven segmentation vs. traditional                   |
| Actor-Critic (DRL)            | Academic Study             | 73.22% reward rate              | Real-time field testing; 20.34% collection % improvement |
| XGBoost Willingness           | Propensity Literature      | 75–82% AUC                      | Industry-standard performance                            |
| LSTM Cashflow                 | Forecasting Benchmarks     | RMSE 15–25%                     | Superior to SARIMA on weekly horizons                    |
| Fraud Detection (Kafka-based) | Bank of Ayudhya (Krungsri) | <60 seconds detection latency   | Event-driven architecture                                |

### Recommended Tech Stack

Core Application Layer:



| Tier                | Technology                            | Rationale                                                             |
| ------------------- | ------------------------------------- | --------------------------------------------------------------------- |
| API / Orchestration | FastAPI (Python) or SpringBoot (Java) | Low-latency REST endpoints for action requests; native async support  |
| Model Serving       | TensorFlow Serving or MLflow          | Sub-100ms model inference; A/B testing, versioning, rollback          |
| Decision Engine     | Drools 8.x + kie-spring               | Fast rule evaluation; hot-deployment of compliance rules              |
| Contextual Bandit   | Custom (Python) or VowpalWabbit       | Lightweight; supports online learning from streaming feedback         |
| Batch Scoring       | PySpark on Databricks                 | Distributed scoring of millions of accounts; native MLlib integration |



### Batch vs. Real-Time Architecture Decision

* **Batch (Recommended for Most Implementations)**
  * **Nightly cycle:** Score all accounts at midnight; populate agent queues for next business day.
  * **Latency tolerance:** 18–24 hours acceptable (most contact attempts happen during business hours anyway).
  * **Cost efficiency:** One nightly PySpark job >> real-time streaming 24/7.
  * **Operational simplicity:** Single DAG orchestration, fewer failure modes.
* **Real-Time Enhancements (Add if high-value ROI):**
  * **Payment received in-flight:** If customer pays via IVR or portal mid-day, trigger re-scoring for same-day escalation.
  * **Status change triggers:** If account rolls into 90+ DPD, immediately flag for legal escalation review.
  * **Tools:** Kafka topics (payments, account updates) → Stream processor (Flink or ksqlDB) → Redis cache update → next call to NBA engine uses fresh data.
