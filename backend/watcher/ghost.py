"""Ghost job score: 0 = fresh, 1 = likely nobody is hiring. Owner: Leo.

Rules (from PLAN.md), each with a readable reason:
  older than 120 days +0.6, else older than 60 days +0.4   (age from published_at, else first_seen_at)
  reposted +0.3
  generic title ("spontaneous application", "talent pool", ...) +0.5
  no source update in 90 days +0.2
Capped at 1. Pure: pass `now` in.
"""
from __future__ import annotations

import re
from datetime import datetime

GHOST_THRESHOLD = 0.6

GENERIC_TITLE_RE = re.compile(
    r"spontaneous|spontan[ée]e|general application|open application|talent pool|talent community|"
    r"candidature spontan[ée]e|candidatures? libres?|future opportunit",
    re.IGNORECASE,
)


def _days_since(then: datetime | None, now: datetime) -> int | None:
    if then is None:
        return None
    return max(0, int((now - then).total_seconds() // 86400))


def ghost_score(
    *,
    title: str | None,
    published_at: datetime | None,
    first_seen_at: datetime | None,
    source_updated_at: datetime | None,
    repost_count: int | None,
    now: datetime,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    age = _days_since(published_at or first_seen_at, now)
    if age is not None and age > 120:
        score += 0.6
        reasons.append(f"Posted {age} days ago")
    elif age is not None and age > 60:
        score += 0.4
        reasons.append(f"Posted {age} days ago")

    if repost_count and repost_count > 0:
        score += 0.3
        reasons.append(f"Reposted {repost_count} time{'s' if repost_count > 1 else ''} in the last 60 days")

    match = GENERIC_TITLE_RE.search(title or "")
    if match:
        score += 0.5
        reasons.append(f"Generic title ('{match.group(0)}')")

    stale = _days_since(source_updated_at, now)
    if stale is not None and stale > 90:
        score += 0.2
        reasons.append(f"Not updated by the company in {stale} days")

    return round(min(score, 1.0), 2), reasons
