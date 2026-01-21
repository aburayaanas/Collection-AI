---
description: Model Integration & Scoring
---

# 02-constraints-flow

### Two-Stage Willingness x Ability Matrix



The two models output independent probabilities that feed a 2×2 matrix (or continuous 2D scorespace).

## Pseudo-code

willingness\_prob = xgboost\_willingness.predict\_proba(engagement\_features)\[^ 1 ]affordability\_band = lstm\_xgboost\_hybrid.predict(cashflow\_features). Model Integration & Scoring affordability\_score = map\_band\_to\_prob(affordability\_band)

## e.g., High→0.8

## Composite score for stratification

nba\_priority = (willingness\_prob \* 0.6 ) + (affordability\_score \* 0.4 )

## 60/40 weights; adjust based on portfolio risk tolerance



## Key Implementation Consideration:

Both models must emit calibrated probabilities (not rawscores). Use isotonic regression or Platt scaling to ensure probabilities are comparable acrossmodels.
