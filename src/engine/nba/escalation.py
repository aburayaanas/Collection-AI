import datetime
from datetime import timedelta
from typing import Optional, Union

from src.core.config import settings

# Account statuses under which a "future legal referral" framing would
# be actively wrong — the account is already there. Matches
# src/engine/nba/schemas.py's AccountStatus enum values exactly.
_ALREADY_LEGAL_TRACK_STATUSES = frozenset({"Legal", "Transfer To Remedial"})


class EscalationEngine:
    """Deterministic Phase Escalation state-machine timeline for collection officer UI."""

    @staticmethod
    def generate_timeline(
        days_past_due: int,
        current_quadrant: str,
        selected_nba: str,
        minimum_acceptable_cash: float,
        account_status: str = "Active",
        products_held: str = "",
        reference_date: Optional[Union[str, datetime.date, datetime.datetime]] = None,
    ) -> dict:
        """Generate a structured timeline of 4 phases.

        Args:
            days_past_due (int): Customer's DPD.
            current_quadrant (str): Customer's risk classification quadrant.
            selected_nba (str): Selected communication channel/action.
            minimum_acceptable_cash (float): The calculated minimum payment boundary.
            account_status (str): Current account lifecycle status
                (PIO_COLL_AI_NBA_CONTEXT_MART.ACCOUNT_STATUS). When this is
                already "Legal" or "Transfer To Remedial", Phases 2-3
                describe the account's *actual* state instead of a future
                trigger condition — see docs/backend_issues.md Issue 4:
                a customer already in legal handling must never be told
                they will be "referred to legal" as if that hasn't
                happened yet.
            products_held (str): Customer's held products
                (PIO_COLL_AI_NBA_CONTEXT_MART.PRODUCTS_HELD), checked
                against ``settings.ESCALATION_LEGAL_INELIGIBLE_PRODUCTS``
                to decide whether Phase 2 may offer a formal demand
                letter for this customer.
            reference_date (Optional[Union[str, date, datetime]]):
                The reference snapshot date to anchor phase windows to.
                Defaults to today's date if not provided.

        Returns:
            dict: Structured phase strings for display.
        """
        if reference_date is not None:
            if isinstance(reference_date, datetime.datetime):
                today = reference_date.date()
            elif isinstance(reference_date, datetime.date):
                today = reference_date
            else:
                try:
                    today = datetime.datetime.strptime(str(reference_date).split(" ")[0].split("T")[0], "%Y-%m-%d").date()
                except Exception:
                    today = datetime.date.today()
        else:
            today = datetime.date.today()

        phase1_days = settings.ESCALATION_PHASE1_DAYS
        phase2_end_day = settings.ESCALATION_PHASE2_END_DAY
        target_date = (today + timedelta(days=phase1_days)).strftime("%Y-%m-%d")

        nba_action = selected_nba.upper()
        min_cash_str = f"JOD {minimum_acceptable_cash:,.2f}"

        curr_status = str(account_status or "Active").strip()

        if curr_status in _ALREADY_LEGAL_TRACK_STATUSES:
            # The account is already under legal/remedial handling — the
            # standard NBA escalation clock (Phase 1-3) does not apply,
            # and presenting it would contradict the account's real state.
            phase_1 = (
                f"Not applicable. Account is already under {curr_status} handling — "
                f"the standard NBA escalation clock does not run for this account."
            )
            phase_2 = (
                f"Not applicable. Account is already under {curr_status} handling. "
                f"Refer to the legal/remedial case owner for current stage and next steps."
            )
            phase_3 = (
                f"Already active: account is under {curr_status} handling. "
                f"See the legal case management system for the current stage — "
                f"do not initiate a new legal referral."
            )
        else:
            phase_1 = f"Current. {nba_action}. Window: 0-{phase1_days} days from today ({target_date})."

            ineligible_products = [
                p.strip().lower()
                for p in settings.ESCALATION_LEGAL_INELIGIBLE_PRODUCTS.split(",")
                if p.strip()
            ]
            held_products_lower = str(products_held or "").lower()
            restricted_product = next(
                (p for p in ineligible_products if p in held_products_lower),
                None,
            )

            if restricted_product:
                phase_2 = (
                    f"Triggered if {nba_action} fails or minimum {min_cash_str} not received by {target_date}. "
                    f"Action: Legal pre-notification SMS only — formal demand letter is NOT applicable for this "
                    f"customer's product terms ('{restricted_product}'); escalate to manual product-compliance "
                    f"review instead. Window: days {phase1_days + 1}-{phase2_end_day}."
                )
            else:
                phase_2 = (
                    f"Triggered if {nba_action} fails or minimum {min_cash_str} not received by {target_date}. "
                    f"Action: Formal demand letter + legal pre-notification SMS. "
                    f"Window: days {phase1_days + 1}-{phase2_end_day}."
                )

            phase_3 = (
                f"Triggered if Phase 2 produces no payment by day {phase2_end_day}. "
                f"Action: Legal referral + credit bureau reporting. Reclassify to Stage 3 per IFRS 9."
            )

        # Determine appropriate recovery quadrant dynamically to avoid logic flaws
        # (e.g. never downgrade a low risk cooperative Q1 customer to Q3 Strategic Defaulter)
        curr_quad = str(current_quadrant).strip().upper()
        if curr_quad == "Q4":
            recovery_quadrant = "Q2 (cooperative monitoring)"
        elif curr_quad in ("Q3", "Q2"):
            recovery_quadrant = "Q1 (cooperative monitoring)"
        else:
            recovery_quadrant = "Q0 (fully recovered/normal monitoring)"

        exit_path = f"De-escalation path: If minimum floor received and restructuring signed, reclassify to {recovery_quadrant}. Rescore in 30 days."

        return {
            "phase_1_current": phase_1,
            "phase_2_trigger": phase_2,
            "phase_3_legal": phase_3,
            "exit_path": exit_path,
        }
