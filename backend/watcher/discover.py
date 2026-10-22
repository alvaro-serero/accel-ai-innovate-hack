"""Company discovery: find Greenhouse / Lever / Ashby boards and write db/companies_seed.csv. Owner: Leo.

Two sources, both validated the same way (a board is kept only if it answers with >= 1 posting):
  1. Keenable `site:` searches on the ATS job hosts, slug cut out of each result URL (needs KEENABLE_API_KEY).
  2. A hand list of ~200 company names, probed with slug variants on all three ATS.

    python -m backend.watcher.discover            # discover, merge into the CSV
    python -m backend.watcher.discover --no-search
    python -m backend.watcher.discover load       # insert the CSV into `companies` (skips existing)
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

from backend.watcher.ats import ATS_VALUES, ATSError, fetch_raw, make_client
from backend.watcher.classify import strip_accents

log = logging.getLogger("watcher.discover")

SEED_FILE = Path(__file__).resolve().parents[2] / "db" / "companies_seed.csv"
SEED_COLUMNS = ["name", "ats", "slug", "hq_city", "tags"]
PROBE_CONCURRENCY = 20

# ---------- hand list: (hq_city, tags, names) ----------

HAND_LIST: list[tuple[str | None, list[str], list[str]]] = [
    ("Paris", ["french-tech"], [
        "Mistral AI", "Hugging Face", "Dust", "Photoroom", "Gladia", "LightOn", "Giskard", "Nabla",
        "H Company", "Kyutai", "Bioptimus", "Owkin", "Shift Technology", "Zelros", "Akur8", "Cosmo Tech",
        "Dataiku", "Mirakl", "Pigment", "Alan", "Qonto", "Pennylane", "Swan", "Ledger", "Sorare",
        "Doctolib", "Contentsquare", "Algolia", "Aircall", "Spendesk", "PayFit", "Swile", "Malt",
        "Lydia", "Sumeria", "Agicap", "Ankorstore", "Back Market", "BlaBlaCar", "Vestiaire Collective",
        "ManoMano", "Exotec", "Ornikar", "Getaround", "Libeo", "Alma", "Brigad", "Side", "Skello",
        "Lucca", "Yousign", "Livestorm", "Front", "Botify", "Didomi", "Sunday", "Partoo", "Planity",
        "Shine", "Indy", "Memo Bank", "Mooncard", "Defacto", "Upflow", "Fygr", "Luko", "Dalma",
        "Descartes Underwriting", "Wakam", "Leocare", "Welcome to the Jungle", "JobTeaser",
        "OpenClassrooms", "Ecovadis", "Ivalua", "Sendinblue", "Brevo", "Hivebrite", "Jellysmack",
        "Voodoo", "Homa", "Deezer", "Criteo", "Ubisoft", "Withings", "Devialet", "Lunii", "Electra",
        "Zenchef", "Moka.care", "Lifen", "Padoa", "Cegid", "Scaleway", "OVHcloud", "Platform.sh",
        "Clever Cloud", "Sinch", "Margo", "Pretto", "Masteos", "Hosman", "Stuart", "Cityscoot",
        "Heetch", "Zity", "Qarnot", "Ynsect", "Innovafeed", "Wandercraft", "Pasqal", "Alice & Bob",
        "Quandela", "Aqemia", "Iktos", "Cardiologs", "Sanofi", "Theodo", "Padok", "Artefact",
        "Ekimetrics", "Sicara", "Hiflow", "Tehtris", "Vade", "Sekoia", "Ledgy", "Spacefill",
        "Shippeo", "Expensya", "Payplug", "Lemon Way", "Treezor", "Mangopay", "Younited", "October",
        "Finfrog", "Cajoo", "Frichti", "La Fourche", "Kard", "Pricemoov", "Tiime", "Matera",
        "Ramify", "Yomoni", "Nalo", "Finary", "Trade Republic", "Bitpanda", "Coinhouse", "Kaiko",
        "Flowdesk", "Morpho", "Zama", "Cryptio", "Mistertemp", "StaffMe", "Comet",
        "Crème de la Crème", "Superprof", "Wooclap", "Sesamm", "Poolside", "Jimini",
        "Weglot", "Rakuten France", "Sigfox", "Believe", "Veepee", "Sezane", "Ulule", "Evaneos",
    ]),
    (None, ["international"], [
        "Datadog", "Stripe", "Airbnb", "Uber", "Spotify", "Snowflake", "Databricks", "MongoDB",
        "Elastic", "Cloudflare", "Twilio", "Zendesk", "HubSpot", "Atlassian", "Figma", "Notion",
        "Canva", "Palantir", "Scale AI", "Anthropic", "OpenAI", "Pinterest", "Lyft", "Coinbase",
        "Ramp", "Brex", "Rippling", "Deel", "Remote", "Okta", "Asana", "Dropbox", "Reddit",
        "Discord", "GitLab", "HashiCorp", "Confluent", "Grafana Labs", "Sentry", "Vercel",
        "Supabase", "ClickHouse", "Perplexity", "Cohere", "Mapbox", "Segment", "Amplitude",
        "Mixpanel", "Intercom", "Docusign", "Gong", "Airtable", "Retool", "Plaid", "Chainalysis",
        "Fivetran", "dbt Labs", "Celonis", "UiPath", "Miro", "Tines", "Personio", "Deliveroo",
        "Synthesia", "ElevenLabs", "DeepL", "Helsing", "Wayve", "Lovable", "n8n", "Aiven",
        "Contentful", "Pipedrive", "Monzo", "Revolut", "N26", "Klarna", "Adyen", "Wise", "Bolt",
        "Glovo", "Black Forest Labs", "Aleph Alpha", "Shopify", "Snyk", "Samsara",
        "Faire", "Instacart", "Robinhood", "Affirm", "Duolingo", "Grammarly", "Webflow",
    ]),
]

ACCEL_PORTFOLIO = {
    "algolia", "swan", "payfit", "celonis", "uipath", "miro", "tines", "personio", "deliveroo",
    "synthesia", "lovable", "spendesk", "sorare",
}

# ---------- slug helpers (pure) ----------

_LEGAL_SUFFIXES = {"ai", "inc", "sas", "sa", "ltd", "gmbh", "labs", "hq", "io", "technologies", "tech"}
_SLUG_OK = re.compile(r"^[A-Za-z0-9_-]{1,100}$")

_URL_PATTERNS = [
    # (ats, host regex)
    ("greenhouse", re.compile(r"^(?:job-)?boards(?:\.eu)?\.greenhouse\.io$")),
    ("greenhouse", re.compile(r"^boards-api\.greenhouse\.io$")),
    ("lever", re.compile(r"^jobs(?:\.eu)?\.lever\.co$")),
    ("ashby", re.compile(r"^jobs\.ashbyhq\.com$")),
]


def extract_board(url: str) -> tuple[str, str] | None:
    """Board URL -> (ats, slug), e.g. 'https://jobs.lever.co/mistral/abc' -> ('lever', 'mistral')."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    segments = [unquote(s) for s in parts.path.split("/") if s]
    for ats, host_re in _URL_PATTERNS:
        if not host_re.match(host):
            continue
        if host.startswith("boards-api."):  # /v1/boards/{slug}/jobs
            slug = segments[2] if len(segments) > 2 and segments[:2] == ["v1", "boards"] else None
        elif ats == "greenhouse" and segments[:1] == ["embed"]:  # /embed/job_board?for={slug}
            slug = (parse_qs(parts.query).get("for") or [None])[0]
        else:
            slug = segments[0] if segments else None
        if not slug or not _SLUG_OK.match(slug):
            return None
        return ats, slug.lower()
    return None


def slug_variants(name: str) -> list[str]:
    """'Mistral AI' -> ['mistralai', 'mistral-ai', 'mistral']."""
    base = strip_accents(name).lower().replace("&", " and ")
    base = re.sub(r"[^a-z0-9\s-]", "", base)
    words = base.replace("-", " ").split()
    if not words:
        return []
    variants: list[str] = []
    for ws in (words, words[:-1] if len(words) > 1 and words[-1] in _LEGAL_SUFFIXES else None):
        if not ws:
            continue
        for v in ("".join(ws), "-".join(ws)):
            if v not in variants:
                variants.append(v)
    return variants


def _tags_for(name: str, tags: list[str]) -> list[str]:
    out = list(tags)
    if any(v in ACCEL_PORTFOLIO for v in slug_variants(name)):
        out.append("accel")
    return out


# ---------- discovery ----------


async def board_size(client: httpx.AsyncClient, ats: str, slug: str) -> int:
    """Number of postings on a board, 0 when it does not exist or fails."""
    try:
        data = await fetch_raw(client, ats, slug, light=True)
    except ATSError:
        return 0
    items = data if isinstance(data, list) else data.get("jobs") if isinstance(data, dict) else None
    return len(items) if isinstance(items, list) else 0


SEARCH_HOSTS = ["jobs.lever.co", "jobs.eu.lever.co", "jobs.ashbyhq.com", "boards.greenhouse.io", "job-boards.greenhouse.io"]
SEARCH_TERMS = ["Paris", "intern Paris", "stage Paris", "stagiaire", "internship France", "alternance Paris"]


async def search_candidates() -> dict[tuple[str, str], dict]:
    from backend.app.config import settings
    from backend.app.search import akeenable_search

    if not settings.keenable_api_key:
        log.warning("KEENABLE_API_KEY is not set: skipping search discovery")
        return {}
    found: dict[tuple[str, str], dict] = {}
    failed = 0
    queries = [f"site:{h} {t}" for h in SEARCH_HOSTS for t in SEARCH_TERMS]
    sem = asyncio.Semaphore(4)

    async def run(q: str):
        nonlocal failed
        async with sem:
            try:
                return await akeenable_search(q)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.warning("search failed for %r: %s", q, exc)
                return []

    for results in await asyncio.gather(*(run(q) for q in queries)):
        for r in results:
            board = extract_board(r.get("url") or "")
            if board and board not in found:
                found[board] = {"name": board[1].replace("-", " ").title(), "hq_city": None, "tags": ["search"]}
    print(f"search: {len(queries)} queries, {failed} failed, {len(found)} unique boards")
    return found


def hand_candidates() -> dict[tuple[str, str], dict]:
    found: dict[tuple[str, str], dict] = {}
    names = set()
    for hq_city, tags, group in HAND_LIST:
        for name in group:
            if name.lower() in names:
                continue
            names.add(name.lower())
            for slug in slug_variants(name):
                for ats in ATS_VALUES:
                    found.setdefault((ats, slug), {"name": name, "hq_city": hq_city, "tags": _tags_for(name, tags)})
    print(f"probe: {len(names)} names -> {len(found)} board requests")
    return found


async def validate(candidates: dict[tuple[str, str], dict]) -> dict[tuple[str, str], dict]:
    sem = asyncio.Semaphore(PROBE_CONCURRENCY)
    async with make_client(PROBE_CONCURRENCY) as client:

        async def check(key):
            async with sem:
                return key, await board_size(client, *key)

        results = await asyncio.gather(*(check(k) for k in candidates))
    kept = {k: {**candidates[k], "jobs": n} for k, n in results if n > 0}
    # One board per company: 'mistralai' and 'mistral-ai' may both answer, and companies that
    # moved ATS often keep a stale old board. Keep the board with the most postings.
    best: dict[str, tuple[str, str]] = {}
    for key, info in kept.items():
        group = info["name"].lower()
        if group not in best or info["jobs"] > kept[best[group]]["jobs"]:
            best[group] = key
    return {k: kept[k] for k in best.values()}


def read_seed(path: Path = SEED_FILE) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {
            (r["ats"], r["slug"].lower()): {
                "name": r["name"], "hq_city": r["hq_city"] or None,
                "tags": [t for t in (r["tags"] or "").split(";") if t],
            }
            for r in csv.DictReader(f)
            if r.get("ats") and r.get("slug")
        }


def write_seed(boards: dict[tuple[str, str], dict], path: Path = SEED_FILE) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SEED_COLUMNS)
        for (ats, slug), info in sorted(boards.items()):
            w.writerow([info["name"], ats, slug, info.get("hq_city") or "", ";".join(info.get("tags") or [])])


async def discover(use_search: bool = True, use_probe: bool = True) -> None:
    candidates: dict[tuple[str, str], dict] = {}
    if use_probe:
        candidates.update(hand_candidates())
    if use_search:
        for key, info in (await search_candidates()).items():
            candidates.setdefault(key, info)
    kept = await validate(candidates)
    total_jobs = sum(i["jobs"] for i in kept.values())
    by_ats = {a: sum(1 for k in kept if k[0] == a) for a in ATS_VALUES}
    print(f"kept {len(kept)} boards ({by_ats}), {total_jobs} postings in total")

    boards = read_seed()
    before = len(boards)
    for key, info in kept.items():
        boards.setdefault(key, {k: info[k] for k in ("name", "hq_city", "tags")})
    write_seed(boards)
    print(f"{SEED_FILE.name}: {before} -> {len(boards)} boards")


# ---------- loader ----------


def load_seed(path: Path = SEED_FILE) -> int:
    from backend.app.db import pool

    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 1
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in SEED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            print(f"error: {path.name} is missing columns {missing}", file=sys.stderr)
            return 1
        rows = list(reader)

    valid, invalid, seen = [], 0, set()
    for i, r in enumerate(rows, start=1):
        ats, slug, name = (r["ats"] or "").strip().lower(), (r["slug"] or "").strip(), (r["name"] or "").strip()
        if ats not in ATS_VALUES or not slug or not name:
            print(f"row {i}: skipped (invalid {'ats' if ats not in ATS_VALUES else 'slug' if not slug else 'name'})")
            invalid += 1
            continue
        if (ats, slug.lower()) in seen:
            continue
        seen.add((ats, slug.lower()))
        tags = [t for t in (r["tags"] or "").split(";") if t]
        valid.append((name, ats, slug, (r["hq_city"] or "").strip() or None, tags))

    try:
        with pool().connection() as conn:
            inserted = 0
            for row in valid:
                cur = conn.execute(
                    "insert into companies (name, ats, slug, hq_city, tags) values (%s, %s, %s, %s, %s) "
                    "on conflict (ats, slug) do nothing",
                    row,
                )
                inserted += cur.rowcount
    except Exception as exc:  # noqa: BLE001
        print(f"error: database failure, nothing inserted ({exc})", file=sys.stderr)
        return 1
    print(f"inserted {inserted}, skipped {len(rows) - inserted - invalid} duplicates, {invalid} invalid")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", default="run", choices=["run", "load"])
    parser.add_argument("--no-search", action="store_true", help="skip Keenable searches")
    parser.add_argument("--no-probe", action="store_true", help="skip the hand list")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.command == "load":
        sys.exit(load_seed())
    try:
        import truststore  # Keenable goes through backend.app.search: trust the OS store locally

        truststore.inject_into_ssl()
    except ImportError:
        pass
    asyncio.run(discover(use_search=not args.no_search, use_probe=not args.no_probe))
