"""
Synthetic Data Generator for AI Data Marts.

Generates synthetic records for three tables:
  1. PIO_COLL_AI_WILLINGNESS_MART  — ML features for the Willingness model
  2. PIO_COLL_AI_ABILITY_MART      — ML features for the Ability model
  3. PIO_COLL_AI_NBA_CONTEXT_MART  — NBA operational context (isolated)

Design Principles:
  - All tables share the same CUST_INFO_IDs, DAY_DATE, INST_CODE, and COUNTRY_CODE.
  - Class balance: TARGET_WILLINGNESS ~35% positive, TARGET_ABILITY ~30% positive.
"""

import sys
from pathlib import Path
import random
from datetime import datetime, timedelta

import oracledb

# Add project root to sys.path so 'src' is resolvable
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.database.connection import db  # noqa: E402
from src.core.config import settings     # noqa: E402

# ── Global config ─────────────────────────────────────────────────────────────
NUM_RECORDS = 5_000

# ── NBA context distributions ─────────────────────────────────────────────────
_ACCOUNT_STATUS_POOL = (
    ["Active"] * 85
    + ["Deceased"] * 3
    + ["Disease"] * 4
    + ["Legal"] * 5
    + ["Transfer To Remedial"] * 3
)

_SMS_WEIGHTS = [50, 25, 15, 10]
_CALL_WEIGHTS = [60, 30, 10]


def generate_dummy_data(num_records: int = NUM_RECORDS):
    """Generate synthetic data for all three AI mart tables."""
    print(f"Generating {num_records:,} synthetic customer records...")

    willingness_data = []
    ability_data = []
    context_data = []
    generated_ids = set()

    # Use only the DATE part (no time) to match DB expectations
    if settings.SNAP_DATE_OVERRIDE:
        snapshot_date = datetime.strptime(settings.SNAP_DATE_OVERRIDE, "%Y-%m-%d").date()
    else:
        snapshot_date = datetime.now().date()

    while len(willingness_data) < num_records:
        cust_info_id = str(random.randint(10_000_000, 99_999_999))
        
        # Ensure we don't pick the same ID twice in one batch
        if cust_info_id in generated_ids:
            continue
        generated_ids.add(cust_info_id)

        # ── Willingness Features ──────────────────────────────────────
        days_since_rpc  = random.choice([None, random.randint(1, 180)])
        ptp_ratio       = round(random.uniform(0.0, 1.0), 4)
        pay_velocity    = random.randint(0, 5)
        partial_ratio   = round(random.uniform(0.0, 1.0), 4)
        self_cure       = random.choice([0, 1])
        bounce_rate     = round(random.uniform(0.0, 1.0), 4)
        broken_ptp      = random.randint(0, 15)

        target_w = 1 if (pay_velocity >= 2 and ptp_ratio > 0.55 and broken_ptp <= 3) else 0

        willingness_data.append((
            snapshot_date, settings.INST_CODE, settings.COUNTRY_CODE,
            cust_info_id, snapshot_date,
            days_since_rpc, ptp_ratio, pay_velocity, partial_ratio,
            self_cure, bounce_rate, broken_ptp, target_w,
        ))

        # ── Ability Features ──────────────────────────────────────────
        inflow_var      = round(random.uniform(0.0, 8_000.0), 2)
        cash_runway     = round(random.uniform(0.0, 90.0), 2)
        spend_volatility= round(random.uniform(0.1, 2.5), 4)
        debt_proxy      = round(random.uniform(0.1, 2.0), 4)
        nsf_rate        = round(random.uniform(0.0, 1.0), 4)
        zero_bal_ratio  = round(random.uniform(0.0, 1.0), 4)

        target_a = 1 if (cash_runway > 20.0 and nsf_rate < 0.15 and debt_proxy < 0.8) else 0

        ability_data.append((
            snapshot_date, settings.INST_CODE, settings.COUNTRY_CODE,
            cust_info_id, snapshot_date,
            inflow_var, cash_runway, spend_volatility,
            debt_proxy, nsf_rate, zero_bal_ratio, target_a,
        ))

        # ── NBA Context ───────────────────────────────────────────────
        account_status = random.choice(_ACCOUNT_STATUS_POOL)
        stress_factor = (bounce_rate + min(broken_ptp / 15.0, 1.0)) / 2.0
        total_due = round(200.0 + stress_factor * 49_800.0, 2)
        sms_sent_this_week = random.choices(range(4), weights=_SMS_WEIGHTS)[0]
        calls_made_today   = random.choices(range(3), weights=_CALL_WEIGHTS)[0]

        # ── KYC & Customer Identity Overview ──────────────────────────
        first_names = ["Khalid", "Ahmed", "Omar", "Aisha", "Fatima", "Sara", "Ali", "Hassan", "Yousef", "Nour", "Rami"]
        last_names = ["Al-Rashidi", "Mansour", "Haddad", "Al-Fayed", "Khoury", "Al-Zoubi", "Othman", "Al-Safi", "Awad"]
        full_legal_name = f"{random.choice(first_names)} {random.choice(first_names)} {random.choice(last_names)}"
        
        customer_segment = random.choice(["Mass retail · Salaried", "Mass retail · Self-employed", "Wealth · Salaried"])
        nationality_residency = random.choice(["Jordanian · Resident", "Expat · Resident"])
        
        if "Self-employed" in customer_segment:
            employer_name = "Self / Trade License"
        else:
            employer_name = random.choice(["Arab Bank", "Zain", "Hikma Pharmaceuticals", "Royal Jordanian", "Ministry of Education", "Orange"])
            
        if "Wealth" in customer_segment:
            verified_income_jod = round(random.uniform(3000.0, 15000.0), 2)
        else:
            verified_income_jod = round(random.uniform(500.0, 2500.0), 2)
            
        income_verified_months_ago = random.randint(1, 24)
        income_last_verified_date = snapshot_date - timedelta(days=30 * income_verified_months_ago)
        
        aml_last_screened_date = snapshot_date - timedelta(days=random.randint(1, 180))
        
        account_open_months_ago = random.randint(income_verified_months_ago + 1, 120)
        account_open_date = snapshot_date - timedelta(days=30 * account_open_months_ago)
        
        products_held = random.choice([
            "Personal loan", 
            "Credit card · Savings", 
            "Personal loan · Credit card · Savings", 
            "Mortgage · Current account",
            "Auto loan · Credit card"
        ])
        
        primary_phone = f"+962 79 {random.randint(100, 999)} {random.randint(1000, 9999)}"

        # ── Block 2: Matrix & Quadrant Classification ─────────────────
        import json
        
        # Correlate DPD and risk score to the quadrant/target
        if target_w == 0 and target_a == 0:  # Q4-ish (Severe Distress / High Risk)
            days_past_due = random.randint(60, 180)
            p_label, c_label = "Q4", "Q3"
            composite_risk_score = random.randint(78, 98)
        elif target_w == 1 and target_a == 0: # Q2 (Vulnerable: High Willingness, Low Ability)
            days_past_due = random.randint(30, 90)
            p_label, c_label = "Q2", "Q4"
            composite_risk_score = random.randint(40, 65)
        elif target_w == 0 and target_a == 1: # Q3 (Strategic Defaulter: Low Willingness, High Ability)
            days_past_due = random.randint(30, 120)
            p_label, c_label = "Q3", "Q4"
            composite_risk_score = random.randint(55, 75)
        else: # Q1 (Low Risk / Cooperative)
            days_past_due = random.randint(1, 30)
            p_label, c_label = "Q1", "Q2"
            composite_risk_score = random.randint(10, 30)

        # 90D Velocity (delta): Ensure Previous Score = (composite_risk_score - delta) is strictly within [0, 100]
        min_possible_delta = composite_risk_score - 100  # ensures score - delta <= 100
        max_possible_delta = composite_risk_score        # ensures score - delta >= 0
        allowed_min = max(-35, min_possible_delta)
        allowed_max = min(30, max_possible_delta)
        if allowed_min > allowed_max:
            allowed_min, allowed_max = allowed_max, allowed_min
        score_delta_90d = random.randint(allowed_min, allowed_max)
            
        classification_probs = json.dumps({
            "primary": {"label": p_label, "conf": round(random.uniform(0.60, 0.95), 2)},
            "competing": {"label": c_label, "conf": round(random.uniform(0.10, 0.30), 2)},
            "residual": {"label": "Q_OTHER", "conf": round(random.uniform(0.01, 0.09), 2)}
        })
        
        # ── Block 3: Behavioral Signal Data (Correlated with Quadrant) ─
        if target_w == 1 and target_a == 1:  # Q1: Cooperative, low risk
            payment_rejection_freq = 0
            contact_avoidance_index = round(random.uniform(0.0, 0.15), 2)
        elif target_w == 1 and target_a == 0:  # Q2: Distressed but cooperative
            payment_rejection_freq = random.randint(1, 3)
            contact_avoidance_index = round(random.uniform(0.05, 0.30), 2)
        elif target_w == 0 and target_a == 1:  # Q3: Strategic defaulter (evades contact)
            payment_rejection_freq = random.randint(0, 1)
            contact_avoidance_index = round(random.uniform(0.65, 0.95), 2)
        else:  # Q4: Chronic high risk default
            payment_rejection_freq = random.randint(2, 5)
            contact_avoidance_index = round(random.uniform(0.70, 0.99), 2)

        # ── Block 5: Financial Exposure Data ──────────────────────────
        total_exposure_jod = round(random.uniform(1000.0, 50000.0), 2)
        current_arrears_jod = round(total_exposure_jod * random.uniform(0.05, 0.35), 2)
        accrued_interest_jod = round(current_arrears_jod * random.uniform(0.02, 0.10), 2)
        late_fees_jod = round(random.uniform(15.0, 100.0), 2)

        # ── Channel Response Rates (Factual baseline metrics) ─────────
        if target_w == 1 and target_a == 1:  # Q1
            call_response_rate = round(random.uniform(0.70, 0.90), 4)
            field_visit_response_rate = round(random.uniform(0.75, 0.95), 4)
            sms_estimated_response_rate = round(random.uniform(0.12, 0.20), 4)
            email_estimated_response_rate = round(random.uniform(0.10, 0.18), 4)
            letter_estimated_response_rate = round(random.uniform(0.15, 0.25), 4)
        elif target_w == 1 and target_a == 0:  # Q2
            call_response_rate = round(random.uniform(0.55, 0.75), 4)
            field_visit_response_rate = round(random.uniform(0.60, 0.80), 4)
            sms_estimated_response_rate = round(random.uniform(0.10, 0.15), 4)
            email_estimated_response_rate = round(random.uniform(0.08, 0.12), 4)
            letter_estimated_response_rate = round(random.uniform(0.12, 0.18), 4)
        elif target_w == 0 and target_a == 1:  # Q3
            call_response_rate = round(random.uniform(0.10, 0.25), 4)
            field_visit_response_rate = round(random.uniform(0.40, 0.60), 4)
            sms_estimated_response_rate = round(random.uniform(0.05, 0.09), 4)
            email_estimated_response_rate = round(random.uniform(0.03, 0.07), 4)
            letter_estimated_response_rate = round(random.uniform(0.10, 0.15), 4)
        else:  # Q4
            call_response_rate = round(random.uniform(0.02, 0.12), 4)
            field_visit_response_rate = round(random.uniform(0.25, 0.45), 4)
            sms_estimated_response_rate = round(random.uniform(0.02, 0.06), 4)
            email_estimated_response_rate = round(random.uniform(0.01, 0.04), 4)
            letter_estimated_response_rate = round(random.uniform(0.05, 0.12), 4)

        context_data.append((
            snapshot_date, settings.INST_CODE, settings.COUNTRY_CODE,
            cust_info_id,
            account_status,
            total_due,
            sms_sent_this_week,
            calls_made_today,
            full_legal_name,
            customer_segment,
            nationality_residency,
            employer_name,
            verified_income_jod,
            income_last_verified_date,
            aml_last_screened_date,
            account_open_date,
            products_held,
            primary_phone,
            score_delta_90d,
            composite_risk_score,
            days_past_due,
            classification_probs,
            payment_rejection_freq,
            contact_avoidance_index,
            total_exposure_jod,
            current_arrears_jod,
            accrued_interest_jod,
            late_fees_jod,
            call_response_rate,
            field_visit_response_rate,
            sms_estimated_response_rate,
            email_estimated_response_rate,
            letter_estimated_response_rate
        ))

    return willingness_data, ability_data, context_data


def insert_data(willingness_data: list, ability_data: list, context_data: list) -> None:
    """Connect to Oracle and bulk-insert all three mart tables."""
    print("Initializing Database Pool...")
    db.initialize_pool()

    print("Connecting to Oracle Database...")
    try:
        with db.get_connection() as connection:
            with connection.cursor() as cursor:
                # ── Ensure Columns Exist for Block 5 ──────────────────
                try:
                    cursor.execute("""
                        ALTER TABLE BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART ADD (
                            TOTAL_EXPOSURE_JOD NUMBER(15,2),
                            CURRENT_ARREARS_JOD NUMBER(15,2),
                            ACCRUED_INTEREST_JOD NUMBER(15,2),
                            LATE_FEES_JOD NUMBER(15,2)
                        )
                    """)
                    print("Successfully added financial columns to PIO_COLL_AI_NBA_CONTEXT_MART.")
                except oracledb.DatabaseError as e:
                    if "ORA-01430" in str(e):
                        pass  # columns already exist
                    else:
                        print(f"Warning adding columns: {e}")

                # ── 0. Clear Run (Truncate Tables) ────────────────────
                print("Clearing old dummy data (Truncate)...")
                cursor.execute("TRUNCATE TABLE PIO_COLL_AI_WILLINGNESS_MART")
                cursor.execute("TRUNCATE TABLE PIO_COLL_AI_ABILITY_MART")
                cursor.execute("TRUNCATE TABLE BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART")

                # ── 1. Willingness Mart ───────────────────────────────
                print("Inserting Willingness data...")
                sql_willingness = """
                    INSERT INTO PIO_COLL_AI_WILLINGNESS_MART (
                        DAY_DATE, INST_CODE, COUNTRY_CODE,
                        CUST_INFO_ID, SNAPSHOT_DATE,
                        DAYS_SINCE_LAST_RPC, PTP_RELIABILITY_RATIO,
                        PAYMENT_VELOCITY_30D, PARTIAL_PAYMENT_RATIO,
                        SELF_CURE_HISTORY_FLAG, BOUNCE_RATE_60D,
                        BROKEN_PTP_COUNT_6M, TARGET_WILLINGNESS
                    ) VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12, :13)
                """
                cursor.executemany(sql_willingness, willingness_data)

                # ── 2. Ability Mart ───────────────────────────────────
                print("Inserting Ability data...")
                sql_ability = """
                    INSERT INTO PIO_COLL_AI_ABILITY_MART (
                        DAY_DATE, INST_CODE, COUNTRY_CODE,
                        CUST_INFO_ID, SNAPSHOT_DATE,
                        INFLOW_VARIANCE_30D, CASH_RUNWAY_DAYS_ESTIMATED,
                        SPENDING_VOLATILITY_CV_60D, DEBT_SERVICE_PROXY_RATIO,
                        NSF_EVENT_RATE_60D, ZERO_BALANCE_DAYS_RATIO_30D,
                        TARGET_ABILITY
                    ) VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12)
                """
                cursor.executemany(sql_ability, ability_data)

                # ── 3. NBA Context Mart ───────────────────────────────
                print("Inserting NBA Context data...")
                sql_context = """
                    INSERT INTO BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART (
                        DAY_DATE, INST_CODE, COUNTRY_CODE, CUST_INFO_ID,
                        ACCOUNT_STATUS, TOTAL_DUE,
                        SMS_SENT_THIS_WEEK, CALLS_MADE_TODAY,
                        FULL_LEGAL_NAME, CUSTOMER_SEGMENT,
                        NATIONALITY_RESIDENCY, EMPLOYER_NAME,
                        VERIFIED_INCOME_JOD, INCOME_LAST_VERIFIED_DATE,
                        AML_LAST_SCREENED_DATE, ACCOUNT_OPEN_DATE,
                        PRODUCTS_HELD, PRIMARY_PHONE,
                        SCORE_DELTA_90D, COMPOSITE_RISK_SCORE,
                        DAYS_PAST_DUE, CLASSIFICATION_PROBABILITIES,
                        PAYMENT_REJECTION_FREQ, CONTACT_AVOIDANCE_INDEX,
                        TOTAL_EXPOSURE_JOD, CURRENT_ARREARS_JOD,
                        ACCRUED_INTEREST_JOD, LATE_FEES_JOD,
                        CALL_RESPONSE_RATE, FIELD_VISIT_RESPONSE_RATE,
                        SMS_ESTIMATED_RESPONSE_RATE, EMAIL_ESTIMATED_RESPONSE_RATE,
                        LETTER_ESTIMATED_RESPONSE_RATE
                    ) VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12, :13, :14, :15, :16, :17, :18, :19, :20, :21, :22, :23, :24, :25, :26, :27, :28, :29, :30, :31, :32, :33)
                """
                cursor.executemany(sql_context, context_data)

                connection.commit()
                print(f"Successfully seeded {len(willingness_data):,} records into all 3 mart tables.")

    except oracledb.Error as e:
        print(f"Database error occurred: {e}")


if __name__ == "__main__":
    w_data, a_data, ctx_data = generate_dummy_data(NUM_RECORDS)
    insert_data(w_data, a_data, ctx_data)
