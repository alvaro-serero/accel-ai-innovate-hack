"""Optional tool: check that a speaker named on an event page really works at the target company. Owner: Taleb.

OFF by default. Turn on with EVENTS_VERIFY_PEOPLE=true.
- Only people already named publicly on the event page (speakers, hosts). Never attendee lists.
- One Keenable web search per person; we read public search results only, never LinkedIn pages.
- Verified only if a linkedin.com/in/ result names the person and mentions the company; otherwise nothing is claimed.
"""
import asyncio
import os
import re

from backend.app.search import akeenable_search
from backend.events.verify import norm

MAX_PEOPLE = 3


def enabled() -> bool:
    return os.getenv("EVENTS_VERIFY_PEOPLE", "false").lower() == "true"


def _matches(hit: dict, name: str, company: str) -> bool:
    url = (hit.get("url") or "").lower()
    if "linkedin.com/in/" not in url:
        return False
    text = norm(f"{hit.get('title', '')} {hit.get('snippet', '')}")
    surname = norm(name).split()[-1] if norm(name) else ""
    has_name = bool(surname) and re.search(rf"\b{re.escape(surname)}\b", text) is not None
    has_company = re.search(rf"\b{re.escape(norm(company))}\b", text) is not None
    return has_name and has_company


async def check_person(name: str, company: str) -> dict:
    """{verified: bool, profile_url: str|None, evidence: str|None}"""
    try:
        hits = await akeenable_search(f'"{name}" {company} LinkedIn')
    except Exception as e:
        print(f"[events.people] {name}: {e}")
        return {"verified": False, "profile_url": None, "evidence": None}
    for h in hits[:5]:
        if _matches(h, name, company):
            return {"verified": True, "profile_url": h["url"], "evidence": (h.get("title") or "")[:160]}
    return {"verified": False, "profile_url": None, "evidence": None}


async def verify_people(contacts: list[dict]) -> list[dict]:
    """Adds verified/profile_url to each contact; for verified ones, appends the proof to `role`
    so the current UI shows it without any schema change. Unverified contacts are left unchanged."""
    if not enabled() or not contacts:
        return contacts
    todo = contacts[:MAX_PEOPLE]
    results = await asyncio.gather(*(check_person(c.get("name") or "", c.get("company") or "") for c in todo))
    out = []
    for c, r in zip(todo, results):
        c = dict(c, verified=r["verified"], profile_url=r["profile_url"])
        if r["verified"]:
            c["role"] = f"{c.get('role') or 'works'} at {c.get('company')} (verified: {r['profile_url']})"
        out.append(c)
    return out + contacts[MAX_PEOPLE:]
