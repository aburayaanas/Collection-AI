"""
Feature Name Expansion Mappings for Collection AI SHAP Explanations.

These mappings are intentionally SHORT (2-5 words) for readability.
Used in the SHAP result columns for human consumption.

Temporary hard-coded dictionaries — will be replaced with
metadata-driven mappings later.
"""


# ═══════════════════════════════════════════════════════════════════════
#  Willingness Model Feature Name Expansions
#  Source features: src/database/features/willingness.sql
# ═══════════════════════════════════════════════════════════════════════
willingness_feature_name_expansion = {
    "TOTAL_PTP_COUNT":             "Total Promise-to-Pay count",
    "PTP_BROKEN_COUNT":            "Broken promises count",
    "PTP_KEPT_COUNT":              "Kept promises count",
    "PTP_BROKEN_RATIO":            "Broken promise ratio",
    "DAYS_SINCE_LAST_BROKEN_PTP":  "Days since broken Promise-to-Pay",
    "TOTAL_ATTEMPTS_LIFETIME":     "Lifetime contact attempts",
    "SUCCESSFUL_CONTACTS":         "Successful contacts",
    "RPC_RATE":                    "Right-party contact rate",
    "DAYS_SINCE_LAST_RPC":         "Days since last contact",
    "ATTEMPTS_LAST_30D":           "Recent contact attempts",
    "SMS_DELIVERED_COUNT":         "SMS delivered count",
    "CALL_ANSWERED_COUNT":         "Calls answered count",
}

# ═══════════════════════════════════════════════════════════════════════
#  Ability Model Feature Name Expansions
#  Source features: src/database/features/ability.sql
# ═══════════════════════════════════════════════════════════════════════
ability_feature_name_expansion = {
    "AVG_MONTHLY_INCOME":      "Average monthly income",
    "INCOME_VOLATILITY":       "Income volatility",
    "CURRENT_BALANCE":         "Current balance",
    "TOTAL_OUTFLOW_6M":        "Six-month total outflow",
    "SPENDING_VOLATILITY":     "Spending volatility",
    "ENTROPY_CATEGORY_COUNT":  "Spending category count",
    "NSF_COUNT":               "NSF events count",
    "FIXED_OBLIGATIONS":       "Fixed obligations",
    "UTILIZATION_RATE":        "Loan utilization rate",
    "DBR_RATIO":               "Debt burden ratio",
    "CASH_RUNWAY_MONTHS":      "Cash runway months",
}


def expand_feature_name(feature_name: str, model_type: str = "willingness") -> str:
    """
    Expand a technical feature name to a business-friendly name.

    Args:
        feature_name: Technical feature name (e.g., "PTP_BROKEN_RATIO")
        model_type: 'willingness' or 'ability'

    Returns:
        Expanded name, or the original name title-cased if not mapped.
    """
    mapping = (
        willingness_feature_name_expansion
        if model_type == "willingness"
        else ability_feature_name_expansion
    )
    return mapping.get(feature_name.upper(), feature_name.replace("_", " ").title())


def format_shap_explanation(reason_cols: str, model_type: str = "willingness") -> str:
    """
    Convert a technical SHAP feature string to business-friendly text.

    Follows the PIO_AML_CUSTOMERS.AML_NEXT_DECISION format exactly.

    Input format:
        "PTP_BROKEN_RATIO: 42.9%; RPC_RATE: 28.7%; ATTEMPTS_LAST_30D: 17.0%"

    Output format:
        "The system scored this customer primarily based on the following factors:
         Broken promise ratio (42.9%),
         Right-party contact rate (28.7%),
         Recent contact attempts (17.0%)."

    Args:
        reason_cols: Technical SHAP string with "FEATURE: XX.X%; ..." format
        model_type: 'willingness' or 'ability'

    Returns:
        Business-friendly explanation string.
    """
    if not reason_cols or not reason_cols.strip():
        return ""

    parts = []
    for segment in reason_cols.split(";"):
        segment = segment.strip()
        if not segment or ":" not in segment:
            continue
        feature, percentage = segment.split(":", 1)
        feature = feature.strip()
        percentage = percentage.strip().rstrip("%").strip()
        expanded_name = expand_feature_name(feature, model_type=model_type)
        parts.append(f"{expanded_name} ({percentage}%)")

    if not parts:
        return ""

    intro = (
        "The system scored this customer primarily based on "
        "the following factors:"
    )
    factors = ",\n".join(parts) + "."
    return f"{intro}\n{factors}"
