from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class FeatureMetadata:
    """
    Metadata for model features, used for UI display and LLM prompting.
    """
    db_column: str
    ui_label: str
    business_context: str

class XAIMapper:
    """
    The deterministic translation layer for Collection AI Explainability.
    Maps raw DB columns to human-readable labels and descriptive context.
    """

    REGISTRY: Dict[str, FeatureMetadata] = {
        # ── Willingness Features ──────────────────────────────────────────
        "DAYS_SINCE_LAST_RPC": FeatureMetadata(
            db_column="DAYS_SINCE_LAST_RPC",
            ui_label="Recency of Contact",
            business_context="The number of days since the last successful Right-Party Contact. Increasing values often indicate a decay in engagement and higher risk of collection avoidance."
        ),
        "PTP_RELIABILITY_RATIO": FeatureMetadata(
            db_column="PTP_RELIABILITY_RATIO",
            ui_label="Long-term Promise Reliability",
            business_context="The historical percentage of Promise-to-Pay (PTP) agreements successfully fulfilled. A high ratio indicates the customer was trustworthy in the long-term past."
        ),
        "PAYMENT_VELOCITY_30D": FeatureMetadata(
            db_column="PAYMENT_VELOCITY_30D",
            ui_label="Recent Payment Frequency",
            business_context="Count of repayment transactions in the last 30 days. Higher velocity indicates an active intent to resolve the debt, regardless of the amount."
        ),
        "PARTIAL_PAYMENT_RATIO": FeatureMetadata(
            db_column="PARTIAL_PAYMENT_RATIO",
            ui_label="Partial Payment Tendency",
            business_context="Ratio of payments that were less than the minimum due. High values indicate a customer is financially constrained but still maintains a willingness to pay what they can."
        ),
        "SELF_CURE_HISTORY_FLAG": FeatureMetadata(
            db_column="SELF_CURE_HISTORY_FLAG",
            ui_label="Self-Cure Behavior",
            business_context="A binary flag indicating if the customer has historically paid without requiring a contact attempt. High importance here suggests the customer prefers minimal intervention."
        ),
        "BOUNCE_RATE_60D": FeatureMetadata(
            db_column="BOUNCE_RATE_60D",
            ui_label="NSF Frequency (60d)",
            business_context="The rate of Non-Sufficient Funds (NSF) events in the last 60 days. This indicates recurring cash flow volatility and a high risk of payment failure."
        ),
        "BROKEN_PTP_COUNT_6M": FeatureMetadata(
            db_column="BROKEN_PTP_COUNT_6M",
            ui_label="Recent Broken Promises (6M)",
            business_context="The total count of defaulted payment agreements over the last 6 months. High values indicate a recent negative shift in compliance behavior, which may override historical reliability."
        ),

        # ── Ability Features ──────────────────────────────────────────────
        "INFLOW_VARIANCE_30D": FeatureMetadata(
            db_column="INFLOW_VARIANCE_30D",
            ui_label="Income Volatility",
            business_context="The variance in credits to the account over the last 30 days. High variance indicates unpredictable income streams, making structured settlement plans risky."
        ),
        "CASH_RUNWAY_DAYS_ESTIMATED": FeatureMetadata(
            db_column="CASH_RUNWAY_DAYS_ESTIMATED",
            ui_label="Estimated Liquidity Runway",
            business_context="Estimated number of days until the customer exhausts current liquid cash based on spending patterns. Low values indicate imminent financial distress."
        ),
        "SPENDING_VOLATILITY_CV_60D": FeatureMetadata(
            db_column="SPENDING_VOLATILITY_CV_60D",
            ui_label="Spending Habit Stability",
            business_context="Coefficient of variation in outflows over 60 days. Rapidly changing spending patterns often precede a default event."
        ),
        "DEBT_SERVICE_PROXY_RATIO": FeatureMetadata(
            db_column="DEBT_SERVICE_PROXY_RATIO",
            ui_label="Debt Service Burden",
            business_context="A proxy for the Debt-to-Income ratio. Higher values indicate that a larger portion of the customer's income is already committed to other obligations."
        ),
        "NSF_EVENT_RATE_60D": FeatureMetadata(
            db_column="NSF_EVENT_RATE_60D",
            ui_label="Payment Rejection Rate",
            business_context="The frequency of rejected transactions due to insufficient funds. This is a critical barrier to 'Ability to Pay'."
        ),
        "ZERO_BALANCE_DAYS_RATIO_30D": FeatureMetadata(
            db_column="ZERO_BALANCE_DAYS_RATIO_30D",
            ui_label="Empty Balance Frequency",
            business_context="Percentage of time the account balance remained at or below zero in the last 30 days. High ratios are a strong signal of severe insolvency."
        ),
    }

    def get_metadata(self, feature_name: str) -> FeatureMetadata:
        """
        Retrieves metadata for a given feature name.
        Includes a critical fallback to prevent UI/LLM crashes.
        """
        # Normalize to upper case to match registry
        key = feature_name.upper()
        
        if key in self.REGISTRY:
            return self.REGISTRY[key]
        
        # Critical Fallback Logic
        return FeatureMetadata(
            db_column=feature_name,
            ui_label=feature_name.replace('_', ' ').title(),
            business_context="System detected behavioral variance in this metric. No specific business definition is mapped, but the feature significantly influenced the model's decision."
        )
