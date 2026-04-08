"""
RewardCalculator — Computes per-step reward signals.
No randomness. No global state. Pure function of action + ground truth.
"""
from typing import Optional
from .models import (
    Action, ActionType, EmailGroundTruth, EmailCategory, Reward,
    ADJACENT_CATEGORIES, PRIORITY_ORDER, PHISHING_ENGAGE_ROUTES,
)


class RewardCalculator:

    def calculate(
        self,
        action: Action,
        ground_truth: Optional[EmailGroundTruth],
        already_opened: set,   # email_ids where read_full was called
        already_read: set,     # email_ids where open_email was called
    ) -> Reward:
        components: dict = {"step_cost": -0.02}

        t = action.action_type

        if t == ActionType.OPEN_EMAIL:
            components.update(self._score_open_email(action, already_read))
        elif t == ActionType.READ_FULL:
            components.update(self._score_read_full(action, already_opened))
        elif t == ActionType.CLASSIFY:
            components.update(self._score_classify(action, ground_truth))
        elif t == ActionType.PRIORITIZE:
            components.update(self._score_prioritize(action, ground_truth))
        elif t == ActionType.ROUTE:
            components.update(self._score_route(action, ground_truth))
        elif t == ActionType.MARK_SPAM:
            components.update(self._score_mark_spam(ground_truth))
        elif t == ActionType.ESCALATE:
            components.update(self._score_escalate(ground_truth))
        elif t == ActionType.DEFER:
            components.update(self._score_defer(ground_truth))
        # SUBMIT: only step_cost applies here; bonus/penalty handled in _handle_submit

        return Reward(value=sum(components.values()), components=components)

    # ── Action-specific scorers ──────────────────────────────────────────────

    def _score_open_email(self, action: Action, already_read: set) -> dict:
        if action.email_id in already_read:
            return {"redundant_action": -0.05}
        return {}

    def _score_read_full(self, action: Action, already_opened: set) -> dict:
        if action.email_id in already_opened:
            return {"redundant_action": -0.05}
        return {}

    def _score_classify(self, action: Action, gt: EmailGroundTruth) -> dict:
        components = {}
        agent_cat  = action.category.value
        true_cat   = gt.true_category.value

        if agent_cat == true_cat:
            components["classification"] = +0.30
        elif frozenset({agent_cat, true_cat}) in ADJACENT_CATEGORIES:
            components["classification"] = +0.10
        else:
            components["classification"] = -0.20

        # Phishing missed penalty stacks on top
        if gt.is_phishing and action.category not in (
            EmailCategory.PHISHING, EmailCategory.SPAM
        ):
            components["phishing_missed"] = -0.50

        return components

    def _score_prioritize(self, action: Action, gt: EmailGroundTruth) -> dict:
        diff = abs(
            PRIORITY_ORDER[action.priority.value] -
            PRIORITY_ORDER[gt.true_priority.value]
        )
        if diff == 0:
            return {"priority": +0.20}
        if diff == 1:
            return {"priority": +0.05}
        return {"priority": -0.10}

    def _score_route(self, action: Action, gt: EmailGroundTruth) -> dict:
        if gt.is_phishing and action.route_action.value in PHISHING_ENGAGE_ROUTES:
            return {"phishing_engaged": -1.00}
        if action.route_action.value == gt.correct_route.value:
            return {"routing": +0.20}
        return {"routing": -0.10}

    def _score_mark_spam(self, gt: EmailGroundTruth) -> dict:
        if gt.is_phishing or gt.true_category == EmailCategory.SPAM:
            return {"phishing_caught": +0.50}
        return {"routing": -0.10}

    def _score_escalate(self, gt: EmailGroundTruth) -> dict:
        if gt.true_category == EmailCategory.URGENT:
            return {"phishing_caught": +0.50}
        return {"routing": -0.10}

    def _score_defer(self, gt: EmailGroundTruth) -> dict:
        if gt.deadline_step is not None:
            return {"urgency_late": -0.10}
        return {}
