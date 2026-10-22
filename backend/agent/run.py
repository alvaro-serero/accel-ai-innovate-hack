"""One agent run for one student: prefilter -> rank -> research -> save -> events -> deliver the brief.

execute_run   the orchestrator (POST /api/users/{id}/runs runs it in the background, the CLI runs it directly)
load_run      GET /api/runs/{id}
load_brief    GET /api/users/{id}/brief (latest finished run)

Run status is derived from the row: finished_at null = running, stats.error = failed, else done.
"""
import time
from datetime import datetime, timedelta, timezone

import httpx
from psycopg.types.json import Jsonb

from backend.agent import profile, qualify, research
from backend.app import llm
from backend.app.config import settings
from backend.app.db import execute, fetch_all, fetch_one
from backend.app.schemas import Brief, BriefStats

# $ per million tokens (input, output), for the cost stat
PRICES = {llm.HAIKU: (0.10, 0.50), llm.SONNET: (2.00, 10.00)}


# ---------- small helpers ----------


def _step(name: str, count_in: int | None, count_out: int | None, started: float, note: str | None = None) -> dict:
    return {"step": name, "count_in": count_in, "count_out": count_out,
            "seconds": round(time.perf_counter() - started, 2), "note": note}


def _usage_snapshot() -> dict:
    return {model: dict(u) for model, u in llm.USAGE.items()}


def _usage_since(before: dict) -> dict:
    """Tokens used since the snapshot, per model, plus an estimated cost."""
    used = {}
    for model, u in llm.USAGE.items():
        diff = {k: u[k] - before.get(model, {}).get(k, 0) for k in ("input", "output", "calls")}
        if diff["calls"]:
            used[model] = diff
    cost = sum(
        u["input"] / 1e6 * PRICES.get(m, (0, 0))[0] + u["output"] / 1e6 * PRICES.get(m, (0, 0))[1]
        for m, u in used.items()
    )
    return {"by_model": used, "cost_usd": round(cost, 4)}


def run_status(run: dict) -> str:
    if run["finished_at"] is None:
        return "running"
    return "failed" if (run["stats"] or {}).get("error") else "done"


# ---------- DB writes ----------


def create_run(user_id: int, kind: str = "manual") -> int:
    return fetch_one("insert into runs (user_id, kind, trace) values (%s, %s, '[]') returning id", (user_id, kind))["id"]


def save_matches(run_id: int, user_id: int, picks: list[dict], briefs: dict) -> None:
    for rank, job in enumerate(picks, 1):
        brief = briefs.get(job["company"])
        execute(
            """insert into matches (run_id, user_id, job_id, rank, fit_score, reasons, gaps, company_brief)
               values (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (run_id, user_id, job["id"], rank, job["fit_score"], Jsonb(job["reasons"]), Jsonb(job["gaps"]),
             Jsonb(brief.model_dump()) if brief else None),
        )


def finish_run(run_id: int, stats: dict, trace: list[dict]) -> None:
    execute("update runs set finished_at = now(), stats = %s, trace = %s where id = %s",
            (Jsonb(stats), Jsonb(trace), run_id))


# ---------- the orchestrator ----------


async def execute_run(run_id: int, user_id: int) -> None:
    trace, stats = [], {}
    usage_before = _usage_snapshot()
    try:
        user = profile.load_user(user_id)

        t = time.perf_counter()
        candidates, ghosts = qualify.load_candidates(user)
        trace.append(_step("load_candidates (SQL)", len(candidates) + ghosts, len(candidates), t,
                           f"{ghosts} ghost jobs skipped"))
        day_ago = datetime.now(timezone.utc) - timedelta(days=1)
        stats.update(
            postings_checked=fetch_one("select count(*) as n from jobs where closed_at is null")["n"],
            new_internships=sum(1 for c in candidates if c["first_seen_at"] and c["first_seen_at"] > day_ago),
            candidates=len(candidates),
            ghosts_skipped=ghosts,
        )

        picks = []
        if candidates:
            picks, rank_stats, rank_trace = await qualify.rank_jobs(
                candidates, user["profile"], user["memory"], user["cv_text"])
            stats.update(rank_stats)
            trace.extend(rank_trace)

        t = time.perf_counter()
        companies = list(dict.fromkeys(p["company"] for p in picks))
        briefs = await research.research_companies(companies)
        trace.append(_step("research (Keenable + Haiku)", len(companies),
                           sum(1 for b in briefs.values() if b), t, "companies with a cited brief"))

        save_matches(run_id, user_id, picks, briefs)

        t = time.perf_counter()
        try:
            from backend.events.radar import refresh_events

            result = await refresh_events(user_id)
            trace.append(_step("events radar", result.found, result.kept, t, f"{result.verified} verified"))
        except Exception as e:  # Taleb's radar is optional for the agent run
            trace.append(_step("events radar", None, None, t, f"skipped: {e}"))

        stats["tokens"] = _usage_since(usage_before)
        finish_run(run_id, stats, trace)
    except Exception as e:
        stats.update(error=f"{type(e).__name__}: {e}", tokens=_usage_since(usage_before))
        finish_run(run_id, stats, trace)
        return

    await send_brief_to_n8n(user)


async def send_brief_to_n8n(user: dict) -> None:
    """The n8n workflow emails the brief. Never fails the run."""
    if not settings.n8n_webhook_url:
        return
    try:
        payload = {"user": {"id": user["id"], "name": user["name"], "email": user["email"]},
                   **load_brief(user["id"]).model_dump(mode="json")}
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.n8n_webhook_url, json=payload)
    except Exception as e:
        print(f"[run] n8n webhook failed: {e}")


# ---------- reads ----------


def load_run(run_id: int) -> dict | None:
    run = fetch_one("select * from runs where id = %s", (run_id,))
    if run is None:
        return None
    return {**run, "status": run_status(run), "stats": run["stats"] or {}, "trace": run["trace"] or []}


MATCH_SELECT = """
    select m.id, m.rank, m.fit_score, m.status, m.reasons, m.gaps, m.company_brief,
           j.id as job_id, j.title, c.name as company, j.city, j.url, j.first_seen_at, j.published_at,
           j.ghost_score, j.ghost_reasons
    from matches m join jobs j on j.id = m.job_id join companies c on c.id = j.company_id
"""


def match_from_row(r: dict) -> dict:
    """matches + jobs row -> the Match shape of schemas.py."""
    return {
        "id": r["id"], "rank": r["rank"], "fit_score": r["fit_score"], "status": r["status"],
        "reasons": r["reasons"] or [], "gaps": r["gaps"] or [], "company_brief": r["company_brief"],
        "job": {
            "id": r["job_id"], "title": r["title"], "company": r["company"], "city": r["city"], "url": r["url"],
            "first_seen_at": r["first_seen_at"], "published_at": r["published_at"],
            "ghost_score": r["ghost_score"] or 0, "ghost_reasons": r["ghost_reasons"] or [],
        },
    }


def load_match(match_id: int) -> dict | None:
    row = fetch_one(MATCH_SELECT + " where m.id = %s", (match_id,))
    return match_from_row(row) if row else None


def user_events(user_id: int) -> list:
    try:
        from backend.events.radar import user_event_matches  # Taleb's, lands at the 14:00 merge

        return user_event_matches(user_id)
    except Exception:
        return []


def load_brief(user_id: int) -> Brief:
    """Latest finished (not failed) run: its matches, the user's events, the headline stats."""
    run = fetch_one(
        """select * from runs where user_id = %s and finished_at is not null and stats->>'error' is null
           order by finished_at desc limit 1""",
        (user_id,),
    )
    if run is None:
        return Brief()
    matches = [match_from_row(r) for r in fetch_all(MATCH_SELECT + " where m.run_id = %s order by m.rank", (run["id"],))]
    events = user_events(user_id)
    s = run["stats"] or {}
    return Brief(
        run_id=run["id"],
        generated_at=run["finished_at"],
        stats=BriefStats(postings_checked=s.get("postings_checked", 0), new_internships=s.get("new_internships", 0),
                         ghosts_skipped=s.get("ghosts_skipped", 0), events_found=len(events)),
        matches=matches,
        events=events,
    )
