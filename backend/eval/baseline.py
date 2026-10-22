"""The 'keyword alert' every job board sells: title contains a target-role keyword, in the user's city, newest first."""
import re

from backend.app.db import fetch_all, fetch_one

STOP = {"intern", "internship", "stage", "stagiaire", "alternance", "trainee", "de", "en", "et", "the", "and", "of", "for",
        "f", "h", "m", "w", "x", "fin", "etudes", "études", "2026", "2027", "junior"}

JOB_COLS = """j.id, j.title, c.name as company, j.city, j.url, j.remote, j.first_seen_at, j.published_at,
              j.ghost_score, left(j.description, 3000) as description"""


def role_keywords(target_roles: list[str]) -> list[str]:
    words = set()
    for role in target_roles or []:
        for w in re.findall(r"[a-zA-Zà-ÿ+#]+", role.lower()):
            if w not in STOP and (len(w) >= 3 or w in {"ml", "ai", "ia", "ux", "ui", "bi"}):
                words.add(w)
    return sorted(words)


def keyword_alert(user_id: int, k: int = 5) -> list[dict]:
    user = fetch_one("select city, target_roles from users where id = %s", (user_id,))
    kws = role_keywords(user["target_roles"])
    if not kws:
        return []
    pattern = r"\m(" + "|".join(re.escape(w) for w in kws) + r")\M"   # Postgres word boundaries
    return fetch_all(f"""select {JOB_COLS} from jobs j join companies c on c.id = j.company_id
                         where j.is_internship and j.closed_at is null
                           and (j.city ilike %s or j.remote) and j.title ~* %s
                         order by coalesce(j.published_at, j.first_seen_at) desc limit %s""",
                     (user["city"] or "Paris", pattern, k))


def agent_picks(user_id: int, run_id: int, k: int = 5) -> list[dict]:
    return fetch_all(f"""select {JOB_COLS}, m.rank from matches m join jobs j on j.id = m.job_id
                         join companies c on c.id = j.company_id
                         where m.user_id = %s and m.run_id = %s order by m.rank limit %s""", (user_id, run_id, k))


def latest_run_id(user_id: int) -> int | None:
    row = fetch_one("select max(run_id) as r from matches where user_id = %s", (user_id,))
    return row["r"] if row else None
