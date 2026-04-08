from env.models import TaskConfig

EASY_TASK_CONFIG = TaskConfig(
    task_id="aim_easy_001",
    num_emails=3,
    max_steps=20,
    seed=42,
    ambiguity_level=0.0,
    has_phishing=False,
    time_pressure=False,
)
