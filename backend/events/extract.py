"""Fetch an event page and extract structured fields with Haiku. Owner: Taleb."""
import asyncio
import html
import re

import httpx

from backend.app.llm import HAIKU, aclaude_json

MAX_CHARS = 6000

SYSTEM = """You read a web page and decide if it describes ONE specific upcoming event (meetup, hackathon, career fair, talk, conference).
Only use what the page says. If a field is not on the page, use null or an empty list. Never guess dates.
starts_at must be ISO 8601 (YYYY-MM-DDTHH:MM, local time) if a date is given, else null.
involvement maps each company named on the page to one of: host, sponsor, speaker, recruiting.
speakers: only people named on the page.
Return this JSON object:
{"is_event": bool, "title": str, "kind": "hackathon|meetup|career_fair|talk|conference|other",
 "starts_at": str|null, "city": str|null, "venue": str|null, "companies": [str],
 "involvement": {"<company>": "host|sponsor|speaker|recruiting"}, "speakers": [{"name": str, "role": str, "company": str}],
 "student_friendly": bool, "registration_url": str|null, "description": str (max 2 sentences)}"""


def _meta(raw_html: str) -> str:
    """Fallback for JavaScript pages (Luma): title, meta/og tags and JSON-LD."""
    bits = []
    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.S | re.I)
    if m:
        bits.append(m.group(1))
    for name in ("og:title", "og:description", "description", "twitter:description", "event:start_time"):
        for m in re.finditer(rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)', raw_html, re.I):
            bits.append(m.group(1))
    for m in re.finditer(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", raw_html, re.S | re.I):
        bits.append(m.group(1)[:2000])
    return html.unescape("\n".join(bits))


async def fetch_text(client: httpx.AsyncClient, url: str) -> str:
    try:
        r = await client.get(url, timeout=8, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 FirstIn/0.1"})
        raw = r.text
    except Exception:
        return ""
    text = ""
    try:
        import trafilatura
        text = trafilatura.extract(raw, include_comments=False) or ""
    except Exception:
        pass
    if len(text) < 200:
        text = (text + "\n" + _meta(raw)).strip()
    return text[:MAX_CHARS]


def source_of(url: str) -> str:
    u = url.lower()
    for key, name in (("lu.ma", "luma"), ("luma.com", "luma"), ("meetup.com", "meetup"), ("eventbrite", "eventbrite")):
        if key in u:
            return name
    return "company site"


async def extract_event(client: httpx.AsyncClient, cand: dict, sem: asyncio.Semaphore) -> dict | None:
    """Extracted event + the page text used (kept for the grounding check), or None."""
    async with sem:
        text = await fetch_text(client, cand["url"])
        if len(text) < 80:  # nothing useful on the page: fall back to the search snippet
            text = f"{cand.get('title', '')}\n{cand.get('snippet', '')}"
        user = f"URL: {cand['url']}\nSEARCH TITLE: {cand.get('title', '')}\nSEARCH SNIPPET: {cand.get('snippet', '')}\n\nPAGE TEXT:\n{text}"
        try:
            data = await aclaude_json(SYSTEM, user, model=HAIKU, max_tokens=1500, effort="low")
        except Exception as e:
            print(f"[events.extract] {cand['url']}: {e}")
            return None
    if not isinstance(data, dict):
        return None
    data.update(url=cand["url"], source=source_of(cand["url"]), _page_text=text, _query_company=cand.get("company"))
    return data
