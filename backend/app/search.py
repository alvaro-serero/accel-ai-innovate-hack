"""Keenable web search, shared by agent (company research) and events (radar).

    from backend.app.search import keenable_search
    results = keenable_search("Datadog meetup Paris 2026")
    # -> [{"url": ..., "title": ..., "snippet": ...}, ...]

API: POST https://api.keenable.ai/v1/search, header X-API-Key, body {"query": ...}.
The response field names below are a guess: print one raw response (raw=True)
and fix _normalise if needed. Taleb checks this first.
"""
import httpx

from backend.app.config import settings

KEENABLE_URL = "https://api.keenable.ai/v1/search"


def _normalise(data) -> list[dict]:
    items = data
    if isinstance(data, dict):
        for key in ("results", "data", "items", "organic", "web"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        out.append(
            {
                "url": it.get("url") or it.get("link"),
                "title": it.get("title") or "",
                "snippet": it.get("snippet") or it.get("description") or it.get("content") or "",
            }
        )
    return [r for r in out if r["url"]]


def keenable_search(query: str, raw: bool = False, timeout: float = 15.0):
    resp = httpx.post(
        KEENABLE_URL,
        headers={"X-API-Key": settings.keenable_api_key, "Content-Type": "application/json"},
        json={"query": query},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if raw else _normalise(data)


async def akeenable_search(query: str, timeout: float = 15.0) -> list[dict]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            KEENABLE_URL,
            headers={"X-API-Key": settings.keenable_api_key, "Content-Type": "application/json"},
            json={"query": query},
        )
        resp.raise_for_status()
        return _normalise(resp.json())
