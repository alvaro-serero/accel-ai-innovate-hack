"""Plain-code checks on extracted events. No LLM: this is what makes the radar trustworthy."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

HORIZON_DAYS = 90

# cities that count as "near" each user city (same region)
REGIONS = {
    "paris": {"paris", "la defense", "boulogne-billancourt", "issy-les-moulineaux", "saint-denis", "neuilly-sur-seine",
              "levallois-perret", "montrouge", "saclay", "palaiseau", "massy", "velizy-villacoublay", "nanterre",
              "courbevoie", "puteaux", "ivry-sur-seine", "pantin", "rueil-malmaison", "versailles", "station f",
              "ile-de-france", "idf", "jouy-en-josas", "orsay", "cergy", "creteil", "bobigny", "montreuil"},
    "london": {"london", "greater london"},
    "lyon": {"lyon", "villeurbanne"},
}


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 \-]", " ", s)).strip()


def parse_date(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%Y-%m-%dT%H:%M", "%d/%m/%Y"):
        try:
            d = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s[:len(fmt) + 2], fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def same_region(event_city: str | None, user_city: str, venue: str | None = None) -> bool:
    uc, ec = norm(user_city), norm(event_city) + " " + norm(venue)
    near = REGIONS.get(uc, {uc})
    return any(c in ec for c in near) if ec.strip() else False


def dedupe_key(ev: dict) -> str:
    d = parse_date(ev.get("starts_at"))
    return f"{norm(ev.get('title'))[:60]}|{d.date().isoformat() if d else '?'}"


def company_grounded(ev: dict, page_text: str, target_companies: list[str]) -> list[str]:
    """Companies (from the event's list or the user's targets) whose name literally appears in the page text."""
    text = norm(page_text)
    names = {c for c in (ev.get("companies") or []) + list(target_companies or []) if c}
    return sorted(c for c in names if norm(c) and re.search(rf"\b{re.escape(norm(c))}\b", text))


def verify(ev: dict, user_city: str, target_companies: list[str], seen: set, now: datetime | None = None) -> tuple[bool, str, list[str]]:
    """Returns (verified, notes, grounded_companies). Notes explain every rejection."""
    now = now or datetime.now(timezone.utc)
    page = ev.get("_page_text", "")
    if not ev.get("is_event"):
        return False, "rejected: not an event page", []
    start = parse_date(ev.get("starts_at"))
    if not start:
        return False, "rejected: no date on the page", []
    if start < now - timedelta(hours=6):
        return False, f"rejected: date in the past ({start.date()})", []
    if start > now + timedelta(days=HORIZON_DAYS):
        return False, f"rejected: more than {HORIZON_DAYS} days away ({start.date()})", []
    if not same_region(ev.get("city"), user_city, ev.get("venue")):
        return False, f"rejected: not near {user_city} ({ev.get('city') or 'no city'})", []
    grounded = company_grounded(ev, page, target_companies)
    involved_targets = [c for c in grounded if norm(c) in {norm(t) for t in target_companies}]
    if target_companies and not involved_targets and ev.get("_query_company"):
        return False, f"rejected: {ev['_query_company']} not named on the page", grounded
    key = dedupe_key(ev)
    if key in seen:
        return False, "rejected: duplicate", grounded
    seen.add(key)
    return True, f"ok: {start.date()}, {ev.get('city')}, companies on page: {', '.join(grounded) or 'none'}", grounded
