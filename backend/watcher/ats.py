"""ATS fetchers for Greenhouse, Lever and Ashby. Owner: Leo.

Every fetcher returns a list of normalised postings, dicts with exactly the keys in POSTING_KEYS.
Parsing is pure (parse_greenhouse / parse_lever / parse_ashby take decoded JSON and never touch
the network), the HTTP part lives in fetch_board.

Check one board by hand (prints the count and the first normalised posting):

    python -m backend.watcher.ats greenhouse datadog
    python -m backend.watcher.ats ashby photoroom --raw
"""
from __future__ import annotations

import asyncio
import html
import json
import re
import ssl
import sys
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

ATS_VALUES = ("greenhouse", "lever", "ashby")
TIMEOUT = 10.0
USER_AGENT = "FirstIn-watcher/0.1 (student hackathon project)"

POSTING_KEYS = (
    "ats_job_id",
    "title",
    "location",
    "remote",
    "employment_type",
    "url",
    "description",
    "published_at",
    "source_updated_at",
)

# Tried in order. A 404 (or, for Lever, an empty list) moves on to the next URL.
BOARD_URLS = {
    "greenhouse": ("https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",),
    "lever": (
        "https://api.lever.co/v0/postings/{slug}?mode=json",
        "https://api.eu.lever.co/v0/postings/{slug}?mode=json",
    ),
    "ashby": ("https://api.ashbyhq.com/posting-api/job-board/{slug}",),
}
# Same boards without descriptions: much lighter, used by discovery to probe slugs.
LIGHT_BOARD_URLS = {
    **BOARD_URLS,
    "greenhouse": ("https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",),
}
FALLBACK_ON_EMPTY = {"lever"}


class ATSError(Exception):
    """A board could not be fetched or parsed. The message names the ATS, slug and cause."""

    def __init__(self, ats: str, slug: str, cause: str):
        super().__init__(f"{ats}/{slug}: {cause}")
        self.ats = ats
        self.slug = slug
        self.cause = cause


# ---------- small pure helpers ----------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)


def html_to_text(raw) -> str | None:
    """Unescape (Greenhouse double-escapes its HTML), drop tags, collapse whitespace."""
    if not raw:
        return None
    text = html.unescape(str(raw))
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    return text or None


def parse_iso(value) -> datetime | None:
    """ISO 8601 string -> aware UTC datetime, or None."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_epoch_ms(value) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _join_locations(*values) -> str | None:
    seen: list[str] = []
    for v in values:
        v = _str(v)
        if v and v not in seen:
            seen.append(v)
    return "; ".join(seen) or None


def _posting(**fields) -> dict:
    return {key: fields.get(key) for key in POSTING_KEYS}


def _items(data, ats: str) -> list:
    if ats == "lever":
        if not isinstance(data, list):
            raise ValueError("unexpected payload shape (expected a list)")
        return data
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("unexpected payload shape (expected an object with a 'jobs' list)")
    return data["jobs"]


# ---------- parsers (pure) ----------


def _greenhouse_employment_type(metadata) -> str | None:
    """Greenhouse has no standard field; boards often expose it as custom metadata."""
    if not isinstance(metadata, list):
        return None
    for m in metadata:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name") or "").lower()
        if any(k in name for k in ("time type", "employment", "contract", "job type")):
            value = m.get("value")
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value if v)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def parse_greenhouse(data) -> list[dict]:
    out = []
    for job in _items(data, "greenhouse"):
        if not isinstance(job, dict):
            continue
        job_id, title = _str(job.get("id")), _str(job.get("title"))
        if not job_id or not title:
            continue
        loc = job.get("location")
        location = _str(loc.get("name")) if isinstance(loc, dict) else None
        out.append(
            _posting(
                ats_job_id=job_id,
                title=title,
                location=location,
                remote=bool(location and _REMOTE_RE.search(location)),
                employment_type=_greenhouse_employment_type(job.get("metadata")),
                url=_str(job.get("absolute_url")),
                description=html_to_text(job.get("content")),
                published_at=parse_iso(job.get("first_published")),
                source_updated_at=parse_iso(job.get("updated_at")),
            )
        )
    return out


def _lever_description(job: dict) -> str | None:
    """descriptionPlain is only the intro; the requirements live in `lists`."""
    parts = [_str(job.get("descriptionPlain"))]
    for block in job.get("lists") or []:
        if isinstance(block, dict):
            heading = _str(block.get("text"))
            body = html_to_text(block.get("content"))
            parts.append(" ".join(p for p in (heading, body) if p) or None)
    parts.append(_str(job.get("additionalPlain")))
    text = "\n\n".join(p for p in parts if p)
    return text or None


def parse_lever(data) -> list[dict]:
    out = []
    for job in _items(data, "lever"):
        if not isinstance(job, dict):
            continue
        job_id, title = _str(job.get("id")), _str(job.get("text"))
        if not job_id or not title:
            continue
        cats = job.get("categories") if isinstance(job.get("categories"), dict) else {}
        all_locs = cats.get("allLocations") if isinstance(cats.get("allLocations"), list) else []
        location = _join_locations(cats.get("location"), *all_locs)
        workplace = str(job.get("workplaceType") or "").lower()
        out.append(
            _posting(
                ats_job_id=job_id,
                title=title,
                location=location,
                remote=workplace == "remote",
                employment_type=_str(cats.get("commitment")),
                url=_str(job.get("hostedUrl")),
                description=_lever_description(job),
                published_at=parse_epoch_ms(job.get("createdAt")),
                source_updated_at=None,
            )
        )
    return out


def parse_ashby(data) -> list[dict]:
    out = []
    for job in _items(data, "ashby"):
        if not isinstance(job, dict) or job.get("isListed") is False:
            continue
        job_id, title = _str(job.get("id")), _str(job.get("title"))
        if not job_id or not title:
            continue
        secondary = [
            s.get("location") for s in job.get("secondaryLocations") or [] if isinstance(s, dict)
        ]
        # isRemote is true for hybrid roles too, so trust workplaceType when it is there.
        workplace = _str(job.get("workplaceType"))
        if workplace:
            remote = workplace.lower() == "remote"
        elif isinstance(job.get("isRemote"), bool):
            remote = job["isRemote"]
        else:
            remote = None
        out.append(
            _posting(
                ats_job_id=job_id,
                title=title,
                location=_join_locations(job.get("location"), *secondary),
                remote=remote,
                employment_type=_str(job.get("employmentType")),
                url=_str(job.get("jobUrl")),
                description=_str(job.get("descriptionPlain")) or html_to_text(job.get("descriptionHtml")),
                published_at=parse_iso(job.get("publishedAt")),
                source_updated_at=parse_iso(job.get("updatedAt")),
            )
        )
    return out


PARSERS = {"greenhouse": parse_greenhouse, "lever": parse_lever, "ashby": parse_ashby}


def parse_board(ats: str, data) -> list[dict]:
    return PARSERS[ats](data)


# ---------- HTTP ----------


def ssl_context() -> ssl.SSLContext | bool:
    """Use the OS trust store when `truststore` is installed (laptops behind TLS inspection),
    otherwise httpx's default certifi bundle (the Docker image)."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return True


def make_client(max_connections: int = 20) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        verify=ssl_context(),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_connections),
    )


RETRY_TIMEOUT = 25.0  # one slower second try: some boards (Lever EU) are slow under load


async def _get(client: httpx.AsyncClient, ats: str, slug: str, url: str) -> httpx.Response:
    target = url.format(slug=quote(slug, safe=""))
    try:
        try:
            return await client.get(target)
        except httpx.TimeoutException:
            return await client.get(target, timeout=RETRY_TIMEOUT)
    except httpx.TimeoutException as exc:
        raise ATSError(ats, slug, "timeout") from exc
    except httpx.HTTPError as exc:
        raise ATSError(ats, slug, f"connection failure ({type(exc).__name__})") from exc


async def fetch_raw(client: httpx.AsyncClient, ats: str, slug: str, light: bool = False):
    """Decoded JSON of a board, following the fallback URLs. Raises ATSError."""
    if ats not in ATS_VALUES:
        raise ATSError(ats, slug, f"unsupported ats {ats!r}")
    urls = (LIGHT_BOARD_URLS if light else BOARD_URLS)[ats]
    empty_payload = None
    last_status = None
    for i, url in enumerate(urls):
        resp = await _get(client, ats, slug, url)
        if resp.status_code == 404:
            last_status = 404
            continue
        if not resp.is_success:
            raise ATSError(ats, slug, f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise ATSError(ats, slug, "invalid JSON") from exc
        if ats in FALLBACK_ON_EMPTY and data == [] and i < len(urls) - 1:
            empty_payload = data
            continue
        return data
    if empty_payload is not None:
        return empty_payload
    raise ATSError(ats, slug, f"HTTP {last_status}")


async def fetch_board(client: httpx.AsyncClient, ats: str, slug: str) -> list[dict]:
    data = await fetch_raw(client, ats, slug)
    try:
        return parse_board(ats, data)
    except ValueError as exc:
        raise ATSError(ats, slug, str(exc)) from exc


# ---------- CLI ----------


async def _main(ats: str, slug: str, raw: bool) -> None:
    async with make_client() as client:
        if raw:
            data = await fetch_raw(client, ats, slug)
            items = data if isinstance(data, list) else data.get("jobs", [])
            print(f"{len(items)} raw postings")
            if items:
                print(json.dumps(items[0], indent=2, default=str)[:4000])
            return
        postings = await fetch_board(client, ats, slug)
    print(f"{len(postings)} postings on {ats}/{slug}")
    if postings:
        first = dict(postings[0])
        if first["description"]:
            first["description"] = first["description"][:300] + "..."
        print(json.dumps(first, indent=2, default=str))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: python -m backend.watcher.ats <greenhouse|lever|ashby> <slug> [--raw]")
    asyncio.run(_main(sys.argv[1], sys.argv[2], "--raw" in sys.argv))
