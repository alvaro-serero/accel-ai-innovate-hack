"""Taleb's sandbox: run the real events pipeline without the shared database.

    python -m backend.events.devserver          # http://localhost:8090/dev

- Database: in-memory fake (only the queries the radar uses). Nothing touches Aiven.
- Search: real Keenable if KEENABLE_API_KEY is set, else simulated results.
- LLM: real Claude if ANTHROPIC_API_KEY is set, else a simulated extractor.
Force simulation with SIM_SEARCH=fake / SIM_LLM=fake. Everything simulated is labelled "SIM" in the UI.
"""
import json
import os
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from backend.app.config import settings
import backend.events.extract as X
import backend.events.people as P
import backend.events.radar as R
import backend.events.search as S

HERE = Path(__file__).resolve().parent
NOW = datetime.now(timezone.utc)
REAL_SEARCH = bool(settings.keenable_api_key) and os.getenv("SIM_SEARCH") != "fake"
REAL_LLM = bool(settings.anthropic_api_key) and os.getenv("SIM_LLM") != "fake"


# ------------------------------------------------------------------ fake database

class FakeDB:
    def __init__(self):
        self.users = {1: {"id": 1, "name": "Demo student", "city": "Paris",
                          "target_companies": ["Mistral AI", "Datadog", "Amazon"],
                          "profile": {"projects": [{"name": "Document extraction platform", "stack": ["Python", "LLM"]},
                                                   {"name": "Knowledge graph + RAG"}]}}}
        self.events: dict[str, dict] = {}
        self.matches: dict[tuple, dict] = {}

    def fetch_one(self, sql, params=None):
        if "from users" in sql:
            return self.users.get(params[0])
        if "insert into events" in sql:
            keys = ["title", "url", "source", "kind", "starts_at", "city", "venue", "companies", "involvement", "speakers",
                    "student_friendly", "description", "verified", "verify_notes"]
            row = dict(zip(keys, params))
            old = self.events.get(row["url"])
            row["id"] = old["id"] if old else len(self.events) + 1
            self.events[row["url"]] = row
            return {"id": row["id"]}
        return None

    def execute(self, sql, params=None):
        if "insert into event_matches" in sql:
            user_id, event_id, score, why, who = params
            self.matches[(user_id, event_id)] = {"id": len(self.matches) + 1, "user_id": user_id, "event_id": event_id,
                                                 "score": score, "why": why, "who_to_meet": who}
        return 1

    def fetch_all(self, sql, params=None):
        if "from event_matches" in sql:
            by_id = {e["id"]: e for e in self.events.values()}
            rows = []
            for (uid, eid), m in self.matches.items():
                e = by_id[eid]
                if uid == params[0] and e["verified"]:
                    rows.append({**m, "event_id": eid, **{k: e[k] for k in ("title", "url", "kind", "starts_at", "city", "venue", "companies", "involvement")}})
            return sorted(rows, key=lambda r: -r["score"])
        return []


DB = FakeDB()
R.fetch_one, R.execute, R.fetch_all = DB.fetch_one, DB.execute, DB.fetch_all


# ------------------------------------------------------------------ simulated search / page / LLM

def _sim_candidates(company: str, city: str) -> list[dict]:
    slug = company.lower().replace(" ", "-")
    return [
        {"url": f"https://lu.ma/sim-{slug}-builders", "title": f"{company} Builders Night {city}", "snippet": f"{company} engineers present, students welcome"},
        {"url": f"https://www.meetup.com/sim-{slug}-meetup/events/1", "title": f"{company} meetup (last year)", "snippet": f"{company} meetup {city}"},
        {"url": f"https://www.eventbrite.fr/e/sim-{slug}-london", "title": f"{company} Summit London", "snippet": f"{company} summit London"},
        {"url": f"https://blog.example.com/sim-{slug}-news", "title": f"{company} raises funding", "snippet": "article"},
    ]


async def sim_search(query: str):
    if "LinkedIn" in query:  # people tool: a public profile result for the speaker, as a search engine would return
        m = re.match(r'"(.+?)" (.+) LinkedIn', query)
        name, comp = (m.group(1), m.group(2)) if m else ("", "")
        slug = name.lower().replace(" ", "-").replace("(", "").replace(")", "")
        return [{"url": f"https://www.linkedin.com/in/sim-{slug}", "title": f"{name} - ML Engineer - {comp} | LinkedIn",
                 "snippet": f"SIM profile. {name} works at {comp} in Paris."},
                {"url": "https://twitter.com/sim", "title": name, "snippet": "unrelated"}]
    comp = next((c for c in DB.users[1]["target_companies"] if query.startswith(c) or f" {c} " in f" {query} "), None)
    if not comp or "meetup" not in query:  # one query per company returns results, like a real noisy search
        return []
    return _sim_candidates(comp, DB.users[1]["city"])


async def sim_fetch(client, url: str) -> str:
    """Simulated page text names the company, so the grounding check behaves like in production."""
    comp = next((c for c in DB.users[1]["target_companies"] if c.lower().replace(" ", "-") in url), "")
    return f"SIM PAGE {url}. {comp} event. Students welcome."


async def sim_llm(system: str, user: str, model=None, max_tokens=1000):
    if "opener" in system:
        return {"opener": "SIM: your talk on evaluation connects to my document extraction project; how do you test your agents?"}
    url = user.split("\n")[0].replace("URL: ", "")
    if "/sim-" not in url:  # never invent details for a real page: without a Claude key, real pages are not extracted
        return {"is_event": False}
    comp = next((c for c in DB.users[1]["target_companies"] if c.lower().replace(" ", "-") in url), "Unknown")
    if "builders" in url:
        when = (NOW + timedelta(days=random.randint(5, 40))).strftime("%Y-%m-%dT18:30")
        return {"is_event": True, "title": f"{comp} Builders Night Paris (SIM)", "kind": random.choice(["meetup", "hackathon"]),
                "starts_at": when, "city": "Paris", "venue": "Station F", "companies": [comp],
                "involvement": {comp: random.choice(["host", "speaker", "recruiting"])},
                "speakers": [{"name": f"Sim Speaker ({comp})", "role": "ML Engineer", "company": comp}], "student_friendly": True}
    if "meetup" in url:
        return {"is_event": True, "title": f"{comp} meetup (SIM)", "kind": "meetup", "starts_at": "2025-03-12T19:00",
                "city": "Paris", "companies": [comp], "involvement": {comp: "speaker"}}
    if "london" in url:
        return {"is_event": True, "title": f"{comp} Summit London (SIM)", "kind": "conference",
                "starts_at": (NOW + timedelta(days=20)).strftime("%Y-%m-%d"), "city": "London", "companies": [comp], "involvement": {comp: "host"}}
    return {"is_event": False}


if not REAL_SEARCH:  # simulated URLs have no real page behind them
    S.akeenable_search = sim_search
    P.akeenable_search = sim_search
    X.fetch_text = sim_fetch
if not REAL_LLM:
    X.aclaude_json = sim_llm
    R.aclaude_json = sim_llm


# ------------------------------------------------------------------ app

app = FastAPI(title="FirstIn events sandbox")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

from backend.events.routes import router as events_router  # noqa: E402

app.include_router(events_router)


class UserPatch(BaseModel):
    city: str = "Paris"
    target_companies: list[str] = []


@app.get("/dev/mode")
def mode():
    return {"search": "keenable" if REAL_SEARCH else "SIM", "llm": "claude" if REAL_LLM else "SIM", "db": "in-memory (SIM)",
            "people_tool": "on" if P.enabled() else "off"}


@app.put("/dev/people")
def toggle_people(on: bool):
    """Sandbox only: switch the speaker-verification tool for the next refresh."""
    os.environ["EVENTS_VERIFY_PEOPLE"] = "true" if on else "false"
    return {"people_tool": "on" if P.enabled() else "off"}


@app.put("/dev/users/{user_id}")
def set_user(user_id: int, p: UserPatch):
    u = DB.users.setdefault(user_id, {"id": user_id, "name": f"User {user_id}", "profile": {}})
    u.update(city=p.city, target_companies=p.target_companies or u.get("target_companies", []))
    return u


@app.get("/dev/users/{user_id}")
def get_user(user_id: int):
    return DB.users.get(user_id)


@app.get("/dev/decisions/{user_id}")
def decisions(user_id: int):
    p = R.RAW_DIR / f"events_raw_user{user_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"candidates": [], "decisions": []}


@app.get("/api/eval")
def eval_results():
    for name in ("results.json", "sim/results.json"):
        p = HERE.parent / "eval" / "results" / name
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")) | {"_file": name}
    return {"jobs": {}, "events": {}, "freshness": {}, "ghost": {}, "grounding": {}, "_file": None}


@app.get("/dev", response_class=HTMLResponse)
def page():
    return (HERE / "devpage.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn
    print(f"Sandbox: http://localhost:8090/dev  (search={'keenable' if REAL_SEARCH else 'SIM'}, llm={'claude' if REAL_LLM else 'SIM'})")
    uvicorn.run(app, host="127.0.0.1", port=8090)
