"""Shared API contract. Owner: Alvaro. Mirrors the 'API contract' section of PLAN.md.

Change a field only after announcing it in the team chat: Marc's UI depends on these names.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------- jobs and matches ----------


class Reason(BaseModel):
    claim: str
    evidence: str  # verbatim quote from the posting or CV, or a fact from a web source
    source: Literal["posting", "cv", "web"]


class JobOut(BaseModel):
    id: int
    title: str
    company: str
    city: str | None = None
    url: str | None = None
    first_seen_at: datetime | None = None
    published_at: datetime | None = None
    ghost_score: float = 0
    ghost_reasons: list[str] = Field(default_factory=list)


class CompanyBrief(BaseModel):
    summary: str
    sources: list[str] = Field(default_factory=list)


class Match(BaseModel):
    id: int
    rank: int
    fit_score: int  # 0..100
    status: Literal["new", "liked", "dismissed", "applied"] = "new"
    job: JobOut
    reasons: list[Reason] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    company_brief: CompanyBrief | None = None


class MatchPatch(BaseModel):
    status: Literal["new", "liked", "dismissed", "applied"]


# ---------- events ----------


class EventOut(BaseModel):
    id: int
    title: str
    url: str | None = None
    kind: str | None = None  # hackathon, meetup, career_fair, talk, conference
    starts_at: datetime | None = None
    city: str | None = None
    venue: str | None = None
    companies: list[str] = Field(default_factory=list)
    involvement: dict[str, str] = Field(default_factory=dict)  # {"Amazon": "speaker"}


class Contact(BaseModel):
    name: str
    role: str | None = None
    company: str | None = None
    opener: str | None = None  # one-line conversation starter


class EventMatch(BaseModel):
    id: int
    score: int
    why: str
    event: EventOut
    who_to_meet: list[Contact] = Field(default_factory=list)


class EventsRefreshResult(BaseModel):
    found: int
    verified: int
    kept: int


# ---------- brief, runs, kit ----------


class BriefStats(BaseModel):
    postings_checked: int = 0
    new_internships: int = 0
    ghosts_skipped: int = 0
    events_found: int = 0


class Brief(BaseModel):
    run_id: int | None = None
    generated_at: datetime | None = None
    stats: BriefStats = Field(default_factory=BriefStats)
    matches: list[Match] = Field(default_factory=list)
    events: list[EventMatch] = Field(default_factory=list)


class TraceStep(BaseModel):
    step: str
    count_in: int | None = None
    count_out: int | None = None
    seconds: float | None = None
    note: str | None = None


class RunOut(BaseModel):
    id: int
    kind: Literal["nightly", "manual", "eval"]
    status: Literal["running", "done", "failed"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stats: dict = Field(default_factory=dict)
    trace: list[TraceStep] = Field(default_factory=list)


class RunCreate(BaseModel):
    kind: Literal["nightly", "manual", "eval"] = "manual"


class RunCreated(BaseModel):
    run_id: int


class Kit(BaseModel):
    cv_bullets: list[str] = Field(default_factory=list)
    cover_letter: str = ""
    linkedin_note: str = ""  # under 300 characters
    contact_hint: str = ""


class KitRequest(BaseModel):
    user_id: int


# ---------- users and memory ----------


class MemoryLine(BaseModel):
    id: int
    kind: Literal["preference", "fact", "dislike"]
    content: str
    source: str | None = None
    created_at: datetime | None = None
    superseded_by: int | None = None  # None = active


class User(BaseModel):
    id: int
    name: str | None = None
    email: str | None = None
    city: str | None = None
    target_roles: list[str] = Field(default_factory=list)
    target_companies: list[str] = Field(default_factory=list)
    start_date: date | None = None
    profile: dict | None = None
    memory: list[MemoryLine] = Field(default_factory=list)


class FeedbackIn(BaseModel):
    user_id: int
    target_type: Literal["job", "event"]
    target_id: int
    verdict: Literal["up", "down"]
    reason: str | None = None


class FeedbackResult(BaseModel):
    memory_added: list[MemoryLine] = Field(default_factory=list)
    memory_superseded: list[int] = Field(default_factory=list)


# ---------- data layer and eval ----------


class DataStats(BaseModel):
    companies: int = 0
    jobs_open: int = 0
    internships_open: int = 0
    ghost_pct: float = 0
    new_last_24h: int = 0
    last_poll_at: datetime | None = None


class FeedItem(BaseModel):
    at: datetime
    kind: Literal["opened", "edited", "closed", "reposted"]
    company: str
    title: str
    url: str | None = None


class PollResult(BaseModel):
    polled: int = 0
    opened: int = 0
    edited: int = 0
    closed: int = 0


class EvalResults(BaseModel):
    jobs: dict = Field(default_factory=dict)  # {baseline_p5, agent_p5, with_memory_p5, judge_agreement}
    events: dict = Field(default_factory=dict)  # {agent_precision, raw_precision}
    freshness: dict = Field(default_factory=dict)
    ghost: dict = Field(default_factory=dict)
    grounding: dict = Field(default_factory=dict)  # {reasons_kept, reasons_dropped}
