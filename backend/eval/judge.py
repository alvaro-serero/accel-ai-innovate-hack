"""Independent judge (OpenAI): Claude never grades its own picks."""
import json
import os

from backend.app.db import fetch_all, fetch_one
from backend.app.llm import openai_json

JUDGE_MODEL = os.getenv("OPENAI_JUDGE_MODEL") or None  # None = settings.openai_model

SYSTEM = """You are a strict career advisor. Given a student's profile, preferences and one internship posting,
decide whether this student would realistically apply. Consider role fit, required skills vs their real skills,
location, start date and their stated preferences.
Return {"would_apply": true|false, "score": 0-100, "why": "one sentence"}."""


def student_context(user_id: int) -> str:
    u = fetch_one("select name, city, target_roles, target_companies, start_date, profile from users where id = %s", (user_id,))
    mem = fetch_all("select kind, content from user_memory where user_id = %s and superseded_by is null", (user_id,))
    profile = u["profile"] if isinstance(u["profile"], dict) else json.loads(u["profile"] or "{}")
    return (f"City: {u['city']}\nTarget roles: {u['target_roles']}\nTarget companies: {u['target_companies']}\n"
            f"Start date: {u['start_date']}\nProfile: {json.dumps(profile, ensure_ascii=False)[:4000]}\n"
            f"Preferences and facts: " + "; ".join(f"{m['kind']}: {m['content']}" for m in mem))


def judge_job(context: str, job: dict) -> dict:
    user = (f"STUDENT:\n{context}\n\nPOSTING: {job['title']} at {job['company']} ({job.get('city') or ''})\n"
            f"{(job.get('description') or '')[:3000]}")
    return openai_json(SYSTEM, user, model=JUDGE_MODEL)
