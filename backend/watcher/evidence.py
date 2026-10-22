"""Freshness and ghost numbers for the benchmark deliverable. Owner: Leo.

    python -m backend.watcher.evidence

Prints JSON and writes backend/watcher/results/watcher_evidence.json (Taleb merges it into results.json).
"New" postings exclude each company's first poll (its baseline snapshot).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.app.db import fetch_all, fetch_one
from backend.watcher.ghost import GHOST_THRESHOLD

OUT_FILE = Path(__file__).resolve().parent / "results" / "watcher_evidence.json"

_NEW_EVENTS = """
select e.job_id, e.kind, e.at, j.published_at, j.first_seen_at, j.is_internship
from job_events e join jobs j on j.id = e.job_id
where e.kind in ('opened', 'reposted')
  and coalesce((e.detail->>'baseline')::boolean, false) = false
  and coalesce((e.detail->>'reopened')::boolean, false) = false
"""

_OPEN_INTERNSHIPS = """
select j.id, c.name as company, j.title, j.url, j.ghost_score, j.ghost_reasons,
       j.first_seen_at, coalesce(j.published_at, j.first_seen_at) as age_ref
from jobs j join companies c on c.id = j.company_id
where j.closed_at is null and j.is_internship
"""


def _percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile, q in 0..1."""
    if not values:
        return None
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _r1(x: float | None) -> float | None:
    return None if x is None else round(x, 1)


def compute(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)

    totals = fetch_one(
        """
        select (select count(*) from companies) as companies,
               (select count(*) from companies where last_polled_at is not null) as companies_polled,
               (select count(*) from jobs) as jobs_seen,
               (select count(*) from jobs where closed_at is null) as jobs_open,
               (select min(first_seen_at) from jobs) as first_poll_at,
               (select max(last_polled_at) from companies) as last_poll_at
        """
    )
    events = {r["kind"]: r["n"] for r in fetch_all("select kind, count(*) as n from job_events group by kind")}

    new = fetch_all(_NEW_EVENTS)
    lags = [
        max(0.0, (r["first_seen_at"] - r["published_at"]).total_seconds() / 3600)
        for r in new if r["published_at"] is not None
    ]
    intern_lags = [
        max(0.0, (r["first_seen_at"] - r["published_at"]).total_seconds() / 3600)
        for r in new if r["published_at"] is not None and r["is_internship"]
    ]

    interns = fetch_all(_OPEN_INTERNSHIPS)
    ghosts = [r for r in interns if r["ghost_score"] is not None and r["ghost_score"] >= GHOST_THRESHOLD]
    buckets = {"0-30": 0, "31-60": 0, "61-120": 0, "120+": 0}
    for r in interns:
        age = max(0, int((now - r["age_ref"]).total_seconds() // 86400)) if r["age_ref"] else 0
        key = "0-30" if age <= 30 else "31-60" if age <= 60 else "61-120" if age <= 120 else "120+"
        buckets[key] += 1
    top = sorted(
        (r for r in interns if r["ghost_score"] is not None),
        key=lambda r: (-r["ghost_score"], r["first_seen_at"]),
    )[:3]

    return {
        "computed_at": now.isoformat(),
        "source": "live database",
        "watched": {
            "companies": totals["companies"],
            "companies_polled": totals["companies_polled"],
            "jobs_seen": totals["jobs_seen"],
            "jobs_open": totals["jobs_open"],
            "first_poll_at": totals["first_poll_at"].isoformat() if totals["first_poll_at"] else None,
            "last_poll_at": totals["last_poll_at"].isoformat() if totals["last_poll_at"] else None,
            "events": events,
        },
        "freshness": {
            "new_postings_detected": len(new),
            "new_internships_detected": sum(1 for r in new if r["is_internship"]),
            "with_published_at": len(lags),
            "lag_hours_median": _r1(_percentile(lags, 0.5)),
            "lag_hours_p90": _r1(_percentile(lags, 0.9)),
            "internship_lag_hours_median": _r1(_percentile(intern_lags, 0.5)),
        },
        "ghost": {
            "threshold": GHOST_THRESHOLD,
            "open_internships": len(interns),
            "flagged": len(ghosts),
            "flagged_pct": _r1(100 * len(ghosts) / len(interns)) if interns else None,
            "age_days_buckets": buckets,
            "examples": [
                {"company": r["company"], "title": r["title"], "url": r["url"],
                 "ghost_score": round(r["ghost_score"], 2), "ghost_reasons": r["ghost_reasons"]}
                for r in top
            ],
        },
    }


def main() -> int:
    try:
        result = compute()
    except Exception as exc:  # noqa: BLE001
        print(f"error: database failure ({exc})", file=sys.stderr)
        return 1
    text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
