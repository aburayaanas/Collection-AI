import datetime
from datetime import timedelta

class EscalationEngine:
    """Deterministic Phase Escalation state-machine timeline for collection officer UI."""

    @staticmethod
    def generate_timeline(
        days_past_due: int,
        current_quadrant: str,
        selected_nba: str,
        minimum_acceptable_cash: float
    ) -> dict:
        """Generate a structured timeline of 4 phases.

        Args:
            days_past_due (int): Customer's DPD.
            current_quadrant (str): Customer's risk classification quadrant.
            selected_nba (str): Selected communication channel/action.
            minimum_acceptable_cash (float): The calculated minimum payment boundary.

        Returns:
            dict: Structured phase strings for display.
        """
        today = datetime.date.today()
        target_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")

        nba_action = selected_nba.upper()
        min_cash_str = f"JOD {minimum_acceptable_cash:,.2f}"

        phase_1 = f"Current. {nba_action}. Window: 0-7 days from today ({target_date})."
        phase_2 = f"Triggered if {nba_action} fails or minimum {min_cash_str} not received by {target_date}. Action: Formal demand letter + legal pre-notification SMS. Window: days 8-21."
        phase_3 = "Triggered if Phase 2 produces no payment by day 21. Action: Legal referral + credit bureau reporting. Reclassify to Stage 3 per IFRS 9."
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
