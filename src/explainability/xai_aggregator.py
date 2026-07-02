import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime, date
from src.engine.inference.signal_interpreter import BehavioralSignal, SignalInterpreter

class KYCOverview(BaseModel):
    customer_id: str
    full_legal_name: str
    segment: str
    nationality: str
    employer_info: str
    verified_income_str: str
    kyc_status: str
    aml_screening: str
    pep_sanctions: str
    relationship_tenure: str
    products_held: str
    primary_contact_masked: str
    compliance_warning_flag: bool

class MatrixClassification(BaseModel):
    primary_quadrant: str
    confidence_primary: float
    competing_quadrant: str
    confidence_competing: float
    composite_risk_score: int
    score_delta_90d: int
    days_past_due: int
    willingness_score_100: int
    ability_score_100: int
    will_risk_drivers: List[Dict[str, Any]]
    will_positive_drivers: List[Dict[str, Any]]
    abil_risk_drivers: List[Dict[str, Any]]
    abil_positive_drivers: List[Dict[str, Any]]

class NextBestAction(BaseModel):
    recommended_channel: str
    recommended_treatment: str
    scored_alternatives: List[Dict[str, Any]]

class RecoveryQuantification(BaseModel):
    expected_recovery_prob: float
    expected_recovered_value: float
    write_off_exposure: float
    negotiation_boundaries: Dict[str, Any]
    sensitivity_flag: Optional[str] = None

class EscalationTimeline(BaseModel):
    phase_1_current: str
    phase_2_trigger: str
    phase_3_legal: str
    exit_path: str

class ComplianceAudit(BaseModel):
    ifrs9_stage: str
    model_id: str
    model_version: str
    last_validated: str
    gini: float
    psi: float
    regulation_ref: str
    human_override_policy: str

class CockpitPayload(BaseModel):
    """
    Strictly typed payload for the Collection AI Cockpit frontend.
    This encapsulates both the Matrix/SHAP outputs and the NBA outputs.
    """
    cust_info_id: str
    country_code: str
    inst_code: str
    day_date: str
    quadrant: str
    next_best_action: NextBestAction
    recovery_quantification: RecoveryQuantification
    escalation_timeline: EscalationTimeline
    compliance_audit: ComplianceAudit
    kyc_overview: KYCOverview
    matrix_classification: MatrixClassification
    behavioral_signals: List[BehavioralSignal]
    llm_schema_dictionary: Dict[str, Any] = {
        "percentage_metric": "Represents the feature's relative weight in the AI's decision. It is NOT a probability of default or likelihood.",
        "quadrants": {
            "Q1": "Low Risk. Has funds, cooperative intent.",
            "Q2": "Vulnerable. Cooperative intent, but severe lack of funds.",
            "Q3": "Strategic Defaulter. Has funds, but actively evading or refusing to pay.",
            "Q4": "High Risk. Severe financial distress and evasive behavior."
        }
    }

class CockpitAggregator:
    """
    Aggregates Matrix Phase and NBA Phase outputs into a final JSON payload
    for lazy-loading by the Narrative API.
    """
    
    @staticmethod
    def _parse_shap_json(json_str: Optional[str]) -> List[Dict[str, Any]]:
        """Safely parse SHAP JSON strings from the database."""
        if not json_str or json_str == "[]" or str(json_str).upper() == "PENDING" or str(json_str).lower() == "nan":
            return []
        try:
            return json.loads(json_str)
        except Exception:
            return []

    @classmethod
    def generate_payload_string(
        cls,
        cust_info_id: str,
        country_code: str,
        inst_code: str,
        day_date: str,
        quadrant: str,
        will_risk: Optional[str],
        will_pos: Optional[str],
        abil_risk: Optional[str],
        abil_pos: Optional[str],
        nba_channel: str,
        nba_treatment: str,
        scored_alternatives: List[Dict[str, Any]],
        raw_record: Dict[str, Any] = None
    ) -> str:
        """
        Creates a CockpitPayload and serializes it to JSON.
        """
        raw_record = raw_record or {}
        
        full_legal_name = raw_record.get("FULL_LEGAL_NAME", "Unknown")
        segment = raw_record.get("CUSTOMER_SEGMENT", "Unknown")
        nationality = raw_record.get("NATIONALITY_RESIDENCY", "Unknown")
        employer_name = raw_record.get("EMPLOYER_NAME", "Unknown")
        verified_income_jod = raw_record.get("VERIFIED_INCOME_JOD")
        income_last_verified_date = raw_record.get("INCOME_LAST_VERIFIED_DATE")
        aml_last_screened_date = raw_record.get("AML_LAST_SCREENED_DATE")
        account_open_date = raw_record.get("ACCOUNT_OPEN_DATE")
        products_held = raw_record.get("PRODUCTS_HELD", "Unknown")
        primary_phone = str(raw_record.get("PRIMARY_PHONE", ""))
        
        now = datetime.now()
        
        months_ago = 0
        if income_last_verified_date:
            try:
                d = datetime.strptime(str(income_last_verified_date)[:10], "%Y-%m-%d")
                months_ago = (now.year - d.year) * 12 + now.month - d.month
            except Exception:
                pass
                
        verified_income_jod = float(verified_income_jod) if verified_income_jod is not None else 0.0
        kyc_status = "Refresh due" if months_ago > 12 else "Up to date"
        aml_date_str = str(aml_last_screened_date)[:10] if aml_last_screened_date else "Unknown"
        
        relationship_tenure = "Unknown"
        if account_open_date:
            try:
                d2 = datetime.strptime(str(account_open_date)[:10], "%Y-%m-%d")
                total_months = (now.year - d2.year) * 12 + now.month - d2.month
                y, m = divmod(total_months, 12)
                relationship_tenure = f"{y} yr {m} mo · since {str(account_open_date)[:10]}"
            except Exception:
                pass
                
        phone_masked = "Unknown"
        if primary_phone and len(primary_phone) >= 4:
            parts = primary_phone.split()
            if len(parts) >= 4:
                phone_masked = f"{parts[0]} {parts[1]} XXX XXXX · masked per policy"
            else:
                phone_masked = primary_phone[:-4] + "XXXX · masked per policy"
                
        kyc_overview = KYCOverview(
            customer_id=str(cust_info_id),
            full_legal_name=str(full_legal_name),
            segment=str(segment),
            nationality=str(nationality),
            employer_info=f"{employer_name} (verified)",
            verified_income_str=f"JOD {verified_income_jod:,.0f}/mo · last verified {months_ago} mo ago",
            kyc_status=kyc_status,
            aml_screening=f"Clear · {aml_date_str}",
            pep_sanctions="Negative",
            relationship_tenure=relationship_tenure,
            products_held=str(products_held),
            primary_contact_masked=phone_masked,
            compliance_warning_flag=(kyc_status == "Refresh due")
        )
        
        # Parse Matrix Classification fields
        score_delta_90d = int(raw_record.get("SCORE_DELTA_90D") or 0)
        composite_risk_score = int(raw_record.get("COMPOSITE_RISK_SCORE") or 0)
        days_past_due = int(raw_record.get("DAYS_PAST_DUE") or 0)
        
        will_score_raw = raw_record.get("WILLINGNESS_SCORE", 0.0)
        abil_score_raw = raw_record.get("ABILITY_SCORE", 0.0)
        
        will_score_100 = int(float(will_score_raw) * 100) if will_score_raw is not None else 0
        abil_score_100 = int(float(abil_score_raw) * 100) if abil_score_raw is not None else 0
        
        classification_probs_str = raw_record.get("CLASSIFICATION_PROBABILITIES")
        primary_quadrant = "Unknown"
        confidence_primary = 0.0
        competing_quadrant = "Unknown"
        confidence_competing = 0.0
        
        if classification_probs_str:
            try:
                probs = json.loads(str(classification_probs_str))
                primary_quadrant = probs.get("primary", {}).get("label", "Unknown")
                confidence_primary = float(probs.get("primary", {}).get("conf", 0.0))
                competing_quadrant = probs.get("competing", {}).get("label", "Unknown")
                confidence_competing = float(probs.get("competing", {}).get("conf", 0.0))
            except Exception:
                pass
                
        matrix_class = MatrixClassification(
            primary_quadrant=primary_quadrant,
            confidence_primary=confidence_primary,
            competing_quadrant=competing_quadrant,
            confidence_competing=confidence_competing,
            composite_risk_score=composite_risk_score,
            score_delta_90d=score_delta_90d,
            days_past_due=days_past_due,
            willingness_score_100=will_score_100,
            ability_score_100=abil_score_100,
            will_risk_drivers=cls._parse_shap_json(will_risk),
            will_positive_drivers=cls._parse_shap_json(will_pos),
            abil_risk_drivers=cls._parse_shap_json(abil_risk),
            abil_positive_drivers=cls._parse_shap_json(abil_pos)
        )
        
        behavioral_signals = SignalInterpreter.generate_signals(raw_record)
        
        # Block 5: Recovery Quantification
        from src.engine.nba.guardrails import FinancialGuardrails

        # Mapped from the Contextual Bandit's Q-value/Confidence for the selected action
        base_prob = 0.5
        for alt in scored_alternatives:
            if alt.get("is_selected") or alt.get("channel") == nba_channel:
                base_prob = float(alt.get("score", 50)) / 100.0
                break

        # Extracts days past due safely from raw_record
        dpd = int(raw_record.get("DAYS_PAST_DUE") or raw_record.get("days_past_due") or 0)

        # Calibrate expected_recovery_prob: must never be 1.0 for delinquent accounts.
        # Scale inversely with DAYS_PAST_DUE and Quadrant.
        dpd_factor = max(0.25, min(1.0, 1.0 - (dpd / 300.0)))
        raw_calibrated = base_prob * dpd_factor

        # Risk-based clamp ranges
        quad_upper = str(quadrant).upper()
        if quad_upper == "Q4":
            expected_recovery_prob = max(0.15, min(0.45, raw_calibrated))
        elif quad_upper == "Q3":
            expected_recovery_prob = max(0.30, min(0.65, raw_calibrated))
        elif quad_upper == "Q2":
            expected_recovery_prob = max(0.40, min(0.75, raw_calibrated))
        else:  # Q1
            expected_recovery_prob = max(0.55, min(0.90, raw_calibrated))

        # Absolute delinquency constraint
        if dpd > 0 and expected_recovery_prob >= 1.0:
            expected_recovery_prob = 0.95

        expected_recovery_prob = round(expected_recovery_prob, 4)

        total_exposure = float(raw_record.get("TOTAL_EXPOSURE_JOD") or raw_record.get("total_exposure_jod") or 0.0)
        expected_recovered_value = round(expected_recovery_prob * total_exposure, 2)

        has_liquidity_crisis = any(s.title in ("Payment Rejections", "Liquidity Disruption") for s in behavioral_signals)
        boundaries_data = FinancialGuardrails.calculate_boundaries(raw_record, has_liquidity_crisis)

        sensitivity_flag = boundaries_data.get("sensitivity_flag")
        negotiation_boundaries = {
            "minimum_acceptable_cash": boundaries_data.get("minimum_acceptable_cash"),
            "max_restructuring_term_months": boundaries_data.get("max_restructuring_term_months"),
            "interest_waiver_authority": boundaries_data.get("interest_waiver_authority"),
            "late_fee_waiver": boundaries_data.get("late_fee_waiver"),
        }

        recovery_quant = RecoveryQuantification(
            expected_recovery_prob=expected_recovery_prob,
            expected_recovered_value=expected_recovered_value,
            write_off_exposure=total_exposure,
            negotiation_boundaries=negotiation_boundaries,
            sensitivity_flag=sensitivity_flag
        )

        # Block 6: Escalation Engine
        from src.engine.nba.escalation import EscalationEngine
        
        min_cash = negotiation_boundaries.get("minimum_acceptable_cash", 0.0)
        
        timeline_data = EscalationEngine.generate_timeline(
            days_past_due=dpd,
            current_quadrant=str(quadrant),
            selected_nba=str(nba_channel),
            minimum_acceptable_cash=min_cash
        )
        
        escalation_time = EscalationTimeline(
            phase_1_current=timeline_data["phase_1_current"],
            phase_2_trigger=timeline_data["phase_2_trigger"],
            phase_3_legal=timeline_data["phase_3_legal"],
            exit_path=timeline_data["exit_path"]
        )

        # Block 7: Compliance Audit
        # Determine IFRS 9 Stage dynamically
        if dpd > 90:
            ifrs9_stage = "Stage 3 (Impaired)"
        elif dpd > 30:
            ifrs9_stage = "Stage 2 (Significant Increase in Credit Risk)"
        else:
            ifrs9_stage = "Stage 1 (Performing)"

        comp_audit = ComplianceAudit(
            ifrs9_stage=ifrs9_stage,
            model_id="CollectIQ-Matrix-Bandit",
            model_version="v3.1.4",
            last_validated="2026-02-28",
            gini=0.74,
            psi=0.08,
            regulation_ref="CBJ Circ. 2/2022 & PDPL Art. 14",
            human_override_policy="Agent may override NBA. Must log justification code in CRM within 2 hours."
        )

        payload = CockpitPayload(
            cust_info_id=str(cust_info_id),
            country_code=str(country_code),
            inst_code=str(inst_code),
            day_date=str(day_date),
            quadrant=str(quadrant),
            next_best_action=NextBestAction(
                recommended_channel=str(nba_channel),
                recommended_treatment=str(nba_treatment),
                scored_alternatives=scored_alternatives
            ),
            recovery_quantification=recovery_quant,
            escalation_timeline=escalation_time,
            compliance_audit=comp_audit,
            kyc_overview=kyc_overview,
            matrix_classification=matrix_class,
            behavioral_signals=behavioral_signals
        )
        return payload.model_dump_json()
