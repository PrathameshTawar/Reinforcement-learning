from env.models import TaskConfig

MEDIUM_TASK_CONFIG = TaskConfig(
    task_id="aim_medium_001",
    num_emails=7,
    max_steps=30,
    seed=137,
    ambiguity_level=0.4,
    has_phishing=True,
    time_pressure=True,
)
