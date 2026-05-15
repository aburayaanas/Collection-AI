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
from datetime import datetime

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

        context_data.append((
            snapshot_date, settings.INST_CODE, settings.COUNTRY_CODE,
            cust_info_id,
            account_status,
            total_due,
            sms_sent_this_week,
            calls_made_today,
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
                        SMS_SENT_THIS_WEEK, CALLS_MADE_TODAY
                    ) VALUES (:1, :2, :3, :4, :5, :6, :7, :8)
                """
                cursor.executemany(sql_context, context_data)

                connection.commit()
                print(f"Successfully seeded {len(willingness_data):,} records into all 3 mart tables.")

    except oracledb.Error as e:
        print(f"Database error occurred: {e}")


if __name__ == "__main__":
    w_data, a_data, ctx_data = generate_dummy_data(NUM_RECORDS)
    insert_data(w_data, a_data, ctx_data)
