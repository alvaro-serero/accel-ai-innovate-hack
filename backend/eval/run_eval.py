"""Evidence CLI. Run from the repo root:

  python -m backend.eval.run_eval sheet --user 1                 # agent (latest run) vs keyword baseline
  python -m backend.eval.run_eval sheet --user 1 --memory        # after 3 thumbs-down + rerun: agent + memory
  python -m backend.eval.run_eval label --user 1                 # blind labelling, 2 minutes, y/n
  python -m backend.eval.run_eval judge --user 1                 # OpenAI judge + agreement with human labels
  python -m backend.eval.run_eval label-events --user 1          # verified events vs raw search top 10
  python -m backend.eval.run_eval compile                        # results.json, results.md, chart.png

Labels live in backend/eval/labels/user<id>.json (sources hidden while labelling).
"""
import argparse
import json
import os
import random
import statistics
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from backend.app.db import fetch_all, fetch_one
from backend.eval.baseline import agent_picks, keyword_alert, latest_run_id

HERE = Path(__file__).resolve().parent
LABELS = Path(os.getenv("EVAL_LABELS_DIR") or HERE / "labels")    # simulate.py points these to sim/ folders
RESULTS = Path(os.getenv("EVAL_RESULTS_DIR") or HERE / "results")
LABELS.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)


def load(user_id: int) -> dict:
    p = LABELS / f"user{user_id}.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    for k in ("sets", "runs", "jobs", "human", "judge", "events_human", "events_sets"):
        d.setdefault(k, {})
    return d


def save(user_id: int, d: dict):
    (LABELS / f"user{user_id}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def remember_jobs(d: dict, rows: list[dict]):
    for r in rows:
        d["jobs"][str(r["id"])] = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()}


# ------------------------------------------------------------------ commands

def cmd_sheet(a):
    d = load(a.user)
    run_id = a.run or latest_run_id(a.user)
    if not run_id:
        raise SystemExit("No run with matches for this user yet: trigger a run first.")
    agent = agent_picks(a.user, run_id)
    key = "agent_memory" if a.memory else "agent"
    d["sets"][key] = [r["id"] for r in agent]
    d["runs"][key] = run_id
    remember_jobs(d, agent)
    if not a.memory or "baseline" not in d["sets"]:
        base = keyword_alert(a.user)
        d["sets"]["baseline"] = [r["id"] for r in base]
        remember_jobs(d, base)
    save(a.user, d)
    print(f"user {a.user}: {key}={d['sets'][key]} (run {run_id}), baseline={d['sets'].get('baseline')}")


def ask(prompt: str) -> bool:
    while True:
        v = input(prompt).strip().lower()
        if v in ("y", "o", "yes", "oui", "1"):
            return True
        if v in ("n", "no", "non", "0"):
            return False


def cmd_label(a):
    d = load(a.user)
    todo = sorted({j for s in d["sets"].values() for j in s} - {int(k) for k in d["human"]})
    random.shuffle(todo)  # blind: sources are hidden and mixed
    print(f"{len(todo)} postings to label. Would you apply? y/n\n")
    for i, jid in enumerate(todo, 1):
        j = d["jobs"][str(jid)]
        desc = textwrap.shorten((j.get("description") or "").replace("\n", " "), 350)
        print(f"[{i}/{len(todo)}] {j['title']} — {j['company']} ({j.get('city') or 'remote'})\n    {j.get('url')}\n    {desc}")
        d["human"][str(jid)] = ask("    would apply? (y/n) ")
        save(a.user, d)
        print()
    print("Done.")


def cmd_judge(a):
    from backend.eval.judge import judge_job, student_context
    d = load(a.user)
    ctx = student_context(a.user)
    ids = sorted({j for s in d["sets"].values() for j in s})
    for jid in ids:
        if str(jid) in d["judge"] and not a.force:
            continue
        r = judge_job(ctx, d["jobs"][str(jid)])
        d["judge"][str(jid)] = {"would_apply": bool(r.get("would_apply")), "score": r.get("score"), "why": r.get("why")}
        save(a.user, d)
        print(f"{d['jobs'][str(jid)]['title'][:60]:60} judge={d['judge'][str(jid)]['would_apply']}")
    both = [k for k in d["judge"] if k in d["human"]]
    if both:
        agree = sum(d["judge"][k]["would_apply"] == d["human"][k] for k in both) / len(both)
        print(f"Agreement with human labels: {agree:.0%} on {len(both)} postings")


def cmd_label_events(a):
    raw_path = RESULTS / f"events_raw_user{a.user}.json"
    if not raw_path.exists():
        raise SystemExit("Run POST /api/users/{id}/events/refresh first.")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    d = load(a.user)
    raw_top = [c["url"] for c in raw["candidates"][:10]]
    agent = [x["url"] for x in raw["decisions"] if x.get("verified")][:10]
    d["events_sets"] = {"raw": raw_top, "agent": agent}
    titles = {c["url"]: c.get("title") for c in raw["candidates"]} | {x["url"]: x.get("title") for x in raw["decisions"]}
    snippets = {c["url"]: c.get("snippet") or "" for c in raw["candidates"]}
    todo = [u for u in dict.fromkeys(raw_top + agent) if u not in d["events_human"]]
    random.shuffle(todo)  # blind: you don't know which list a page comes from
    print("Open each link if needed. Answer y only if ALL are true: a REAL event, UPCOMING (<90 days),")
    print("REACHABLE (your city), and one of YOUR target companies is REALLY involved. Otherwise n.\n")
    for i, u in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {titles.get(u) or ''}\n    {u}\n    {textwrap.shorten(snippets.get(u, '').replace(chr(10), ' '), 220)}")
        d["events_human"][u] = ask("    good event? (y/n) ")
        save(a.user, d)
    print("Done.")


# ------------------------------------------------------------------ compile

def precision(ids: list, labels: dict) -> float | None:
    vals = [labels[str(i)] for i in ids if str(i) in labels]
    return round(sum(vals) / len(vals), 3) if vals else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 3) if xs else None


def freshness_and_ghost() -> tuple[dict, dict]:
    first = fetch_one("select min(at) as t from job_events")
    t0 = first["t"] if first else None
    fresh = {"companies_watched": fetch_one("select count(*) as n from companies where last_polled_at is not null")["n"],
             "jobs_open": fetch_one("select count(*) as n from jobs where closed_at is null")["n"],
             "internships_open": fetch_one("select count(*) as n from jobs where closed_at is null and is_internship")["n"],
             "watching_since": t0.isoformat() if t0 else None}
    if t0:
        # A posting is "new" only if it appeared after the first poll of ITS company: companies added
        # later would otherwise count their whole backlog (old postings) as fresh detections.
        newly_opened = """with first_poll as (select company_id, min(first_seen_at) as t from jobs group by company_id)
                          select j.* from jobs j join first_poll f on f.company_id = j.company_id
                          where j.first_seen_at > f.t + interval '15 minutes'"""
        new = fetch_one(f"select count(*) as n, count(*) filter (where is_internship) as ni from ({newly_opened}) x")
        lag = fetch_one(f"""select percentile_cont(0.5) within group (order by extract(epoch from (first_seen_at - published_at)) / 60) as med,
                                   count(*) as n
                            from ({newly_opened}) x where published_at is not null and first_seen_at >= published_at""")
        changes = fetch_all("""select kind, count(*) as n from job_events where at > %s + interval '15 minutes' group by kind""", (t0,))
        fresh.update({"postings_detected": new["n"], "internships_opened_since_first_poll": new["ni"],
                      "median_lag_hours": round(lag["med"] / 60, 2) if lag and lag["med"] is not None else None,
                      "lag_sample_size": lag["n"] if lag else 0,
                      "events_since_first_poll": {r["kind"]: r["n"] for r in changes}})
    g = fetch_one("""select count(*) as n, count(*) filter (where ghost_score >= 0.6) as ghosts
                     from jobs where closed_at is null and is_internship""")
    examples = fetch_all("""select j.title, c.name as company, j.ghost_score, j.ghost_reasons, j.published_at, j.first_seen_at, j.url
                            from jobs j join companies c on c.id = j.company_id
                            where j.closed_at is null and j.is_internship and j.ghost_score >= 0.6
                            order by j.ghost_score desc limit 3""")
    ghost = {"open_internships": g["n"], "flagged": g["ghosts"],
             "internships_flagged_pct": round(100 * g["ghosts"] / g["n"], 1) if g["n"] else None,
             "examples": [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in e.items()} for e in examples]}
    return fresh, ghost


FUNNEL_STAGES = [  # (stage shown, rejection reason that stops a page at this stage)
    ("pages found by search", None),
    ("readable", "extraction failed"),
    ("is an event page", "not an event page"),
    ("has a date", "no date on the page"),
    ("upcoming (not past)", "date in the past"),
    ("within 90 days", "more than"),
    ("near the student", "not near"),
    ("target company named on the page", "not named on the page"),
    ("not a duplicate", "duplicate"),
]


def events_funnel() -> dict | None:
    """Automatic evidence, no labels needed: how many raw search results survive each plain-code check."""
    files = sorted(RESULTS.glob("events_raw_user*.json"))
    if not files:
        return None
    decisions = [x for p in files for x in json.loads(p.read_text(encoding="utf-8"))["decisions"]]
    remaining, stages, reasons = len(decisions), [], {}
    for stage, reason in FUNNEL_STAGES:
        if reason:
            dropped = sum(1 for x in decisions if not x["verified"] and reason in x["notes"])
            reasons[reason] = dropped
            remaining -= dropped
        stages.append({"stage": stage, "remaining": remaining})
    kept = sum(1 for x in decisions if x["verified"])
    return {"runs": len(files), "pages": len(decisions), "kept": kept,
            "kept_pct": round(100 * kept / len(decisions), 1) if decisions else None,
            "stages": stages, "rejected_by_reason": reasons,
            "method": "Every raw Keenable result goes through the same plain-code checks (no LLM judgement); each rejection is stored with its reason."}


EUROPE_HINTS = ("france", "paris", "europe", "emea", "eu ")


def _job_flags(job: dict, user_city: str) -> dict:
    """Objective problems a student would hit with a posting, read from the database (no LLM, no labels)."""
    from backend.events.verify import same_region
    now = datetime.now(timezone.utc)
    published = job.get("published_at") or job.get("first_seen_at")
    age_days = (now - published).days if published else None
    loc = f"{job.get('city') or ''} {job.get('location') or ''}".lower()
    near = same_region(job.get("city") or job.get("location"), user_city)
    remote_ok = bool(job.get("remote")) and any(h in loc for h in EUROPE_HINTS)
    return {"ghost": (job.get("ghost_score") or 0) >= 0.6,
            "stale_60d": age_days is not None and age_days > 60,
            "off_location": not (near or remote_ok),
            "closed": job.get("closed_at") is not None,
            "age_days": age_days}


def jobs_auto() -> dict | None:
    """Agent top 5 vs keyword-alert top 5 on objective flags, for every user with a labelling sheet."""
    users = sorted(int(p.stem.replace("user", "")) for p in LABELS.glob("user*.json"))
    if not users:
        return None
    totals = {}
    per_user = []
    for u in users:
        d = load(u)
        city = (fetch_one("select city from users where id = %s", (u,)) or {}).get("city") or "Paris"
        row = {"user": u}
        for method, ids in d["sets"].items():
            if not ids:
                continue
            jobs = fetch_all("""select j.id, j.title, j.city, j.location, j.remote, j.ghost_score, j.published_at,
                                       j.first_seen_at, j.closed_at from jobs j where j.id = any(%s)""", (list(ids),))
            flags = [_job_flags(j, city) for j in jobs]
            t = totals.setdefault(method, {"postings": 0, "ghost": 0, "stale_60d": 0, "off_location": 0, "closed": 0, "ages": []})
            t["postings"] += len(flags)
            for k in ("ghost", "stale_60d", "off_location", "closed"):
                t[k] += sum(f[k] for f in flags)
            t["ages"] += [f["age_days"] for f in flags if f["age_days"] is not None]
            row[method] = {k: sum(f[k] for f in flags) for k in ("ghost", "stale_60d", "off_location", "closed")}
        per_user.append(row)
    out = {}
    for method, t in totals.items():
        n = max(1, t["postings"])
        out[method] = {"postings": t["postings"],
                       "ghost_pct": round(100 * t["ghost"] / n, 1), "stale_60d_pct": round(100 * t["stale_60d"] / n, 1),
                       "off_location_pct": round(100 * t["off_location"] / n, 1), "closed_pct": round(100 * t["closed"] / n, 1),
                       "median_age_days": statistics.median(t["ages"]) if t["ages"] else None}
    return {"users": len(users), "by_method": out, "per_user": per_user,
            "method": "Same users, top 5 of each method, flags read from the jobs table: ghost score >= 0.6, published more "
                      "than 60 days ago, not in the student's region nor remote open to France/Europe, closed since."}


def cmd_jobs_auto(a):
    r = jobs_auto()
    if not r:
        raise SystemExit("No labelling sheet yet: run `sheet --user N` first.")
    print(f"{r['users']} students, top 5 of each method\n")
    print(f"{'method':14} {'postings':>8} {'ghost':>7} {'>60 days':>9} {'off-location':>13} {'closed':>7} {'median age':>11}")
    for m, s in r["by_method"].items():
        print(f"{m:14} {s['postings']:>8} {s['ghost_pct']:>6}% {s['stale_60d_pct']:>8}% {s['off_location_pct']:>12}% "
              f"{s['closed_pct']:>6}% {str(s['median_age_days']) + ' d':>11}")


def cmd_events_funnel(a):
    f = events_funnel()
    if not f:
        raise SystemExit("No events_raw_user*.json yet: run a refresh first.")
    print(f"{f['runs']} radar runs, {f['pages']} pages from search -> {f['kept']} events shown ({f['kept_pct']}%)\n")
    for s in f["stages"]:
        print(f"  {s['remaining']:4}  {s['stage']}")
    print("\nrejected by reason:", f["rejected_by_reason"])


def grounding() -> dict:
    rows = fetch_all("select stats from runs where stats is not null order by id desc limit 50")
    kept = dropped = 0
    for r in rows:
        s = r["stats"] if isinstance(r["stats"], dict) else json.loads(r["stats"] or "{}")
        gr = s.get("grounding") or {}
        kept += int(gr.get("kept", s.get("reasons_kept", 0)) or 0)
        dropped += int(gr.get("dropped", s.get("reasons_dropped", 0)) or 0)
    total = kept + dropped
    return {"reasons_checked": total, "reasons_kept": kept, "reasons_dropped": dropped,
            "shown_reasons_verified_pct": 100.0 if kept else None,
            "generated_reasons_verified_pct": round(100 * kept / total, 1) if total else None}


def cmd_compile(a):
    users = sorted(int(p.stem.replace("user", "")) for p in LABELS.glob("user*.json"))
    per_user, agreements, ev_agent, ev_raw = [], [], [], []
    for u in users:
        d = load(u)
        row = {"user": u, **{f"{k}_p5": precision(v, d["human"]) for k, v in d["sets"].items()}}
        both = [k for k in d["judge"] if k in d["human"]]
        if both:
            row["judge_agreement"] = round(sum(d["judge"][k]["would_apply"] == d["human"][k] for k in both) / len(both), 3)
            agreements.append(row["judge_agreement"])
        row["judge_agent_p5"] = precision(d["sets"].get("agent", []), {k: v["would_apply"] for k, v in d["judge"].items()})
        row["judge_baseline_p5"] = precision(d["sets"].get("baseline", []), {k: v["would_apply"] for k, v in d["judge"].items()})
        if d.get("events_sets"):
            ev_agent.append(precision(d["events_sets"].get("agent", []), d["events_human"]))
            ev_raw.append(precision(d["events_sets"].get("raw", []), d["events_human"]))
        per_user.append(row)
    fresh, ghost = freshness_and_ghost()
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_users": len(users),
        "jobs": {"auto": jobs_auto(),
                 "baseline_p5": mean(r.get("baseline_p5") for r in per_user),
                 "agent_p5": mean(r.get("agent_p5") for r in per_user),
                 "with_memory_p5": mean(r.get("agent_memory_p5") for r in per_user),
                 "judge_agent_p5": mean(r.get("judge_agent_p5") for r in per_user),
                 "judge_baseline_p5": mean(r.get("judge_baseline_p5") for r in per_user),
                 "judge_agreement": mean(agreements),
                 "users": len(users),
                 "method": "Blind human labels (would apply? y/n) on the agent's top 5 vs the keyword-alert baseline's top 5, sources hidden and shuffled."},
        "events": {"agent_precision": mean(ev_agent), "raw_precision": mean(ev_raw), "labelled_users": len(ev_agent),
                   "method": "Human labels: real, upcoming within 90 days, reachable, target company really involved.",
                   "funnel": events_funnel()},
        "grounding": grounding(),
        "freshness": fresh,
        "ghost": ghost,
        "per_user": per_user,
        "live": {"freshness": "live", "ghost": "live", "jobs": "labelled during the hackathon", "events": "labelled during the hackathon"},
    }
    (RESULTS / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_md(results)
    chart(results)
    try:
        funnel_chart(results["events"]["funnel"])
    except ImportError:
        pass
    print(json.dumps({k: results[k] for k in ("n_users", "jobs", "events", "grounding")}, indent=2, default=str))
    print(f"\nWritten: {RESULTS / 'results.json'}, results.md, chart.png, events_funnel.png")


def pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def funnel_md(f: dict | None) -> str:
    if not f:
        return "- no radar run yet"
    lines = [f"- {s['remaining']} {s['stage']}" for s in f["stages"]]
    return "\n".join(lines) + f"\n\n{f['pages']} raw search results over {f['runs']} runs -> {f['kept']} events shown ({f['kept_pct']}%)."


def funnel_chart(f: dict | None):
    if not f:
        return
    import matplotlib.pyplot as plt
    stages = f["stages"]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    vals = [s["remaining"] for s in stages]
    ax.barh(range(len(stages)), vals, color=["#9ca3af"] + ["#93c5fd"] * (len(stages) - 2) + ["#2563eb"])
    ax.set_yticks(range(len(stages)), [s["stage"] for s in stages])
    ax.invert_yaxis()
    for i, v in enumerate(vals):
        ax.text(v + max(vals) * 0.01, i, str(v), va="center")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"Events radar: {f['pages']} search results -> {f['kept']} verified events (plain-code checks)")
    fig.tight_layout()
    if RESULTS.name == "sim":
        fig.text(0.5, 0.45, "SIMULATED DATA", ha="center", va="center", fontsize=40, color="#dc2626", alpha=0.3, rotation=15)
    fig.savefig(RESULTS / "events_funnel.png", dpi=160)


def write_md(r: dict):
    j, e, f, g, gr = r["jobs"], r["events"], r["freshness"], r["ghost"], r["grounding"]
    ex = "\n".join(f"- {x['title']} ({x['company']}): ghost score {x['ghost_score']}, {', '.join(x['ghost_reasons'] or [])}" for x in g["examples"]) or "- none"
    md = f"""# FirstIn: evidence

Generated {r['generated_at']} with {r['n_users']} real students (our team, real CVs).

## Match quality (precision@5, blind human labels)
| Method | Precision@5 |
|---|---|
| Keyword alert (title keyword + city, newest first) | {pct(j['baseline_p5'])} |
| FirstIn agent | {pct(j['agent_p5'])} |
| FirstIn agent + memory (after 3 thumbs-down with reasons) | {pct(j['with_memory_p5'])} |

Independent OpenAI judge: agent {pct(j['judge_agent_p5'])} vs baseline {pct(j['judge_baseline_p5'])}; agreement with human labels {pct(j['judge_agreement'])}.

## Grounding
{gr['reasons_checked']} generated reasons checked against the posting or CV text: {gr['reasons_kept']} kept, {gr['reasons_dropped']} dropped. 100% of displayed reasons carry a verified quote.

## Freshness (live)
- Companies watched: {f.get('companies_watched')}; open postings: {f.get('jobs_open')}; open internships: {f.get('internships_open')}
- Postings detected since the first poll: {f.get('postings_detected')} (internships: {f.get('internships_opened_since_first_poll')})
- Median lag between publication and our detection: {f.get('median_lag_hours')} hours

## Ghost jobs (live)
{g['flagged']} of {g['open_internships']} open internships flagged ({g['internships_flagged_pct']}%). Examples:
{ex}

## Events radar
Precision of verified events: {pct(e['agent_precision'])} vs raw search top 10: {pct(e['raw_precision'])} (blind human labels, {e.get('labelled_users', 0)} students).

Filtering funnel (automatic, every check is plain code):
{funnel_md(e.get('funnel'))}

## Limits
Small sample (our team), labels by the users themselves, one day of polling for freshness.
"""
    (RESULTS / "results.md").write_text(md, encoding="utf-8")


def chart(r: dict):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed: skipping chart.png (pip install matplotlib)")
        return
    j, e = r["jobs"], r["events"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [3, 2]})
    labels = ["Keyword alert", "FirstIn", "FirstIn + memory"]
    vals = [j["baseline_p5"], j["agent_p5"], j["with_memory_p5"]]
    cols = ["#9ca3af", "#2563eb", "#1e3a8a"]
    axes[0].bar(labels, [100 * (v or 0) for v in vals], color=cols)
    for i, v in enumerate(vals):
        axes[0].text(i, 100 * (v or 0) + 2, pct(v), ha="center")
    axes[0].set_ylim(0, 110); axes[0].set_title("Internships worth applying to in the top 5"); axes[0].set_ylabel("Precision@5 (%)")
    ev = [e["raw_precision"], e["agent_precision"]]
    axes[1].bar(["Raw search", "Verified radar"], [100 * (v or 0) for v in ev], color=["#9ca3af", "#2563eb"])
    for i, v in enumerate(ev):
        axes[1].text(i, 100 * (v or 0) + 2, pct(v), ha="center")
    axes[1].set_ylim(0, 110); axes[1].set_title("Events that are real, upcoming, nearby")
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"FirstIn evidence ({r['n_users']} students, blind labels)")
    fig.tight_layout()
    if RESULTS.name == "sim":  # never let a simulated chart reach the pitch
        fig.text(0.5, 0.45, "SIMULATED DATA", ha="center", va="center", fontsize=44, color="#dc2626", alpha=0.3, rotation=15)
    fig.savefig(RESULTS / "chart.png", dpi=160)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet"); s.add_argument("--user", type=int, required=True); s.add_argument("--run", type=int); s.add_argument("--memory", action="store_true")
    s = sub.add_parser("label"); s.add_argument("--user", type=int, required=True)
    s = sub.add_parser("judge"); s.add_argument("--user", type=int, required=True); s.add_argument("--force", action="store_true")
    s = sub.add_parser("label-events"); s.add_argument("--user", type=int, required=True)
    sub.add_parser("events-funnel")
    sub.add_parser("jobs-auto")
    sub.add_parser("compile")
    a = p.parse_args()
    {"sheet": cmd_sheet, "label": cmd_label, "judge": cmd_judge, "label-events": cmd_label_events,
     "events-funnel": cmd_events_funnel, "jobs-auto": cmd_jobs_auto, "compile": cmd_compile}[a.cmd](a)


if __name__ == "__main__":
    main()
