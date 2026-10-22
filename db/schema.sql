-- FirstIn shared schema. Owner: Leo. Frozen at 12:40: add columns only, never rename or drop.
-- Safe to re-run (if not exists everywhere). Apply with: python -m backend.app.db

-- Companies we watch
create table if not exists companies (
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
create table if not exists jobs (
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
create table if not exists job_events (
  id bigserial primary key,
  job_id int references jobs(id),
  kind text check (kind in ('opened','edited','closed','reposted')),
  at timestamptz default now(),
  detail jsonb
);

create table if not exists users (
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
create table if not exists user_memory (
  id serial primary key,
  user_id int references users(id),
  kind text check (kind in ('preference','fact','dislike')),
  content text not null,            -- 'prefers startups under 200 people'
  source text,                      -- 'feedback:job:123' or 'onboarding'
  created_at timestamptz default now(),
  superseded_by int references user_memory(id)   -- null = active
);

create table if not exists runs (
  id serial primary key,
  user_id int references users(id),
  kind text check (kind in ('nightly','manual','eval')),
  started_at timestamptz default now(),
  finished_at timestamptz,          -- null = still running
  stats jsonb,                      -- candidates, scored, picked, ghosts_skipped, cost
  trace jsonb                       -- step-by-step log shown in the UI
);

create table if not exists matches (
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

create table if not exists feedback (
  id serial primary key,
  user_id int references users(id),
  target_type text check (target_type in ('job','event')),
  target_id int,
  verdict text check (verdict in ('up','down')),
  reason text,
  created_at timestamptz default now()
);

create table if not exists kits (
  id serial primary key,
  user_id int references users(id),
  job_id int references jobs(id),
  cv_bullets jsonb,
  cover_letter text,
  linkedin_note text,
  contact_hint text,
  created_at timestamptz default now()
);

create table if not exists events (
  id serial primary key,
  title text not null,
  url text unique,
  source text,                      -- 'luma','meetup','eventbrite','company site'
  kind text,                        -- hackathon, meetup, career_fair, talk, conference
  starts_at timestamptz,
  city text,
  venue text,
  companies text[] default '{}',
  involvement jsonb,                -- {company: 'host'|'sponsor'|'speaker'|'recruiting'}
  speakers jsonb,                   -- [{name, role, company}]
  student_friendly boolean,
  description text,
  first_seen_at timestamptz default now(),
  verified boolean default false,
  verify_notes text
);

create table if not exists event_matches (
  id serial primary key,
  user_id int references users(id),
  event_id int references events(id),
  score int,
  why text,
  who_to_meet jsonb,
  status text default 'new',
  unique (user_id, event_id)
);

create index if not exists jobs_open_internships_idx on jobs (is_internship, closed_at);
create index if not exists job_events_at_idx on job_events (at desc);
