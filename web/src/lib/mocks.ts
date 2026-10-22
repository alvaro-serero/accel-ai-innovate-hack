import type { Brief, DataStats, EvalResults, EventMatch, FeedItem, Kit, RunOut, User } from "./types";

const ago = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();

const event: EventMatch = {
  id: 1, score: 78,
  why: "Engineers from your target company are speaking; 2 km from you; students welcome",
  event: {
    id: 11, title: "Cloud & AI Builders Meetup Paris", url: "https://lu.ma/example", kind: "meetup",
    starts_at: "2026-10-28T10:43:23.803661Z", city: "Paris", venue: "Station F",
    companies: ["Amazon"], involvement: { Amazon: "speaker" },
  },
  who_to_meet: [{
    name: "Speaker name", role: "Solutions Architect", company: "Amazon",
    opener: "Your talk on agent infra connects to my internship scout project; how do you handle stale data?",
  }],
};

export const mockBrief = (): Brief => ({
  run_id: 1,
  generated_at: "2026-10-22T06:43:23.803661Z",
  stats: { postings_checked: 412, new_internships: 9, ghosts_skipped: 3, events_found: 4 },
  matches: [
    {
      id: 1, rank: 1, fit_score: 88, status: "new",
      job: { id: 101, title: "Machine Learning Engineer Intern (6 months)", company: "Example AI", city: "Paris",
        url: "https://jobs.lever.co/example-ai/123", first_seen_at: ago(2), published_at: ago(4), ghost_score: 0, ghost_reasons: [] },
      reasons: [
        { claim: "Matches your RAG project", evidence: "experience building retrieval pipelines", source: "posting" },
        { claim: "You have the required stack", evidence: "Python, PyTorch, FastAPI", source: "cv" },
      ],
      gaps: ["No Kubernetes experience mentioned"],
      company_brief: { summary: "Series B AI startup, engineering team doubled this year.", sources: ["https://example.com/news"] },
    },
    {
      id: 2, rank: 2, fit_score: 81, status: "new",
      job: { id: 102, title: "Data Engineer Intern", company: "Sample Fintech", city: "Paris",
        url: "https://boards.greenhouse.io/samplefintech/jobs/456", first_seen_at: ago(8), published_at: ago(23), ghost_score: 0.1, ghost_reasons: [] },
      reasons: [{ claim: "Wants SQL + Airflow", evidence: "SQL, dbt, Airflow", source: "posting" }],
      gaps: [],
      company_brief: { summary: "Fintech scale-up, 300 people.", sources: ["https://example.com/a"] },
    },
    {
      id: 3, rank: 3, fit_score: 76, status: "new",
      job: { id: 103, title: "Applied Research Intern, LLM Evaluation", company: "Mistral AI", city: "Paris",
        url: "https://jobs.lever.co/mistral/789", first_seen_at: ago(5), published_at: ago(6), ghost_score: 0.05, ghost_reasons: [] },
      reasons: [
        { claim: "On your target company list", evidence: "Mistral AI", source: "cv" },
        { claim: "Evaluation work fits your RAG project", evidence: "design evaluation suites for retrieval and reasoning", source: "posting" },
        { claim: "Team is hiring interns this winter", evidence: "announced a new Paris research hub", source: "web" },
      ],
      gaps: ["Research publications preferred", "Start date may be earlier than Feb 2027"],
      company_brief: { summary: "Foundation-model lab, ~700 people, expanding Paris research.", sources: ["https://example.com/mistral"] },
    },
    {
      id: 4, rank: 4, fit_score: 72, status: "new",
      job: { id: 104, title: "Software Engineer Intern — Observability Data", company: "Datadog", city: "Paris",
        url: "https://careers.datadoghq.com/detail/321", first_seen_at: ago(11), published_at: ago(12), ghost_score: 0.2, ghost_reasons: [] },
      reasons: [{ claim: "Python + SQL data pipelines", evidence: "build data pipelines in Python and SQL", source: "posting" }],
      gaps: ["Go experience preferred"],
      company_brief: { summary: "Public observability company, large Paris engineering office.", sources: ["https://example.com/dd"] },
    },
    {
      id: 5, rank: 5, fit_score: 64, status: "new",
      job: { id: 105, title: "AI Intern (all levels)", company: "Demo Corp", city: "Paris",
        url: "https://example.com/demo-corp/ai-intern", first_seen_at: ago(14), published_at: ago(24 * 70), ghost_score: 0.7,
        ghost_reasons: ["Reposted 4 times in 60 days", "No named team or manager", "Published date 70 days ago"] },
      reasons: [{ claim: "Mentions PyTorch", evidence: "familiarity with PyTorch", source: "posting" }],
      gaps: ["Vague role description"],
      company_brief: { summary: "Consulting firm, 5,000 people.", sources: ["https://example.com/demo"] },
    },
  ],
  events: [event],
});

export const mockUser = (id = 1): User => ({
  id, name: "Demo Student", email: "student@example.com", city: "Paris",
  target_roles: ["ML engineer intern", "Data engineer intern"],
  target_companies: ["Amazon", "Datadog", "Mistral AI"],
  start_date: null,
  profile: { skills: ["Python", "PyTorch", "SQL"], projects: [{ name: "RAG assistant", stack: ["Python"], one_line: "Retrieval assistant used by 30 classmates" }] },
  memory: [
    { id: 1, kind: "fact", content: "Targets ML engineer internships starting Feb 2027", source: "onboarding", created_at: null, superseded_by: null },
    { id: 2, kind: "preference", content: "Prefers big tech companies", source: "onboarding", created_at: null, superseded_by: 3 },
    { id: 3, kind: "preference", content: "Prefers startups under 200 people", source: "feedback:job:102", created_at: null, superseded_by: null },
  ],
});

const fullTrace = [
  { step: "SQL prefilter (open internships, city, ghost < 0.6)", count_in: 412, count_out: 64, seconds: 0.1, note: null },
  { step: "Haiku quick score", count_in: 64, count_out: 15, seconds: 8.2, note: null },
  { step: "Sonnet qualifier + grounding check", count_in: 15, count_out: 5, seconds: 21.0, note: null },
  { step: "Company research (Keenable)", count_in: 5, count_out: 5, seconds: 6.4, note: null },
];

let mockRunStartedAt = 0;
export const startMockRun = () => { mockRunStartedAt = Date.now(); return { run_id: 1 }; };

export const mockRun = (): RunOut => {
  const elapsed = mockRunStartedAt ? (Date.now() - mockRunStartedAt) / 1000 : Infinity;
  const steps = Math.min(fullTrace.length, Math.floor(elapsed / 1.8));
  const done = steps >= fullTrace.length;
  return {
    id: 1, kind: "manual", status: done ? "done" : "running",
    started_at: "2026-10-22T10:41:23.803661Z", finished_at: done ? "2026-10-22T10:42:23.803661Z" : null,
    stats: { candidates: 64, scored: 64, deep_scored: 15, picked: 5, ghosts_skipped: 3 },
    trace: fullTrace.slice(0, steps),
  };
};

export const mockKit = (): Kit => ({
  cv_bullets: [
    "Built a retrieval-augmented assistant in Python (FastAPI, PyTorch) used by 30 classmates",
    "Designed an evaluation set of 200 questions to measure answer grounding",
  ],
  cover_letter: "Dear team,\n\nI'm a student looking for a 6-month ML engineering internship starting February 2027. I recently built a retrieval-augmented assistant in Python and PyTorch, and your posting's focus on retrieval pipelines is exactly the work I want to go deeper on.\n\nThank you for your time,\nDemo Student",
  linkedin_note: "Hi, I saw the ML intern opening on your team and it lines up with a RAG assistant I built this year. Would you be open to a quick chat about what the team is working on?",
  contact_hint: "An ML engineer on the applied team; LinkedIn search: 'Example AI machine learning engineer Paris'",
});

export const mockEvents = (): EventMatch[] => [event];

export const mockStats = (): DataStats => ({
  companies: 287, jobs_open: 4120, internships_open: 212, ghost_pct: 18.4, new_last_24h: 37,
  last_poll_at: new Date(Date.now() - 3 * 60_000).toISOString(),
});

export const mockFeed = (): FeedItem[] => [
  { at: new Date(Date.now() - 4 * 60_000).toISOString(), kind: "opened", company: "Example AI", title: "ML Engineer Intern", url: "https://example.com/1" },
  { at: new Date(Date.now() - 19 * 60_000).toISOString(), kind: "edited", company: "Sample Fintech", title: "Data Engineer Intern", url: "https://example.com/2" },
  { at: new Date(Date.now() - 33 * 60_000).toISOString(), kind: "closed", company: "Demo Corp", title: "Backend Intern", url: "https://example.com/3" },
  { at: new Date(Date.now() - 51 * 60_000).toISOString(), kind: "reposted", company: "Demo Corp", title: "AI Intern (all levels)", url: "https://example.com/4" },
];

export const mockEval = (): EvalResults => ({
  jobs: { baseline_p5: 0.35, agent_p5: 0.7, with_memory_p5: 0.8, judge_agreement: 0.82, users: 4, source: "mock" },
  events: { agent_precision: 0.8, raw_precision: 0.3, source: "mock" },
  freshness: { postings_detected: 37, median_lag_hours: 2.5, not_on_linkedin_pct: 40, source: "mock" },
  ghost: { internships_flagged_pct: 18.4, source: "mock" },
  grounding: { reasons_kept: 47, reasons_dropped: 6, source: "mock" },
});
