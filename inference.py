"""
inference.py — OpenEnv RL Hackathon submission entry point.
Outputs EXACT required protocol format to stdout.
"""
import os
import sys
import json
import time
import re

# ── Environment config ───────────────────────────────────────────────────────
API_BASE_URL = os.environ.get("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME   = os.environ.get("MODEL_NAME",   "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN     = os.environ.get("HF_TOKEN")

import openai
from env import AIMEnv
from env.models import Action, ActionType, EmailCategory, PriorityLevel, RouteAction
from tasks import EASY_TASK_CONFIG, MEDIUM_TASK_CONFIG, HARD_TASK_CONFIG

# ── OpenAI client ────────────────────────────────────────────────────────────
if not HF_TOKEN:
    # No token — will fallback to heuristic-only, LLM calls will be skipped
    client = None
else:
    client = openai.OpenAI(
        api_key=HF_TOKEN,
        base_url=API_BASE_URL,
    )

SYSTEM_PROMPT = """You are an email triage agent. Analyze the inbox and decide the next action.
You MUST respond with a single JSON object — no markdown, no explanation.

Valid action types and required fields:
  {"action_type": "open_email",  "email_id": "<id>"}
  {"action_type": "read_full",   "email_id": "<id>"}
  {"action_type": "classify",    "email_id": "<id>", "category": "<urgent|normal|spam|phishing|newsletter|internal|external>"}
  {"action_type": "prioritize",  "email_id": "<id>", "priority": "<critical|high|medium|low>"}
  {"action_type": "route",       "email_id": "<id>", "route_action": "<archive|delete|forward|reply|flag|ignore>"}
  {"action_type": "mark_spam",   "email_id": "<id>"}
  {"action_type": "escalate",    "email_id": "<id>"}
  {"action_type": "submit"}

Strategy:
1. read_full on suspicious emails before classifying
2. classify + prioritize + route every email
3. mark_spam or escalate when appropriate
4. submit when all emails are handled or steps are running low
"""


def format_prompt(obs) -> str:
    return obs.summary()


def parse_action(raw: str) -> Action | None:
    """Parse LLM JSON output into Action. Returns None on failure."""
    try:
        # Strip markdown fences if present
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        at = data.get("action_type", "")
        return Action(
            action_type=ActionType(at),
            email_id=data.get("email_id"),
            category=EmailCategory(data["category"]) if "category" in data else None,
            priority=PriorityLevel(data["priority"]) if "priority" in data else None,
            route_action=RouteAction(data["route_action"]) if "route_action" in data else None,
        )
    except Exception:
        return None


def llm_decide(obs) -> tuple[Action, str | None]:
    """Call LLM with up to 3 retries. Returns (action, error_or_None)."""
    if client is None:
        return heuristic_decide(obs), "no_client:heuristic_fallback"
    prompt = format_prompt(obs)
    last_err = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0,
                max_tokens=150,
            )
            raw = response.choices[0].message.content.strip()
            action = parse_action(raw)
            if action is not None:
                return action, None
            last_err = f"parse_failed:attempt_{attempt+1}"
        except Exception as e:
            last_err = str(e).replace("\n", " ")[:120]
            if attempt < 2:
                time.sleep(1.0)
    # Fallback to heuristic
    return heuristic_decide(obs), last_err


def heuristic_decide(obs) -> Action:
    """Keyword-based fallback. Never crashes."""
    # Prioritise pending emails
    for email_id in obs.pending_emails:
        # Not yet classified
        if email_id not in obs.classified:
            # Read full if not opened yet
            if email_id not in obs.opened_emails:
                return Action(action_type=ActionType.READ_FULL, email_id=email_id)
            # Classify based on subject keywords
            partial = next((e for e in obs.inbox if e.email_id == email_id), None)
            if partial:
                subj = partial.subject.lower()
                if any(k in subj for k in ("phish", "password", "verify", "suspended", "payroll")):
                    return Action(action_type=ActionType.MARK_SPAM, email_id=email_id)
                if any(k in subj for k in ("urgent", "critical", "down", "breach", "corruption")):
                    cat = EmailCategory.URGENT
                elif any(k in subj for k in ("newsletter", "weekly", "digest", "brew")):
                    cat = EmailCategory.NEWSLETTER
                elif any(k in subj for k in ("prize", "cheap", "free", "win", "bitcoin")):
                    cat = EmailCategory.SPAM
                else:
                    cat = EmailCategory.NORMAL
                return Action(action_type=ActionType.CLASSIFY, email_id=email_id, category=cat)
        # Classified but not prioritized
        if email_id not in obs.prioritized:
            return Action(action_type=ActionType.PRIORITIZE, email_id=email_id, priority=PriorityLevel.MEDIUM)
        # Classified + prioritized but not routed
        if email_id not in obs.routed:
            cat = obs.classified.get(email_id, "normal")
            route = RouteAction.DELETE if cat in ("spam", "phishing") else RouteAction.ARCHIVE
            return Action(action_type=ActionType.ROUTE, email_id=email_id, route_action=route)

    return Action(action_type=ActionType.SUBMIT)


def run_episode(config, use_llm: bool = True) -> bool:
    """
    Run one episode. Prints START / STEP / END to stdout.
    Returns True if episode completed successfully.
    """
    env = AIMEnv(config)
    rewards: list[float] = []
    step_n = 0
    success = False

    print(f"[START] task={config.task_id} env=aim-env model={MODEL_NAME}")
    sys.stdout.flush()

    try:
        obs = env.reset()
        done = False

        while not done:
            error_str = "null"
            try:
                if use_llm:
                    action, err = llm_decide(obs)
                    if err:
                        error_str = err
                else:
                    action = heuristic_decide(obs)
            except Exception as e:
                action = Action(action_type=ActionType.SUBMIT)
                error_str = str(e).replace("\n", " ")[:120]

            try:
                obs, reward, done, info = env.step(action)
                r_val = reward.value
            except Exception as e:
                r_val = -0.05
                done = True
                error_str = str(e).replace("\n", " ")[:120]

            rewards.append(r_val)
            action_str = action.action_type.value
            if action.email_id:
                action_str += f":{action.email_id}"

            print(
                f"[STEP] step={step_n} action={action_str} "
                f"reward={r_val:.2f} done={'true' if done else 'false'} "
                f"error={error_str}"
            )
            sys.stdout.flush()
            step_n += 1

        success = True

    except Exception as e:
        # Catch anything that slips through — END must still print
        print(
            f"[STEP] step={step_n} action=submit reward={-0.05:.2f} "
            f"done=true error={str(e).replace(chr(10), ' ')[:120]}"
        )
        sys.stdout.flush()

    finally:
        rewards_str = ",".join(f"{r:.2f}" for r in rewards) if rewards else "0.00"
        print(
            f"[END] success={'true' if success else 'false'} "
            f"steps={step_n} rewards={rewards_str}"
        )
        sys.stdout.flush()

    return success


if __name__ == "__main__":
    tasks = [EASY_TASK_CONFIG, MEDIUM_TASK_CONFIG, HARD_TASK_CONFIG]
    use_llm = True  # set False to run heuristic-only (no API calls)

    for task_cfg in tasks:
        run_episode(task_cfg, use_llm=use_llm)
