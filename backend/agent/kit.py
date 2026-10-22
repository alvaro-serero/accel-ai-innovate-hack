"""Application kit for one job: CV bullets, cover letter, LinkedIn note, who to contact.
Nothing is ever sent: the student copies and sends everything themselves.

Pure: write_kit (Sonnet), ground_bullets, trim_words, trim_chars, build_kit.
DB:   load_job, save_kit.  make_kit glues them together for POST /api/jobs/{job_id}/kit.
"""
import re

from psycopg.types.json import Jsonb

from backend.agent.qualify import compact_profile, memory_text
from backend.app.db import execute, fetch_one
from backend.app.llm import SONNET, claude_json

COVER_MAX_WORDS = 180
NOTE_MAX_CHARS = 300
POSTING_CHARS = 6000

KIT_SYSTEM = """You prepare an application kit for one student and one internship posting.
The student reviews and sends everything themselves.

Return:
{
  "cv_bullets": ["3 to 5 bullets"],
  "cover_letter": "...",
  "linkedin_note": "...",
  "contact": {"who": "...", "search": "..."}
}
Rules:
- Use ONLY facts written in the CV: never invent projects, employers, numbers, tools or results.
- cv_bullets: rewrite 3 to 5 real CV items (projects, experiences) so they speak to this posting's requirements.
  Start with a strong verb, max 25 words each, keep the CV's real numbers.
- cover_letter: under 180 words, first person, 2 or 3 short paragraphs, specific to this company and role,
  cites 2 concrete CV facts that match the posting, no cliches, signed with the student's name.
- linkedin_note: under 300 characters, a connection note to one person on the team. Friendly and specific:
  one concrete link between the student's work and the team. Do not ask for a referral.
- contact.who: the kind of person to contact (role and team, e.g. "an ML engineer on the inference team"). Never invent a name.
- contact.search: a LinkedIn people-search string, e.g. "Mistral AI" "machine learning engineer" Paris"""

# Words that don't prove a bullet comes from the CV: common English plus generic CV verbs.
STOPWORDS = set("""
the and for with from that this into over your our you are was were has have had its via all can one two new use
used using built build building developed develop designed design work worked working team teams project projects
experience skills skill strong across their which while within based more than also about using including improved
created create led lead managed delivered implemented ensuring ensure end
""".split())


# ---------- pure functions ----------


def significant_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#]+", text.lower()) if len(w) >= 3 and w not in STOPWORDS}


def ground_bullets(bullets: list[str], cv_text: str) -> tuple[list[str], int]:
    """Keep bullets sharing at least one significant word with the CV. Returns (kept, dropped_count)."""
    cv_words = significant_words(cv_text)
    kept = [b for b in bullets if significant_words(b) & cv_words]
    return kept, len(bullets) - len(kept)


def _longest_sentence_prefix(text: str, fits) -> str:
    best = ""
    for m in re.finditer(r"[.!?](?=\s|$)", text):
        if not fits(text[: m.end()]):
            break
        best = text[: m.end()]
    return best


def trim_words(text: str, max_words: int) -> str:
    """Under max_words, cut at the last full sentence that fits."""
    text = text.strip()
    fits = lambda t: len(t.split()) < max_words
    if fits(text):
        return text
    return _longest_sentence_prefix(text, fits) or " ".join(text.split()[: max_words - 1])


def trim_chars(text: str, max_chars: int) -> str:
    """Under max_chars, cut at the last full sentence that fits."""
    text = text.strip()
    fits = lambda t: len(t) < max_chars
    if fits(text):
        return text
    return _longest_sentence_prefix(text, fits) or text[: max_chars - 1].rsplit(" ", 1)[0]


def write_kit(job: dict, profile: dict, cv_text: str, memory: list[dict], student_name: str) -> dict:
    prompt = (
        f"STUDENT NAME: {student_name or '(not given)'}\n\nSTUDENT PROFILE:\n{compact_profile(profile)}\n\n"
        f"PREFERENCES (memory):\n{memory_text(memory)}\n\nCV:\n{cv_text}\n\n"
        f"POSTING: {job['title']} at {job['company']} ({job.get('city') or 'remote'})\n"
        f"{(job.get('description') or '')[:POSTING_CHARS]}"
    )
    return claude_json(KIT_SYSTEM, prompt, model=SONNET, max_tokens=4000)


def build_kit(raw: dict, cv_text: str) -> tuple[dict, int]:
    """LLM answer -> Kit fields, with the bullet check and the length limits applied."""
    bullets = [str(b).strip() for b in raw.get("cv_bullets") or [] if str(b).strip()][:5]
    bullets, dropped = ground_bullets(bullets, cv_text)
    contact = raw.get("contact") if isinstance(raw.get("contact"), dict) else {}
    who, search = str(contact.get("who") or "").strip(), str(contact.get("search") or "").strip()
    hint = f"{who[:1].upper()}{who[1:]}." if who else ""
    if search:
        hint = f"{hint} LinkedIn search: {search}".strip()
    kit = {
        "cv_bullets": bullets,
        "cover_letter": trim_words(str(raw.get("cover_letter") or ""), COVER_MAX_WORDS),
        "linkedin_note": trim_chars(str(raw.get("linkedin_note") or ""), NOTE_MAX_CHARS),
        "contact_hint": hint,
    }
    return kit, dropped


# ---------- DB functions ----------


def load_job(job_id: int) -> dict | None:
    return fetch_one(
        """select j.id, j.title, j.city, j.description, c.name as company
           from jobs j join companies c on c.id = j.company_id where j.id = %s""",
        (job_id,),
    )


def save_kit(user_id: int, job_id: int, kit: dict) -> None:
    execute(
        """insert into kits (user_id, job_id, cv_bullets, cover_letter, linkedin_note, contact_hint)
           values (%s, %s, %s, %s, %s, %s)""",
        (user_id, job_id, Jsonb(kit["cv_bullets"]), kit["cover_letter"], kit["linkedin_note"], kit["contact_hint"]),
    )


# ---------- glue ----------


def make_kit(user: dict, job: dict) -> dict:
    active = [m for m in user["memory"] if m["superseded_by"] is None]
    raw = write_kit(job, user["profile"], user["cv_text"], active, user.get("name") or "")
    kit, dropped = build_kit(raw, user["cv_text"])
    if dropped:
        print(f"[kit] dropped {dropped} CV bullet(s) with no word in common with the CV")
    save_kit(user["id"], job["id"], kit)
    return kit
