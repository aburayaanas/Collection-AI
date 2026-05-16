### Phase 3: Reinforcement Learning (Feedback Loop)
- [ ] **DWH Integration**: Coordinate with DB team to create `PIO_COLL_AI_NBA_FEEDBACK` view (Outcome tracking e.g., Paid > 0 in 72h).
- [ ] **Reward Tracker**: Implement `src/engine/nba/reward_tracker.py` to ingest feedback and map outcomes to decisions.
- [ ] **Bandit Reinforcement**: Implement the update logic to adjust Bandit weights based on reward success rates.
- [ ] **Automation**: Schedule the Reward Tracker to run daily with a 3-day lookback lag.
- [ ] **Monitoring**: Create a dashboard to track "Success Rate per Channel" over time.

### Phase 4: MLOps & Automated Orchestration
- [ ] **Containerization**: Create a `Dockerfile` and `docker-compose.yml` for stable, repeatable environments.
- [ ] **Scheduling**: Work with infra to attach the container to an orchestrator (Airflow/Jenkins) for a 2:00 AM daily run.
- [ ] **Alerting**: Implement a Slack/Email webhook in `src.core.logger` to alert on `CRITICAL` pipeline failures.
- [ ] **Logging Retention**: Implement a log rotation policy to keep the last 30 days of production logs.

### Phase 5: The Champion / Challenger Rollout (A/B Testing)
- [ ] **Control Group Logic**: Add a hashing-based split in `src.engine.nba.orchestrator` to route 10% of customers to a "Control" group.
- [ ] **Manual Override**: Ensure Control group customers receive the "Old Process" recommendations (Baseline).
- [ ] **KPI Comparison**: Build a query to compare the Recovery Rate ($ collected) of the AI group vs. the Control group.
- [ ] **Portfolio Scaling**: Implement a configuration flag to slowly increase AI coverage (e.g., 10% -> 50% -> 90%).