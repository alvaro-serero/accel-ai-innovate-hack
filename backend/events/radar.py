"""Events radar pipeline. Owner: Taleb.

refresh_events(user_id): search.py (Keenable queries per target company x city)
-> extract.py (fetch page, trafilatura, Haiku -> event JSON)
-> verify.py (future date, same city/region, company named in page text, dedupe)
-> rank -> upsert events + event_matches.
Alvaro's run.py calls this, so keep the signature.
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from backend.app.db import execute, fetch_all, fetch_one
from backend.app.llm import HAIKU, aclaude_json
from backend.app.schemas import Contact, EventMatch, EventOut, EventsRefreshResult
from backend.events.extract import extract_event
from backend.events.people import verify_people
from backend.events.search import search_events
from backend.events.verify import norm, parse_date, verify

RAW_DIR = Path(__file__).resolve().parent.parent / "eval" / "results"
INVOLVEMENT_POINTS = {"host": 40, "recruiting": 40, "speaker": 30, "sponsor": 20}
KIND_BONUS = {"career_fair": 15, "hackathon": 15}


def score_event(ev: dict, target_companies: list[str], now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    targets = {norm(t) for t in target_companies}
    inv = ev.get("involvement") or {}
    best = max([INVOLVEMENT_POINTS.get(str(v).lower(), 0) for c, v in inv.items() if norm(c) in targets] or [0])
    start = parse_date(ev.get("starts_at"))
    days = (start - now).days if start else 90
    soon = max(0, 30 - days // 3)  # 30 points today, 0 at 90 days
    friendly = 15 if ev.get("student_friendly") else 0
    return min(100, best + soon + friendly + KIND_BONUS.get(ev.get("kind") or "", 0))


def why_line(ev: dict, target_companies: list[str], city: str) -> str:
    targets = {norm(t): t for t in target_companies}
    parts = [f"{targets[norm(c)]} is {v}" for c, v in (ev.get("involvement") or {}).items() if norm(c) in targets]
    start = parse_date(ev.get("starts_at"))
    when = f"{ev.get('kind') or 'event'} on {start.strftime('%d %b')}" if start else ""
    where = f"in {ev.get('city') or city}"
    friendly = "students welcome" if ev.get("student_friendly") else ""
    return "; ".join(filter(None, [", ".join(parts), when, where, friendly]))


OPENER_SYSTEM = """Write a one-line opener (max 220 characters) a student could say to this person at the event.
Link the person's talk or company to ONE real project or experience from the student's profile. No flattery, no invented facts.
Return {"opener": "..."}."""


async def who_to_meet(ev: dict, target_companies: list[str], profile: dict) -> list[dict]:
    targets = {norm(t) for t in target_companies}
    people = [s for s in (ev.get("speakers") or []) if s.get("name") and norm(s.get("company")) in targets][:3]
    out = []
    for p in people:
        try:
            r = await aclaude_json(OPENER_SYSTEM, f"PERSON: {json.dumps(p, ensure_ascii=False)}\nEVENT: {ev.get('title')}\n"
                                                  f"STUDENT PROFILE: {json.dumps(profile, ensure_ascii=False)[:3000]}", model=HAIKU, max_tokens=300)
            opener = r.get("opener", "") if isinstance(r, dict) else ""
        except Exception:
            opener = ""
        out.append({"name": p["name"], "role": p.get("role"), "company": p.get("company"), "opener": opener})
    # as in the plan: only people named on the page; no named speaker means no "who to meet"
    return await verify_people(out)  # optional, off unless EVENTS_VERIFY_PEOPLE=true


def _store_event(ev: dict, verified: bool, notes: str) -> int:
    row = fetch_one(
        """insert into events (title, url, source, kind, starts_at, city, venue, companies, involvement, speakers,
                               student_friendly, description, verified, verify_notes)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s)
           on conflict (url) do update set title=excluded.title, kind=excluded.kind, starts_at=excluded.starts_at,
               city=excluded.city, venue=excluded.venue, companies=excluded.companies, involvement=excluded.involvement,
               speakers=excluded.speakers, student_friendly=excluded.student_friendly, description=excluded.description,
               verified=excluded.verified, verify_notes=excluded.verify_notes
           returning id""",
        (ev.get("title") or ev["url"], ev["url"], ev.get("source"), ev.get("kind"), parse_date(ev.get("starts_at")),
         ev.get("city"), ev.get("venue"), ev.get("companies") or [], json.dumps(ev.get("involvement") or {}),
         json.dumps(ev.get("speakers") or []), bool(ev.get("student_friendly")), ev.get("description"), verified, notes))
    return row["id"]


async def refresh_events(user_id: int) -> EventsRefreshResult:
    user = fetch_one("select id, city, target_companies, profile from users where id = %s", (user_id,))
    if not user:
        raise ValueError(f"user {user_id} not found")
    city = user["city"] or "Paris"
    companies = list(user["target_companies"] or [])
    profile = user["profile"] or {}
    if isinstance(profile, str):
        profile = json.loads(profile)

    candidates = await search_events(companies, city)
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient() as client:
        extracted = await asyncio.gather(*(extract_event(client, c, sem) for c in candidates))

    seen, kept, verified_n, log = set(), 0, 0, []
    for cand, ev in zip(candidates, extracted):
        if not ev:
            log.append({"url": cand["url"], "title": cand.get("title"), "verified": False, "notes": "rejected: extraction failed"})
            continue
        ok, notes, _ = verify(ev, city, companies, seen)
        event_id = _store_event(ev, ok, notes)
        log.append({"url": ev["url"], "title": ev.get("title"), "starts_at": ev.get("starts_at"), "verified": ok,
                    "notes": notes, "event_id": event_id})
        if not ok:
            continue
        verified_n += 1
        meet = await who_to_meet(ev, companies, profile)
        execute("""insert into event_matches (user_id, event_id, score, why, who_to_meet)
                   values (%s,%s,%s,%s,%s::jsonb)
                   on conflict (user_id, event_id) do update set score=excluded.score, why=excluded.why, who_to_meet=excluded.who_to_meet""",
                (user_id, event_id, score_event(ev, companies), why_line(ev, companies, city), json.dumps(meet, ensure_ascii=False)))
        kept += 1

    # raw search results + every decision with its reason: used by the events precision eval and the data-layer file
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / f"events_raw_user{user_id}.json").write_text(json.dumps(
        {"at": datetime.now(timezone.utc).isoformat(), "candidates": candidates, "decisions": log},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[events] user {user_id}: found {len(candidates)}, verified {verified_n}, kept {kept}")
    return EventsRefreshResult(found=len(candidates), verified=verified_n, kept=kept)


def _load(v, default):
    return (json.loads(v) if isinstance(v, str) else v) or default


def user_event_matches(user_id: int) -> list[EventMatch]:
    rows = fetch_all("""select m.id, m.score, m.why, m.who_to_meet, e.id as event_id, e.title, e.url, e.kind, e.starts_at,
                               e.city, e.venue, e.companies, e.involvement
                        from event_matches m join events e on e.id = m.event_id
                        where m.user_id = %s and e.verified and (e.starts_at is null or e.starts_at > now())
                        order by m.score desc, e.starts_at asc limit 20""", (user_id,))
    return [EventMatch(id=r["id"], score=r["score"] or 0, why=r["why"] or "",
                       event=EventOut(id=r["event_id"], title=r["title"], url=r["url"], kind=r["kind"], starts_at=r["starts_at"],
                                      city=r["city"], venue=r["venue"], companies=r["companies"] or [],
                                      involvement=_load(r["involvement"], {})),
                       who_to_meet=[Contact(**c) for c in _load(r["who_to_meet"], []) if c.get("name")])
            for r in rows]
