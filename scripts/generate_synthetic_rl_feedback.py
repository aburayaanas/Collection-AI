"""
Synthetic RL Feedback Generator — Phase 3 Contextual Bandit.

Populates PIO_COLL_AI_RL_FEEDBACK with plausible agent-action/customer-
outcome records so the LinUCB bandit (src/engine/nba/reward_tracker.py)
has something to learn from before the DB team's real outcome-tracking
procedure exists. Writes to the exact same table the real procedure will
write to — nothing else changes once that exists
(docs/phase3_contextual_bandit_rl.md section 1).

Two sources of rows:
  1. Default: one feedback row per existing, non-excluded
     PIO_COLL_AI_NBA_ACTIONS row (grounded in real pipeline output).
  2. --topup (opt-in): tops up quadrant x channel cells below
     --min-samples using real customers from that quadrant, under new
     backdated DAY_DATEs (with a matching NBA_ACTIONS row so quadrant
     recovery keeps working, docs sec 5.3) — never invents new
     CUST_INFO_IDs, never touches the mart tables.

Outcome simulation is deliberately NOT a flat per-quadrant lookup table:
customer-level CONTACT_AVOIDANCE_INDEX (already in
PIO_COLL_AI_NBA_CONTEXT_MART) modulates gentle-channel effectiveness, so
two customers in the *same* quadrant can get different simulated outcomes
for the *same* channel — the personalization gap a quadrant-only bandit
can't capture but LinUCB can (docs sec 3). Reward mapping reuses
reward_tracker.map_outcome() so this generator and real ingestion can
never disagree about what an outcome is worth; treatment/decision-reason
strings reuse ContextualBandit's own builders for the same reason.

Usage:
    python -m scripts.generate_synthetic_rl_feedback
    python -m scripts.generate_synthetic_rl_feedback --dry-run
    python -m scripts.generate_synthetic_rl_feedback --topup --min-samples 30
"""

import argparse
import random
import sys
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.database.connection import db  # noqa: E402
from src.engine.nba.bandit import ContextualBandit  # noqa: E402
from src.engine.nba.reward_tracker import map_outcome  # noqa: E402

_bandit = ContextualBandit()  # heuristic-only instance, used only for _select_treatment/_build_decision_reason reuse

# ── Simulation constants ─────────────────────────────────────────────

OVERRIDE_PROBABILITY = 0.15
OVERRIDE_REASON_POOL = ["AGENT_JUDGMENT", "CUSTOMER_REQUEST", "RESOURCE_CONSTRAINT", "FORCE_MAJEURE"]

# One step down the aggressiveness hierarchy (bandit.CHANNEL_COST) — what
# an agent might substitute when they override the AI's recommendation.
_DOWNGRADE = {
    "Field Visit": "Outgoing Call",
    "Dunning Letter": "Email",
    "Outgoing Call": "SMS",
    "SMS": "Email",
    "Email": "SMS",
}

_AGGRESSIVE_CHANNELS = {"Outgoing Call", "Dunning Letter", "Field Visit"}
_ALL_CHANNELS = ["SMS", "Email", "Outgoing Call", "Dunning Letter", "Field Visit"]
_QUADRANTS = ("Q1", "Q2", "Q3", "Q4")

# Base P(outcome) x100 by quadrant, for a "gentle" channel (Email/SMS) contact.
_BASE_OUTCOME_WEIGHTS = {
    "Q1": {"PAID_IN_FULL": 40, "KEPT_PTP": 35, "RESTRUCTURE_AGREED": 10, "BROKEN_PTP": 5, "IGNORED": 10},
    "Q2": {"PAID_IN_FULL": 5, "KEPT_PTP": 30, "RESTRUCTURE_AGREED": 30, "BROKEN_PTP": 15, "IGNORED": 20},
    "Q3": {"PAID_IN_FULL": 5, "KEPT_PTP": 15, "RESTRUCTURE_AGREED": 5, "BROKEN_PTP": 20, "IGNORED": 55},
    "Q4": {"PAID_IN_FULL": 3, "KEPT_PTP": 12, "RESTRUCTURE_AGREED": 5, "BROKEN_PTP": 25, "IGNORED": 55},
}

# Additive shift moved from IGNORED into KEPT_PTP/PAID_IN_FULL when the
# channel used is "aggressive" — strongest where escalation matters most.
_AGGRESSIVE_SHIFT = {"Q1": 5, "Q2": 10, "Q3": 25, "Q4": 20}


def _outcome_weights(quadrant: str, channel: str, contact_avoidance_index: float) -> Dict[str, float]:
    """Per-customer outcome distribution — see module docstring for why
    this isn't a flat per-quadrant lookup table."""
    weights = dict(_BASE_OUTCOME_WEIGHTS[quadrant])

    if channel in _AGGRESSIVE_CHANNELS:
        shift = _AGGRESSIVE_SHIFT[quadrant]
        shift = min(shift, weights["IGNORED"] - 1)
        weights["IGNORED"] -= shift
        weights["KEPT_PTP"] += shift * 0.6
        weights["PAID_IN_FULL"] += shift * 0.4
    else:
        # Gentle channel: a high-avoidance customer is much less reachable
        # by Email/SMS specifically. Move mass from the positive buckets
        # into IGNORED, proportional to how much positive mass exists.
        positive_total = weights["KEPT_PTP"] + weights["PAID_IN_FULL"] + weights["RESTRUCTURE_AGREED"]
        moved = min(contact_avoidance_index * 30.0, positive_total * 0.9)
        if positive_total > 0:
            for key in ("KEPT_PTP", "PAID_IN_FULL", "RESTRUCTURE_AGREED"):
                weights[key] -= moved * (weights[key] / positive_total)
        weights["IGNORED"] += moved

    return {k: max(0.1, v) for k, v in weights.items()}


def _simulate_outcome(quadrant: str, channel: str, contact_avoidance_index: float) -> str:
    weights = _outcome_weights(quadrant, channel, contact_avoidance_index)
    return random.choices(list(weights.keys()), weights=list(weights.values()), k=1)[0]


def _simulate_override(recommended_channel: str) -> Tuple[int, Optional[str], str]:
    if random.random() < OVERRIDE_PROBABILITY:
        actual = _DOWNGRADE.get(recommended_channel, recommended_channel)
        return 1, random.choice(OVERRIDE_REASON_POOL), actual
    return 0, None, recommended_channel


# ── DB access ────────────────────────────────────────────────────────

def fetch_actionable_nba_rows() -> List[dict]:
    """All non-excluded NBA_ACTIONS rows, joined with CONTACT_AVOIDANCE_INDEX
    (current mart snapshot — same "current snapshot" convention as
    RewardTracker's own ingestion query, docs sec 5.4)."""
    sql = """
        SELECT
            a.DAY_DATE, a.INST_CODE, a.COUNTRY_CODE, a.CUST_INFO_ID,
            a.RECOMMENDED_CHANNEL,
            REGEXP_SUBSTR(a.DECISION_REASON, 'Q[0-9]') AS QUADRANT,
            NVL(ctx.CONTACT_AVOIDANCE_INDEX, 0.0) AS CONTACT_AVOIDANCE_INDEX
        FROM BI_DWH.PIO_COLL_AI_NBA_ACTIONS a
        LEFT JOIN (
            SELECT CUST_INFO_ID, CONTACT_AVOIDANCE_INDEX,
                   ROW_NUMBER() OVER (PARTITION BY CUST_INFO_ID ORDER BY DAY_DATE DESC) AS RN
            FROM BI_DWH.PIO_COLL_AI_NBA_CONTEXT_MART
        ) ctx ON ctx.CUST_INFO_ID = a.CUST_INFO_ID AND ctx.RN = 1
        WHERE a.RECOMMENDED_CHANNEL != 'None'
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchall()]
        cursor.close()
    return rows


_MERGE_FEEDBACK_SQL = """
    MERGE INTO BI_DWH.PIO_COLL_AI_RL_FEEDBACK t
    USING dual ON (
        t.DAY_DATE = TO_DATE(:DAY_DATE, 'YYYY-MM-DD') AND
        t.INST_CODE = :INST_CODE AND
        t.COUNTRY_CODE = :COUNTRY_CODE AND
        t.CUST_INFO_ID = :CUST_INFO_ID
    )
    WHEN MATCHED THEN
        UPDATE SET
            AI_RECOMMENDED_CHANNEL = :AI_RECOMMENDED_CHANNEL,
            AGENT_OVERRIDE_FLAG = :AGENT_OVERRIDE_FLAG,
            OVERRIDE_REASON_CODE = :OVERRIDE_REASON_CODE,
            ACTUAL_CHANNEL_USED = :ACTUAL_CHANNEL_USED,
            CUSTOMER_OUTCOME = :CUSTOMER_OUTCOME,
            BANDIT_REWARD_SCORE = :BANDIT_REWARD_SCORE
    WHEN NOT MATCHED THEN
        INSERT (
            DAY_DATE, INST_CODE, COUNTRY_CODE, CUST_INFO_ID,
            AI_RECOMMENDED_CHANNEL, AGENT_OVERRIDE_FLAG, OVERRIDE_REASON_CODE,
            ACTUAL_CHANNEL_USED, CUSTOMER_OUTCOME, BANDIT_REWARD_SCORE
        ) VALUES (
            TO_DATE(:DAY_DATE, 'YYYY-MM-DD'), :INST_CODE, :COUNTRY_CODE, :CUST_INFO_ID,
            :AI_RECOMMENDED_CHANNEL, :AGENT_OVERRIDE_FLAG, :OVERRIDE_REASON_CODE,
            :ACTUAL_CHANNEL_USED, :CUSTOMER_OUTCOME, :BANDIT_REWARD_SCORE
        )
"""

_MERGE_NBA_ACTION_SQL = """
    MERGE INTO BI_DWH.PIO_COLL_AI_NBA_ACTIONS t
    USING dual ON (
        t.DAY_DATE = TO_DATE(:DAY_DATE, 'YYYY-MM-DD') AND
        t.INST_CODE = :INST_CODE AND
        t.COUNTRY_CODE = :COUNTRY_CODE AND
        t.CUST_INFO_ID = :CUST_INFO_ID
    )
    WHEN NOT MATCHED THEN
        INSERT (
            DAY_DATE, INST_CODE, COUNTRY_CODE, CUST_INFO_ID,
            RECOMMENDED_CHANNEL, RECOMMENDED_OFFER, DECISION_REASON
        ) VALUES (
            TO_DATE(:DAY_DATE, 'YYYY-MM-DD'), :INST_CODE, :COUNTRY_CODE, :CUST_INFO_ID,
            :RECOMMENDED_CHANNEL, :RECOMMENDED_OFFER, :DECISION_REASON
        )
"""


def write_feedback(records: List[dict]) -> None:
    if not records:
        return
    with db.get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.executemany(_MERGE_FEEDBACK_SQL, records, batcherrors=True)
            errors = cursor.getbatcherrors()
            if errors:
                print(f"  {len(errors)} batch error(s) writing feedback; first: {errors[0].message}")
            conn.commit()
        finally:
            cursor.close()


def write_nba_action_stubs(records: List[dict]) -> None:
    if not records:
        return
    with db.get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.executemany(_MERGE_NBA_ACTION_SQL, records, batcherrors=True)
            errors = cursor.getbatcherrors()
            if errors:
                print(f"  {len(errors)} batch error(s) writing NBA action stubs; first: {errors[0].message}")
            conn.commit()
        finally:
            cursor.close()


# ── Record generation ────────────────────────────────────────────────

def generate_feedback_records(nba_rows: List[dict]) -> List[dict]:
    records = []
    for row in nba_rows:
        quadrant = row["QUADRANT"] or "Q4"
        recommended = row["RECOMMENDED_CHANNEL"]
        override_flag, override_reason, actual_channel = _simulate_override(recommended)
        outcome = _simulate_outcome(quadrant, actual_channel, float(row["CONTACT_AVOIDANCE_INDEX"] or 0.0))
        records.append({
            "DAY_DATE": row["DAY_DATE"].strftime("%Y-%m-%d"),
            "INST_CODE": row["INST_CODE"],
            "COUNTRY_CODE": row["COUNTRY_CODE"],
            "CUST_INFO_ID": row["CUST_INFO_ID"],
            "AI_RECOMMENDED_CHANNEL": recommended,
            "AGENT_OVERRIDE_FLAG": override_flag,
            "OVERRIDE_REASON_CODE": override_reason,
            "ACTUAL_CHANNEL_USED": actual_channel,
            "CUSTOMER_OUTCOME": outcome,
            "BANDIT_REWARD_SCORE": round(map_outcome(outcome), 2),
        })
    return records


def generate_topup_records(
    nba_rows: List[dict],
    existing_records: List[dict],
    min_samples: int,
) -> Tuple[List[dict], List[dict]]:
    """Tops up (quadrant, ACTUAL_CHANNEL_USED) cells below `min_samples`.

    Returns (feedback_records, nba_action_stub_records) — the latter must
    be written first (or in the same transaction) so quadrant recovery
    (docs sec 5.3) has something to join against.
    """
    # Count by (quadrant, actual_channel) — quadrant isn't on the feedback
    # record itself, so pair it back up via the source nba_rows list
    # (generate_feedback_records iterates nba_rows in the same order).
    counts: Counter = Counter()
    by_quadrant: Dict[str, List[dict]] = defaultdict(list)
    for src, rec in zip(nba_rows, existing_records):
        quadrant = src["QUADRANT"] or "Q4"
        counts[(quadrant, rec["ACTUAL_CHANNEL_USED"])] += 1
        by_quadrant[quadrant].append(src)

    feedback_topup: List[dict] = []
    nba_topup: List[dict] = []
    date_offset_by_customer: Dict[str, int] = defaultdict(int)

    for quadrant in _QUADRANTS:
        pool = by_quadrant.get(quadrant)
        if not pool:
            continue
        for channel in _ALL_CHANNELS:
            deficit = min_samples - counts.get((quadrant, channel), 0)
            if deficit <= 0:
                continue
            treatment = _bandit._select_treatment(quadrant)
            decision_reason = _bandit._build_decision_reason(quadrant, channel, treatment)
            for _ in range(deficit):
                source = random.choice(pool)
                date_offset_by_customer[source["CUST_INFO_ID"]] += 1
                backdated = source["DAY_DATE"] - timedelta(days=7 * date_offset_by_customer[source["CUST_INFO_ID"]])
                day_date_str = backdated.strftime("%Y-%m-%d")

                nba_topup.append({
                    "DAY_DATE": day_date_str,
                    "INST_CODE": source["INST_CODE"],
                    "COUNTRY_CODE": source["COUNTRY_CODE"],
                    "CUST_INFO_ID": source["CUST_INFO_ID"],
                    "RECOMMENDED_CHANNEL": channel,
                    "RECOMMENDED_OFFER": treatment,
                    "DECISION_REASON": decision_reason,
                })

                outcome = _simulate_outcome(quadrant, channel, float(source["CONTACT_AVOIDANCE_INDEX"] or 0.0))
                feedback_topup.append({
                    "DAY_DATE": day_date_str,
                    "INST_CODE": source["INST_CODE"],
                    "COUNTRY_CODE": source["COUNTRY_CODE"],
                    "CUST_INFO_ID": source["CUST_INFO_ID"],
                    "AI_RECOMMENDED_CHANNEL": channel,
                    "AGENT_OVERRIDE_FLAG": 0,
                    "OVERRIDE_REASON_CODE": None,
                    "ACTUAL_CHANNEL_USED": channel,
                    "CUSTOMER_OUTCOME": outcome,
                    "BANDIT_REWARD_SCORE": round(map_outcome(outcome), 2),
                })

    return feedback_topup, nba_topup


# ── Reporting ────────────────────────────────────────────────────────

def _print_summary(label: str, feedback_records: List[dict]) -> None:
    print(f"\n{label}: {len(feedback_records):,} record(s)")
    if not feedback_records:
        return
    outcome_counts = Counter(r["CUSTOMER_OUTCOME"] for r in feedback_records)
    channel_counts = Counter(r["ACTUAL_CHANNEL_USED"] for r in feedback_records)
    override_rate = sum(r["AGENT_OVERRIDE_FLAG"] for r in feedback_records) / len(feedback_records)
    print(f"  Outcomes: {dict(outcome_counts)}")
    print(f"  Actual channel used: {dict(channel_counts)}")
    print(f"  Override rate: {override_rate:.1%}")


# ── CLI entry point ──────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without touching the DB.")
    parser.add_argument("--topup", action="store_true", help="Also top up thin quadrant x channel cells (see module docstring).")
    parser.add_argument("--min-samples", type=int, default=30, help="Top-up floor per (quadrant, channel) cell (default: 30).")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible runs.")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print("Initializing Database Pool...")
    db.initialize_pool()
    try:
        print("Fetching actionable PIO_COLL_AI_NBA_ACTIONS rows...")
        nba_rows = fetch_actionable_nba_rows()
        print(f"  {len(nba_rows):,} actionable rows found (excluded/no-channel rows skipped).")

        records = generate_feedback_records(nba_rows)
        _print_summary("Default feedback (real NBA_ACTIONS rows)", records)

        nba_topup: List[dict] = []
        topup_records: List[dict] = []
        if args.topup:
            topup_records, nba_topup = generate_topup_records(nba_rows, records, args.min_samples)
            _print_summary(f"Top-up feedback (min_samples={args.min_samples})", topup_records)

        if args.dry_run:
            print("\n--dry-run: no changes written.")
            return

        print("\nWriting feedback...")
        write_feedback(records)
        if topup_records:
            print("Writing top-up NBA_ACTIONS stubs...")
            write_nba_action_stubs(nba_topup)
            print("Writing top-up feedback...")
            write_feedback(topup_records)

        total = len(records) + len(topup_records)
        print(f"\nDone. {total:,} PIO_COLL_AI_RL_FEEDBACK record(s) written/updated.")
    finally:
        db.close_pool()


if __name__ == "__main__":
    main()
