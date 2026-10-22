"""Find candidate event pages with Keenable web search. Owner: Taleb."""
import asyncio
import re
from datetime import date

from backend.app.search import akeenable_search

MAX_CANDIDATES = 40


def build_queries(companies: list[str], city: str) -> list[tuple[str, str | None]]:
    """(query, company it targets). ~6 per company + 2 generic per user."""
    year = date.today().year
    out: list[tuple[str, str | None]] = []
    for c in companies:
        out += [
            (f"{c} meetup {city} {year}", c),
            (f"{c} hackathon {city}", c),
            (f"{c} career fair students {city}", c),
            (f"site:lu.ma {c} {city}", c),
            (f"site:meetup.com {c} {city}", c),
            (f"site:eventbrite.fr {c}", c),
        ]
    out += [(f"forum entreprises ingénieurs {city} {year}", None), (f"salon stage {city} {year}", None)]
    return out


def _norm_url(url: str) -> str:
    return re.sub(r"[?#].*$", "", url.strip()).rstrip("/").lower()


async def search_events(companies: list[str], city: str) -> list[dict]:
    """Deduplicated candidates: {url, title, snippet, query, company}, capped at MAX_CANDIDATES."""
    sem = asyncio.Semaphore(6)

    async def one(q: str, comp: str | None) -> list[dict]:
        async with sem:
            try:
                return [dict(hit, query=q, company=comp) for hit in await akeenable_search(q)]
            except Exception as e:  # one failing query must not kill the radar
                print(f"[events.search] {q!r}: {e}")
                return []

    batches = await asyncio.gather(*(one(q, c) for q, c in build_queries(companies, city)))
    seen, out = set(), []
    # round-robin across queries so one noisy query does not fill the cap
    for i in range(max((len(b) for b in batches), default=0)):
        for b in batches:
            if i < len(b):
                key = _norm_url(b[i]["url"])
                if key not in seen:
                    seen.add(key)
                    out.append(b[i])
    return out[:MAX_CANDIDATES]
