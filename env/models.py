"""
AIM-Env Models — Single source of truth for all types.
Matches SYSTEM_CONTRACT.md exactly.
"""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Dict, List, Optional
from enum import Enum


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    OPEN_EMAIL  = "open_email"
    READ_FULL   = "read_full"
    CLASSIFY    = "classify"
    PRIORITIZE  = "prioritize"
    ROUTE       = "route"
    DEFER       = "defer"
    MARK_SPAM   = "mark_spam"
    ESCALATE    = "escalate"
    SUBMIT      = "submit"


class EmailCategory(str, Enum):
    URGENT     = "urgent"
    NORMAL     = "normal"
    SPAM       = "spam"
    PHISHING   = "phishing"
    NEWSLETTER = "newsletter"
    INTERNAL   = "internal"
    EXTERNAL   = "external"


class PriorityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


class RouteAction(str, Enum):
    ARCHIVE = "archive"
    DELETE  = "delete"
    FORWARD = "forward"
    REPLY   = "reply"
    FLAG    = "flag"
    IGNORE  = "ignore"


# ---------------------------------------------------------------------------
# Shared Constants
# ---------------------------------------------------------------------------

ADJACENT_CATEGORIES: frozenset = frozenset({
    frozenset({"urgent",     "normal"}),
    frozenset({"spam",       "phishing"}),
    frozenset({"newsletter", "internal"}),
    frozenset({"internal",   "external"}),
})

PRIORITY_ORDER: Dict[str, int] = {
    "critical": 0,
    "high":     1,
    "medium":   2,
    "low":      3,
}

PHISHING_ENGAGE_ROUTES: frozenset = frozenset({"reply", "forward"})


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class Action(BaseModel):
    action_type:  ActionType
    email_id:     Optional[str]           = None
    category:     Optional[EmailCategory] = None
    priority:     Optional[PriorityLevel] = None
    route_action: Optional[RouteAction]   = None


class ActionResult(BaseModel):
    success: bool
    message: str
    reward:  float


class EmailPartial(BaseModel):
    email_id:       str
    sender_name:    str
    sender_domain:  str
    subject:        str
    preview:        str   # exactly first 120 chars of body
    has_attachment: bool
    timestamp:      str   # "YYYY-MM-DD HH:MM"


class EmailFull(EmailPartial):
    body:             str
    links:            List[str]
    attachment_names: List[str]
    reply_to:         str


class EmailGroundTruth(BaseModel):
    email_id:      str
    true_category: EmailCategory
    true_priority: PriorityLevel
    is_phishing:   bool
    deadline_step: Optional[int] = None
    correct_route: RouteAction


class Observation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=False)

    inbox:              List[EmailPartial]           = Field(default_factory=list)
    opened_emails:      Dict[str, EmailFull]         = Field(default_factory=dict)
    time_step:          int
    max_time_steps:     int
    pending_emails:     List[str]                    = Field(default_factory=list)
    last_action_result: Optional[ActionResult]       = None
    classified:         Dict[str, str]               = Field(default_factory=dict)
    prioritized:        Dict[str, str]               = Field(default_factory=dict)
    routed:             Dict[str, str]               = Field(default_factory=dict)
    deferred:           List[str]                    = Field(default_factory=list)
    escalated:          List[str]                    = Field(default_factory=list)
    marked_spam:        List[str]                    = Field(default_factory=list)
    alerts:             List[str]                    = Field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"=== INBOX TRIAGE — Step {self.time_step}/{self.max_time_steps} ===",
            f"Pending: {len(self.pending_emails)} emails | "
            f"Classified: {len(self.classified)} | Prioritized: {len(self.prioritized)} | "
            f"Routed: {len(self.routed)} | Spam: {len(self.marked_spam)} | "
            f"Escalated: {len(self.escalated)}",
        ]
        if self.alerts:
            lines.append("ALERTS: " + " | ".join(self.alerts))
        lines.append("\n--- INBOX ---")
        for e in self.inbox:
            status = "OPENED" if e.email_id in self.opened_emails else "UNREAD"
            lines.append(
                f"[{status}] {e.email_id} | From: {e.sender_name} <{e.sender_domain}> "
                f"| Subject: {e.subject} | Preview: {e.preview[:80]}"
            )
        if self.opened_emails:
            lines.append("\n--- FULL CONTENT ---")
            for eid, ef in self.opened_emails.items():
                lines.append(
                    f"[{eid}] Body: {ef.body} | Links: {ef.links} "
                    f"| Reply-To: {ef.reply_to}"
                )
        return "\n".join(lines)


class Reward(BaseModel):
    value:      float
    components: Dict[str, float]


class TaskConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id:         str
    seed:            int
    num_emails:      int
    max_steps:       int
    ambiguity_level: float
    has_phishing:    bool
    time_pressure:   bool

    @field_validator("ambiguity_level")
    @classmethod
    def check_ambiguity(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("ambiguity_level must be in [0.0, 1.0]")
        return v

    @field_validator("num_emails")
    @classmethod
    def check_num_emails(cls, v: int) -> int:
        if v < 1:
            raise ValueError("num_emails must be >= 1")
        return v

    @field_validator("max_steps")
    @classmethod
    def check_max_steps(cls, v: int) -> int:
        if v < 5:
            raise ValueError("max_steps must be >= 5")
        return v

    @field_validator("seed")
    @classmethod
    def check_seed(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("seed must be a positive integer")
        return v


class EpisodeResult(BaseModel):
    task_id:            str
    final_score:        float
    classification_acc: float
    priority_acc:       float
    routing_acc:        float
    risk_score:         float
    efficiency_score:   float
    steps_used:         int
    phishing_caught:    int
    phishing_engaged:   int
