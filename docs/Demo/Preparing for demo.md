## what does each feature mean and does and how iot help in finding if a customer is willing or not.
        schema = {
            "CUST_INFO_ID": pl.String,
            # PTP Features (Integers)
            "SNAPSHOT_DATE": pl.String,
            "DAYS_SINCE_LAST_RPC": pl.Int64,
            "PTP_RELIABILITY_RATIO": pl.Float64,
            "PAYMENT_VELOCITY_30D": pl.Int64,
            "PARTIAL_PAYMENT_RATIO": pl.Float64,
            "SELF_CURE_HISTORY_FLAG": pl.Int64,
            "BOUNCE_RATE_60D": pl.Float64,
            "BROKEN_PTP_COUNT_6M": pl.Int64,
            "TARGET_WILLINGNESS": pl.Int64,
        }

## what does each feature mean and does and how iot help in finding if a customer is willing or not.

        schema = {
            "CUST_INFO_ID": pl.String,
            "SNAPSHOT_DATE": pl.String,
            "INFLOW_VARIANCE_30D": pl.Float64,
            "CASH_RUNWAY_DAYS_ESTIMATED": pl.Float64,
            "SPENDING_VOLATILITY_CV_60D": pl.Float64,
            "DEBT_SERVICE_PROXY_RATIO": pl.Float64,
            "NSF_EVENT_RATE_60D": pl.Float64,
            "ZERO_BALANCE_DAYS_RATIO_30D": pl.Float64,
            "TARGET_ABILITY": pl.Int64
        }