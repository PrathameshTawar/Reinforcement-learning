# Deployment Guide — AIM-Env (Hugging Face Spaces)

---

## 1. Overview

- **What**: AIM-Env is a POMDP email triage RL environment with an LLM agent (`inference.py`) and an optional React + FastAPI demo stack
- **Deployment target**: Hugging Face Spaces — Docker SDK
- **Architecture**: Two independent deployment surfaces:
  - `inference.py` — hackathon evaluation entry point, runs as a standalone Python process, no server required
  - FastAPI backend + React frontend — demo UI, deployed as a Docker Space serving both on a single container via nginx reverse proxy

> The evaluator only runs `python inference.py`. The web stack is optional and purely for demo purposes.

---

## 2. Prerequisites

- Hugging Face account with write access to a Space
- `git` + `git-lfs` installed locally
- Python 3.11+, `pip`, `node 18+`, `npm`
- HF CLI: `pip install huggingface_hub`
- Active HF token with `write` scope: [hf.co/settings/tokens](https://huggingface.co/settings/tokens)
- HF router credits for LLM inference: [hf.co/settings/billing](https://huggingface.co/settings/billing)

---

## 3. Repository Structure

```
Reinforcement-learning/
│
├── inference.py              ← HACKATHON ENTRY POINT — evaluator runs this
│
├── env/                      ← POMDP environment package
│   ├── __init__.py
│   ├── models.py             ← all Pydantic types (source of truth)
│   ├── env.py                ← AIMEnv — reset/step/grade
│   ├── email_generator.py    ← seeded deterministic email generation
│   ├── reward.py             ← RewardCalculator
│   └── grader.py             ← Grader — grades episode on SUBMIT
│
├── tasks/
│   ├── __init__.py
│   ├── task_easy.py          ← aim_easy_001  (3 emails, 20 steps)
│   ├── task_medium.py        ← aim_medium_001 (7 emails, 30 steps)
│   └── task_hard.py          ← aim_hard_001  (12 emails, 45 steps)
│
├── backend/
│   ├── Dockerfile            ← backend container (Python 3.11-slim)
│   ├── requirements.txt
│   └── app/
│       ├── main.py           ← FastAPI app (⚠ CORS/TrustedHost need fixing for HF)
│       ├── api/routes.py
│       ├── services/
│       └── core/config.py
│
├── src/                      ← React frontend (Vite + Tailwind)
│   ├── App.jsx
│   ├── pages/
│   └── services/api.js       ← ⚠ baseURL hardcoded to '/api' — needs nginx proxy
│
├── Dockerfile                ← ⚠ BROKEN — references frontend/ dir that doesn't exist
│                               See Section 7 for the fixed version
├── docker-compose.yml        ← local dev only
├── package.json
├── vite.config.js
└── training/
    └── train.py
```

---

## 4. Environment Configuration

### Required secrets — set in HF Space Settings → Variables and Secrets

| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `HF_TOKEN` | Secret | **YES** | none | HF token used as `api_key` for LLM inference |
| `API_BASE_URL` | Variable | no | `https://router.huggingface.co/v1` | LLM inference endpoint |
| `MODEL_NAME` | Variable | no | `Qwen/Qwen2.5-72B-Instruct` | Model served via HF router |
| `OPENAI_API_KEY` | Secret | no | `""` | Only needed if routing to OpenAI instead of HF |

### Setting secrets via HF CLI
```bash
huggingface-cli secret set HF_TOKEN --space <your-username>/<space-name>
```

### Setting via Space UI
Space → Settings → Variables and Secrets → New Secret

### ⚠ Critical: `main.py` CORS + TrustedHost must be updated before deploying
```python
# Replace hardcoded localhost origins with your Space URL
allow_origins=["https://<username>-<space-name>.hf.space"]
allowed_hosts=["<username>-<space-name>.hf.space", "localhost"]
```

---

## 5. Dependencies

### `backend/requirements.txt` — current state + issues

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0      # ← not used (Settings inherits BaseModel, not BaseSettings)
python-multipart==0.0.6
openai==1.3.0                 # ← minimum 1.52+ recommended for router compatibility
numpy==1.24.3                 # ← conflicts with pydantic v2 on some platforms; use 1.26.4
matplotlib==3.8.0             # ← dead weight, never called — remove
seaborn==0.13.0               # ← dead weight, never called — remove
```

### Recommended clean `requirements.txt` for the Space
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
python-multipart==0.0.6
openai>=1.52.0
numpy==1.26.4
```

### `inference.py` has no `requirements.txt` of its own
The evaluator needs `pydantic` and `openai` available. If running outside Docker,
create a root-level `requirements.txt`:
```
pydantic>=2.5.0
openai>=1.52.0
```

---

## 6. Deployment Steps

### Option A — Inference-only Space (hackathon submission)

```bash
# 1. Create Space
huggingface-cli repo create <space-name> --type space --space-sdk docker

# 2. Clone
git clone https://huggingface.co/spaces/<username>/<space-name>
cd <space-name>

# 3. Copy only what the evaluator needs
cp -r /path/to/project/env .
cp -r /path/to/project/tasks .
cp /path/to/project/inference.py .

# 4. Create root requirements.txt
echo "pydantic>=2.5.0\nopenai>=1.52.0" > requirements.txt

# 5. Create Dockerfile (see Section 7 — Option A)

# 6. Set secret
huggingface-cli secret set HF_TOKEN --space <username>/<space-name>

# 7. Push
git add . && git commit -m "deploy inference" && git push
```

### Option B — Full stack Space (demo UI + backend)

```bash
# 1–2. Same as above

# 3. Copy full project
cp -r /path/to/project/* .

# 4. Fix CORS and TrustedHost in backend/app/main.py (see Section 4)

# 5. Use the fixed Dockerfile (see Section 7 — Option B)

# 6. Set secrets
huggingface-cli secret set HF_TOKEN --space <username>/<space-name>

# 7. Push
git add . && git commit -m "deploy full stack" && git push
```

### Verify build
- Space → Logs tab → watch for `Application startup complete`
- Hit `https://<username>-<space-name>.hf.space/health` → `{"status": "healthy"}`

---

## 7. Docker Setup

### Option A — Inference-only (minimal, hackathon-safe)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY env/ ./env/
COPY tasks/ ./tasks/
COPY inference.py .

# Non-root user (HF requirement)
RUN useradd -m -u 1000 user
USER user

# HF Spaces expects port 7860
EXPOSE 7860

CMD ["python", "inference.py"]
```

> HF Spaces Docker SDK **requires port 7860**. The evaluator connects to this port.

---

### Option B — Full stack (nginx + FastAPI + React)

```dockerfile
FROM node:18-alpine AS frontend-build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY src/ ./src/
COPY index.html vite.config.js postcss.config.js tailwind.config.js ./
RUN npm run build
# Output: /app/dist

FROM python:3.11-slim AS final
WORKDIR /app

RUN apt-get update && apt-get install -y nginx && rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir fastapi==0.104.1 uvicorn[standard]==0.24.0 \
    pydantic==2.5.0 python-multipart==0.0.6 "openai>=1.52.0" numpy==1.26.4

# App code
COPY backend/app ./app
COPY env ./env
COPY tasks ./tasks
COPY inference.py .

# React build output
COPY --from=frontend-build /app/dist /usr/share/nginx/html

# nginx config — proxy /api to uvicorn on 8000, serve React on 7860
COPY nginx.conf /etc/nginx/nginx.conf

RUN useradd -m -u 1000 user && chown -R user:user /app /usr/share/nginx/html
USER user

EXPOSE 7860

# Start both nginx and uvicorn
CMD nginx && uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### `nginx.conf` (required for Option B)

```nginx
events {}
http {
    include /etc/nginx/mime.types;
    server {
        listen 7860;

        location /api/ {
            proxy_pass http://127.0.0.1:8000/api/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location / {
            root /usr/share/nginx/html;
            try_files $uri $uri/ /index.html;
        }
    }
}
```

---

## 8. Performance Optimization

- **No model weights to load** — LLM inference is remote (HF router). Cold start is Python import time only (~2–3s)
- **Pydantic model compilation** — first `AIMEnv` instantiation triggers Pydantic schema compilation. Pre-warm by importing at module level (already done)
- **Remove matplotlib/seaborn** from requirements — saves ~150MB image size and ~8s build time
- **Use `python:3.11-slim` not `python:3.11`** — saves ~800MB image size
- **`npm ci` not `npm install`** — deterministic, faster in CI/Docker
- **Multi-stage build** (Option B) — keeps final image lean by discarding node_modules
- **`--no-cache-dir` on pip** — reduces layer size
- **`sys.stdout.flush()` after every print** — already implemented, critical for streaming log parsers

---

## 9. Scaling & Limitations

### HF Spaces free tier constraints
| Resource | Limit | Impact |
|---|---|---|
| CPU | 2 vCPU | inference.py is single-threaded, fine |
| RAM | 16 GB (free), 8 GB (basic) | env + pydantic + openai client ~200MB, fine |
| Sleep mode | After 48h inactivity | Demo Space will sleep; inference.py is run-once |
| Persistent storage | None (ephemeral) | No state survives restart — fine for this project |
| Egress | Unlimited | LLM calls to router.huggingface.co are internal |

### HF router credit limits
- Free tier: limited monthly credits — exhausted mid-run in testing
- LLM fallback to heuristic agent is already implemented — Space won't crash on 402
- For sustained LLM usage: add pre-paid credits or use a smaller model (`Qwen/Qwen2.5-7B-Instruct`)

### Workarounds
- Run `inference.py` with `use_llm=False` for zero-cost heuristic baseline
- Set `MODEL_NAME=Qwen/Qwen2.5-7B-Instruct` for ~10x cheaper inference with acceptable quality
- For the demo Space: disable sleep via Space Settings → "Keep Space awake" (paid feature)

---

## 10. Monitoring & Debugging

### Logs
- Space → Logs tab — real-time stdout/stderr
- `inference.py` uses `print()` + `sys.stdout.flush()` — all output visible immediately
- FastAPI access logs via uvicorn appear automatically

### Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `410 - api-inference.huggingface.co is no longer supported` | Old endpoint | Set `API_BASE_URL=https://router.huggingface.co/v1` |
| `402 - depleted monthly credits` | HF free tier exhausted | Add credits or switch to smaller model |
| `ImportError: cannot import name 'RouteOption'` | Old `env/__init__.py` | Already fixed — ensure latest code is pushed |
| `ModuleNotFoundError: pydantic` | Missing requirements | Add `pydantic>=2.5.0` to root `requirements.txt` |
| `[END]` not printed | Crash before `try/finally` | Already fixed — `[END]` is in `finally` block |
| Space stuck on "Building" | Dockerfile COPY path wrong | Verify all `COPY` source paths exist in repo root |
| CORS blocked on demo | `allow_origins` hardcoded to localhost | Update `main.py` with Space URL (see Section 4) |
| `TrustedHostMiddleware` 400 | `allowed_hosts` hardcoded | Add Space hostname to `allowed_hosts` |
| `parse_failed:attempt_3` in STEP error | LLM returned non-JSON | Increase `max_tokens=200`, check model supports JSON mode |

### Health check
```bash
curl https://<username>-<space-name>.hf.space/health
# Expected: {"status": "healthy"}
```

---

## 11. CI/CD

### GitHub → HF Spaces auto-sync

```yaml
# .github/workflows/deploy.yml
name: Deploy to HF Spaces

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          lfs: true

      - name: Push to HF Space
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          git config user.email "ci@github.com"
          git config user.name "CI"
          git remote add hf https://user:$HF_TOKEN@huggingface.co/spaces/<username>/<space-name>
          git push hf main --force
```

### Best practices
- Store `HF_TOKEN` in GitHub Secrets, never in code
- Use branch protection on `main` — only merge after local `python inference.py` passes
- Tag releases: `git tag v1.0.0 && git push hf v1.0.0:main`
- Keep `inference.py` + `env/` + `tasks/` changes in separate commits from frontend changes — easier rollback

---

## 12. Security Considerations

- `HF_TOKEN` must be set as a **Secret** (not a Variable) in Space settings — Secrets are not exposed in logs or to the frontend
- Never commit `HF_TOKEN` to git — add `.env` to `.gitignore`
- `inference.py` reads token at import time — if token is missing, `client=None` and falls back to heuristic (no crash, no leak)
- FastAPI backend: `TrustedHostMiddleware` and CORS must be updated from `localhost` to the actual Space domain before deploying (see Section 4) — current config blocks all external requests
- The `env.state()` method exposes ground truth — it is never called from `inference.py` (enforced by design), but ensure no route in `routes.py` calls it either
- Rate limiter in `main.py` is currently dead code (function defined but never registered) — register it or remove it:
  ```python
  # To register properly:
  @app.middleware("http")
  async def rate_limit(request: Request, call_next):
      ...
  ```

---

## 13. Future Improvements

| Improvement | Why | How |
|---|---|---|
| Fix `_make_full()` to return real email body/links | LLM currently gets truncated fake data — phishing detection is blind | Store full template data in `env.py` during `reset()` |
| Add JSON mode to LLM calls | Eliminates `parse_failed` errors entirely | `response_format={"type": "json_object"}` (model-dependent) |
| Switch `Settings` to `pydantic_settings.BaseSettings` | Current `BaseModel` doesn't read env vars at runtime | `from pydantic_settings import BaseSettings` |
| Move to AWS ECS / GCP Cloud Run | HF Spaces has no persistent storage, no custom domains, sleeps | Containerize with same Dockerfile, add ALB + Route53 |
| Add Redis for session state | FastAPI is stateless — no episode state between requests | Redis for `env` instance caching per session |
| Structured logging (JSON) | Current `print()` is unstructured — hard to query in production | `structlog` or `python-json-logger` |
| Prometheus metrics endpoint | No observability on episode scores, latency, error rates | `prometheus-fastapi-instrumentator` |
| Smaller default model | `Qwen2.5-72B` is expensive — `7B` is 10x cheaper with ~85% quality | `MODEL_NAME=Qwen/Qwen2.5-7B-Instruct` as default |
