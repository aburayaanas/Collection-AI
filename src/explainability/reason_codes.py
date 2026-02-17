"""
Reason Code Schema and Mapper.

This module provides the mapping between model features and human-readable
reason codes suitable for customer-facing explanations and regulatory reporting.

Design Principles:
1. Human-Readable - All codes have clear, non-technical descriptions
2. Configurable - Mappings loaded from YAML configuration
3. Auditable - Codes are versioned and traceable to features
4. Regulator-Friendly - Descriptions suitable for model risk documentation
"""

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

# Use standard logging to avoid config dependency
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReasonCode:
    """
    A single reason code representing a feature's contribution to a prediction.
    
    Attributes:
        code: Unique identifier (e.g., 'W001', 'A003')
        feature_name: Original model feature name
        display_name: Human-readable feature name
        description: Full description for customer/regulator communication
        category: Grouping category (e.g., 'payment_behavior', 'financial_health')
        direction: Whether higher values increase ('positive') or decrease ('negative') the score
    """
    code: str
    feature_name: str
    display_name: str
    description: str
    category: str
    direction: str = "positive"  # 'positive' or 'negative'


@dataclass
class ReasonCodeConfig:
    """
    Configuration for reason code mapping.
    
    Attributes:
        version: Configuration version for audit trail
        model_type: 'willingness' or 'ability'
        codes: List of defined reason codes
        feature_to_code: Mapping from feature names to codes
    """
    version: str
    model_type: str
    codes: List[ReasonCode]
    feature_to_code: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Build feature-to-code lookup after initialization."""
        self.feature_to_code = {rc.feature_name: rc.code for rc in self.codes}
    
    def get_schema_hash(self) -> str:
        """
        Generate a hash of the feature schema for drift detection.
        
        Returns:
            SHA256 hash of sorted feature names
        """
        feature_str = ",".join(sorted(self.feature_to_code.keys()))
        return hashlib.sha256(feature_str.encode()).hexdigest()[:16]


class ReasonCodeMapper:
    """
    Maps model features to human-readable reason codes.
    
    This class loads reason code definitions from YAML configuration
    and provides methods to translate SHAP feature contributions into
    customer-facing explanations.
    
    Usage:
        mapper = ReasonCodeMapper(model_type="willingness")
        reason_codes = mapper.map_contributions(
            feature_contributions=[("PTP_KEPT_COUNT", 0.15), ("DAYS_SINCE_LAST_PAYMENT", -0.08)],
            max_codes=3
        )
    """
    
    # Default reason codes when no config file is available
    DEFAULT_WILLINGNESS_CODES: List[Dict] = [
        {
            "code": "W001",
            "feature_name": "PTP_KEPT_COUNT",
            "display_name": "Promises Kept",
            "description": "Number of payment promises honored by the customer",
            "category": "payment_behavior",
            "direction": "positive"
        },
        {
            "code": "W002",
            "feature_name": "PTP_BROKEN_COUNT",
            "display_name": "Promises Broken",
            "description": "Number of payment promises not honored",
            "category": "payment_behavior",
            "direction": "negative"
        },
        {
            "code": "W003",
            "feature_name": "DAYS_SINCE_LAST_PAYMENT",
            "display_name": "Days Since Payment",
            "description": "Number of days since the last recorded payment",
            "category": "payment_recency",
            "direction": "negative"
        },
        {
            "code": "W004",
            "feature_name": "TOTAL_PAYMENT_AMT",
            "display_name": "Total Payments",
            "description": "Total amount of payments made",
            "category": "payment_volume",
            "direction": "positive"
        },
        {
            "code": "W005",
            "feature_name": "CONTACT_SUCCESS_RATE",
            "display_name": "Contact Success",
            "description": "Rate of successful customer contacts",
            "category": "engagement",
            "direction": "positive"
        },
        {
            "code": "W006",
            "feature_name": "DELINQUENCY_DAYS",
            "display_name": "Days Delinquent",
            "description": "Number of days the account has been delinquent",
            "category": "delinquency",
            "direction": "negative"
        },
    ]
    
    DEFAULT_ABILITY_CODES: List[Dict] = [
        {
            "code": "A001",
            "feature_name": "CASH_RUNWAY_MONTHS",
            "display_name": "Cash Runway",
            "description": "Estimated months of cash runway based on balance and expenses",
            "category": "liquidity",
            "direction": "positive"
        },
        {
            "code": "A002",
            "feature_name": "NSF_COUNT",
            "display_name": "Insufficient Funds Events",
            "description": "Count of non-sufficient funds events",
            "category": "financial_stress",
            "direction": "negative"
        },
        {
            "code": "A003",
            "feature_name": "UTILIZATION_RATE",
            "display_name": "Credit Utilization",
            "description": "Ratio of credit used to credit available",
            "category": "credit_health",
            "direction": "negative"
        },
        {
            "code": "A004",
            "feature_name": "INCOME_STABILITY_SCORE",
            "display_name": "Income Stability",
            "description": "Measure of income consistency over time",
            "category": "income",
            "direction": "positive"
        },
        {
            "code": "A005",
            "feature_name": "DEBT_TO_INCOME",
            "display_name": "Debt-to-Income Ratio",
            "description": "Ratio of total debt payments to income",
            "category": "debt_burden",
            "direction": "negative"
        },
        {
            "code": "A006",
            "feature_name": "AVG_MONTHLY_BALANCE",
            "display_name": "Average Balance",
            "description": "Average monthly account balance",
            "category": "liquidity",
            "direction": "positive"
        },
    ]
    
    def __init__(
        self,
        model_type: str,
        config_path: Optional[str] = None
    ):
        """
        Initialize the reason code mapper.
        
        Args:
            model_type: 'willingness' or 'ability'
            config_path: Optional path to YAML config file.
                        If None, uses default embedded codes.
        
        Raises:
            ValueError: If model_type is invalid
        """
        if model_type not in ("willingness", "ability"):
            raise ValueError(f"model_type must be 'willingness' or 'ability', got: {model_type}")
        
        self.model_type = model_type
        self.config = self._load_config(config_path)
        
        logger.info(
            f"ReasonCodeMapper initialized for {model_type}: "
            f"version={self.config.version}, "
            f"codes={len(self.config.codes)}, "
            f"schema_hash={self.config.get_schema_hash()}"
        )
    
    def _load_config(self, config_path: Optional[str]) -> ReasonCodeConfig:
        """
        Load reason code configuration from file or defaults.
        
        Args:
            config_path: Path to YAML config, or None for defaults
            
        Returns:
            ReasonCodeConfig instance
        """
        if config_path:
            path = Path(config_path)
            if path.exists():
                return self._load_from_yaml(path)
            else:
                logger.warning(f"Config file not found: {config_path}. Using defaults.")
        
        return self._load_defaults()
    
    def _load_from_yaml(self, path: Path) -> ReasonCodeConfig:
        """Load configuration from YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        codes = [
            ReasonCode(**code_data)
            for code_data in data.get("codes", [])
        ]
        
        return ReasonCodeConfig(
            version=data.get("version", "1.0.0"),
            model_type=self.model_type,
            codes=codes
        )
    
    def _load_defaults(self) -> ReasonCodeConfig:
        """Load default embedded reason codes."""
        default_codes = (
            self.DEFAULT_WILLINGNESS_CODES
            if self.model_type == "willingness"
            else self.DEFAULT_ABILITY_CODES
        )
        
        codes = [ReasonCode(**code_data) for code_data in default_codes]
        
        return ReasonCodeConfig(
            version="1.0.0-default",
            model_type=self.model_type,
            codes=codes
        )
    
    def map_contributions(
        self,
        feature_contributions: List[Tuple[str, float]],
        max_codes: int = 3,
        min_contribution: float = 0.01
    ) -> List[Tuple[ReasonCode, float]]:
        """
        Map feature contributions to reason codes.
        
        Args:
            feature_contributions: List of (feature_name, shap_value) tuples
            max_codes: Maximum number of reason codes to return
            min_contribution: Minimum absolute contribution to include
            
        Returns:
            List of (ReasonCode, contribution) tuples, sorted by impact
        """
        # Filter by minimum contribution
        significant = [
            (feat, val) for feat, val in feature_contributions
            if abs(val) >= min_contribution
        ]
        
        # Sort by absolute contribution (most impactful first)
        sorted_contributions = sorted(
            significant,
            key=lambda x: abs(x[1]),
            reverse=True
        )
        
        # Map to reason codes
        result = []
        for feature_name, contribution in sorted_contributions[:max_codes]:
            code = self._get_code_for_feature(feature_name)
            if code:
                result.append((code, contribution))
            else:
                # Create a generic code for unmapped features
                generic_code = self._create_generic_code(feature_name)
                result.append((generic_code, contribution))
                logger.debug(f"Created generic code for unmapped feature: {feature_name}")
        
        return result
    
    def _get_code_for_feature(self, feature_name: str) -> Optional[ReasonCode]:
        """Get the reason code for a feature, if mapped."""
        code_id = self.config.feature_to_code.get(feature_name)
        if code_id:
            return next(
                (rc for rc in self.config.codes if rc.code == code_id),
                None
            )
        return None
    
    def _create_generic_code(self, feature_name: str) -> ReasonCode:
        """Create a generic reason code for unmapped features."""
        # Generate a unique code based on feature name
        prefix = "W" if self.model_type == "willingness" else "A"
        code_num = abs(hash(feature_name)) % 900 + 100  # 100-999
        
        return ReasonCode(
            code=f"{prefix}{code_num}",
            feature_name=feature_name,
            display_name=self._humanize_feature_name(feature_name),
            description=f"Model factor: {self._humanize_feature_name(feature_name)}",
            category="other",
            direction="positive"
        )
    
    def _humanize_feature_name(self, feature_name: str) -> str:
        """Convert a feature name to a human-readable format."""
        # Convert SNAKE_CASE to Title Case
        words = feature_name.lower().replace("_", " ").split()
        return " ".join(word.capitalize() for word in words)
    
    def get_all_codes(self) -> List[ReasonCode]:
        """Return all configured reason codes."""
        return list(self.config.codes)
    
    def get_config_version(self) -> str:
        """Return the configuration version."""
        return self.config.version
    
    def get_schema_hash(self) -> str:
        """Return the feature schema hash for drift detection."""
        return self.config.get_schema_hash()
