"""
Explainability Module — Collection AI.

Implements the 4-layer SHAP architecture (following AML Smart_AML2025):

Layer 1  shap_explainer.py
         ShapAlertFilter  – de-duplicates against previous DWH patterns.
         CollectionShapExplainer – per-customer SHAP with multiprocessing.

Layer 2  feature_name_expansion.py
         Short feature-name mappings + format_shap_explanation().

Layer 3  description.py
         Detailed contextual feature descriptions.

Layer 4  shadow_runner.py
         run_shap_phase() orchestrates everything after scoring.
         ShadowExplainer class wrapper for backward compatibility.

Output format follows PIO_AML_CUSTOMERS.AML_NEXT_DECISION:
    "The system scored this customer primarily based on the following factors:
     Broken promise ratio (42.9%),
     Right-party contact rate (28.7%),
     Recent contact attempts (17.0%)."
"""

# Layer 1 — SHAP engine
from src.explainability.shap_explainer import (
    CollectionShapExplainer,
    ShapAlertFilter,
    get_shap_explainer,
    SHAP_AVAILABLE,
    GPU_AVAILABLE,
)

# Layer 2 — Feature name expansion
from src.explainability.feature_name_expansion import (
    willingness_feature_name_expansion,
    ability_feature_name_expansion,
    expand_feature_name,
    format_shap_explanation,
)

# Layer 3 — Feature descriptions
from src.explainability.description import (
    willingness_feature_descriptions,
    ability_feature_descriptions,
    get_feature_description,
)

# Layer 4 — Pipeline orchestration
from src.explainability.shadow_runner import (
    run_shap_phase,
    ShadowExplainer,
    ExplainabilityConfig,
    ShadowExplainabilityResult,
)

# Legacy (kept for backward compat)
from src.explainability.reason_codes import (
    ReasonCode,
    ReasonCodeMapper,
    ReasonCodeConfig,
)

__all__ = [
    # Layer 1
    "CollectionShapExplainer",
    "ShapAlertFilter",
    "get_shap_explainer",
    "SHAP_AVAILABLE",
    "GPU_AVAILABLE",
    # Layer 2
    "willingness_feature_name_expansion",
    "ability_feature_name_expansion",
    "expand_feature_name",
    "format_shap_explanation",
    # Layer 3
    "willingness_feature_descriptions",
    "ability_feature_descriptions",
    "get_feature_description",
    # Layer 4
    "run_shap_phase",
    "ShadowExplainer",
    "ExplainabilityConfig",
    "ShadowExplainabilityResult",
    # Legacy
    "ReasonCode",
    "ReasonCodeMapper",
    "ReasonCodeConfig",
]
