"""
Detailed Feature Descriptions for Collection AI SHAP Explanations.

These provide contextual explanations for WHY each feature is significant.
Stored in the SHAP_DESCRIPTION column (separate from the short expansion names).

Temporary hard-coded dictionaries — will be replaced with
metadata-driven descriptions later.
"""


# ═══════════════════════════════════════════════════════════════════════
#  Willingness Model Feature Descriptions
# ═══════════════════════════════════════════════════════════════════════
willingness_feature_descriptions = {
    "TOTAL_PTP_COUNT": (
        "Total number of Promise-to-Pay agreements recorded for this "
        "customer, indicating their engagement with repayment commitments."
    ),
    "PTP_BROKEN_COUNT": (
        "Count of broken Promise-to-Pay agreements, reflecting the "
        "customer's tendency to default on repayment commitments."
    ),
    "PTP_KEPT_COUNT": (
        "Count of honored Promise-to-Pay agreements, indicating the "
        "customer's reliability in following through on commitments."
    ),
    "PTP_BROKEN_RATIO": (
        "Ratio of broken promises to total promises, a key indicator "
        "of the customer's willingness to repay obligations."
    ),
    "DAYS_SINCE_LAST_BROKEN_PTP": (
        "Number of days since the last broken Promise-to-Pay, showing "
        "recent repayment behaviour trends."
    ),
    "TOTAL_ATTEMPTS_LIFETIME": (
        "Total lifetime contact attempts made to the customer across "
        "all channels, reflecting collection engagement history."
    ),
    "SUCCESSFUL_CONTACTS": (
        "Number of successful right-party contacts, indicating the "
        "customer's reachability and engagement level."
    ),
    "RPC_RATE": (
        "Right-Party Contact rate — the proportion of contact attempts "
        "that successfully reached the customer."
    ),
    "DAYS_SINCE_LAST_RPC": (
        "Days since the last successful contact, signaling recency of "
        "customer engagement (the 'Ostrich' signal)."
    ),
    "ATTEMPTS_LAST_30D": (
        "Number of contact attempts in the last 30 days, measuring "
        "recent collection intensity and customer responsiveness."
    ),
    "SMS_DELIVERED_COUNT": (
        "Number of SMS messages successfully delivered, indicating "
        "channel effectiveness and customer reachability via SMS."
    ),
    "CALL_ANSWERED_COUNT": (
        "Number of phone calls answered by the customer, indicating "
        "channel preference and willingness to engage by phone."
    ),
}

# ═══════════════════════════════════════════════════════════════════════
#  Ability Model Feature Descriptions
# ═══════════════════════════════════════════════════════════════════════
ability_feature_descriptions = {
    "AVG_MONTHLY_INCOME": (
        "Average monthly income inflow over the last 6 months, "
        "reflecting the customer's earning capacity and income level."
    ),
    "INCOME_VOLATILITY": (
        "Standard deviation of income amounts, measuring income "
        "stability and predictability of the customer's cash inflows."
    ),
    "CURRENT_BALANCE": (
        "Current total balance across all active accounts, indicating "
        "the customer's immediate liquidity position."
    ),
    "TOTAL_OUTFLOW_6M": (
        "Total outgoing spend over the last 6 months, reflecting "
        "the customer's spending level relative to income."
    ),
    "SPENDING_VOLATILITY": (
        "Standard deviation of spending amounts, measuring the "
        "consistency and predictability of expenses."
    ),
    "ENTROPY_CATEGORY_COUNT": (
        "Count of unique spending categories, indicating the diversity "
        "of the customer's financial activity and lifestyle complexity."
    ),
    "NSF_COUNT": (
        "Count of Non-Sufficient Funds events in the last 6 months, "
        "a strong indicator of financial stress and cash flow shortfalls."
    ),
    "FIXED_OBLIGATIONS": (
        "Total monthly fixed obligations (loan instalments), measuring "
        "the customer's committed debt service burden."
    ),
    "UTILIZATION_RATE": (
        "Ratio of current loan balances to original loan amounts, "
        "indicating how much of available credit has been consumed."
    ),
    "DBR_RATIO": (
        "Debt Burden Ratio — monthly obligations divided by monthly "
        "income, a key measure of financial strain."
    ),
    "CASH_RUNWAY_MONTHS": (
        "Estimated months of cash runway based on current balance and "
        "average monthly spending, indicating financial resilience."
    ),
}


def get_feature_description(
    feature_name: str, model_type: str = "willingness"
) -> str:
    """
    Return the detailed description for a feature.

    Args:
        feature_name: Technical feature name (e.g., "PTP_BROKEN_RATIO")
        model_type: 'willingness' or 'ability'

    Returns:
        Detailed contextual description, or a generic fallback.
    """
    mapping = (
        willingness_feature_descriptions
        if model_type == "willingness"
        else ability_feature_descriptions
    )
    return mapping.get(
        feature_name.upper(),
        f"Model factor: {feature_name.replace('_', ' ').title()}.",
    )
