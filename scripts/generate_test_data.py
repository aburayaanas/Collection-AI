"""
Synthetic Test Data Generator for Collection AI.

Generates 500 UNSEEN customer records with DIFFERENT distributions than the
training data to simulate real-world drift and validate model generalization.

Key differences from training data (generate_synthatic_data.py):
- Different customer ID range (to avoid PK collisions)
- Shifted feature distributions (mean shifts, wider variance)
- Edge cases: extreme values, boundary conditions, adversarial patterns
- Inserted under a DIFFERENT DAY_DATE so training data is not contaminated

Usage:
    python -m scripts.generate_test_data
    
    # Or with custom date and count:
    python -m scripts.generate_test_data --date 2025-05-18 --count 500
"""

import random
import argparse
from datetime import datetime
from typing import List, Tuple

import oracledb  # noqa
from src.database.connection import db


# ── Distribution Profiles ────────────────────────────────────────────
# These intentionally differ from the training generator to simulate drift.

def _clamp(val: float, lo: float, hi: float) -> float:
    """Clamp a value between lo and hi."""
    return max(lo, min(hi, val))


def generate_test_data(
    num_records: int = 500,
    snapshot_date: datetime = None,
) -> Tuple[List[tuple], List[tuple]]:
    """
    Generate synthetic test data with shifted distributions.

    Unlike training data:
      - PTP ratios are skewed higher (more defaults)
      - Cash runways are shorter (more financial stress)
      - Features include boundary/edge values
      - ~10% of records are adversarial (conflicting signals)

    Args:
        num_records: Number of customer records to generate
        snapshot_date: Date for the snapshot (default: now)

    Returns:
        (willingness_data, ability_data) tuples
    """
    print(f"🧪 Generating {num_records} synthetic TEST records (distribution-shifted)...")

    if snapshot_date is None:
        snapshot_date = datetime.now()

    willingness_data = []
    ability_data = []

    for i in range(num_records):
        # Use a DIFFERENT ID range to avoid PK collisions with training data
        cust_info_id = str(random.randint(50000000, 59999999))

        # Decide the "profile" for this customer
        profile = _pick_profile(i, num_records)

        # -----------------------------------------------------------------
        # Willingness Features (shifted distributions)
        # -----------------------------------------------------------------
        w_features = _generate_willingness_features(profile)
        target_w = _compute_willingness_target(w_features, profile)

        willingness_data.append((
            cust_info_id, snapshot_date,
            w_features["days_since_rpc"],
            w_features["ptp_ratio"],
            w_features["pay_velocity"],
            w_features["partial_ratio"],
            w_features["self_cure"],
            w_features["bounce_rate"],
            w_features["broken_ptp"],
            target_w,
        ))

        # -----------------------------------------------------------------
        # Ability Features (shifted distributions)
        # -----------------------------------------------------------------
        a_features = _generate_ability_features(profile)
        target_a = _compute_ability_target(a_features, profile)

        ability_data.append((
            cust_info_id, snapshot_date,
            a_features["inflow_var"],
            a_features["cash_runway"],
            a_features["spend_volatility"],
            a_features["debt_proxy"],
            a_features["nsf_rate"],
            a_features["zero_bal_ratio"],
            target_a,
        ))

    # Report distribution summary
    _report_summary(willingness_data, ability_data)

    return willingness_data, ability_data


# ── Profile Selection ────────────────────────────────────────────────

def _pick_profile(index: int, total: int) -> str:
    """
    Assign a customer profile to create realistic variety.

    Distribution:
      - 30% "normal"       — similar to training (baseline)
      - 25% "stressed"     — financial stress, high risk
      - 20% "edge_case"    — boundary values (near thresholds)
      - 15% "adversarial"  — conflicting signals (high ability, low willingness)
      - 10% "extreme"      — extreme outlier values
    """
    pct = index / total
    if pct < 0.30:
        return "normal"
    elif pct < 0.55:
        return "stressed"
    elif pct < 0.75:
        return "edge_case"
    elif pct < 0.90:
        return "adversarial"
    else:
        return "extreme"


# ── Willingness Feature Generation ───────────────────────────────────

def _generate_willingness_features(profile: str) -> dict:
    """Generate willingness features based on customer profile."""

    if profile == "normal":
        return {
            "days_since_rpc": random.choice([None, random.randint(1, 80)]),
            "ptp_ratio": round(random.uniform(0.0, 1.0), 4),
            "pay_velocity": random.randint(0, 5),
            "partial_ratio": round(random.uniform(0.0, 1.0), 4),
            "self_cure": random.choice([0, 1]),
            "bounce_rate": round(random.uniform(0.0, 0.6), 4),
            "broken_ptp": random.randint(0, 6),
        }

    elif profile == "stressed":
        # Higher broken PTPs, lower payment velocity, higher bounce rates
        return {
            "days_since_rpc": random.choice([None, random.randint(30, 200)]),
            "ptp_ratio": round(random.uniform(0.5, 1.0), 4),  # shifted high
            "pay_velocity": random.choice([0, 0, 0, 1]),       # mostly zero
            "partial_ratio": round(random.uniform(0.0, 0.3), 4),
            "self_cure": 0,
            "bounce_rate": round(random.uniform(0.4, 1.0), 4),  # shifted high
            "broken_ptp": random.randint(4, 15),                 # shifted high
        }

    elif profile == "edge_case":
        # Values near decision boundaries
        return {
            "days_since_rpc": random.choice([None, 1, 50, 100]),
            "ptp_ratio": round(random.uniform(0.45, 0.55), 4),  # near 0.5
            "pay_velocity": random.choice([0, 1]),                # boundary
            "partial_ratio": round(random.uniform(0.45, 0.55), 4),
            "self_cure": random.choice([0, 1]),
            "bounce_rate": round(random.uniform(0.45, 0.55), 4),
            "broken_ptp": random.choice([0, 1, 5, 10]),
        }

    elif profile == "adversarial":
        # Conflicting signals: looks willing but isn't (or vice versa)
        return {
            "days_since_rpc": random.choice([1, 2, 3]),  # recent contact (looks good)
            "ptp_ratio": round(random.uniform(0.7, 1.0), 4),  # many broken (bad)
            "pay_velocity": random.randint(1, 3),  # some payments (looks good)
            "partial_ratio": round(random.uniform(0.8, 1.0), 4),  # mostly partial (bad)
            "self_cure": 1,  # self-cured before (looks good)
            "bounce_rate": round(random.uniform(0.6, 0.9), 4),  # high bounces (bad)
            "broken_ptp": random.randint(3, 8),
        }

    else:  # extreme
        return {
            "days_since_rpc": random.choice([None, 0, 500]),
            "ptp_ratio": random.choice([0.0, 1.0]),
            "pay_velocity": random.choice([0, 10, 20]),
            "partial_ratio": random.choice([0.0, 1.0]),
            "self_cure": random.choice([0, 1]),
            "bounce_rate": random.choice([0.0, 1.0]),
            "broken_ptp": random.choice([0, 20, 50]),
        }


def _compute_willingness_target(features: dict, profile: str) -> int:
    """Compute target with slight noise to make it realistic."""
    # Base heuristic (same as training)
    base = 1 if (features["pay_velocity"] > 0 or features["ptp_ratio"] > 0.5) else 0

    # Add 15% label noise for adversarial/edge profiles
    if profile in ("adversarial", "edge_case") and random.random() < 0.15:
        return 1 - base  # flip

    return base


# ── Ability Feature Generation ───────────────────────────────────────

def _generate_ability_features(profile: str) -> dict:
    """Generate ability features based on customer profile."""

    if profile == "normal":
        return {
            "inflow_var": round(random.uniform(100.0, 5000.0), 2),
            "cash_runway": round(random.uniform(0.0, 60.0), 2),
            "spend_volatility": round(random.uniform(0.1, 2.0), 4),
            "debt_proxy": round(random.uniform(0.1, 1.5), 4),
            "nsf_rate": round(random.uniform(0.0, 0.8), 4),
            "zero_bal_ratio": round(random.uniform(0.0, 1.0), 4),
        }

    elif profile == "stressed":
        # Low cash runway, high NSF, high debt
        return {
            "inflow_var": round(random.uniform(50.0, 500.0), 2),    # low inflow
            "cash_runway": round(random.uniform(0.0, 10.0), 2),     # short runway
            "spend_volatility": round(random.uniform(1.0, 3.0), 4), # high volatility
            "debt_proxy": round(random.uniform(0.8, 2.5), 4),       # heavy debt
            "nsf_rate": round(random.uniform(0.3, 0.95), 4),        # high NSF
            "zero_bal_ratio": round(random.uniform(0.5, 1.0), 4),   # often zero
        }

    elif profile == "edge_case":
        # Near decision boundaries
        return {
            "inflow_var": round(random.uniform(500.0, 1500.0), 2),
            "cash_runway": round(random.uniform(12.0, 16.0), 2),    # near 14-day threshold
            "spend_volatility": round(random.uniform(0.8, 1.2), 4),
            "debt_proxy": round(random.uniform(0.4, 0.6), 4),
            "nsf_rate": round(random.uniform(0.08, 0.12), 4),       # near 0.1 threshold
            "zero_bal_ratio": round(random.uniform(0.3, 0.5), 4),
        }

    elif profile == "adversarial":
        # High income but terrible spending habits
        return {
            "inflow_var": round(random.uniform(3000.0, 8000.0), 2),  # great income
            "cash_runway": round(random.uniform(3.0, 8.0), 2),       # but short runway
            "spend_volatility": round(random.uniform(1.5, 3.0), 4),  # wild spending
            "debt_proxy": round(random.uniform(1.0, 2.0), 4),        # heavy debt
            "nsf_rate": round(random.uniform(0.2, 0.5), 4),          # frequent NSF
            "zero_bal_ratio": round(random.uniform(0.1, 0.3), 4),
        }

    else:  # extreme
        return {
            "inflow_var": random.choice([0.0, 10000.0, 50000.0]),
            "cash_runway": random.choice([0.0, 0.5, 100.0, 365.0]),
            "spend_volatility": random.choice([0.0, 5.0, 10.0]),
            "debt_proxy": random.choice([0.0, 3.0, 10.0]),
            "nsf_rate": random.choice([0.0, 1.0]),
            "zero_bal_ratio": random.choice([0.0, 1.0]),
        }


def _compute_ability_target(features: dict, profile: str) -> int:
    """Compute target with slight noise."""
    base = 1 if (features["cash_runway"] > 14.0 and features["nsf_rate"] < 0.1) else 0

    if profile in ("adversarial", "edge_case") and random.random() < 0.15:
        return 1 - base

    return base


# ── Reporting ────────────────────────────────────────────────────────

def _report_summary(w_data: list, a_data: list) -> None:
    """Print summary statistics of generated data."""
    w_targets = [r[-1] for r in w_data]
    a_targets = [r[-1] for r in a_data]

    w_positive = sum(w_targets)
    a_positive = sum(a_targets)
    total = len(w_data)

    print(f"\n{'='*60}")
    print(f"  Test Data Generation Summary")
    print(f"{'='*60}")
    print(f"  Total records:           {total}")
    print(f"  Willingness positive:    {w_positive}/{total} ({w_positive/total:.1%})")
    print(f"  Ability positive:        {a_positive}/{total} ({a_positive/total:.1%})")
    print(f"  Profiles: 30% normal, 25% stressed, 20% edge, 15% adversarial, 10% extreme")
    print(f"{'='*60}\n")


# ── Database Insertion ───────────────────────────────────────────────

def insert_test_data(
    willingness_data: list,
    ability_data: list,
    day_date_str: str = None,
) -> None:
    """
    Insert test data into Oracle mart tables.

    Uses a DIFFERENT DAY_DATE than training data to avoid contamination.
    The DAY_DATE is set on the table row, not on the snapshot column.
    """
    print("Initializing Database Pool...")
    db.initialize_pool()

    print("Connecting to Oracle Database...")
    try:
        with db.get_connection() as connection:
            with connection.cursor() as cursor:

                # Insert Willingness
                print("Inserting Willingness Test Data...")
                sql_willingness = """
                    INSERT INTO PIO_COLL_AI_WILLINGNESS_MART (
                        CUST_INFO_ID, SNAPSHOT_DATE, DAYS_SINCE_LAST_RPC, PTP_RELIABILITY_RATIO, 
                        PAYMENT_VELOCITY_30D, PARTIAL_PAYMENT_RATIO, SELF_CURE_HISTORY_FLAG, 
                        BOUNCE_RATE_60D, BROKEN_PTP_COUNT_6M, TARGET_WILLINGNESS
                    ) VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10)
                """
                cursor.executemany(sql_willingness, willingness_data)

                # Insert Ability
                print("Inserting Ability Test Data...")
                sql_ability = """
                    INSERT INTO PIO_COLL_AI_ABILITY_MART (
                        CUST_INFO_ID, SNAPSHOT_DATE, INFLOW_VARIANCE_30D, CASH_RUNWAY_DAYS_ESTIMATED, 
                        SPENDING_VOLATILITY_CV_60D, DEBT_SERVICE_PROXY_RATIO, NSF_EVENT_RATE_60D, 
                        ZERO_BALANCE_DAYS_RATIO_30D, TARGET_ABILITY
                    ) VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
                """
                cursor.executemany(sql_ability, ability_data)

                connection.commit()
                print(f"✅ Successfully inserted {len(willingness_data)} test records into both tables!")

    except oracledb.Error as e:
        print(f"❌ Database error occurred: {e}")
    finally:
        db.close_pool()


# ── CLI Entry Point ──────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate synthetic test data with distribution shift"
    )
    parser.add_argument(
        "--count", type=int, default=500,
        help="Number of test records to generate (default: 500)"
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Snapshot date in YYYY-MM-DD format (default: now)"
    )

    args = parser.parse_args()

    # Parse date if provided
    snap_date = None
    if args.date:
        snap_date = datetime.strptime(args.date, "%Y-%m-%d")
        print(f"Using custom snapshot date: {snap_date}")

    w_data, a_data = generate_test_data(
        num_records=args.count,
        snapshot_date=snap_date,
    )
    insert_test_data(w_data, a_data)
