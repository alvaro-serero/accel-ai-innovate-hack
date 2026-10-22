"""Company research for the picked jobs: 2 Keenable searches -> Haiku 2-sentence brief with cited URLs.

search_company  Keenable only, never raises (returns [] on any failure)
write_brief     LLM only, takes plain search results (testable without Keenable)
research_company / research_companies  add the per-day in-memory cache
"""
import asyncio
from datetime import date

from backend.app.config import settings
from backend.app.llm import HAIKU, aclaude_json
from backend.app.schemas import CompanyBrief
from backend.app.search import akeenable_search

QUERIES = ["{company} funding 2026", "{company} engineering team news"]
RESULTS_PER_QUERY = 5
SNIPPET_CHARS = 400

BRIEF_SYSTEM = """You brief a student who is about to apply for an internship at a company.
From the web search results only, write exactly 2 sentences about the company:
recent funding or growth, and news about its engineering or product team.
Use only facts stated in the results. If the results say nothing useful about this company, return an empty summary.
Return {"summary": "...", "sources": ["url of every result you used"]}
Only cite URLs that appear in the results."""

# (company lowercased, today's date) -> brief. Only successes are cached, so a Keenable outage retries next run.
_CACHE: dict[tuple[str, str], CompanyBrief] = {}


# ---------- Keenable ----------


async def search_company(company: str) -> list[dict]:
    if not settings.keenable_api_key:
        return []
    queries = [q.format(company=company) for q in QUERIES]
    answers = await asyncio.gather(*(akeenable_search(q) for q in queries), return_exceptions=True)
    results, seen = [], set()
    for answer in answers:
        if isinstance(answer, Exception):  # timeout, 401, bad JSON...: skip that query
            continue
        for r in answer[:RESULTS_PER_QUERY]:
            if r["url"] not in seen:
                seen.add(r["url"])
                results.append(r)
    return results


# ---------- LLM ----------


def results_text(results: list[dict]) -> str:
    return "\n\n".join(f"URL: {r['url']}\nTITLE: {r['title']}\n{r['snippet'][:SNIPPET_CHARS]}" for r in results)


async def write_brief(company: str, results: list[dict]) -> CompanyBrief | None:
    """None when there is nothing to say or no valid citation."""
    if not results:
        return None
    try:
        out = await aclaude_json(
            BRIEF_SYSTEM, f"COMPANY: {company}\n\nSEARCH RESULTS:\n{results_text(results)}",
            model=HAIKU, max_tokens=1000, effort="low",
        )
    except Exception:
        return None
    allowed = {r["url"] for r in results}
    sources = [u for u in out.get("sources") or [] if u in allowed]  # drop any URL not in the results
    summary = (out.get("summary") or "").strip()
    if not summary or not sources:
        return None
    return CompanyBrief(summary=summary, sources=sources)


# ---------- cache + batch ----------


async def research_company(company: str) -> CompanyBrief | None:
    key = (company.lower(), date.today().isoformat())
    if key in _CACHE:
        return _CACHE[key]
    brief = await write_brief(company, await search_company(company))
    if brief is not None:
        _CACHE[key] = brief
    return brief


async def research_companies(companies: list[str]) -> dict[str, CompanyBrief | None]:
    names = list(dict.fromkeys(companies))  # unique, keep order
    briefs = await asyncio.gather(*(research_company(c) for c in names))
    return dict(zip(names, briefs))
