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
import random
import statistics
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from backend.app.db import fetch_all, fetch_one
from backend.eval.baseline import agent_picks, keyword_alert, latest_run_id

HERE = Path(__file__).resolve().parent
LABELS = HERE / "labels"
RESULTS = HERE / "results"
LABELS.mkdir(exist_ok=True)
RESULTS.mkdir(exist_ok=True)


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
    todo = [u for u in dict.fromkeys(raw_top + agent) if u not in d["events_human"]]
    random.shuffle(todo)
    print("Is this a REAL event, UPCOMING (<90 days), REACHABLE (your city) and is the target company REALLY involved? y/n\n")
    for i, u in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {titles.get(u) or ''}\n    {u}")
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
        new = fetch_one("""select count(*) as n, count(*) filter (where j.is_internship) as ni
                           from job_events e join jobs j on j.id = e.job_id
                           where e.kind = 'opened' and e.at > %s + interval '15 minutes'""", (t0,))
        lag = fetch_one("""select percentile_cont(0.5) within group (order by extract(epoch from (j.first_seen_at - j.published_at)) / 60) as med
                           from jobs j where j.published_at is not null and j.first_seen_at > %s + interval '15 minutes'
                             and j.first_seen_at >= j.published_at""", (t0,))
        changes = fetch_all("""select kind, count(*) as n from job_events where at > %s + interval '15 minutes' group by kind""", (t0,))
        fresh.update({"postings_detected": new["n"], "internships_opened_since_first_poll": new["ni"],
                      "median_lag_hours": round(lag["med"] / 60, 2) if lag and lag["med"] is not None else None,
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
        "jobs": {"baseline_p5": mean(r.get("baseline_p5") for r in per_user),
                 "agent_p5": mean(r.get("agent_p5") for r in per_user),
                 "with_memory_p5": mean(r.get("agent_memory_p5") for r in per_user),
                 "judge_agent_p5": mean(r.get("judge_agent_p5") for r in per_user),
                 "judge_baseline_p5": mean(r.get("judge_baseline_p5") for r in per_user),
                 "judge_agreement": mean(agreements),
                 "users": len(users),
                 "method": "Blind human labels (would apply? y/n) on the agent's top 5 vs the keyword-alert baseline's top 5, sources hidden and shuffled."},
        "events": {"agent_precision": mean(ev_agent), "raw_precision": mean(ev_raw),
                   "method": "Human labels: real, upcoming within 90 days, reachable, target company really involved."},
        "grounding": grounding(),
        "freshness": fresh,
        "ghost": ghost,
        "per_user": per_user,
        "live": {"freshness": "live", "ghost": "live", "jobs": "labelled during the hackathon", "events": "labelled during the hackathon"},
    }
    (RESULTS / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_md(results)
    chart(results)
    print(json.dumps({k: results[k] for k in ("n_users", "jobs", "events", "grounding")}, indent=2, default=str))
    print(f"\nWritten: {RESULTS / 'results.json'}, results.md, chart.png")


def pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


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
Precision of verified events: {pct(e['agent_precision'])} vs raw search top 10: {pct(e['raw_precision'])}.

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
    fig.savefig(RESULTS / "chart.png", dpi=160)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet"); s.add_argument("--user", type=int, required=True); s.add_argument("--run", type=int); s.add_argument("--memory", action="store_true")
    s = sub.add_parser("label"); s.add_argument("--user", type=int, required=True)
    s = sub.add_parser("judge"); s.add_argument("--user", type=int, required=True); s.add_argument("--force", action="store_true")
    s = sub.add_parser("label-events"); s.add_argument("--user", type=int, required=True)
    sub.add_parser("compile")
    a = p.parse_args()
    {"sheet": cmd_sheet, "label": cmd_label, "judge": cmd_judge, "label-events": cmd_label_events, "compile": cmd_compile}[a.cmd](a)


if __name__ == "__main__":
    main()
