from typing import Optional, Dict, List, Tuple
from .models import (
    Action, ActionType, Observation, ActionResult, TaskConfig,
    EmailPartial, EmailFull, EmailGroundTruth, EpisodeResult,
    EmailCategory, PriorityLevel, RouteAction,
)
from .reward import Reward, RewardCalculator
from .email_generator import EmailGenerator


class AIMEnv:
    def __init__(self, config: TaskConfig):
        self.config = config
        self._reset_state()

    def _reset_state(self):
        self._inbox: List[EmailPartial] = []
        self._ground_truths: List[EmailGroundTruth] = []
        self._opened_emails: Dict[str, EmailFull] = {}   # email_id -> EmailFull
        self._opened_set: set = set()    # read_full called
        self._read_set: set = set()      # open_email called
        self._deadline_fired: set = set()
        self._classified: Dict[str, str] = {}
        self._prioritized: Dict[str, str] = {}
        self._routed: Dict[str, str] = {}
        self._marked_spam: List[str] = []
        self._escalated: List[str] = []
        self._deferred: List[str] = []
        self._alerts: List[str] = []
        self._action_history: List[dict] = []
        self._time_step: int = 0
        self._done: bool = False
        self._reset_called: bool = False

    def reset(self) -> Observation:
        self._reset_state()
        generator = EmailGenerator(self.config.seed)
        partials, ground_truths = generator.generate(
            num_emails=self.config.num_emails,
            ambiguity_level=self.config.ambiguity_level,
            has_phishing=self.config.has_phishing,
            time_pressure=self.config.time_pressure,
            max_steps=self.config.max_steps,
        )
        self._inbox = partials
        self._ground_truths = ground_truths
        self._reset_called = True
        return self._build_observation(None)

    def step(self, action: Action) -> Tuple[Observation, Reward, bool, dict]:
        if not self._reset_called:
            raise RuntimeError("reset() must be called before step()")

        # After done: return gracefully, no crash
        if self._done:
            obs = self._build_observation(None)
            return obs, Reward(value=-0.05, components={"invalid_action": -0.05}), True, {}

        calculator = RewardCalculator()
        gt = self._get_ground_truth(action.email_id) if action.action_type != ActionType.SUBMIT else None

        # Validate action
        if action.action_type != ActionType.SUBMIT:
            if action.email_id is None:
                return self._invalid(action, "email_id required")
            if not any(e.email_id == action.email_id for e in self._inbox):
                return self._invalid(action, f"email_id {action.email_id} not in inbox")
        if action.action_type == ActionType.CLASSIFY and action.category is None:
            return self._invalid(action, "category required for CLASSIFY")
        if action.action_type == ActionType.PRIORITIZE and action.priority is None:
            return self._invalid(action, "priority required for PRIORITIZE")
        if action.action_type == ActionType.ROUTE and action.route_action is None:
            return self._invalid(action, "route_action required for ROUTE")

        # Dispatch
        if action.action_type == ActionType.OPEN_EMAIL:
            self._read_set.add(action.email_id)
        elif action.action_type == ActionType.READ_FULL:
            self._opened_set.add(action.email_id)
            # Build EmailFull from template data via generator (stored in ground truth)
            # We expose the full email by finding the partial and enriching it
            partial = next(e for e in self._inbox if e.email_id == action.email_id)
            if action.email_id not in self._opened_emails:
                # EmailFull is built from the generator's template — we reconstruct it
                self._opened_emails[action.email_id] = self._make_full(partial, gt)
        elif action.action_type == ActionType.CLASSIFY:
            self._classified[action.email_id] = action.category.value
        elif action.action_type == ActionType.PRIORITIZE:
            self._prioritized[action.email_id] = action.priority.value
        elif action.action_type == ActionType.ROUTE:
            self._routed[action.email_id] = action.route_action.value
        elif action.action_type == ActionType.MARK_SPAM:
            if action.email_id not in self._marked_spam:
                self._marked_spam.append(action.email_id)
        elif action.action_type == ActionType.ESCALATE:
            if action.email_id not in self._escalated:
                self._escalated.append(action.email_id)
        elif action.action_type == ActionType.DEFER:
            if action.email_id not in self._deferred:
                self._deferred.append(action.email_id)

        reward = calculator.calculate(
            action=action,
            ground_truth=gt,
            already_opened=self._opened_set,
            already_read=self._read_set,
        )

        # Check deadlines
        deadline_rewards = self._check_deadlines()
        for dr in deadline_rewards:
            reward.value += dr.value
            reward.components.update(dr.components)

        self._action_history.append(action.model_dump())
        self._time_step += 1

        info: dict = {}

        if action.action_type == ActionType.SUBMIT:
            self._done = True
            episode_result = self._grade()
            info = {"episode_result": episode_result.model_dump()}
        elif self._time_step >= self.config.max_steps:
            self._done = True

        action_result = ActionResult(success=True, message="ok", reward=reward.value)
        obs = self._build_observation(action_result)
        return obs, reward, self._done, info

    # ── helpers ─────────────────────────────────────────────────────────────

    def _invalid(self, action: Action, msg: str) -> Tuple[Observation, Reward, bool, dict]:
        r = Reward(value=-0.05, components={"invalid_action": -0.05})
        ar = ActionResult(success=False, message=msg, reward=-0.05)
        return self._build_observation(ar), r, False, {}

    def _get_ground_truth(self, email_id: Optional[str]) -> Optional[EmailGroundTruth]:
        if email_id is None:
            return None
        return next((g for g in self._ground_truths if g.email_id == email_id), None)

    def _make_full(self, partial: EmailPartial, gt: Optional[EmailGroundTruth]) -> EmailFull:
        """Construct a minimal EmailFull from partial — body is preview for now."""
        return EmailFull(
            email_id=partial.email_id,
            sender_name=partial.sender_name,
            sender_domain=partial.sender_domain,
            subject=partial.subject,
            preview=partial.preview,
            has_attachment=partial.has_attachment,
            timestamp=partial.timestamp,
            body=partial.preview,
            links=[],
            attachment_names=[],
            reply_to=partial.sender_domain,
        )

    def _check_deadlines(self) -> List[Reward]:
        penalties = []
        handled = self._handled_set()
        for gt in self._ground_truths:
            if (gt.deadline_step is not None
                    and gt.email_id not in self._deadline_fired
                    and self._time_step == gt.deadline_step
                    and gt.email_id not in handled):
                self._deadline_fired.add(gt.email_id)
                penalties.append(Reward(value=-0.30, components={"urgency_late": -0.30}))
        return penalties

    def _handled_set(self) -> set:
        return (set(self._classified)
                | set(self._routed)
                | set(self._marked_spam)
                | set(self._escalated))

    def _build_observation(self, last_action_result: Optional[ActionResult]) -> Observation:
        handled = self._handled_set()
        pending = [e.email_id for e in self._inbox if e.email_id not in handled]
        return Observation(
            inbox=list(self._inbox),
            opened_emails=dict(self._opened_emails),
            time_step=self._time_step,
            max_time_steps=self.config.max_steps,
            pending_emails=pending,
            last_action_result=last_action_result,
            classified=dict(self._classified),
            prioritized=dict(self._prioritized),
            routed=dict(self._routed),
            deferred=list(self._deferred),
            escalated=list(self._escalated),
            marked_spam=list(self._marked_spam),
            alerts=list(self._alerts),
        )

    def _grade(self) -> EpisodeResult:
        from .grader import Grader
        return Grader().grade_episode(
            classified=self._classified,
            prioritized=self._prioritized,
            routed=self._routed,
            marked_spam=self._marked_spam,
            escalated=self._escalated,
            ground_truths=self._ground_truths,
            steps_used=self._time_step,
            max_steps=self.config.max_steps,
            task_id=self.config.task_id,
        )

    def state(self) -> dict:
        """For grader/tests only — never call from inference.py."""
        return {
            "ground_truths": [g.model_dump() for g in self._ground_truths],
            "action_history": self._action_history,
            "time_step": self._time_step,
        }
