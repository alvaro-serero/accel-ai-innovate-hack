export type Source = "posting" | "cv" | "web";
export interface Reason { claim: string; evidence: string; source: Source | string }
export interface CompanyBrief { summary: string; sources: string[] }
export interface JobOut {
  id: number; title: string; company: string; city: string; url: string;
  first_seen_at: string; published_at: string | null; ghost_score: number; ghost_reasons: string[];
}
export interface Match {
  id: number; rank: number; fit_score: number; status: string; job: JobOut;
  reasons: Reason[]; gaps: string[]; company_brief: CompanyBrief | null;
}
export interface EventOut {
  id: number; title: string; url: string; kind: string; starts_at: string | null; city: string;
  venue: string | null; companies: string[]; involvement: Record<string, string>;
}
export interface Contact { name: string; role: string | null; company: string | null; opener: string | null }
export interface EventMatch { id: number; score: number; why: string; event: EventOut; who_to_meet: Contact[] }
export interface Brief {
  run_id: number | null; generated_at: string | null;
  stats: { postings_checked: number; new_internships: number; ghosts_skipped: number; events_found: number };
  matches: Match[]; events: EventMatch[];
}
export interface MemoryLine {
  id: number; kind: "preference" | "fact" | "dislike" | string; content: string; source: string;
  created_at: string | null; superseded_by: number | null;
}
export interface Project { name: string; stack: string[]; one_line: string }
export interface User {
  id: number; name: string; email: string; city: string; target_roles: string[]; target_companies: string[];
  start_date: string | null;
  // Shape comes from an LLM (backend/agent/profile.py): render defensively, fields may be strings or lists.
  profile: { skills?: unknown; projects?: unknown; education?: unknown; experiences?: unknown; graduation_year?: number } | null;
  memory?: MemoryLine[];
}
export interface TraceStep { step: string; count_in: number; count_out: number; seconds: number; note: string | null }
export interface RunOut {
  id: number; kind: string; status: "running" | "done" | "failed" | string; started_at: string;
  finished_at: string | null; stats: Record<string, number>; trace: TraceStep[];
}
export interface Kit { cv_bullets: string[]; cover_letter: string; linkedin_note: string; contact_hint: string }
export interface FeedbackResult { memory_added: MemoryLine[]; memory_superseded: number[] }
export interface DataStats {
  companies: number; jobs_open: number; internships_open: number; ghost_pct: number; new_last_24h: number; last_poll_at: string | null;
}
export interface FeedItem { at: string; kind: "opened" | "edited" | "closed" | "reposted" | string; company: string; title: string; url: string }
export interface PollResult { polled: number; opened: number; edited: number; closed: number }
export interface EventsRefreshResult { found: number; verified: number; kept: number }
type Src = { source?: string };
export interface EvalResults {
  jobs: { baseline_p5: number; agent_p5: number; with_memory_p5: number; judge_agreement?: number; users?: number } & Src;
  events: { agent_precision: number; raw_precision: number } & Src;
  freshness: Record<string, number | string>;
  ghost: Record<string, number | string>;
  grounding?: { reasons_kept: number; reasons_dropped: number } & Src;
}
