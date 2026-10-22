# FirstIn

Internship scout for students: reads company job boards at the source, skips ghost jobs, ranks internships against your CV with cited reasons, learns from your feedback, finds events where you can meet the people hiring. You send every application yourself.

Full plan: [PLAN.md](PLAN.md).

## Run locally

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in keys; keep ENABLE_SCHEDULER=false on laptops
uvicorn backend.app.main:app --reload --port 8080
# open http://localhost:8080/docs
```

Apply the database schema (Leo, once, after DATABASE_URL is set):

```bash
python -m backend.app.db
```

## Who owns what

| Folder / file | Owner | Branch |
| --- | --- | --- |
| `backend/agent/`, `backend/app/schemas.py`, `backend/app/llm.py` | Alvaro | `feat/agent` |
| `backend/watcher/`, `backend/app/db.py`, `db/` | Leo | `feat/watcher` |
| `backend/events/`, `backend/eval/` | Taleb | `feat/events` |
| `backend/app/main.py`, `config.py`, `Dockerfile`, `web/` (Lovable) | Marc | `feat/web-deploy` |
| `backend/app/search.py` (Keenable), `fixtures.py` | shared, announce changes | |

Rules: edit only your folder; every route stays at its path and response model (see `schemas.py`); merges at 14:00 and 14:45.

## Deploy (Aiven Runtime)

GitHub repo, branch `main`, Dockerfile at `./Dockerfile`, port 8080 HTTP. Postgres integration exposes `DATABASE_URL`. Secrets: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `KEENABLE_API_KEY`, `N8N_WEBHOOK_URL`, and `ENABLE_SCHEDULER=true`. Pushing does not redeploy: Actions > Deploy latest commit.
