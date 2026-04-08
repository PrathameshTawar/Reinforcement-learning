"""
Email Environment package containing RL structures and evaluation utilities.
"""

from .env import AIMEnv
from .models import (
    Action, ActionType, Observation, TaskConfig, EmailPartial, EmailFull,
    EmailGroundTruth, EpisodeResult, EmailCategory, PriorityLevel, RouteAction
)
from .reward import Reward
from .email_generator import EmailGenerator
from .grader import Grader

__all__ = [
    "AIMEnv",
    "Action",
    "ActionType",
    "Observation",
    "TaskConfig",
    "EmailPartial",
    "EmailFull",
    "EmailGroundTruth",
    "EpisodeResult",
    "EmailCategory",
    "PriorityLevel",
    "RouteAction",
    "Reward",
    "EmailGenerator",
    "Grader",
]
