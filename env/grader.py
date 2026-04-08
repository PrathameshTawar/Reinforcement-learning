from typing import Dict, List
from .models import EpisodeResult, EmailGroundTruth, EmailCategory, RouteAction


class Grader:
    def grade_episode(
        self,
        classified: Dict[str, str],
        prioritized: Dict[str, str],
        routed: Dict[str, str],
        marked_spam: List[str],
        escalated: List[str],
        ground_truths: List[EmailGroundTruth],
        steps_used: int,
        max_steps: int,
        task_id: str,
    ) -> EpisodeResult:
        total = max(1, len(ground_truths))
        phishing_gts = [g for g in ground_truths if g.is_phishing]
        total_phishing = max(1, len(phishing_gts))

        # Classification accuracy
        cls_correct = sum(
            1 for g in ground_truths
            if classified.get(g.email_id) == g.true_category.value
            or (g.true_category in (EmailCategory.SPAM, EmailCategory.PHISHING)
                and g.email_id in marked_spam)
        )
        cls_acc = cls_correct / total

        # Priority accuracy
        pri_correct = sum(
            1 for g in ground_truths
            if prioritized.get(g.email_id) == g.true_priority.value
        )
        pri_acc = pri_correct / total

        # Routing accuracy
        rte_correct = sum(
            1 for g in ground_truths
            if routed.get(g.email_id) == g.correct_route.value
            or (g.correct_route == RouteAction.DELETE and g.email_id in marked_spam)
        )
        rte_acc = rte_correct / total

        # Phishing
        phishing_caught = sum(
            1 for g in phishing_gts
            if g.email_id in marked_spam
            or classified.get(g.email_id) == EmailCategory.PHISHING.value
        )
        phishing_engaged = sum(
            1 for g in phishing_gts
            if routed.get(g.email_id) in ("reply", "forward")
        )
        risk_score = max(-0.5, (phishing_caught - phishing_engaged * 2) / total_phishing)

        # Efficiency
        efficiency = max(0.0, 1.0 - (steps_used / max(1, max_steps)))

        final_score = max(0.0, min(1.0,
            0.30 * cls_acc
            + 0.20 * pri_acc
            + 0.20 * rte_acc
            + 0.20 * max(0.0, risk_score)
            + 0.10 * efficiency
        ))

        return EpisodeResult(
            task_id=task_id,
            final_score=round(final_score, 4),
            classification_acc=round(cls_acc, 4),
            priority_acc=round(pri_acc, 4),
            routing_acc=round(rte_acc, 4),
            risk_score=round(risk_score, 4),
            efficiency_score=round(efficiency, 4),
            steps_used=steps_used,
            phishing_caught=phishing_caught,
            phishing_engaged=phishing_engaged,
        )
