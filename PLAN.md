# Internship Scout: Build Plan

Oct 22, 2026 · @Alvaro Serero

We build an agent that finds real internships first, for students, and prepares quality applications they send themselves. Four branches, one shared schema and API contract, feature freeze at 14:45.

## Product and scope

**Working name: FirstIn.** One-line pitch: *"Your internship scout works the night shift: it finds real internships the hour they open, skips ghost jobs, and finds the events where you can meet the people hiring. You send every application yourself."*

**User:** an engineering or business student searching for an internship (our own case: Feb 2027 end-of-studies internship, Paris). Narrow on purpose: students only, internships only.

**Principles (say them in the pitch and show them in the UI):**

- Quality over quantity: max 5 job picks per morning, each with cited reasons. No mass applying.
- Never auto-send. The agent prepares, the student sends. A visible "You send it" label on every draft.
- Grounded: every claim cites the posting text, the CV line or a web source.
- Fresh: we read company job boards at the source (Greenhouse, Lever, Ashby) every 10 minutes and flag ghost jobs.

**MVP features (must ship):**

1. Onboarding: upload CV (PDF), city, target roles, target companies, start date.
2. Jobs watcher: polls 150 to 400 company job boards, stores every posting with its history.
3. Morning brief: top 5 internships with fit score, cited reasons, gaps, ghost flag, company research snippet.
4. Feedback memory: thumbs down plus a reason, the agent learns a preference and re-ranks.
5. Application kit: tailored CV bullets, short cover letter, LinkedIn note to one relevant person. Copy buttons only.
6. Events radar: upcoming meetups, hackathons, career fairs and talks linked to the student's target companies, near their city, with who to meet there.
7. Data layer page: live feed of postings opened, edited, closed, plus stats (companies watched, ghost %).

**Cut (roadmap slide only):** auto-sending anything, LinkedIn profile optimisation, Workday or Amazon-style corporate career sites, mobile app, multi-user auth (a user id in the URL is enough for the demo).

## Demo journey (the 3-minute video)

The video follows one student (one of us, real CV) from onboarding to the morning brief. Everything we build serves this path; anything off it waits.

| Time | Screen | What the judge sees |
| --- | --- | --- |
| 0:00 | Slide | Problem: AI made applying free, recruiters drown in spam, students apply late and to ghost jobs |
| 0:20 | Onboarding | Upload CV, Paris, "ML engineer intern", target companies (Mistral, Datadog, Amazon), Feb 2027 |
| 0:40 | Morning brief | "Since last night: 412 postings checked, 9 new internships, 3 ghost jobs skipped", top 5 picks with cited reasons |
| 1:15 | Feedback | Thumbs down "too big a company", brief re-ranks, a new memory line appears |
| 1:40 | Application kit | Tailored CV bullets, cover letter, LinkedIn note, big "You send it" label |
| 2:05 | Events | "AWS Summit Paris" style event tied to Amazon, near you, who to meet, why |
| 2:25 | Data layer page | Live feed of postings opened or edited in the last hours, ghost % stat |
| 2:40 | Evidence | Precision@5 chart vs keyword baseline, freshness and ghost numbers |
| 2:55 | Pitch slide | Who, why now, first users |

Mark live vs recorded in the video: the watcher feed and stats are live; the overnight run is triggered manually during the demo and labelled "replayed nightly run".

## Architecture and stack

One Python backend, one Postgres, one container on Aiven Runtime. No microservices, no embeddings, no queue: at our scale (a few hundred internship postings) SQL filtering plus LLM ranking is enough.

**Data flow:**

1. **Watcher** (every 10 min) polls Greenhouse, Lever and Ashby boards, upserts `jobs`, appends to `job_events` (opened, edited, closed, reposted), tags internships and computes a ghost score.
2. **Onboarding** turns the uploaded CV into a structured `profile` (LLM).
3. **Run** (nightly at 06:00, or a button in the demo): SQL prefilter, then cheap LLM scoring of every candidate, then deep qualifier on the top 15 with the student's memory, then company research (Keenable) on the top 5. Writes `matches` and a `runs` trace.
4. **Events radar**: for each target company and the student's city, Keenable searches, page fetch, LLM extraction, verification (future date, distance, real company involvement), then `events` and `event_matches`.
5. **Feedback**: a thumbs down with a reason goes to the memory curator, which adds or supersedes lines in `user_memory`. Next run uses them.
6. **Frontend** reads brief, kits, events, data feed and eval results through the API.

| Layer | Choice | Notes |
| --- | --- | --- |
| Backend | Python 3.11, FastAPI, uvicorn, pydantic v2, httpx, psycopg 3, APScheduler | Scheduler runs inside the app process |
| LLM | Claude Sonnet (`claude-sonnet-5-5`) for qualifier, kit, memory curator, CV parsing; Claude Haiku (`claude-haiku-5-5`) for bulk tagging and event extraction | Use whatever key the team has; keep all calls in `backend/app/llm.py` |
| Web search | Keenable API: `POST https://api.keenable.ai/v1/search`, header `X-API-Key`, body `{"query": ...}` | Sign up with code ACCEL-PARIS |
| Page text | httpx + trafilatura | For event pages |
| CV parsing | pypdf | Text out, then LLM to JSON |
| Data | Aiven for PostgreSQL (one service) | Job history, memory, matches, events, traces |
| Frontend | Lovable (React, Vite, Tailwind), hosted on Lovable | Calls the API on Aiven Runtime (CORS on). Lives in its own GitHub repo created by Lovable's GitHub sync (Lovable cannot sync into a subfolder of this repo); API base URL in `VITE_API_URL` |
| Deploy | Aiven Runtime from the GitHub repo, `Dockerfile` at root, port 8080 | `DATABASE_URL` injected by the Postgres integration; set `ENABLE_SCHEDULER=true`; push does not redeploy, use "Deploy latest commit" |

**Partner tools we use (graded, so each one gets a real job and a mention on the pitch slide):**

| Partner | Job in FirstIn | Credits |
| --- | --- | --- |
| Anthropic | All agent reasoning: CV parsing, qualifier, kit, memory curator, event extraction | $100 x 4 = $400, far more than we need |
| OpenAI | Independent eval judge, so Claude never grades its own picks; second opinion on match labels | $50 x 4 |
| Aiven | PostgreSQL for the whole data layer, Runtime hosts the API | Team credits |
| Lovable | The whole frontend | Lovable credits |
| Keenable | Company research and events search | $1,000 each, code ACCEL-PARIS |
| n8n | Delivers the morning brief: backend POSTs the brief JSON to an n8n webhook, n8n sends the email | Cloud Pro code |
| ElevenLabs (stretch) | "Listen to your brief" audio version, 20 minutes of work if everything else is done | Only if time |

Budget check: one full run for one student is roughly 150 cheap Haiku calls plus 15 Sonnet calls plus 5 Keenable searches, well under $1.

Sources: [Aiven Runtime deploy docs](https://aiven.io/docs/products/runtime/deploy-apps), [Keenable docs](https://docs.keenable.ai).

## Repo layout and branch rules

Each person owns one folder and never edits another's. The shared contract files land on `main` by 12:40, before anyone branches off for real work.

```
firstin/
  Dockerfile, requirements.txt, .env.example     Marc
  db/schema.sql, db/companies_seed.csv           Leo   (schema frozen 12:40, add-only after)
  backend/app/main.py, config.py                 Marc  (FastAPI app, CORS, routers, scheduler start)
  backend/app/db.py                              Leo   (connection pool, helpers)
  backend/app/schemas.py, llm.py                 Alvaro (shared pydantic models, Claude + OpenAI wrappers)
  backend/watcher/   ats.py poller.py classify.py ghost.py routes.py        Leo
  backend/agent/     profile.py qualify.py research.py kit.py memory.py run.py routes.py   Alvaro
  backend/events/    search.py extract.py verify.py routes.py               Taleb
  backend/eval/      labels/ baseline.py judge.py run_eval.py results/      Taleb
  web/  placeholder only: the frontend lives in the Lovable repo (below)      Marc
```

**Frontend repo:** Lovable creates and syncs its own GitHub repo: [marcchend/pixel-perfect-replay-2823](https://github.com/marcchend/pixel-perfect-replay-2823) (private; Marc adds the team as collaborators). It talks to this backend only through `VITE_API_URL`. If the submission needs a single repo, the Lovable code is copied into `web/` at 15:15.

**Rules:**

1. Branches: `feat/agent` (Alvaro), `feat/watcher` (Leo), `feat/events` (Taleb), `feat/web-deploy` (Marc).
2. `main.py` includes all four routers from the start. Each `routes.py` starts as a stub returning hardcoded JSON that matches `schemas.py`, so Marc can build the UI against it immediately and merges never conflict.
3. One shared Aiven Postgres for dev and prod. Everyone connects to it with the same `DATABASE_URL`, so the watcher's real data is visible to everyone within minutes. Schema changes go through Leo, add columns only, never drop.
4. Secrets live in `.env`, never committed. `.env.example` lists `DATABASE_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `KEENABLE_API_KEY`, `N8N_WEBHOOK_URL`.
5. Merge to `main` only at the merge points (see Timeline), through a quick PR. Pull `main` into your branch right after each merge point.
6. A change to a shared file (`schemas.py`, `schema.sql`, `main.py`) is announced in the team chat first, then made by its owner.

## Data model (db/schema.sql)

This is the contract. Leo runs it on Aiven Postgres at 12:30; nobody renames or drops a column after 12:40. `job_events` is append-only: it is our history and the "data layer in action" file.

```sql
-- Companies we watch
create table companies (
  id serial primary key,
  name text not null,
  ats text not null check (ats in ('greenhouse','lever','ashby')),
  slug text not null,               -- board token used in the ATS URL
  hq_city text,
  tags text[] default '{}',         -- e.g. {'ai','fintech','accel'}
  last_polled_at timestamptz,
  unique (ats, slug)
);

-- Every posting we have ever seen
create table jobs (
  id serial primary key,
  company_id int references companies(id),
  ats_job_id text not null,
  title text not null,
  location text,
  city text,                        -- normalised, e.g. 'Paris'
  remote boolean,
  employment_type text,             -- raw from ATS
  is_internship boolean,
  url text,
  description text,                 -- plain text
  published_at timestamptz,         -- from ATS when available
  source_updated_at timestamptz,    -- from ATS when available
  first_seen_at timestamptz default now(),
  last_seen_at timestamptz default now(),
  closed_at timestamptz,            -- set when it disappears from the board
  content_hash text,
  repost_count int default 0,
  ghost_score real default 0,       -- 0 fresh .. 1 likely ghost
  ghost_reasons text[] default '{}',
  unique (company_id, ats_job_id)
);

-- Append-only history: the data layer in action
create table job_events (
  id bigserial primary key,
  job_id int references jobs(id),
  kind text check (kind in ('opened','edited','closed','reposted')),
  at timestamptz default now(),
  detail jsonb
);

create table users (
  id serial primary key,
  name text,
  email text,
  city text,
  target_roles text[] default '{}',
  target_companies text[] default '{}',
  start_date date,
  cv_text text,
  profile jsonb,                    -- skills, projects, education, languages
  created_at timestamptz default now()
);

-- Long-term memory, with contradiction handling
create table user_memory (
  id serial primary key,
  user_id int references users(id),
  kind text check (kind in ('preference','fact','dislike')),
  content text not null,            -- 'prefers startups under 200 people'
  source text,                      -- 'feedback:job:123' or 'onboarding'
  created_at timestamptz default now(),
  superseded_by int references user_memory(id)   -- null = active
);

create table runs (
  id serial primary key,
  user_id int references users(id),
  kind text check (kind in ('nightly','manual','eval')),
  started_at timestamptz default now(),
  finished_at timestamptz,
  stats jsonb,                      -- candidates, scored, picked, ghosts_skipped, cost
  trace jsonb                       -- step-by-step log shown in the UI
);

create table matches (
  id serial primary key,
  run_id int references runs(id),
  user_id int references users(id),
  job_id int references jobs(id),
  rank int,
  fit_score int,                    -- 0..100
  reasons jsonb,                    -- [{claim, evidence, source}]
  gaps jsonb,                       -- ['no Rust experience']
  company_brief jsonb,              -- {summary, sources:[url]}
  status text default 'new' check (status in ('new','liked','dismissed','applied')),
  created_at timestamptz default now()
);

create table feedback (
  id serial primary key,
  user_id int references users(id),
  target_type text check (target_type in ('job','event')),
  target_id int,
  verdict text check (verdict in ('up','down')),
  reason text,
  created_at timestamptz default now()
);

create table kits (
  id serial primary key,
  user_id int references users(id),
  job_id int references jobs(id),
  cv_bullets jsonb,
  cover_letter text,
  linkedin_note text,
  contact_hint text,                -- 'an ML engineer on the team, search: ...'
  created_at timestamptz default now()
);

create table events (
  id serial primary key,
  title text not null,
  url text unique,
  source text,                      -- 'luma','meetup','eventbrite','company site'
  kind text,                        -- hackathon, meetup, career_fair, talk, conference
  starts_at timestamptz,
  city text,
  venue text,
  companies text[] default '{}',    -- companies involved
  involvement jsonb,                -- {company: 'host'|'sponsor'|'speaker'|'recruiting'}
  speakers jsonb,                   -- [{name, role, company}]
  student_friendly boolean,
  description text,
  first_seen_at timestamptz default now(),
  verified boolean default false,
  verify_notes text
);

create table event_matches (
  id serial primary key,
  user_id int references users(id),
  event_id int references events(id),
  score int,
  why text,
  who_to_meet jsonb,
  status text default 'new',
  unique (user_id, event_id)
);

create index on jobs (is_internship, closed_at);
create index on job_events (at desc);
```

## API contract

All routes are under `/api`. Stubs return the exact shapes below from 12:40, so Marc never waits for the backend. Pydantic models with the same names live in `backend/app/schemas.py`.

| Method and path | Owner | Body or query | Returns |
| --- | --- | --- | --- |
| `POST /api/users` | Alvaro | multipart: `cv` (PDF), `name`, `email`, `city`, `target_roles` (comma list), `target_companies`, `start_date` | `User` with parsed `profile` |
| `GET /api/users/{id}` | Alvaro |  | `User` + active `memory` lines |
| `POST /api/users/{id}/runs` | Alvaro | `{"kind":"manual"}` | `{"run_id": 12}` (runs in background) |
| `GET /api/runs/{run_id}` | Alvaro |  | `Run` with `status`, `stats`, `trace` |
| `GET /api/users/{id}/brief` | Alvaro |  | `Brief` (latest run) |
| `POST /api/feedback` | Alvaro | `{user_id, target_type, target_id, verdict, reason}` | `{"memory_added": [...], "memory_superseded": [...]}` |
| `POST /api/jobs/{job_id}/kit` | Alvaro | `{"user_id": 1}` | `Kit` |
| `PATCH /api/matches/{id}` | Alvaro | `{"status":"applied"}` | `Match` |
| `GET /api/data/stats` | Leo |  | `{companies, jobs_open, internships_open, ghost_pct, new_last_24h, last_poll_at}` |
| `GET /api/data/feed` | Leo | `?limit=50` | `[{at, kind, company, title, url}]` |
| `POST /api/watcher/poll` | Leo |  | `{polled, opened, edited, closed}` (manual trigger for the demo) |
| `GET /api/users/{id}/events` | Taleb |  | `[EventMatch]` |
| `POST /api/users/{id}/events/refresh` | Taleb |  | `{found, verified, kept}` |
| `GET /api/eval` | Taleb |  | `{jobs:{agent_p5, baseline_p5, with_memory_p5}, events:{agent_precision, raw_precision}, freshness:{...}, ghost:{...}}` |

**Core shapes** (copy into `schemas.py` and into Lovable's mock data):

```json
{
  "Brief": {
    "run_id": 12, "generated_at": "2026-10-22T06:00:00Z",
    "stats": {"postings_checked": 412, "new_internships": 9, "ghosts_skipped": 3, "events_found": 4},
    "matches": ["Match"], "events": ["EventMatch"]
  },
  "Match": {
    "id": 7, "rank": 1, "fit_score": 86, "status": "new",
    "job": {"id": 301, "title": "ML Engineer Intern", "company": "Mistral AI", "city": "Paris",
            "url": "https://...", "first_seen_at": "...", "published_at": "...",
            "ghost_score": 0.1, "ghost_reasons": []},
    "reasons": [{"claim": "Matches your RAG project", "evidence": "'experience with retrieval pipelines'", "source": "posting"},
                {"claim": "Python + PyTorch required", "evidence": "CV: 'PyTorch, 2 projects'", "source": "cv"}],
    "gaps": ["No Kubernetes experience"],
    "company_brief": {"summary": "Raised ... in ...", "sources": ["https://..."]}
  },
  "EventMatch": {
    "id": 3, "score": 78, "why": "Amazon engineers speak; 2.1 km from you",
    "event": {"title": "...", "url": "...", "kind": "meetup", "starts_at": "...", "city": "Paris",
              "venue": "...", "companies": ["Amazon"], "involvement": {"Amazon": "speaker"}},
    "who_to_meet": [{"name": "...", "role": "SDE", "company": "Amazon", "opener": "..."}]
  },
  "Kit": {"cv_bullets": ["..."], "cover_letter": "...", "linkedin_note": "...", "contact_hint": "..."}
}
```

## Alvaro: feat/agent (the brain, plus merge lead)

You own everything that reasons about the student: profile, ranking, memory, application kit. You also run the merges at 14:00 and 14:45.

1. **12:15 to 12:40, contracts on `main`:** create the GitHub repo, push `backend/app/schemas.py` (models from the API contract), `backend/app/llm.py` and `backend/agent/routes.py` returning hardcoded stub JSON.
   - `llm.py`: `claude_json(system, user, model, schema_hint) -> dict` with JSON extraction and one retry on parse failure; `openai_json(...)` with the same signature for Taleb's judge. Log tokens per call into a module-level counter (feeds the cost stat).
2. **`profile.py`:** pypdf to text, then Sonnet to `{education, graduation_year, skills[], projects[{name, stack[], one_line}], experiences[{org, role, one_line}], languages[], interests[]}`. Save to `users.profile`. Seed `user_memory` with target roles and companies as `fact` lines.
3. **`qualify.py`, the three-stage ranker:**
   - Stage 0, SQL prefilter: `is_internship and closed_at is null and (city = user.city or remote) and ghost_score < 0.6`, minus jobs the user dismissed. Count ghosts skipped for the stats.
   - Stage 1, Haiku on every candidate (asyncio, semaphore 8): title + first 1,500 chars + compact profile + active memory lines, returns `{score, one_line}`.
   - Stage 2, Sonnet on the top 15: full posting + full profile + memory, returns `{fit_score, reasons[{claim, evidence, source}], gaps[], red_flags[]}`.
   - **Grounding check:** drop any reason whose `evidence` quote is not found (normalised, lowercase) in the posting or CV text. Count kept vs dropped: that is a metric for the pitch ("100% of shown reasons are verifiable").
   - Final pick: top 5, max 2 per company.
4. **`research.py`:** for each picked company, two Keenable searches (`"{company} funding 2026"`, `"{company} engineering team news"`), then Haiku writes a 2-sentence brief citing the URLs. Cache per company in a dict for the day.
5. **`run.py`:** orchestrates steps 3 to 4, writes `runs.stats` and a readable `runs.trace` (one entry per step: name, count in, count out, seconds), calls Taleb's `refresh_events(user_id)` if importable, then POSTs the brief JSON to `N8N_WEBHOOK_URL`.
6. **`memory.py`, the memory curator:** on each feedback, Sonnet gets the job (or event), the verdict, the reason and the active memory lines, and returns `{add:[{kind, content}], supersede:[{id, why}]}`. Apply it: new lines inserted, contradicted lines get `superseded_by`. Example: "I want big tech" then later "too corporate" supersedes the first.
7. **`kit.py`:** Sonnet writes 3 to 5 CV bullets rewritten from real CV items only (forbid invented facts in the prompt, then check each bullet shares a noun with the CV), a cover letter under 180 words, a LinkedIn note under 300 characters, and a `contact_hint` (who to look for and the search string).

**Checkpoints:** 13:15 qualifier runs from a CLI script on real watcher data. 14:00 routes live and merged. 14:30 memory and kit work from the UI.

## Leo: feat/watcher (the data layer)

You own the database and the live job data. The earlier your poller runs, the more history and evidence we have at 15:00, so speed beats polish here.

1. **12:15 to 12:35, Aiven:** create the account, one PostgreSQL service (smallest plan, a Paris or Frankfurt region), run `db/schema.sql` with psql, post the `DATABASE_URL` privately in the team chat.
2. **`db.py`:** psycopg 3 `ConnectionPool` from `DATABASE_URL`; helpers `fetch_all(sql, params)`, `fetch_one`, `execute`.
3. **`ats.py`, three fetchers that return one normalised dict** `{ats_job_id, title, location, remote, employment_type, url, description, published_at, source_updated_at}`:
   - Greenhouse: `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`. Fields: `id`, `title`, `location.name`, `absolute_url`, `updated_at`, `first_published` if present, `content` (HTML-escaped: unescape, then strip tags).
   - Lever: `GET https://api.lever.co/v0/postings/{slug}?mode=json` (EU companies: `api.eu.lever.co`). Fields: `id`, `text`, `categories.location`, `categories.commitment`, `hostedUrl`, `createdAt` (ms), `descriptionPlain`, `workplaceType`.
   - Ashby: `GET https://api.ashbyhq.com/posting-api/job-board/{slug}`. Fields: `id`, `title`, `location`, `employmentType` (has "Intern"), `isRemote`, `publishedAt`, `jobUrl`, `descriptionPlain`.
   - Check the real field names on the first response of each and adjust; this list is from memory.
4. **Company discovery into `companies_seed.csv` (target 150 to 400 companies by 13:15):**
   - Fastest: Keenable searches like `site:jobs.lever.co Paris intern`, `site:jobs.ashbyhq.com Paris`, `site:boards.greenhouse.io Paris stage`, then regex the slug out of each URL.
   - Plus a hand list of about 200 names (Paris AI startups, French Tech 120, Accel Europe portfolio, US tech with Paris offices) and a probe script that tries slug variants on all three endpoints and keeps those that answer with at least one job.
5. **`poller.py`** (async httpx, 20 concurrent, 10 s timeout), per company:
   - New posting: insert into `jobs`, event `opened`.
   - `content_hash` (sha1 of title + location + description) changed: update, event `edited`.
   - Open in DB but gone from the board: set `closed_at`, event `closed`.
   - Same company and normalised title as a posting closed in the last 60 days: `repost_count + 1`, event `reposted`.
   - Always update `last_seen_at` and `companies.last_polled_at`.
6. **`classify.py`:** `is_internship` by regex on title and employment type (`intern`, `internship`, `stage`, `stagiaire`, `trainee`, `working student`, `fin d'études`), Haiku only for ambiguous ones. Normalise `city` with a small regex map (Paris, Île-de-France, London, Remote...).
7. **`ghost.py`:** score from 0 to 1 with readable reasons: older than 60 days +0.4 (older than 120 days +0.6), reposted +0.3, generic title ("spontaneous", "general application", "talent pool", "candidature spontanée") +0.5, no source update in 90 days +0.2, capped at 1.
8. **Scheduler:** expose `register_jobs(scheduler)` that adds the poll every 10 minutes; Marc calls it from `main.py`.
9. **Routes:** `GET /api/data/stats`, `GET /api/data/feed`, `POST /api/watcher/poll`.
10. **From 14:15, evidence:** give Taleb the freshness numbers (postings opened since the first poll, lag between `published_at` and `first_seen_at`) and ghost numbers (% of open internships with score at least 0.6, age distribution), and draft the "data layer in action" TXT.

**Checkpoints:** 12:40 schema live. 13:00 first poll of 50+ companies stored. 13:30 150+ companies, scheduler on. 14:00 merged.

## Taleb: feat/events plus evidence

You own the events radar until 13:45, then the benchmarks that prove the whole product works. The evidence criterion is where most teams will be weak, so it is worth a full person.

**Part A, events radar (12:15 to 13:45):**

1. **Keenable:** sign up with ACCEL-PARIS, try 10 queries by hand to learn what comes back (response fields, snippet length).
2. **`search.py`:** for each target company C and city X, run about 6 queries: `"{C} meetup {X} 2026"`, `"{C} hackathon {X}"`, `"{C} career fair students {X}"`, `"site:lu.ma {C} {X}"`, `"site:meetup.com {C} {X}"`, `"site:eventbrite.fr {C}"`. Plus 2 generic ones per user: `"forum entreprises ingénieurs {X} 2026"`, `"salon stage {X} 2026"`. Dedupe URLs, cap at 40 per user.
3. **`extract.py`:** fetch each page (httpx, 8 s timeout), trafilatura to text, cut to 6,000 characters, Haiku to `{is_event, title, kind, starts_at, city, venue, companies[], involvement{}, speakers[], student_friendly, registration_url}`. Luma pages are partly JavaScript: if the text is empty, use the page's meta tags or the search snippet.
4. **`verify.py`, plain code checks, no LLM:** is an event; starts in the future and within 90 days; city is the user's city or in the same region; the company name literally appears in the page text (grounding); not a duplicate (normalised title plus date). Write `verified` and `verify_notes` ("rejected: date in the past").
5. **Ranking:** score = involvement (host or recruiting 40, speaker 30, sponsor 20) + sooner is better (up to 30) + student friendly 15 + kind bonus (career fair, hackathon 15). `who_to_meet`: speakers from the target company plus a one-line opener from Haiku that links the talk to one of the student's projects.
6. **Expose** `refresh_events(user_id)` for Alvaro's run, plus the two event routes.

**Part B, evidence (13:45 to 14:45):**

1. **Test users:** onboard all four of us with our real CVs (that is also our user research).
2. **`baseline.py`:** the "keyword alert" baseline every job board sells: postings whose title contains a target-role keyword, in the user's city, newest first.
3. **Blind labelling:** for each of us, mix the agent's top 5 and the baseline's top 5, shuffle, hide the source, and the person labels each posting "would apply" or not. 2 minutes per person.
4. **Memory before and after:** each of us gives 3 thumbs down with reasons, rerun, label the new top 5. Gives three numbers: baseline, agent, agent + memory.
5. **`judge.py`, OpenAI as an independent judge:** score the top 10 of both methods for each user against their profile and stated preferences; report agreement with our human labels. Claude never grades its own picks.
6. **Events:** label the agent's verified events vs the raw top 10 search results (real, upcoming, reachable, company really involved) and report precision for both.
7. **Collect** Leo's freshness and ghost numbers and Alvaro's grounding counter into `eval/results/results.json`, serve it at `GET /api/eval`, and export one chart PNG for the submission.

## Marc: feat/web-deploy (what the judges see)

You own the app shell, the deploy and the whole frontend. The UI is built on mock data first, so you never wait for the backend.

1. **12:15 to 12:40, shell on `main`:**
   - `backend/app/main.py`: FastAPI app, CORS open (`*` is fine today), `GET /api/health`, includes the four routers, starts an APScheduler `AsyncIOScheduler` on startup and calls `watcher.register_jobs(scheduler)`.
   - `config.py` reads the env vars from `.env.example`. `requirements.txt`. `Dockerfile`: `python:3.11-slim`, install requirements, `CMD uvicorn backend.app.main:app --host 0.0.0.0 --port 8080`.
   - *Status: done by Alvaro in the skeleton commit; Docker build tested locally by Marc (health and all stub routes OK, with and without the scheduler).*
2. **12:40 to 13:10, deploy hello-world to Aiven Runtime now, not at 15:00:** Runtime, Deploy application, connect GitHub, repo and branch `main`, Dockerfile at `./Dockerfile`, port 8080 HTTP. Add the Postgres integration so `DATABASE_URL` is injected, and the API keys as secret env vars plus `ENABLE_SCHEDULER=true`. Check `/api/health` on the public URL. Keep one instance only, because the scheduler runs inside the app. Pushing does not redeploy: use Actions, then "Deploy latest commit".
   - Prerequisites: one shared Aiven organisation for the whole team (Leo creates it with the Postgres service and invites Marc as admin). The GitHub connection must be made by the repo owner (Alvaro), since Aiven installs a GitHub app on the account that owns the repo; after that anyone in the Aiven org can deploy. The app can be deployed before the database exists (stubs answer without it). Deadline: deployed by 13:30, before merge 1.
   - *Status: done. API live at https://01a1638c-60d5-73df-914c-5817003873f2-8080.eur-1.aiven.app (Postgres connected, `ENABLE_SCHEDULER=true`, scheduler on). All routes answer 200 against the real data; CORS `*` OK. The frontend uses this URL by default (`src/lib/api.ts`).*
3. **13:10 to 14:00, Lovable on mock data** (the mock data is the exact JSON returned by the stub routes, so field names match `schemas.py`; API base URL in `VITE_API_URL`; frontend in its own Lovable-synced repo). Screens, in this order:
   1. Morning brief: stats bar ("412 postings checked, 9 new internships, 3 ghosts skipped"), 5 match cards with fit score, "first seen 2 h ago", ghost badge, reasons with a source chip (posting, CV, web), gaps, company brief with links, buttons thumbs up, thumbs down (asks for a reason), Prepare kit.
   2. Kit drawer: CV bullets, cover letter, LinkedIn note, each with a copy button, and the banner "You send it. FirstIn never sends anything for you."
   3. Onboarding: CV upload, city, roles, companies, start date.
   4. Events: cards with date, kind, company involvement, city, who to meet plus opener, register link.
   5. Memory panel: active memory lines, superseded ones struck through (this shows the learning).
   6. Data layer: live feed of opened, edited, closed postings (refresh every 10 s), stat tiles, the latest run trace as steps with count in and out.
   7. Evidence: bars for baseline, agent, agent + memory; event precision; freshness and ghost tiles.
   - *Status: done. All 7 screens generated in Lovable, reviewed against this plan and the stub API, then fixed for the demo journey (commit `1b4ca38` in the Lovable repo):*
     - *Thumbs down hides the card, PATCHes the match to `dismissed`, shows "FirstIn learned: ..." and a "Re-rank now" banner that starts a new run (demo step 1:15).*
     - *New user with no run yet sees a "Run my first scout" empty state instead of a blank brief.*
     - *Last user id is remembered (localStorage) so Data layer, Evidence and Onboarding link back to the right student.*
     - *Null-safe dates (missing `generated_at` / `starts_at`) and no "NaN%" on an empty grounding counter.*
   - *Checked: typecheck, tests and production build pass; all pages load against the local backend; CORS and `PATCH /api/matches/{id}` OK. Visual check in the Lovable preview still to do.*
   - *Every API call falls back to mock data when it fails; a "demo data" pill shows in the header. Watch it during the video.*
4. **Design:** calm and clean, one accent colour, no dashboards-for-the-sake-of-it. The brief should read like a short morning email.
5. **14:00 to 14:45:** switch from mocks to the real API, fix what breaks after the merge.
   - Set the Aiven URL as the default `BASE` in `src/lib/api.ts` (Lovable has no simple UI for `VITE_*` env vars; the URL is public anyway).
   - The backend must exclude matches with status `dismissed` (or jobs with a thumbs down) at the next run, otherwise "Re-rank now" shows the same picks (Alvaro, Stage 0).
6. **14:45 to 15:15:** record the 3-minute video with Alvaro narrating, following the Demo journey table. Record a backup take of each screen in case the live run is slow.

**Starter Lovable prompt:** *"Build FirstIn, an internship scout for students. Pages: Morning brief, Events, Memory, Data layer, Evidence, Onboarding. Fetch from VITE\_API\_URL with these endpoints and shapes: \[paste API table and Core shapes\]. Use mock data when the API fails. Clean, minimal, one accent colour, cards with source chips. Every draft shows 'You send it.'"*

## Timeline and merge points

Two merges (14:00 and 14:45), feature freeze at 14:45, submission done by 15:30. Confirm the real submission deadline at the welcome desk now; if it is earlier, cut the Events tab polish and the memory rerun first.

| Time | Alvaro (agent) | Leo (watcher) | Taleb (events, evidence) | Marc (web, deploy) |
| --- | --- | --- | --- | --- |
| 12:15 to 12:40 | Repo, `schemas.py`, `llm.py`, agent stubs on `main` | Aiven Postgres, run schema, share `DATABASE_URL` | Keenable account, manual query tests | `main.py`, Dockerfile, requirements on `main` |
| 12:40 to 13:15 | `profile.py`, Stage 0 and 1 of the ranker | ATS fetchers, company discovery, first poll | `search.py`, `extract.py` | Aiven Runtime hello-world live |
| 13:15 to 14:00 | Stage 2, grounding check, `research.py`, `run.py` | Poller events, classify, ghost score, scheduler on | `verify.py`, ranking, routes | Lovable screens on mock data |
| **14:00** | **Merge 1: watcher + agent into `main`, redeploy** |  |  |  |
| 14:00 to 14:45 | `memory.py`, `kit.py`, n8n webhook | Stats and feed routes, freshness and ghost numbers | Merge events; test users, baseline, blind labels, judge | Real API wiring, fixes |
| **14:45** | **Merge 2 + feature freeze, final deploy** |  |  |  |
| 14:45 to 15:15 | Narrates the video, writes the one-line pitch | Data layer TXT, checks the live URL | Results JSON, chart, pitch slide | Records the video |
| 15:15 to 15:30 | Submits everything | Backup | Backup | Backup |

At 13:15 and 14:30, a 3-minute standup: each person says done, blocked, next. Anything not started by 14:15 is cut.

## Evidence and submission checklist

Five deliverables, each with one owner. Every number we show says whether it comes from a live run or a recorded scenario.

- [ ] **Project name + one-line pitch, hosted URL** (Alvaro): Lovable URL of the frontend, API on Aiven Runtime.
- [ ] **3-minute demo MP4** (Marc records, Alvaro narrates): follows the Demo journey table.
- [ ] **Data layer in action, TXT** (Leo): the tables and what lives where, the polling loop, one real `job_events` excerpt (opened, edited, closed lines with timestamps), one real `runs.trace`, and the memory table before and after a feedback.
- [ ] **Before/after benchmarks, files** (Taleb): `results.json` + chart PNG + a short `results.md`:
  - Match quality: precision@5 for keyword baseline, agent, agent + memory (blind human labels, 4 users), plus OpenAI judge agreement.
  - Grounding: % of displayed reasons whose quote was verified in the posting or CV.
  - Freshness: postings detected since the first poll, lag between publication and our detection.
  - Ghost jobs: % of open internships flagged, with 3 real examples.
  - Events: precision of verified events vs raw search results.
- [ ] **One pitch slide, link** (Taleb, Alvaro reviews):
  - **Who:** students hunting an internship, starting with engineering schools in Paris (us).
  - **Why now:** AI made applying free, so recruiters are flooded and filter harder; being early and precise beats sending more.
  - **Point of difference:** read at the source, first; skip ghost jobs; meet the people hiring at events; never auto-send.
  - **First users:** our own school (ESILV, De Vinci group), student associations like Vinci AI, then school career services who are judged on placement rates.
  - **Built with:** Anthropic, OpenAI, Aiven, Lovable, Keenable, n8n.

## Risks and fallbacks

| Risk | Sign | Fallback |
| --- | --- | --- |
| Too few Paris internships on Greenhouse, Lever, Ashby | Fewer than 30 open internships at 13:30 | Widen to all of France + remote, add London; in the pitch say "internship-heavy boards next" |
| ATS field names differ from this plan | Parse errors on first poll | Print one raw response per ATS first, then map |
| Aiven Runtime deploy fails | No health URL by 13:15 | Ask the Aiven mentors on site immediately; meanwhile keep running locally and expose it through an HTTPS tunnel (cloudflared), since the Lovable app (HTTPS) cannot call `http://localhost` |
| Lovable cannot reach the API | CORS or mixed-content errors | CORS `*` on FastAPI, HTTPS URL only, mock data fallback stays in the UI |
| Event pages are JavaScript-only | Empty extracted text | Use the search snippet and page meta tags; keep only events with a date |
| LLM run too slow for the live demo | Run takes over 60 s | Pre-run at 14:40, demo shows the stored brief; label it "recorded nightly run" |
| Merge conflicts | Anyone edits outside their folder | Folder ownership rule; Alvaro resolves at merge points |
| Not enough time for labels | 14:30 and no test users yet | Label with 2 users instead of 4; keep the baseline vs agent comparison, drop the memory rerun |
