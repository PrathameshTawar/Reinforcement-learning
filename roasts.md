# 🔥 ROASTS.md — v2 (Post-Fix Edition)
### AIM-Env — OpenEnv RL Hackathon Submission Review
### Updated after surgical fixes. Previous verdict: auto-reject. Current verdict: below.

---

## What Was Fixed (Credit Where Due)

The 7 auto-reject issues from v1 are resolved:

| Issue | Status |
|---|---|
| `RouteOption` import crash | ✅ Fixed → `RouteAction` |
| `env.step()` returns 3 values | ✅ Fixed → returns 4-tuple |
| `TaskConfig` field mismatches (`time_budget`, float `time_pressure`) | ✅ Fixed |
| `task_id` missing from all task configs | ✅ Fixed |
| `env.py` wrong field names throughout | ✅ Fixed |
| `grader.py` inverted pipeline | ✅ Fixed |
| `inference.py` output format | ✅ Fixed — exact protocol format |
| `API_BASE_URL` / `MODEL_NAME` / `HF_TOKEN` missing | ✅ Fixed |
| `[END]` not guaranteed on crash | ✅ Fixed — `try/finally` |
| `logging` module corrupting output | ✅ Fixed — `print()` only |
| `env.step()` raises after done | ✅ Fixed — returns gracefully |
| `generate_emails()` wrong method name | ✅ Fixed → `generate()` |
| `EpisodeResult` wrong field names | ✅ Fixed |

The project now imports cleanly, runs all three tasks without crashing, and produces
valid protocol output. Verified output:

```
[START] task=aim_easy_001 env=aim-env model=gpt-4o-mini
[STEP] step=0 action=read_full:email_000 reward=-0.07 done=false error=null
[STEP] step=6 action=submit reward=-0.02 done=true error=null
[END] success=true steps=7 rewards=-0.07,-0.22,-0.07,0.08,-0.07,0.28,-0.02
```

That's the good news. Now the remaining problems.

---

## 1. Critical Failures (Remaining Auto-Reject Risks)

### ❌ REJECT RISK #1 — `HF_TOKEN` Missing Kills the Process Before `[START]`

```python
if not HF_TOKEN:
    print("FATAL: HF_TOKEN environment variable is not set.", file=sys.stderr)
    sys.exit(1)
```

`sys.exit(1)` before `[START]` is printed. The evaluator requires `[END]` always
prints even on crash. If `HF_TOKEN` is not injected into the sandbox before the
process starts — which is an environment configuration issue, not a code issue —
the evaluator sees no output at all. No `[START]`, no `[END]`. Marked as failed.

Fix: print `[START]` and `[END]` before exiting, or move the token check inside
`run_episode()` wrapped in the `try/finally`.

---

### ❌ REJECT RISK #2 — Heuristic Agent Doesn't Prioritize or Route

The heuristic in `inference.py` classifies every email but only sometimes prioritizes
and routes — it checks `pending_emails` for emails not yet classified, then not yet
prioritized, then not yet routed. But `pending_emails` is defined as emails not yet
in `classified | routed | marked_spam | escalated`. Once an email is classified, it
is still in `pending_emails` (classification alone doesn't remove it). So the loop
will re-enter the classify branch on the next call for the same email.

Wait — actually the heuristic checks `if email_id not in obs.classified` first, then
`if email_id not in obs.prioritized`, then `if email_id not in obs.routed`. This is
correct in logic. But `pending_emails` only removes an email when it's routed or
marked_spam or escalated — not when classified or prioritized. So the heuristic will
correctly walk through classify → prioritize → route for each email. This is fine.

The real problem: the heuristic never calls `ESCALATE` for urgent emails. It routes
everything to `ARCHIVE` or `DELETE`. Urgent emails that should be escalated get
archived. The grader penalizes this. Scores will be suboptimal but not zero.

---

### ⚠️ RISK #3 — `_make_full()` Returns Fake `EmailFull` Data

```python
def _make_full(self, partial: EmailPartial, gt) -> EmailFull:
    return EmailFull(
        ...
        body=partial.preview,      # body = first 120 chars only
        links=[],                  # all links stripped
        attachment_names=[],       # all attachments stripped
        reply_to=partial.sender_domain,  # reply_to = domain, not actual address
    )
```

The entire point of `READ_FULL` is to reveal phishing indicators: suspicious links,
`.exe` attachments, mismatched `reply_to` domains. The LLM agent calls `READ_FULL`
to get this data before deciding. It gets back truncated body, empty links, and a
fake reply_to. The LLM is making decisions on incomplete information and will miss
phishing emails that would be obvious from the full body.

This is an architectural gap — the `EmailGenerator` generates full template data
but `env.py` doesn't store it anywhere accessible after splitting into partial +
ground truth. The fix requires storing the full template body/links in the env
during `reset()`.

---

## 2. Output Format — Now Correct

All fields verified against spec:

| Field | Required | Actual | Status |
|---|---|---|---|
| `[START] task=` | ✅ | `task=aim_easy_001` | ✅ |
| `[START] env=` | ✅ | `env=aim-env` | ✅ |
| `[START] model=` | ✅ | `model=gpt-4o-mini` | ✅ |
| `[STEP] step=n` | ✅ | `step=0` | ✅ |
| `[STEP] action=` | ✅ | `action=read_full:email_000` | ✅ |
| `[STEP] reward=X.XX` | ✅ | `reward=-0.07` | ✅ |
| `[STEP] done=true\|false` | ✅ | `done=false` | ✅ |
| `[STEP] error=null` | ✅ | `error=null` | ✅ |
| `[END] success=` | ✅ | `success=true` | ✅ |
| `[END] steps=` | ✅ | `steps=7` | ✅ |
| `[END] rewards=` | ✅ | `rewards=-0.07,-0.22,...` | ✅ |
| No logging prefix | ✅ | `print()` only | ✅ |
| `try/finally` on `[END]` | ✅ | Present | ✅ |

One minor note: `action=read_full:email_000` uses `:` as separator between action
type and email_id. The spec says `action=<action_str>` without defining the format
of `action_str`. This is an interpretation call — if the evaluator expects just the
action type with no email_id appended, this could fail. Consider `action=read_full`
only, or check the spec for examples.

---

## 3. Architecture Weaknesses (Remaining)

**`_make_full()` is a stub that defeats the purpose of `READ_FULL`.**
Already covered above. The LLM gets fake data. Phishing detection via link inspection
is impossible. This is the single biggest remaining weakness in the RL loop.

**The heuristic agent is the de facto agent for the entire submission.**
The LLM path requires a working `API_BASE_URL` endpoint. In evaluation, if the
endpoint is slow or the model produces malformed JSON, the 3-retry logic falls back
to heuristic after 3 seconds of waiting. The heuristic is what actually runs most
of the time. The heuristic doesn't escalate, doesn't defer, and doesn't use
`MARK_SPAM` for non-phishing spam detection based on domain analysis. It's a
keyword matcher on subject lines. It will score around 0.3-0.5 on easy, lower on hard.

**The grader's efficiency score is inverted.**
```python
efficiency = max(0.0, 1.0 - (steps_used / max(1, max_steps)))
```
An agent that submits immediately (0 steps) gets `efficiency=1.0`. An agent that
uses all steps gets `efficiency=0.0`. This rewards doing nothing. The correct
formula should reward handling all emails efficiently, not just finishing fast.
The docs define efficiency as steps used relative to emails handled, not raw step count.

**The web stack (FastAPI + React + Docker) is still present and still broken.**
CORS locked to localhost. `TrustedHostMiddleware` blocks all HuggingFace domains.
Dockerfile copies from `frontend/` which doesn't exist. `docker-compose.yml`
references `./frontend/Dockerfile` which doesn't exist. None of this affects
`inference.py` scoring, but if the HuggingFace Space requirement means the web
demo must be running, the deployment will fail.

**`training/train.py` still uses the old broken `obs.opened` and `obs.time_left` fields.**
The new `Observation` model has `opened_emails` (dict) and `time_step` / `max_time_steps`.
`training/train.py` still accesses `obs.opened` and `obs.time_left` — both gone.
The training script crashes on the first `get_state_key(obs)` call. It was not updated.

---

## 4. Hackathon Strategy (Remaining Issues)

**The submission runs heuristic, not LLM, in practice.**
The LLM agent is the headline feature. But `READ_FULL` returns fake data, the
heuristic fallback triggers on any parse failure, and the heuristic doesn't use
the full action space. The submission will be evaluated as a keyword-matching
heuristic with an LLM wrapper that adds latency.

**No score improvement mechanism.**
The original had fake Q-learning. The new version has no learning at all — it's
purely zero-shot inference. That's actually fine for a hackathon, but the submission
should be honest about this. The `training/` folder still exists and implies there's
a trained policy. There isn't.

**Hard task will score poorly.**
With `ambiguity_level=0.8` and 4 phishing emails, the heuristic's keyword matching
on subject lines will miss most phishing (phishing subjects are designed to look
legitimate). The LLM with fake `READ_FULL` data won't do much better. Hard task
score will be below 0.3.

---

## 5. Performance & Infra (Remaining Issues)

**`matplotlib` and `seaborn` still in `backend/requirements.txt`.**
Still dead weight. Still inflating the Docker image. Still never called.

**`training/train.py` still broken** — accesses removed observation fields.
Not a scoring issue but wastes anyone who tries to run it.

**LLM retry loop adds up to 3 seconds of sleep per failed step.**
In a 45-step hard episode with a flaky endpoint, that's potentially 135 seconds
of sleep. The evaluator likely has a timeout. If the episode takes too long, it
gets killed mid-run. No `[END]` from the evaluator's perspective.

---

## 6. LLM Usage (Remaining Issues)

**`temperature=0` is correct. `max_tokens=150` may be too low.**
A full classify+prioritize+route JSON response with a long email_id is around
60-80 tokens. 150 is fine for single actions. But if the model adds any explanation
before the JSON (which smaller models do), the JSON gets cut off and `parse_action()`
returns `None`, triggering a retry. Consider 200.

**System prompt lists all 8 action types but the heuristic only uses 5.**
`DEFER`, `OPEN_EMAIL`, and `ESCALATE` are in the system prompt but the heuristic
never produces them. If the LLM decides to `DEFER` an email, the env handles it
correctly (it's a valid action), but the heuristic fallback will never defer.
Inconsistency between LLM and fallback behavior means the episode trajectory
changes unpredictably depending on which agent is running each step.

---

## 7. Code Quality (Remaining Issues)

**`env.py` imports `RewardCalculator` from `reward.py` but `reward.py` exports the class as `RewardCalculator`.**
This is fine. But `env.py` also imports `Reward` from `reward.py`:
```python
from .reward import Reward, RewardCalculator
```
`Reward` is defined in `models.py`, not `reward.py`. `reward.py` imports it from
`models.py`. This creates a transitive import that works but is confusing — `Reward`
should be imported from `.models` directly in `env.py`.

**`_make_full()` accepts `gt: Optional[EmailGroundTruth]` but never uses it.**
The ground truth has `is_phishing`, `correct_route`, and other fields that could
inform what "full" data to expose. It's passed in and ignored. The method signature
implies it will use ground truth to construct the full email. It doesn't.

**`grader.py` efficiency formula is wrong** (covered in section 3 but worth repeating
as a code quality issue — the formula is in the code, not just a design decision).

**`tasks/__init__.py` doesn't export `ALL_TASKS` or `TASK_MAP`.**
The docs and `training-loop.md` reference `from tasks import ALL_TASKS`. The
`__init__.py` only exports the three individual configs. Any code using `ALL_TASKS`
will get an `ImportError`. The training loop doc is now dead documentation.

---

## 8. Hidden Time Bombs (Remaining)

**`HF_TOKEN` check exits before `[START]` — covered in section 1.**

**`training/train.py` accesses `obs.opened` and `obs.time_left` — both removed.**
Anyone running `python training/train.py` gets `AttributeError` immediately.

**`env_service.py` in the backend still accesses `obs.opened`, `obs.time_left`, `email.id`, `email.sender`.**
The backend was not updated. If anyone runs the web demo, every `/run-demo` call
crashes with `AttributeError`. The demo page will show the error toast on every click.

**`inference.py` module-level code runs on import.**
```python
HF_TOKEN = os.environ.get("HF_TOKEN")
if not HF_TOKEN:
    sys.exit(1)
```
This runs when `import inference` is executed — not just when `__main__` runs.
Any test or script that imports `inference` without `HF_TOKEN` set will kill the
process. Including the test file `test_platform.py` if it ever imports inference.

---

## 9. What To Fix Next (Priority Order)

**#1 — Move `HF_TOKEN` check inside `run_episode()` with `try/finally`.**
The process must never exit before printing `[START]` and `[END]`.

**#2 — Fix `_make_full()` to store and return actual template data.**
In `reset()`, store the full template bodies/links alongside the partials.
`READ_FULL` is useless without real data. This is the biggest scoring gap.

**#3 — Fix `backend/app/services/env_service.py` field names.**
`obs.opened` → `obs.opened_emails`, `obs.time_left` → `obs.time_step`,
`email.id` → `email.email_id`, `email.sender` → `email.sender_name`.
The web demo is broken until this is fixed.

**#4 — Fix `training/train.py` observation field access.**
Same field name fixes as above. The training script is dead code until then.

**#5 — Add `ALL_TASKS` to `tasks/__init__.py`.**
```python
ALL_TASKS = [EASY_TASK_CONFIG, MEDIUM_TASK_CONFIG, HARD_TASK_CONFIG]
TASK_MAP = {c.task_id: c for c in ALL_TASKS}
```

---

## 10. Updated Verdict

**Would this pass validation?** Probably yes — with one condition.

If `HF_TOKEN` is correctly injected into the sandbox environment before the process
starts, the submission will run, produce valid protocol output, and complete all
three tasks without crashing. The format is correct. The env works. The output
is parseable.

If `HF_TOKEN` is missing or injected after import, `sys.exit(1)` fires before
`[START]` and the submission fails. Fix #1 above eliminates this risk entirely.

**Would this win?** No.

The heuristic scores ~0.3-0.5 on easy, lower on medium and hard. The LLM agent
gets fake `READ_FULL` data and can't detect phishing from links. The grader's
efficiency formula rewards doing nothing. The hard task will score below 0.3.
A well-tuned heuristic with correct escalation logic and real `READ_FULL` data
would outscore this submission without any LLM calls.

**One-line updated summary:**

> It runs now, the format is correct, and it won't crash — but the LLM is flying
> blind on fake email data, the heuristic doesn't escalate, and the efficiency
> formula rewards submitting immediately with zero emails handled.
