"""The three-stage ranker.

Stage 0  load_candidates  SQL prefilter (the only DB function here)
Stage 1  quick_score      Haiku on every candidate, cheap 0-100 score
Stage 2  deep_qualify     Sonnet on the top 15: fit score, cited reasons, gaps, red flags
         grounding_check  drop any reason whose quote is not really in the posting or CV
         pick_top         top 5, max 2 per company, fit >= 40, at least one grounded reason

Everything after load_candidates takes plain lists of dicts, so it runs without the database.
rank_jobs chains stages 1-2 and returns (picks, stats, trace) for run.py and the CLI.
"""
import asyncio
import re
import time

from backend.app.db import fetch_all
from backend.app.llm import HAIKU, SONNET, aclaude_json

GHOST_LIMIT = 0.6
QUICK_CHARS = 1500  # posting chars sent to Haiku
DEEP_CHARS = 8000  # posting chars sent to Sonnet
DEEP_TOP = 15
PICK_TOP = 5
MAX_PER_COMPANY = 2
MIN_FIT = 40  # weaker jobs never reach the morning brief
QUICK_CONCURRENCY = 8
DEEP_CONCURRENCY = 5

QUICK_SYSTEM = """You screen internship postings for one student.
Score how well this posting fits the student from 0 to 100, looking at:
- role match with the student's target roles,
- overlap between the required skills and the student's skills and projects,
- level: it must be an internship a student can do,
- the student's memory: respect preferences and dislikes strongly.
Return {"score": 0-100, "one_line": "why, max 20 words"}"""

DEEP_SYSTEM = """You qualify one internship posting for one student, carefully and honestly.
Return:
{
  "fit_score": 0-100,
  "reasons": [{"claim": "...", "evidence": "...", "source": "posting" or "cv"}],
  "gaps": ["requirement in the posting that the CV does not show"],
  "red_flags": ["concern about the posting itself"]
}
Rules for reasons (give 2 to 4):
- "claim" is short and addressed to the student, e.g. "Matches your RAG project".
- "evidence" MUST be a verbatim quote copied character for character from the POSTING or the CV:
  5 to 25 consecutive words, no paraphrase, no ellipsis, no quotation marks around it, no "CV:" prefix.
- "source" says where the quote comes from: "posting" or "cv".
Red flags: vague or generic posting, wrong level, dates that clash with the student's availability, not really an internship.
Memory lines are the student's own preferences and dislikes: let them move the score."""


# ---------- stage 0: SQL prefilter (DB) ----------


# A remote job outside the user's city must be open to someone in France: "Remote, US" is not.
REMOTE_OK_RE = re.compile(r"\b(?:france|europe|european|emea|eu|anywhere|worldwide|global)\b", re.I)


def remote_reachable(location: str | None) -> bool:
    """'France - Remote' yes, 'Remote' yes (no country given), 'Remote, US' no."""
    if REMOTE_OK_RE.search(location or ""):
        return True
    return not re.sub(r"remote|[^a-z]", "", (location or "").lower())  # nothing but "remote"


def load_candidates(user: dict) -> tuple[list[dict], int]:
    """Open internships in the user's city (or remote and reachable from France), minus dismissed ones.
    Returns (candidates, ghosts_skipped)."""
    city = (user.get("city") or "").lower()
    rows = fetch_all(
        """select j.id, j.company_id, c.name as company, j.title, j.city, j.location, j.remote, j.url,
                  j.description, j.first_seen_at, j.published_at,
                  coalesce(j.ghost_score, 0) as ghost_score, j.ghost_reasons
           from jobs j join companies c on c.id = j.company_id
           where j.is_internship and j.closed_at is null
             and (lower(j.city) = lower(%(city)s) or coalesce(j.remote, false))
             and not exists (select 1 from matches m
                             where m.user_id = %(user_id)s and m.job_id = j.id and m.status = 'dismissed')""",
        {"city": user.get("city") or "", "user_id": user["id"]},
    )
    rows = [r for r in rows if (r["city"] or "").lower() == city or remote_reachable(r["location"])]
    candidates = [r for r in rows if r["ghost_score"] < GHOST_LIMIT]
    return candidates, len(rows) - len(candidates)


# ---------- prompt helpers ----------


def compact_profile(profile: dict) -> str:
    p = profile or {}
    lines = []
    if p.get("education"):
        lines.append(f"Education: {p['education']} (graduates {p.get('graduation_year') or '?'})")
    if p.get("skills"):
        lines.append("Skills: " + ", ".join(p["skills"][:30]))
    for pr in (p.get("projects") or [])[:6]:
        lines.append(f"Project: {pr.get('name')} [{', '.join(pr.get('stack') or [])}]")
    for ex in (p.get("experiences") or [])[:4]:
        lines.append(f"Experience: {ex.get('role')} at {ex.get('org')}")
    if p.get("languages"):
        lines.append("Languages: " + ", ".join(p["languages"]))
    return "\n".join(lines)


def memory_text(memory: list[dict]) -> str:
    """Active memory lines only (superseded_by is null)."""
    active = [m for m in memory if m.get("superseded_by") is None]
    return "\n".join(f"- {m['kind']}: {m['content']}" for m in active) or "(none)"


def posting_text(job: dict) -> str:
    return f"{job['title']}\n{job.get('description') or ''}"


def posting_header(job: dict) -> str:
    where = job.get("city") or ("Remote" if job.get("remote") else "?")
    return f"{job['title']} at {job['company']} ({where})"


def clamp_score(value) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


# ---------- stage 1: quick score (Haiku) ----------


async def quick_score(candidates: list[dict], profile: dict, memory: list[dict]) -> list[dict]:
    """Adds quick_score and quick_line to every candidate."""
    student = f"STUDENT:\n{compact_profile(profile)}\n\nMEMORY:\n{memory_text(memory)}"
    sem = asyncio.Semaphore(QUICK_CONCURRENCY)

    async def score_one(job: dict) -> dict:
        prompt = f"{student}\n\nPOSTING: {posting_header(job)}\n{(job.get('description') or '')[:QUICK_CHARS]}"
        async with sem:
            try:
                out = await aclaude_json(QUICK_SYSTEM, prompt, model=HAIKU, max_tokens=1000, effort="low")
                return {**job, "quick_score": clamp_score(out.get("score")), "quick_line": out.get("one_line", "")}
            except Exception as e:  # one bad call must not kill the run
                return {**job, "quick_score": 0, "quick_line": f"scoring failed: {e}"}

    return await asyncio.gather(*(score_one(j) for j in candidates))


# ---------- stage 2: deep qualify (Sonnet) ----------


async def deep_qualify(top: list[dict], profile: dict, memory: list[dict], cv_text: str) -> list[dict]:
    """Adds fit_score, reasons, gaps, red_flags to each job. Reasons are NOT grounded yet."""
    student = (
        f"STUDENT PROFILE:\n{compact_profile(profile)}\n\nMEMORY:\n{memory_text(memory)}\n\n"
        f"CV (quote from this):\n{cv_text}"
    )
    sem = asyncio.Semaphore(DEEP_CONCURRENCY)

    async def qualify_one(job: dict) -> dict:
        prompt = f"{student}\n\nPOSTING (quote from this): {posting_header(job)}\n{posting_text(job)[:DEEP_CHARS]}"
        async with sem:
            try:
                out = await aclaude_json(DEEP_SYSTEM, prompt, model=SONNET, max_tokens=4000)
            except Exception as e:
                return {**job, "fit_score": 0, "reasons": [], "gaps": [], "red_flags": [f"qualifier failed: {e}"]}
        reasons = [r for r in out.get("reasons") or [] if isinstance(r, dict)]
        return {
            **job,
            "fit_score": clamp_score(out.get("fit_score")),
            "reasons": reasons,
            "gaps": [str(g) for g in out.get("gaps") or []],
            "red_flags": [str(f) for f in out.get("red_flags") or []],
        }

    return await asyncio.gather(*(qualify_one(j) for j in top))


# ---------- grounding check ----------

_SAME_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def normalise(text: str) -> str:
    """Lowercase, straight quotes and dashes, collapsed whitespace."""
    return re.sub(r"\s+", " ", (text or "").translate(_SAME_CHARS).lower()).strip()


def grounding_check(reasons: list[dict], posting: str, cv_text: str) -> tuple[list[dict], int]:
    """Keep only reasons whose evidence is literally in the posting or the CV.
    The source is set to where the quote was actually found. Returns (kept, dropped_count)."""
    posting_n, cv_n = normalise(posting), normalise(cv_text)
    kept = []
    for r in reasons:
        quote = normalise(str(r.get("evidence", ""))).strip("'\" ")
        in_posting, in_cv = quote in posting_n, quote in cv_n
        if not quote or not (in_posting or in_cv):
            continue
        claimed = r.get("source")
        if (claimed == "posting" and in_posting) or (claimed == "cv" and in_cv):
            source = claimed
        else:
            source = "posting" if in_posting else "cv"
        kept.append({"claim": str(r.get("claim", "")), "evidence": str(r["evidence"]).strip(), "source": source})
    return kept, len(reasons) - len(kept)


# ---------- final pick ----------


def pick_top(jobs: list[dict], k: int = PICK_TOP, max_per_company: int = MAX_PER_COMPANY) -> list[dict]:
    """Best fit first, at most max_per_company per company.
    Only jobs with fit >= MIN_FIT and at least one grounded reason."""
    picks, per_company = [], {}
    for job in sorted(jobs, key=lambda j: j["fit_score"], reverse=True):
        if job["fit_score"] < MIN_FIT or not job["reasons"]:
            continue
        if per_company.get(job["company_id"], 0) >= max_per_company:
            continue
        per_company[job["company_id"]] = per_company.get(job["company_id"], 0) + 1
        picks.append(job)
        if len(picks) == k:
            break
    return picks


# ---------- stages 1-2 chained ----------


def _step(name: str, count_in: int, count_out: int, started: float, note: str | None = None) -> dict:
    return {"step": name, "count_in": count_in, "count_out": count_out,
            "seconds": round(time.perf_counter() - started, 2), "note": note}


async def rank_jobs(candidates: list[dict], profile: dict, memory: list[dict], cv_text: str):
    """Returns (picks, stats, trace). No DB access."""
    trace = []

    t = time.perf_counter()
    scored = await quick_score(candidates, profile, memory)
    top = sorted(scored, key=lambda j: j["quick_score"], reverse=True)[:DEEP_TOP]
    trace.append(_step("quick_score (Haiku)", len(candidates), len(top), t, f"kept top {DEEP_TOP}"))

    t = time.perf_counter()
    deep = await deep_qualify(top, profile, memory, cv_text)
    trace.append(_step("deep_qualify (Sonnet)", len(top), len(deep), t))

    t = time.perf_counter()
    kept_total = dropped_total = 0
    for job in deep:
        job["reasons"], dropped = grounding_check(job["reasons"], posting_text(job), cv_text)
        kept_total += len(job["reasons"])
        dropped_total += dropped
    trace.append(_step("grounding_check", kept_total + dropped_total, kept_total, t, "reasons whose quote was found"))

    t = time.perf_counter()
    picks = pick_top(deep)
    trace.append(_step("pick_top", len(deep), len(picks), t, f"top {PICK_TOP}, max {MAX_PER_COMPANY} per company, fit >= {MIN_FIT}"))

    stats = {
        "scored": len(scored),
        "deep_scored": len(deep),
        "picked": len(picks),
        "reasons_kept": kept_total,
        "reasons_dropped": dropped_total,
    }
    return picks, stats, trace
