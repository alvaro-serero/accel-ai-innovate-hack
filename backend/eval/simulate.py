"""Dry run of the whole evidence pipeline on SIMULATED labels, without database or API keys.

    python -m backend.eval.simulate

Writes only to backend/eval/labels/sim/ and backend/eval/results/sim/ (never the real results.json).
Every number it produces is fake and tagged "source": "SIM": use it to test compile, the chart and the UI, never in the pitch.
"""
import json
import os
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["EVAL_LABELS_DIR"] = str(HERE / "labels" / "sim")
os.environ["EVAL_RESULTS_DIR"] = str(HERE / "results" / "sim")

from backend.eval import run_eval as E  # noqa: E402  (reads the env vars above)

random.seed(7)


def fake_labels(user: int):
    jobs, human, judge = {}, {}, {}
    sets = {"baseline": [], "agent": [], "agent_memory": []}
    hit_rate = {"baseline": 0.35, "agent": 0.65, "agent_memory": 0.8}  # arbitrary simulation parameters
    jid = user * 100
    for name in sets:
        for _ in range(5):
            jid += 1
            sets[name].append(jid)
            jobs[str(jid)] = {"id": jid, "title": f"SIM {name} posting {jid}", "company": "SIM Co", "city": "Paris"}
            human[str(jid)] = random.random() < hit_rate[name]
            agree = random.random() < 0.85
            judge[str(jid)] = {"would_apply": human[str(jid)] if agree else not human[str(jid)], "score": 50, "why": "SIM"}
    raw = [f"https://sim.example/raw/{user}/{i}" for i in range(10)]
    agent = [f"https://sim.example/agent/{user}/{i}" for i in range(4)]
    ev_h = {u: random.random() < 0.3 for u in raw} | {u: random.random() < 0.85 for u in agent}
    E.save(user, {"sets": sets, "runs": {"agent": 1, "agent_memory": 2}, "jobs": jobs, "human": human, "judge": judge,
                  "events_sets": {"raw": raw, "agent": agent}, "events_human": ev_h})


def fake_freshness_and_ghost():
    return ({"companies_watched": 287, "jobs_open": 4120, "internships_open": 212, "postings_detected": 37,
             "internships_opened_since_first_poll": 9, "median_lag_hours": 2.5, "source": "SIM"},
            {"open_internships": 212, "flagged": 39, "internships_flagged_pct": 18.4,
             "examples": [{"title": "SIM Spontaneous application intern", "company": "SIM Co", "ghost_score": 0.9,
                           "ghost_reasons": ["generic title", "older than 120 days"]}], "source": "SIM"})


def fake_grounding():
    return {"reasons_checked": 53, "reasons_kept": 47, "reasons_dropped": 6, "shown_reasons_verified_pct": 100.0,
            "generated_reasons_verified_pct": 88.7, "source": "SIM"}


def main():
    for u in (1, 2, 3, 4):
        fake_labels(u)
    E.freshness_and_ghost = fake_freshness_and_ghost
    E.grounding = fake_grounding
    E.cmd_compile(None)
    out = E.RESULTS / "results.json"
    data = json.loads(out.read_text(encoding="utf-8"))
    data["source"] = "SIM"
    for k in ("jobs", "events"):
        data[k]["source"] = "SIM"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSIMULATED results in {E.RESULTS} (labels in {E.LABELS}). Do not use these numbers in the pitch.")


if __name__ == "__main__":
    main()
