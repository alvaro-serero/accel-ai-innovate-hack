"""Onboarding: CV PDF -> text -> structured profile -> users row + seed memory.

Pure functions (no DB): pdf_to_text, parse_profile, normalise_profile.
DB functions: save_user, load_user.
onboard_user glues them together (used by POST /api/users and the CLI).
"""
import io
from datetime import date

from psycopg.types.json import Jsonb
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from backend.app.db import execute, fetch_all, fetch_one
from backend.app.llm import SONNET, claude_json

MAX_CV_CHARS = 15000

PROFILE_SYSTEM = """You read a student's CV and turn it into a structured profile.
Only use facts written in the CV. Never invent or guess skills, projects, dates or employers.
If something is missing, use null (for scalars) or [] (for lists).

Return this JSON shape:
{
  "education": "degree, school, main field (one line)",
  "graduation_year": 2027,
  "skills": ["Python", "PyTorch", ...],
  "projects": [{"name": "...", "stack": ["..."], "one_line": "what it does / result"}],
  "experiences": [{"org": "...", "role": "...", "one_line": "what you did / result"}],
  "languages": ["French (native)", "English (C1)"],
  "interests": ["..."]
}"""


# ---------- pure functions ----------


def pdf_to_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except PyPdfError as e:
        raise ValueError(f"Not a readable PDF: {e}")
    lines = [" ".join(line.split()) for line in "\n".join(pages).splitlines()]
    return "\n".join(line for line in lines if line)


def normalise_profile(raw: dict) -> dict:
    """Make sure every key exists with the right type, whatever the LLM returned."""
    raw = raw if isinstance(raw, dict) else {}

    def str_list(value) -> list[str]:
        return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []

    def dict_list(value, keys: list[str]) -> list[dict]:
        out = []
        for item in value if isinstance(value, list) else []:
            if isinstance(item, dict):
                out.append({k: item.get(k) for k in keys})
        return out

    year = raw.get("graduation_year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None

    projects = dict_list(raw.get("projects"), ["name", "stack", "one_line"])
    for p in projects:
        p["stack"] = str_list(p["stack"])

    return {
        "education": raw.get("education") or None,
        "graduation_year": year,
        "skills": str_list(raw.get("skills")),
        "projects": projects,
        "experiences": dict_list(raw.get("experiences"), ["org", "role", "one_line"]),
        "languages": str_list(raw.get("languages")),
        "interests": str_list(raw.get("interests")),
    }


def parse_profile(cv_text: str) -> dict:
    raw = claude_json(PROFILE_SYSTEM, f"CV:\n{cv_text[:MAX_CV_CHARS]}", model=SONNET, max_tokens=3000)
    return normalise_profile(raw)


def split_list(text: str) -> list[str]:
    """'ML engineer intern, Data intern' -> ['ML engineer intern', 'Data intern']"""
    return [part.strip() for part in (text or "").split(",") if part.strip()]


def parse_start_date(text: str) -> date | None:
    """Accepts YYYY-MM-DD or YYYY-MM; empty -> None."""
    text = (text or "").strip()
    if not text:
        return None
    if len(text) == 7:
        text += "-01"
    return date.fromisoformat(text)


def seed_memory_lines(target_roles: list[str], target_companies: list[str]) -> list[str]:
    return [f"Target role: {r}" for r in target_roles] + [f"Target company: {c}" for c in target_companies]


# ---------- DB functions ----------


def save_user(
    name: str,
    email: str,
    city: str,
    target_roles: list[str],
    target_companies: list[str],
    start_date: date | None,
    cv_text: str,
    profile: dict,
) -> int:
    row = fetch_one(
        """insert into users (name, email, city, target_roles, target_companies, start_date, cv_text, profile)
           values (%s, %s, %s, %s, %s, %s, %s, %s) returning id""",
        (name, email, city, target_roles, target_companies, start_date, cv_text, Jsonb(profile)),
    )
    user_id = row["id"]
    for line in seed_memory_lines(target_roles, target_companies):
        execute(
            "insert into user_memory (user_id, kind, content, source) values (%s, 'fact', %s, 'onboarding')",
            (user_id, line),
        )
    return user_id


def load_user(user_id: int) -> dict | None:
    """users row (with cv_text) plus every memory line, active and superseded."""
    user = fetch_one("select * from users where id = %s", (user_id,))
    if user is None:
        return None
    user["memory"] = fetch_all("select * from user_memory where user_id = %s order by id", (user_id,))
    return user


# ---------- glue ----------


def onboard_user(
    pdf_bytes: bytes,
    name: str = "",
    email: str = "",
    city: str = "Paris",
    target_roles: str = "",
    target_companies: str = "",
    start_date: str = "",
) -> dict:
    cv_text = pdf_to_text(pdf_bytes)
    if len(cv_text) < 50:
        raise ValueError("Could not read text from this PDF (scanned image?)")
    profile = parse_profile(cv_text)
    user_id = save_user(
        name=name,
        email=email,
        city=city,
        target_roles=split_list(target_roles),
        target_companies=split_list(target_companies),
        start_date=parse_start_date(start_date),
        cv_text=cv_text,
        profile=profile,
    )
    return load_user(user_id)
