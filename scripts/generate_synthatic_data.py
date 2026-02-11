"""
Synthetic Data Generator for AI Data Marts.
Generates 1,000 matching records for Willingness and Ability to unblock ML development.
"""

import random
from datetime import datetime, timedelta #noqa
import oracledb
from src.database.connection import db

def generate_dummy_data(num_records=1000):
    """Generates synthetic data for both Data Marts."""
    print(f"Generating {num_records} synthetic customer records...")
    
    willingness_data = []
    ability_data = []
    
    # Use today for the snapshot
    snapshot_date = datetime.now()

    for _ in range(num_records):
        # 1. Generate the 8-digit Customer ID (e.g., '20200008')
        cust_info_id = str(random.randint(10000000, 99999999))
        
        # ---------------------------------------------------------------------
        # 2. Generate Willingness Data
        # ---------------------------------------------------------------------
        days_since_rpc = random.choice([None, random.randint(1, 100)])
        ptp_ratio = round(random.uniform(0.0, 1.0), 4)
        pay_velocity = random.randint(0, 5)
        partial_ratio = round(random.uniform(0.0, 1.0), 4)
        self_cure = random.choice([0, 1])
        bounce_rate = round(random.uniform(0.0, 1.0), 4)
        broken_ptp = random.randint(0, 10)
        
        # Simple logical heuristic for the target
        target_w = 1 if (pay_velocity > 0 or ptp_ratio > 0.5) else 0

        willingness_data.append((
            cust_info_id, snapshot_date, days_since_rpc, ptp_ratio,
            pay_velocity, partial_ratio, self_cure, bounce_rate,
            broken_ptp, target_w
        ))

        # ---------------------------------------------------------------------
        # 3. Generate Ability Data
        # ---------------------------------------------------------------------
        inflow_var = round(random.uniform(100.0, 5000.0), 2)
        cash_runway = round(random.uniform(0.0, 60.0), 2)
        spend_volatility = round(random.uniform(0.1, 2.0), 4)
        debt_proxy = round(random.uniform(0.1, 1.5), 4)
        nsf_rate = round(random.uniform(0.0, 0.8), 4)
        zero_bal_ratio = round(random.uniform(0.0, 1.0), 4)
        
        # Simple logical heuristic for the target
        target_a = 1 if (cash_runway > 14.0 and nsf_rate < 0.1) else 0

        ability_data.append((
            cust_info_id, snapshot_date, inflow_var, cash_runway,
            spend_volatility, debt_proxy, nsf_rate, zero_bal_ratio, target_a
        ))

    return willingness_data, ability_data

def insert_data(willingness_data, ability_data):
    """Connects to Oracle and bulk-inserts the generated data."""
    print("Initializing Database Pool...")
    db.initialize_pool()
    
    print("Connecting to Oracle Database...")
    try:
        with db.get_connection() as connection:
            with connection.cursor() as cursor:
                
                # Insert Willingness
                print("Inserting Willingness Data...")
                sql_willingness = """
                    INSERT INTO PIO_COLL_AI_WILLINGNESS_MART (
                        CUST_INFO_ID, SNAPSHOT_DATE, DAYS_SINCE_LAST_RPC, PTP_RELIABILITY_RATIO, 
                        PAYMENT_VELOCITY_30D, PARTIAL_PAYMENT_RATIO, SELF_CURE_HISTORY_FLAG, 
                        BOUNCE_RATE_60D, BROKEN_PTP_COUNT_6M, TARGET_WILLINGNESS
                    ) VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10)
                """
                cursor.executemany(sql_willingness, willingness_data)
                
                # Insert Ability
                print("Inserting Ability Data...")
                sql_ability = """
                    INSERT INTO PIO_COLL_AI_ABILITY_MART (
                        CUST_INFO_ID, SNAPSHOT_DATE, INFLOW_VARIANCE_30D, CASH_RUNWAY_DAYS_ESTIMATED, 
                        SPENDING_VOLATILITY_CV_60D, DEBT_SERVICE_PROXY_RATIO, NSF_EVENT_RATE_60D, 
                        ZERO_BALANCE_DAYS_RATIO_30D, TARGET_ABILITY
                    ) VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
                """
                cursor.executemany(sql_ability, ability_data)
                
                connection.commit()
                print("✅ Successfully seeded 1,000 records into both tables!")
                
    except oracledb.Error as e:
        print(f"❌ Database error occurred: {e}")

if __name__ == "__main__":
    w_data, a_data = generate_dummy_data(1000)
    insert_data(w_data, a_data)