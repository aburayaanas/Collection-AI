"""
Clean and align the 3 demo showcase customers (Q1, Q2, Q4) in the Oracle DB.

Ensures:
- 48618400 (Q1 Low Risk): 0.04 avoidance, 0 rejections -> no evasive/liquidity signals, high will/ability, Email PTP.
- 10617433 (Q2 Vulnerable): 0.12 avoidance, 2 rejections, 2450.0 inflow variance -> payment rejection & liquidity signals, NO evasion, Email Restructuring.
- 10017292 (Q4 High Risk): 0.88 avoidance, 4 rejections, 3 broken PTPs -> contact failure & evasive pattern + payment rejection & liquidity, Field Visit escalation.
- Clean ASCII strings without encoding artifacts.
- Calibrated factual channel response rates (ACTUAL for calls/field visits, ESTIMATED for SMS/email/letters).
- Pre-caches audited 5-section executive narratives in AI_NARRATIVE for instant, bulletproof demo presentation.
"""

import sys
from pathlib import Path
import json

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import db
from src.core.config import settings
from src.explainability.xai_aggregator import CockpitAggregator
from src.engine.nba.bandit import ContextualBandit, Channel
from src.engine.nba.schemas import CustomerState
from src.engine.inference.signal_interpreter import SignalInterpreter


SHOWCASE_CONFIGS = {
    "48618400": {
        "quadrant": "Q1",
        "segment": "Mass retail / Salaried",
        "nationality": "Jordanian / Resident",
        "products": "Credit card, Savings",
        "contact_avoidance": 0.04,
        "payment_rejection_freq": 0,
        "broken_ptp": 0,
        "days_since_rpc": 3,
        "ptp_reliability": 0.95,
        "inflow_variance": 120.0,
        "call_response_rate": 0.78,
        "field_visit_response_rate": 0.85,
        "sms_estimated_response_rate": 0.15,
        "email_estimated_response_rate": 0.12,
        "letter_estimated_response_rate": 0.20,
        "narrative": """### SECTION 1 — IDENTITY & COMPLIANCE GATE
- **KYC Anchor:** Rami Hassan Awad (CIF-48618400), Jordanian / Resident Mass retail / Salaried customer employed at Orange (verified), 9 yr 7 mo tenure.
- **KYC Status & Gate:** KYC is Up to date. Verified income is JOD 1,897/mo (last verified 11 months ago). Compliance gate is clear; all standard settlement arrangements and forbearance options are legally authorized.
- **AML / PEP / Sanctions:** Screened clear on 2026-03-14. PEP and Sanctions checks negative.
- **Products Held:** Credit card, Savings.

### SECTION 2 — MATRIX STATE & UNCERTAINTY ENVELOPE
- **Primary Classification & Scores:** Classified into Q1 (Low Risk). Composite risk score is 17/100, willingness score is 91/100, ability score is 93/100, with 12 days past due (DPD).
- **Confidence & Uncertainty:** High model confidence in Q1 at 69.0% (competing quadrant Q2 at 16.0%, uncertainty gap +53.0%).
- **Score Velocity:** 90-day risk delta is -33 pts (significant risk improvement / stabilization trajectory).
- **Willingness & Ability SHAP Drivers:** 
  - *Protective Anchors:* Strong historical commitment anchored by Recent Broken Promises (53.9% decision weight) and Long-term Promise Reliability (28.5% decision weight), reflecting consistent follow-through on past commitments. Ability is solidly anchored by a zero Payment Rejection Rate (55.6% decision weight) and manageable Debt Service Burden (27.5% decision weight).
  - *Risk Drivers:* Minor residual risk from Income Volatility (+5.8% decision weight), which remains within normal operating limits.
- **Agent Posture:** Low-friction, relationship-preserving soft touch. Emphasize self-service digital settlement.

### SECTION 3 — BEHAVIORAL INTELLIGENCE & CHANNEL STRATEGY
- **Signal Breakdown:** Zero adverse behavioral signals. No contact avoidance or payment rejections detected.
- **Recommended Channel Rationale:** Digital Email outreach (Confidence 100/100) selected for Promise-to-Pay (PTP) scheduling. Top alternative is SMS (90/100), Outgoing Call (80/100), and Dunning Letter (70/100). Email provides immediate payment links with lowest operational friction.
- **Agent Approach:** Respectful, professional reminder tone. Provide straightforward digital payment link and confirm normal account status upon receipt.

### SECTION 4 — RECOVERY QUANTIFICATION & ESCALATION CLOCK
- **Business Case:** Expected recovery probability is 90.0%, representing JOD 29,634.48 expected recovery against JOD 32,927.20 write-off exposure.
- **Negotiation Boundaries:** Minimum acceptable cash settlement floor is JOD 2,911.65. Maximum restructuring term is 18 months. Interest waiver authority is JOD 113.28; late fee waiver is 100% pre-approved.
- **Escalation Timeline:**
  - `PHASE 1 — ACTIVE`: Active Email outreach. Response window: 0-7 days (ending 2026-09-03).
  - `PHASE 2 — TRIGGER`: Triggered if payment of JOD 2,911.65 is not received by 2026-09-03. Action: Formal demand letter + legal pre-notification SMS (days 8-21).
  - `PHASE 3 — LEGAL`: Triggered if Phase 2 produces no cure by day 21. Action: Legal referral and bureau reporting. Reclassify to Stage 3 per IFRS 9.
  - `EXIT — DE-ESCALATION`: Receipt of minimum cash floor clears active delinquency; reclassify to Q0 (normal monitoring).

### SECTION 5 — MODEL AUDIT TRAIL
Decision governed by CollectIQ-Matrix-Bandit v3.1.4 (validated 2026-02-28, Gini 0.74, PSI 0.08); IFRS 9 Stage 1 (Performing); regulatory framework: CBJ Circ. 2/2022 & PDPL Art. 14; human override policy: Agent may override NBA. Must log justification code in CRM within 2 hours."""
    },
    "10617433": {
        "quadrant": "Q2",
        "segment": "Mass retail / Self-employed",
        "nationality": "Jordanian / Resident",
        "products": "Personal loan, Credit card, Savings",
        "contact_avoidance": 0.12,
        "payment_rejection_freq": 2,
        "broken_ptp": 0,
        "days_since_rpc": 5,
        "ptp_reliability": 0.85,
        "inflow_variance": 2450.0,
        "call_response_rate": 0.65,
        "field_visit_response_rate": 0.70,
        "sms_estimated_response_rate": 0.12,
        "email_estimated_response_rate": 0.09,
        "letter_estimated_response_rate": 0.15,
        "narrative": """### SECTION 1 — IDENTITY & COMPLIANCE GATE
- **KYC Anchor:** Ahmed Ahmed Mansour (CIF-10617433), Jordanian / Resident Mass retail / Self-employed customer operating under Self / Trade License (verified), 7 yr 0 mo tenure.
- **KYC Status & Gate:** KYC is Up to date. Verified income is JOD 2,316/mo (last verified 4 months ago). Compliance gate is clear; agent is fully authorized to propose formal restructuring and temporary payment moratoriums.
- **AML / PEP / Sanctions:** Screened clear on 2026-04-28. PEP and Sanctions checks negative.
- **Products Held:** Personal loan, Credit card, Savings.

### SECTION 2 — MATRIX STATE & UNCERTAINTY ENVELOPE
- **Primary Classification & Scores:** Classified into Q2 (Vulnerable). Composite risk score is 43/100, willingness score is 97/100, ability score is 6/100, with 50 days past due (DPD).
- **Confidence & Uncertainty:** Model confidence in Q2 is 76.0% (competing quadrant Q4 at 18.0%, uncertainty gap +58.0%).
- **Score Velocity:** 90-day risk delta is -26 pts (improving trend in engagement, despite financial distress).
- **Willingness & Ability SHAP Drivers:**
  - *Willingness Anchors:* High willingness driven by zero Recent Broken Promises (56.8% decision weight) and strong Long-term Promise Reliability (33.1% decision weight), confirming clear intent to fulfill obligations.
  - *Ability Risk Drivers:* Severe capacity impairment driven by elevated Debt Service Burden (46.2% decision weight) and recent Payment Rejection Rate (44.1% decision weight), confirming acute cashflow compression.
- **Agent Posture:** Empathetic, advisory, and solution-driven. Prioritize debt restructuring over aggressive collection demands.

### SECTION 3 — BEHAVIORAL INTELLIGENCE & CHANNEL STRATEGY
- **Signal Breakdown:** 
  - *[OBSERVED]* Payment Rejections: 2 direct debit rejections recorded recently.
  - *[HYPOTHESIS]* Liquidity Disruption: Significant monthly inflow variance detected (inflow variance exceeds threshold), indicating trade receipt delay or business cashflow disruption.
  - *Contact Disposition:* Non-evasive (Contact avoidance index 0.12). Customer remains reachable and receptive.
- **Recommended Channel Rationale:** Digital Email outreach (Confidence 100/100) selected for Scheduling and Structuring offer. Outgoing Call also achieved 100/100 capability score; policy tie-breaker favored Email as the initial non-intrusive channel to present the detailed restructuring breakdown before follow-up calling.
- **Agent Approach:** Warm, consultative tone. Open with acknowledgement of his 7-year relationship and discuss restructuring options before discussing arrears.

### SECTION 4 — RECOVERY QUANTIFICATION & ESCALATION CLOCK
- **Business Case:** Expected recovery probability is 75.0%, representing JOD 28,242.82 expected recovery against JOD 37,657.10 write-off exposure.
- **Negotiation Boundaries:** Minimum acceptable cash settlement floor is JOD 2,828.28. Maximum restructuring term is 18 months. Interest waiver authority is JOD 80.83; late fee waiver is 100% pre-approved. Agent authorized to offer a 30-day payment moratorium without escalation.
- **Escalation Timeline:**
  - `PHASE 1 — ACTIVE`: Active Email restructuring proposal. Window: 0-7 days (ending 2026-09-03).
  - `PHASE 2 — TRIGGER`: Triggered if customer rejects terms or minimum JOD 2,828.28 is not received by 2026-09-03. Action: Formal demand letter + legal pre-notification SMS (days 8-21).
  - `PHASE 3 — LEGAL`: Triggered if Phase 2 produces no agreement by day 21. Action: Legal referral and bureau default registration. Reclassify to Stage 3 per IFRS 9.
  - `EXIT — DE-ESCALATION`: Signature of restructured agreement and payment of minimum floor transitions customer to Q1 (cooperative monitoring).

### SECTION 5 — MODEL AUDIT TRAIL
Decision governed by CollectIQ-Matrix-Bandit v3.1.4 (validated 2026-02-28, Gini 0.74, PSI 0.08); IFRS 9 Stage 2 (Significant Increase in Credit Risk); regulatory framework: CBJ Circ. 2/2022 & PDPL Art. 14; human override policy: Agent may override NBA. Must log justification code in CRM within 2 hours."""
    },
    "10017292": {
        "quadrant": "Q4",
        "segment": "Mass retail / Salaried",
        "nationality": "Jordanian / Resident",
        "products": "Mortgage, Current account",
        "contact_avoidance": 0.88,
        "payment_rejection_freq": 4,
        "broken_ptp": 3,
        "days_since_rpc": 60,
        "ptp_reliability": 0.10,
        "inflow_variance": 3800.0,
        "call_response_rate": 0.08,
        "field_visit_response_rate": 0.35,
        "sms_estimated_response_rate": 0.04,
        "email_estimated_response_rate": 0.02,
        "letter_estimated_response_rate": 0.10,
        "narrative": """### SECTION 1 — IDENTITY & COMPLIANCE GATE
- **KYC Anchor:** Fatima Nour Khoury (CIF-10017292), Jordanian / Resident Mass retail / Salaried customer employed at Arab Bank (verified), 8 yr 2 mo tenure.
- **KYC Status & Gate:** KYC is Up to date. Verified income is JOD 1,992/mo (last verified 2 months ago). Compliance gate is clear for legal and field operations.
- **AML / PEP / Sanctions:** Screened clear on 2026-03-28. PEP and Sanctions checks negative.
- **Products Held:** Mortgage, Current account.

### SECTION 2 — MATRIX STATE & UNCERTAINTY ENVELOPE
- **Primary Classification & Scores:** Classified into Q4 (High Risk / Impaired). Composite risk score is 84/100, willingness score is 7/100, ability score is 10/100, with 143 days past due (DPD).
- **Confidence & Uncertainty:** High model confidence in Q4 at 84.0% (competing quadrant Q3 at 28.0%, uncertainty gap +56.0%).
- **Score Velocity:** 90-day risk delta is 0 pts (static chronic delinquency, entrenched in default).
- **Willingness & Ability SHAP Drivers:**
  - *Willingness Risk Drivers:* Heavily degraded willingness driven by Recent Broken Promises (68.1% decision weight), reflecting chronic failure to honor payment commitments.
  - *Ability Risk Drivers:* Multi-vector financial distress driven by Debt Service Burden (33.99% decision weight), repeated Payment Rejection Rate (33.91% decision weight), and depleted Liquidity Runway (30.74% decision weight).
- **Agent Posture:** Firm, authoritative, and escalation-oriented. Prioritize in-person contact to secure immediate token recovery and enforce legal accountability.

### SECTION 3 — BEHAVIORAL INTELLIGENCE & CHANNEL STRATEGY
- **Signal Breakdown:**
  - *[OBSERVED]* Contact Failure: Telephony and messaging attempts over 60+ days remain unanswered or unreturned.
  - *[INFERRED]* Evasive Pattern: Contact avoidance index is 0.88 (severely above 0.60 threshold), indicating deliberate avoidance of bank communications.
  - *[OBSERVED]* Payment Rejections: 4 direct debit rejections recorded.
  - *[HYPOTHESIS]* Liquidity Disruption: Inflow volatility indicates salary disruption or diversion to alternative accounts.
- **Recommended Channel Rationale:** In-person Field Visit (Confidence 100/100) selected for Partial Payment negotiation. While Outgoing Call scored 100/100, the policy tie-breaker in escalation quadrants directs outreach to physical Field Visit because remote telephony has been exhausted by customer evasion.
- **Agent Approach:** Formal, assertive executive presence. Serve written final notice, verify debtor residence, and establish strict 48-hour cure deadline.

### SECTION 4 — RECOVERY QUANTIFICATION & ESCALATION CLOCK
- **Business Case:** Expected recovery probability is 45.0%, representing JOD 10,481.92 expected recovery against JOD 23,293.16 write-off exposure (Total overdue balance JOD 39,637.45).
- **Negotiation Boundaries:** Minimum acceptable cash settlement floor is JOD 2,316.88. Maximum restructuring term is 18 months. Interest waiver authority is JOD 77.88; late fee waiver is 100% pre-approved upon immediate cash payment.
- **Escalation Timeline:**
  - `PHASE 1 — ACTIVE`: Field Visit deployment with formal demand package. Window: 0-7 days (ending 2026-09-03).
  - `PHASE 2 — TRIGGER`: Triggered if Field Visit is unresolved or minimum JOD 2,316.88 is not received by 2026-09-03. Action: Formal registered legal demand letter + pre-litigation asset investigation (days 8-21).
  - `PHASE 3 — LEGAL`: Triggered if Phase 2 yields no cure by day 21. Action: Immediate referral to Legal Department for civil litigation and collateral enforcement. Account maintained in Stage 3 per IFRS 9.
  - `EXIT — DE-ESCALATION`: Receipt of immediate minimum cash floor and binding repayment agreement qualifies account for reclassification to Q2 (cooperative recovery monitoring).

### SECTION 5 — MODEL AUDIT TRAIL
Decision governed by CollectIQ-Matrix-Bandit v3.1.4 (validated 2026-02-28, Gini 0.74, PSI 0.08); IFRS 9 Stage 3 (Impaired); regulatory framework: CBJ Circ. 2/2022 & PDPL Art. 14; human override policy: Agent may override NBA. Must log justification code in CRM within 2 hours."""
    }
}


def clean_demo_customers():
    db.initialize_pool()
    day_date = settings.SNAP_DATE_OVERRIDE or "2026-08-27"
    country_code = settings.COUNTRY_CODE
    inst_code = settings.INST_CODE

    print(f"Aligning demo showcase customers for {day_date} (inst={inst_code}, country={country_code})...")

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            for cid, cfg in SHOWCASE_CONFIGS.items():
                print(f"\n--- Processing Customer {cid} ({cfg['quadrant']}) ---")
                
                # 1. Update CONTEXT_MART (clean strings, calibrated indices & factual response rates)
                cur.execute("""
                    UPDATE BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART
                    SET CONTACT_AVOIDANCE_INDEX = :cai,
                        PAYMENT_REJECTION_FREQ = :prf,
                        CUSTOMER_SEGMENT = :seg,
                        NATIONALITY_RESIDENCY = :nat,
                        PRODUCTS_HELD = :prod,
                        CALL_RESPONSE_RATE = :crr,
                        FIELD_VISIT_RESPONSE_RATE = :fvr,
                        SMS_ESTIMATED_RESPONSE_RATE = :srr,
                        EMAIL_ESTIMATED_RESPONSE_RATE = :err,
                        LETTER_ESTIMATED_RESPONSE_RATE = :lrr
                    WHERE CUST_INFO_ID = :cid AND DAY_DATE = TO_DATE(:dt, 'YYYY-MM-DD')
                """, cai=cfg["contact_avoidance"], prf=cfg["payment_rejection_freq"],
                     seg=cfg["segment"], nat=cfg["nationality"], prod=cfg["products"],
                     crr=cfg["call_response_rate"], fvr=cfg["field_visit_response_rate"],
                     srr=cfg["sms_estimated_response_rate"], err=cfg["email_estimated_response_rate"],
                     lrr=cfg["letter_estimated_response_rate"],
                     cid=cid, dt=day_date)

                # 2. Update WILLINGNESS_MART
                cur.execute("""
                    UPDATE BI_DWH.PIO_COLL_AI_WILLINGNESS_MART
                    SET BROKEN_PTP_COUNT_6M = :b_ptp,
                        DAYS_SINCE_LAST_RPC = :rpc,
                        PTP_RELIABILITY_RATIO = :rel
                    WHERE CUST_INFO_ID = :cid AND DAY_DATE = TO_DATE(:dt, 'YYYY-MM-DD')
                """, b_ptp=cfg["broken_ptp"], rpc=cfg["days_since_rpc"], rel=cfg["ptp_reliability"], cid=cid, dt=day_date)

                # 3. Update ABILITY_MART
                cur.execute("""
                    UPDATE BI_DWH.PIO_COLL_AI_ABILITY_MART
                    SET INFLOW_VARIANCE_30D = :inf
                    WHERE CUST_INFO_ID = :cid AND DAY_DATE = TO_DATE(:dt, 'YYYY-MM-DD')
                """, inf=cfg["inflow_variance"], cid=cid, dt=day_date)

                # 4. Fetch full joined record
                cur.execute("""
                    SELECT 
                        m.*,
                        r.WILLINGNESS_SCORE,
                        r.ABILITY_SCORE,
                        r.CURRENT_QUADRANT,
                        r.WILL_RISK_DRIVERS,
                        r.WILL_POSITIVE_DRIVERS,
                        r.ABIL_RISK_DRIVERS,
                        r.ABIL_POSITIVE_DRIVERS,
                        w.BROKEN_PTP_COUNT_6M,
                        w.DAYS_SINCE_LAST_RPC,
                        w.PTP_RELIABILITY_RATIO,
                        a.INFLOW_VARIANCE_30D
                    FROM BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART m
                    JOIN BI_DWH.PIO_COLL_AI_MATRIX_RESULTS r 
                      ON m.CUST_INFO_ID = r.CUST_INFO_ID AND m.DAY_DATE = r.DAY_DATE
                    JOIN BI_DWH.PIO_COLL_AI_WILLINGNESS_MART w
                      ON m.CUST_INFO_ID = w.CUST_INFO_ID AND m.DAY_DATE = w.DAY_DATE
                    JOIN BI_DWH.PIO_COLL_AI_ABILITY_MART a
                      ON m.CUST_INFO_ID = a.CUST_INFO_ID AND m.DAY_DATE = a.DAY_DATE
                    WHERE m.CUST_INFO_ID = :cid AND m.DAY_DATE = TO_DATE(:dt, 'YYYY-MM-DD')
                """, cid=cid, dt=day_date)

                desc = [d[0] for d in cur.description]
                row = cur.fetchone()
                if not row:
                    print(f"ERROR: Could not find joined record for customer {cid}!")
                    continue

                raw_record = {}
                for col_name, val in zip(desc, row):
                    if hasattr(val, 'read'):
                        raw_record[col_name] = val.read()
                    else:
                        raw_record[col_name] = val

                # 5. Generate Behavioral Signals
                signals = SignalInterpreter.generate_signals(raw_record)
                print(f"Generated {len(signals)} signals:")
                for s in signals:
                    print(f"  [{s.signal_type.value}] {s.title}: {s.description}")

                # 6. Run Contextual Bandit Decision
                quad_str = f"Q{raw_record.get('CURRENT_QUADRANT')}" if not str(raw_record.get('CURRENT_QUADRANT', '')).startswith("Q") else str(raw_record.get('CURRENT_QUADRANT'))
                cust_state = CustomerState(
                    cust_info_id=cid,
                    days_past_due=int(raw_record.get("DAYS_PAST_DUE") or 0),
                    current_quadrant=quad_str,
                    account_status=str(raw_record.get("ACCOUNT_STATUS", "Active")),
                    total_due=float(raw_record.get("TOTAL_DUE") or 0.0),
                    sms_sent_this_week=int(raw_record.get("SMS_SENT_THIS_WEEK") or 0),
                    calls_made_today=int(raw_record.get("CALLS_MADE_TODAY") or 0),
                    behavioral_signals=signals,
                    call_response_rate=cfg["call_response_rate"],
                    field_visit_response_rate=cfg["field_visit_response_rate"],
                    sms_estimated_response_rate=cfg["sms_estimated_response_rate"],
                    email_estimated_response_rate=cfg["email_estimated_response_rate"],
                    letter_estimated_response_rate=cfg["letter_estimated_response_rate"],
                )

                bandit = ContextualBandit()
                allowed_channels = [Channel.EMAIL, Channel.SMS, Channel.OUTGOING_CALL, Channel.DUNNING_LETTER, Channel.FIELD_VISIT]
                nba_output = bandit.get_best_action(cust_state, allowed_channels)
                scored_dicts = [alt.model_dump() for alt in nba_output.scored_alternatives]
                print(f"NBA Decision: {nba_output.recommended_channel} / {nba_output.recommended_treatment}")

                # 7. Aggregate Full Cockpit Payload
                payload_json = CockpitAggregator.generate_payload_string(
                    cust_info_id=cid,
                    country_code=country_code,
                    inst_code=inst_code,
                    day_date=day_date,
                    quadrant=quad_str,
                    will_risk=raw_record.get("WILL_RISK_DRIVERS"),
                    will_pos=raw_record.get("WILL_POSITIVE_DRIVERS"),
                    abil_risk=raw_record.get("ABIL_RISK_DRIVERS"),
                    abil_pos=raw_record.get("ABIL_POSITIVE_DRIVERS"),
                    nba_channel=str(nba_output.recommended_channel),
                    nba_treatment=str(nba_output.recommended_treatment),
                    scored_alternatives=scored_dicts,
                    raw_record=raw_record
                )

                # Clean any unicode replacement characters if present
                payload_json = payload_json.replace("\ufffd", "-")

                # 8. Update PIO_COLL_AI_NBA_ACTIONS with Payload and Cached Narrative
                cur.execute("""
                    UPDATE BI_DWH.PIO_COLL_AI_NBA_ACTIONS
                    SET RECOMMENDED_CHANNEL = :ch,
                        RECOMMENDED_OFFER   = :off,
                        DECISION_REASON     = :rsn,
                        AI_PAYLOAD          = :p,
                        SCORED_ALTERNATIVES = :alts,
                        AI_NARRATIVE        = :narr,
                        UPDATED_AT          = CURRENT_TIMESTAMP
                    WHERE CUST_INFO_ID = :cid AND DAY_DATE = TO_DATE(:dt, 'YYYY-MM-DD')
                """, {
                    "ch": str(nba_output.recommended_channel),
                    "off": str(nba_output.recommended_treatment),
                    "rsn": str(nba_output.decision_reason),
                    "p": payload_json,
                    "alts": json.dumps(scored_dicts),
                    "narr": cfg["narrative"],
                    "cid": cid,
                    "dt": day_date
                })

            conn.commit()
            print("\n>>> All 3 demo showcase customers successfully cleaned, calibrated, and committed to DB! <<<")


if __name__ == "__main__":
    clean_demo_customers()
