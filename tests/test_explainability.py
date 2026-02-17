"""
Unit tests for the Explainability Module.

These tests verify:
1. Reason code mapping
2. SHAP explainer (mocked when SHAP unavailable)
3. Shadow mode runner behavior
4. Graceful degradation on failures
"""

import pytest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import List

import numpy as np

# Check for optional dependencies
try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False
    pl = None

# Test reason codes
from src.explainability.reason_codes import (
    ReasonCode,
    ReasonCodeMapper,
    ReasonCodeConfig,
)


class TestReasonCode:
    """Tests for ReasonCode dataclass."""
    
    def test_reason_code_creation(self):
        """ReasonCode should be creatable with required fields."""
        code = ReasonCode(
            code="W001",
            feature_name="PTP_KEPT_COUNT",
            display_name="Promises Kept",
            description="Number of payment promises honored",
            category="payment_behavior"
        )
        assert code.code == "W001"
        assert code.feature_name == "PTP_KEPT_COUNT"
        assert code.direction == "positive"  # default
    
    def test_reason_code_immutable(self):
        """ReasonCode should be immutable (frozen)."""
        code = ReasonCode(
            code="W001",
            feature_name="TEST",
            display_name="Test",
            description="Test desc",
            category="test"
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            code.code = "W002"


class TestReasonCodeConfig:
    """Tests for ReasonCodeConfig."""
    
    def test_config_builds_lookup(self):
        """Config should build feature-to-code lookup."""
        codes = [
            ReasonCode(
                code="W001",
                feature_name="FEATURE_A",
                display_name="A",
                description="A",
                category="test"
            ),
            ReasonCode(
                code="W002",
                feature_name="FEATURE_B",
                display_name="B",
                description="B",
                category="test"
            ),
        ]
        config = ReasonCodeConfig(
            version="1.0.0",
            model_type="willingness",
            codes=codes
        )
        
        assert config.feature_to_code["FEATURE_A"] == "W001"
        assert config.feature_to_code["FEATURE_B"] == "W002"
    
    def test_schema_hash_consistency(self):
        """Same features should produce same hash."""
        codes1 = [
            ReasonCode(code="W001", feature_name="A", display_name="A", description="A", category="test"),
            ReasonCode(code="W002", feature_name="B", display_name="B", description="B", category="test"),
        ]
        codes2 = [
            ReasonCode(code="W002", feature_name="B", display_name="B", description="B", category="test"),
            ReasonCode(code="W001", feature_name="A", display_name="A", description="A", category="test"),
        ]
        
        config1 = ReasonCodeConfig(version="1.0.0", model_type="willingness", codes=codes1)
        config2 = ReasonCodeConfig(version="1.0.0", model_type="willingness", codes=codes2)
        
        # Same features, different order - should produce same hash
        assert config1.get_schema_hash() == config2.get_schema_hash()


class TestReasonCodeMapper:
    """Tests for ReasonCodeMapper."""
    
    def test_mapper_initialization_willingness(self):
        """Mapper should initialize with default willingness codes."""
        mapper = ReasonCodeMapper(model_type="willingness")
        
        assert mapper.model_type == "willingness"
        assert len(mapper.get_all_codes()) > 0
        assert mapper.get_config_version() == "1.0.0-default"
    
    def test_mapper_initialization_ability(self):
        """Mapper should initialize with default ability codes."""
        mapper = ReasonCodeMapper(model_type="ability")
        
        assert mapper.model_type == "ability"
        assert len(mapper.get_all_codes()) > 0
    
    def test_mapper_invalid_model_type(self):
        """Mapper should reject invalid model types."""
        with pytest.raises(ValueError, match="must be 'willingness' or 'ability'"):
            ReasonCodeMapper(model_type="invalid")
    
    def test_map_contributions_sorts_by_impact(self):
        """Contributions should be sorted by absolute value."""
        mapper = ReasonCodeMapper(model_type="willingness")
        
        contributions = [
            ("PTP_KEPT_COUNT", 0.1),
            ("DAYS_SINCE_LAST_PAYMENT", -0.3),
            ("TOTAL_PAYMENT_AMT", 0.2),
        ]
        
        result = mapper.map_contributions(contributions, max_codes=3)
        
        # Should be sorted by absolute value descending
        values = [abs(v) for _, v in result]
        assert values == sorted(values, reverse=True)
    
    def test_map_contributions_respects_max_codes(self):
        """Should not return more than max_codes."""
        mapper = ReasonCodeMapper(model_type="willingness")
        
        contributions = [
            ("FEATURE_1", 0.1),
            ("FEATURE_2", 0.2),
            ("FEATURE_3", 0.3),
            ("FEATURE_4", 0.4),
            ("FEATURE_5", 0.5),
        ]
        
        result = mapper.map_contributions(contributions, max_codes=3)
        assert len(result) == 3
    
    def test_map_contributions_filters_by_min_contribution(self):
        """Should filter out small contributions."""
        mapper = ReasonCodeMapper(model_type="willingness")
        
        contributions = [
            ("FEATURE_1", 0.001),  # Too small
            ("FEATURE_2", 0.02),   # OK
            ("FEATURE_3", 0.005),  # Too small
        ]
        
        result = mapper.map_contributions(
            contributions, 
            max_codes=10, 
            min_contribution=0.01
        )
        
        assert len(result) == 1
        assert result[0][0].feature_name == "FEATURE_2"
    
    def test_creates_generic_code_for_unmapped_features(self):
        """Should create generic codes for unmapped features."""
        mapper = ReasonCodeMapper(model_type="willingness")
        
        contributions = [
            ("UNKNOWN_FEATURE_XYZ", 0.5),
        ]
        
        result = mapper.map_contributions(contributions, max_codes=3)
        
        assert len(result) == 1
        code, _ = result[0]
        assert code.feature_name == "UNKNOWN_FEATURE_XYZ"
        assert code.code.startswith("W")  # Willingness prefix
    
    def test_humanize_feature_name(self):
        """Should convert SNAKE_CASE to Title Case."""
        mapper = ReasonCodeMapper(model_type="willingness")
        
        result = mapper._humanize_feature_name("DAYS_SINCE_LAST_PAYMENT")
        assert result == "Days Since Last Payment"


@pytest.mark.skipif(not POLARS_AVAILABLE, reason="Polars not installed")
class TestShadowModeGuarantees:
    """
    Tests to verify shadow mode guarantees.
    
    These tests ensure that explainability never affects predictions.
    """
    
    def test_explanation_failure_returns_result_not_exception(self):
        """Shadow mode should catch exceptions and return failure result."""
        from src.explainability.shap_explainer import ShapExplainer
        
        # Create a mock model that raises on predict
        mock_model = MagicMock()
        mock_model.get_score.side_effect = Exception("Model error")
        
        explainer = ShapExplainer(
            model=mock_model,
            model_version="test_v1",
            model_type="willingness"
        )
        
        # Create test data
        df = pl.DataFrame({
            "CUST_INFO_ID": [1, 2, 3],
            "FEATURE_A": [0.1, 0.2, 0.3],
            "FEATURE_B": [0.4, 0.5, 0.6],
        })
        
        # This should NOT raise - shadow mode catches exceptions
        result = explainer.explain(
            df=df,
            feature_cols=["FEATURE_A", "FEATURE_B"],
            id_col="CUST_INFO_ID"
        )
        
        # Result should indicate failure
        assert result.success is False
        assert result.error_message is not None


@pytest.mark.skipif(not POLARS_AVAILABLE, reason="Polars not installed")
class TestExplanationResultDataFrame:
    """Tests for ExplanationResult.to_dataframe()."""
    
    def test_to_dataframe_creates_correct_schema(self):
        """to_dataframe should create proper schema with reason columns."""
        from src.explainability.shap_explainer import (
            ExplanationResult,
            LocalExplanation,
        )
        
        local_explanations = [
            LocalExplanation(
                record_id=1,
                base_value=0.5,
                prediction=0.7,
                feature_contributions=[
                    ("FEATURE_A", 0.15),
                    ("FEATURE_B", -0.05),
                    ("FEATURE_C", 0.10),
                ]
            ),
        ]
        
        result = ExplanationResult(
            model_version="test_v1",
            model_type="willingness",
            explainability_version="1.0.0",
            feature_schema_hash="abc123",
            global_importance=None,
            local_explanations=local_explanations
        )
        
        df = result.to_dataframe()
        
        assert "RECORD_ID" in df.columns
        assert "BASE_VALUE" in df.columns
        assert "PREDICTION" in df.columns
        assert "REASON_1" in df.columns
        assert "REASON_1_VALUE" in df.columns
        assert "REASON_2" in df.columns
        assert "REASON_3" in df.columns


@pytest.mark.skipif(not POLARS_AVAILABLE, reason="Polars not installed")
class TestGlobalImportance:
    """Tests for GlobalImportance."""
    
    def test_get_top_features(self):
        """Should return top N features by importance."""
        from src.explainability.shap_explainer import GlobalImportance
        
        importance = GlobalImportance(
            model_version="test",
            model_type="willingness",
            feature_importances={
                "FEATURE_A": 0.1,
                "FEATURE_B": 0.3,
                "FEATURE_C": 0.2,
                "FEATURE_D": 0.05,
            },
            importance_type="shap_mean_abs",
            computed_at=datetime.now(),
            sample_size=100,
            computation_time_seconds=1.0
        )
        
        top_2 = importance.get_top_features(n=2)
        
        assert len(top_2) == 2
        assert top_2[0][0] == "FEATURE_B"  # Highest
        assert top_2[1][0] == "FEATURE_C"  # Second highest


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
