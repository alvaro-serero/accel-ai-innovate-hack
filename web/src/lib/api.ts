// Every network call in FirstIn goes through this file.
import { useEffect, useState, useSyncExternalStore } from "react";
import * as M from "./mocks";
import type {
  Brief, DataStats, EvalResults, EventMatch, EventsRefreshResult, FeedItem, FeedbackResult, Kit, Match,
  PollResult, RunOut, User,
} from "./types";

// Public API on Aiven Runtime; VITE_API_URL overrides it (set it to "" to force mock data).
const DEFAULT_API_URL = "https://01a1638c-60d5-73df-914c-5817003873f2-8080.eur-1.aiven.app";
const BASE = ((import.meta.env["VITE_API_URL"] as string | undefined) ?? DEFAULT_API_URL).replace(/\/$/, "");

// ---- demo-data indicator ----
let usingMocks = false;
const listeners = new Set<() => void>();
function setMock(v: boolean) {
  if (usingMocks === v) return;
  usingMocks = v;
  listeners.forEach((l) => l());
}
export function useUsingMocks() {
  return useSyncExternalStore(
    (l) => { listeners.add(l); return () => listeners.delete(l); },
    () => usingMocks,
    () => false,
  );
}

async function call<T>(method: string, path: string, mock: () => T, body?: unknown): Promise<T> {
  if (!BASE) { setMock(true); return mock(); }
  try {
    const init: RequestInit = { method };
    if (body instanceof FormData) init.body = body;
    else if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "Content-Type": "application/json" }; }
    const res = await fetch(`${BASE}/api${path}`, init);
    if (!res.ok) throw new Error(`${res.status}`);
    const data = (await res.json()) as T;
    setMock(false);
    return data;
  } catch {
    setMock(true);
    return mock();
  }
}

export const api = {
  createUser: (form: FormData) =>
    call<User>("POST", "/users", () => ({
      ...M.mockUser(1),
      name: String(form.get("name") || "Demo Student"),
      email: String(form.get("email") || "student@example.com"),
      city: String(form.get("city") || "Paris"),
      profile: { ...M.mockUser(1).profile, education: [{ school: "Example University", degree: "MSc Computer Science" }] },
    }), form),
  getUser: (id: string) => call<User>("GET", `/users/${id}`, () => M.mockUser(Number(id) || 1)),
  startRun: (id: string) => call<{ run_id: number }>("POST", `/users/${id}/runs`, M.startMockRun, { kind: "manual" }),
  getRun: (runId: number) => call<RunOut>("GET", `/runs/${runId}`, M.mockRun),
  getBrief: (id: string) => call<Brief>("GET", `/users/${id}/brief`, M.mockBrief),
  feedback: (b: { user_id: number; target_type: "job" | "event"; target_id: number; verdict: "up" | "down"; reason: string }) =>
    call<FeedbackResult>("POST", "/feedback", () => ({
      memory_added: [{ id: 99, kind: b.verdict === "up" ? "preference" : "dislike",
        content: b.verdict === "up" ? "Likes roles like this one" : `Not this: ${b.reason || "no reason given"}`,
        source: `feedback:${b.target_type}:${b.target_id}`, created_at: null, superseded_by: null }],
      memory_superseded: [],
    }), b),
  kit: (jobId: number, userId: number) => call<Kit>("POST", `/jobs/${jobId}/kit`, M.mockKit, { user_id: userId }),
  setMatchStatus: (matchId: number, status: Match["status"]) =>
    call<Match>("PATCH", `/matches/${matchId}`, () => ({ ...M.mockBrief().matches.find((m) => m.id === matchId)!, status }), { status }),
  stats: () => call<DataStats>("GET", "/data/stats", M.mockStats),
  feed: (limit = 50) => call<FeedItem[]>("GET", `/data/feed?limit=${limit}`, M.mockFeed),
  poll: () => call<PollResult>("POST", "/watcher/poll", () => ({ polled: 287, opened: 2, edited: 1, closed: 0 })),
  events: (id: string) => call<EventMatch[]>("GET", `/users/${id}/events`, M.mockEvents),
  refreshEvents: (id: string) => call<EventsRefreshResult>("POST", `/users/${id}/events/refresh`, () => ({ found: 12, verified: 5, kept: 1 })),
  eval: () => call<EvalResults>("GET", "/eval", M.mockEval),
};

// ---- current user ----
// The URL (/u/:userId) is the source of truth; we remember the last one so pages
// outside it (Data layer, Evidence, Onboarding) link back to the right student.
const USER_KEY = "firstin:userId";
export function rememberUser(id: string) {
  try { localStorage.setItem(USER_KEY, id); } catch { /* private mode */ }
}
export function useLastUserId() {
  const [id, setId] = useState("1");
  useEffect(() => {
    try { const v = localStorage.getItem(USER_KEY); if (v) setId(v); } catch { /* private mode */ }
  }, []);
  return id;
}

// ---- formatting helpers ----
export function relTime(iso: string | null | undefined) {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}
