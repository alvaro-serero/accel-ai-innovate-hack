"""Mock data returned by the stub routes until the real code lands.
Shapes match schemas.py exactly. Marc can also paste these into Lovable as mock data.
Company names here are placeholders, not real postings.
"""
from datetime import datetime, timedelta, timezone

from backend.app.schemas import (
    Brief,
    BriefStats,
    CompanyBrief,
    Contact,
    DataStats,
    EvalResults,
    EventMatch,
    EventOut,
    FeedItem,
    JobOut,
    Kit,
    Match,
    MemoryLine,
    Reason,
    RunOut,
    TraceStep,
    User,
)

NOW = datetime.now(timezone.utc)

MATCHES = [
    Match(
        id=1,
        rank=1,
        fit_score=88,
        job=JobOut(
            id=101,
            title="Machine Learning Engineer Intern (6 months)",
            company="Example AI",
            city="Paris",
            url="https://jobs.lever.co/example-ai/123",
            first_seen_at=NOW - timedelta(hours=3),
            published_at=NOW - timedelta(hours=5),
            ghost_score=0.0,
        ),
        reasons=[
            Reason(claim="Matches your RAG project", evidence="experience building retrieval pipelines", source="posting"),
            Reason(claim="You have the required stack", evidence="Python, PyTorch, FastAPI", source="cv"),
        ],
        gaps=["No Kubernetes experience mentioned"],
        company_brief=CompanyBrief(
            summary="Series B AI startup, engineering team doubled this year.",
            sources=["https://example.com/news"],
        ),
    ),
    Match(
        id=2,
        rank=2,
        fit_score=81,
        job=JobOut(
            id=102,
            title="Data Engineer Intern",
            company="Sample Fintech",
            city="Paris",
            url="https://boards.greenhouse.io/samplefintech/jobs/456",
            first_seen_at=NOW - timedelta(hours=9),
            published_at=NOW - timedelta(days=1),
            ghost_score=0.1,
        ),
        reasons=[Reason(claim="Wants SQL + Airflow", evidence="SQL, dbt, Airflow", source="posting")],
        gaps=[],
        company_brief=CompanyBrief(summary="Fintech scale-up, 300 people.", sources=["https://example.com/a"]),
    ),
]

EVENTS = [
    EventMatch(
        id=1,
        score=78,
        why="Engineers from your target company are speaking; 2 km from you; students welcome",
        event=EventOut(
            id=11,
            title="Cloud & AI Builders Meetup Paris",
            url="https://lu.ma/example",
            kind="meetup",
            starts_at=NOW + timedelta(days=6),
            city="Paris",
            venue="Station F",
            companies=["Amazon"],
            involvement={"Amazon": "speaker"},
        ),
        who_to_meet=[
            Contact(
                name="Speaker name",
                role="Solutions Architect",
                company="Amazon",
                opener="Your talk on agent infra connects to my internship scout project; how do you handle stale data?",
            )
        ],
    )
]

BRIEF = Brief(
    run_id=1,
    generated_at=NOW - timedelta(hours=4),
    stats=BriefStats(postings_checked=412, new_internships=9, ghosts_skipped=3, events_found=4),
    matches=MATCHES,
    events=EVENTS,
)

USER = User(
    id=1,
    name="Demo Student",
    email="student@example.com",
    city="Paris",
    target_roles=["ML engineer intern", "Data engineer intern"],
    target_companies=["Amazon", "Datadog", "Mistral AI"],
    profile={"skills": ["Python", "PyTorch", "SQL"], "projects": [{"name": "RAG assistant", "stack": ["Python"], "one_line": "..."}]},
    memory=[
        MemoryLine(id=1, kind="fact", content="Targets ML engineer internships starting Feb 2027", source="onboarding"),
        MemoryLine(id=2, kind="preference", content="Prefers big tech companies", source="onboarding", superseded_by=3),
        MemoryLine(id=3, kind="preference", content="Prefers startups under 200 people", source="feedback:job:102"),
    ],
)

RUN = RunOut(
    id=1,
    kind="manual",
    status="done",
    started_at=NOW - timedelta(minutes=2),
    finished_at=NOW - timedelta(minutes=1),
    stats={"candidates": 64, "scored": 64, "deep_scored": 15, "picked": 5, "ghosts_skipped": 3},
    trace=[
        TraceStep(step="SQL prefilter (open internships, city, ghost < 0.6)", count_in=412, count_out=64, seconds=0.1),
        TraceStep(step="Haiku quick score", count_in=64, count_out=15, seconds=8.2),
        TraceStep(step="Sonnet qualifier + grounding check", count_in=15, count_out=5, seconds=21.0),
        TraceStep(step="Company research (Keenable)", count_in=5, count_out=5, seconds=6.4),
    ],
)

KIT = Kit(
    cv_bullets=["Built a retrieval-augmented assistant in Python (FastAPI, PyTorch) used by 30 classmates"],
    cover_letter="Dear team, ...",
    linkedin_note="Hi, I saw the ML intern opening on your team and ...",
    contact_hint="An ML engineer on the applied team; LinkedIn search: 'Example AI machine learning engineer Paris'",
)

DATA_STATS = DataStats(companies=287, jobs_open=4120, internships_open=212, ghost_pct=18.4, new_last_24h=37, last_poll_at=NOW)

FEED = [
    FeedItem(at=NOW - timedelta(minutes=4), kind="opened", company="Example AI", title="ML Engineer Intern", url="https://example.com/1"),
    FeedItem(at=NOW - timedelta(minutes=19), kind="edited", company="Sample Fintech", title="Data Engineer Intern", url="https://example.com/2"),
    FeedItem(at=NOW - timedelta(minutes=33), kind="closed", company="Demo Corp", title="Backend Intern", url="https://example.com/3"),
]

EVAL = EvalResults(
    jobs={"baseline_p5": 0.35, "agent_p5": 0.7, "with_memory_p5": 0.8, "judge_agreement": 0.82, "users": 4, "source": "mock"},
    events={"agent_precision": 0.8, "raw_precision": 0.3, "source": "mock"},
    freshness={"postings_detected": 37, "median_lag_hours": 2.5, "not_on_linkedin_pct": 40, "source": "mock"},
    ghost={"internships_flagged_pct": 18.4, "source": "mock"},
    grounding={"reasons_kept": 47, "reasons_dropped": 6, "source": "mock"},
)
