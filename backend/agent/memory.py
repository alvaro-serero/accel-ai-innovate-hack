"""Feedback -> memory curator -> user_memory lines (add new ones, supersede contradicted ones).

Pure: curate (Sonnet), clean_plan (validates the LLM answer against the real memory ids).
DB:   save_feedback, set_match_status, target_text, apply_plan.
handle_feedback glues them together for POST /api/feedback.
"""
from backend.app.db import execute, fetch_all, fetch_one
from backend.app.llm import SONNET, claude_json

KINDS = ("preference", "fact", "dislike")
DESCRIPTION_CHARS = 800

CURATOR_SYSTEM = """You maintain the long-term memory of an internship scout agent for one student.
You get one piece of feedback (thumbs up or down, with an optional reason) on a job or event,
and the student's current active memory lines with their ids.

Return {"add": [{"kind": "...", "content": "..."}], "supersede": [{"id": 12, "why": "..."}]}

add: new lines worth remembering for ranking future jobs.
- kind: "preference" (what they want), "dislike" (what they avoid), "fact" (stable fact about them).
- content: short (max 15 words) and general, e.g. "prefers startups under 200 people", not "disliked job 12".
- Never repeat a line that already exists.
supersede: existing lines that the new feedback clearly contradicts.
- Every superseded line must be replaced by a line in add.
- Example: memory has "wants big tech companies", reason "too corporate"
  -> add "prefers startups and smaller companies", supersede the big tech line.
If nothing general can be learned (for example no reason given), return empty lists."""


# ---------- pure functions ----------


def memory_with_ids(memory: list[dict]) -> str:
    return "\n".join(f"[{m['id']}] {m['kind']}: {m['content']}" for m in memory) or "(empty)"


def curate(target: str, verdict: str, reason: str | None, memory: list[dict]) -> dict:
    """memory = active lines only. Returns the raw curator plan."""
    prompt = (
        f"FEEDBACK: thumbs {verdict}\nREASON: {reason or '(none given)'}\n\n{target}\n\n"
        f"ACTIVE MEMORY:\n{memory_with_ids(memory)}"
    )
    return claude_json(CURATOR_SYSTEM, prompt, model=SONNET, max_tokens=2000)


def clean_plan(plan: dict, memory: list[dict]) -> tuple[list[dict], list[int]]:
    """Keep valid new lines and only supersede ids that are this user's active lines.
    No new line -> nothing is superseded (a line is only retired when a newer one replaces it)."""
    existing = {m["content"].strip().lower() for m in memory}
    add = []
    for item in plan.get("add") or []:
        if not isinstance(item, dict):
            continue
        kind, content = item.get("kind"), str(item.get("content") or "").strip()
        if kind in KINDS and content and content.lower() not in existing:
            existing.add(content.lower())
            add.append({"kind": kind, "content": content})
    active_ids = {m["id"] for m in memory}
    supersede = []
    for item in plan.get("supersede") or []:
        try:
            line_id = int(item.get("id"))
        except (AttributeError, TypeError, ValueError):
            continue
        if line_id in active_ids and line_id not in supersede:
            supersede.append(line_id)
    return add, (supersede if add else [])


# ---------- DB functions ----------


def save_feedback(user_id: int, target_type: str, target_id: int, verdict: str, reason: str | None) -> None:
    execute(
        "insert into feedback (user_id, target_type, target_id, verdict, reason) values (%s, %s, %s, %s, %s)",
        (user_id, target_type, target_id, verdict, reason),
    )


def set_match_status(user_id: int, job_id: int, status: str) -> None:
    """All of this user's matches for the job, so a dismissed job never comes back in later runs."""
    execute("update matches set status = %s where user_id = %s and job_id = %s", (status, user_id, job_id))


def target_text(target_type: str, target_id: int) -> str:
    if target_type == "job":
        row = fetch_one(
            """select j.title, c.name as company, j.description
               from jobs j join companies c on c.id = j.company_id where j.id = %s""",
            (target_id,),
        )
        if row:
            return f"JOB: {row['title']} at {row['company']}\n{(row['description'] or '')[:DESCRIPTION_CHARS]}"
    else:
        row = fetch_one("select title, kind, companies, description from events where id = %s", (target_id,))
        if row:
            return (f"EVENT: {row['title']} ({row['kind']}), companies: {', '.join(row['companies'] or [])}\n"
                    f"{(row['description'] or '')[:DESCRIPTION_CHARS]}")
    return f"{target_type.upper()} {target_id} (details not found)"


def active_memory(user_id: int) -> list[dict]:
    return fetch_all("select * from user_memory where user_id = %s and superseded_by is null order by id", (user_id,))


def apply_plan(user_id: int, source: str, add: list[dict], supersede: list[int]) -> list[dict]:
    """Insert new lines; superseded lines point to the first new one. Returns the new rows."""
    added = [
        fetch_one(
            "insert into user_memory (user_id, kind, content, source) values (%s, %s, %s, %s) returning *",
            (user_id, a["kind"], a["content"], source),
        )
        for a in add
    ]
    for line_id in supersede:
        execute(
            "update user_memory set superseded_by = %s where id = %s and user_id = %s and superseded_by is null",
            (added[0]["id"], line_id, user_id),
        )
    return added


# ---------- glue ----------


def handle_feedback(user_id: int, target_type: str, target_id: int, verdict: str, reason: str | None) -> dict:
    save_feedback(user_id, target_type, target_id, verdict, reason)
    if target_type == "job":
        set_match_status(user_id, target_id, "dismissed" if verdict == "down" else "liked")

    memory = active_memory(user_id)
    try:
        plan = curate(target_text(target_type, target_id), verdict, reason, memory)
    except Exception as e:  # feedback and match status are saved anyway; memory just doesn't change
        print(f"[memory] curator failed: {e}")
        plan = {}
    add, supersede = clean_plan(plan, memory)
    added = apply_plan(user_id, f"feedback:{target_type}:{target_id}", add, supersede)
    return {"memory_added": added, "memory_superseded": supersede}
