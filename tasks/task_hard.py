from env.models import TaskConfig

HARD_TASK_CONFIG = TaskConfig(
    task_id="aim_hard_001",
    num_emails=12,
    max_steps=45,
    seed=999,
    ambiguity_level=0.8,
    has_phishing=True,
    time_pressure=True,
)
