import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { ThumbsDown, ThumbsUp, AlertTriangle, ExternalLink, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { api, relTime } from "@/lib/api";
import type { FeedbackResult, Match, RunOut } from "@/lib/types";
import { EventCard } from "@/components/EventCard";
import { KitDrawer } from "@/components/KitDrawer";

export const Route = createFileRoute("/u/$userId/")({
  head: () => ({
    meta: [
      { title: "Morning brief — FirstIn" },
      { name: "description", content: "Your overnight internship brief: fresh matches, ghost jobs skipped, events nearby." },
      { property: "og:title", content: "Morning brief — FirstIn" },
      { property: "og:description", content: "Fresh internships found overnight, with grounded reasons." },
    ],
  }),
  component: BriefPage,
});

const sourceCls: Record<string, string> = {
  posting: "bg-src-posting text-src-posting-fg",
  cv: "bg-src-cv text-src-cv-fg",
  web: "bg-src-web text-src-web-fg",
};

function BriefPage() {
  const { userId } = Route.useParams();
  const qc = useQueryClient();
  const brief = useQuery({ queryKey: ["brief", userId], queryFn: () => api.getBrief(userId) });
  const [run, setRun] = useState<RunOut | null>(null);
  const [running, setRunning] = useState(false);
  const [kitFor, setKitFor] = useState<Match | null>(null);
  const [downFor, setDownFor] = useState<Match | null>(null);
  const [applied, setApplied] = useState<Set<number>>(new Set());
  // Thumbs-down hides the card right away; the next run re-ranks with the new memory.
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());
  const [memoryChanged, setMemoryChanged] = useState(false);

  async function runNow() {
    setRunning(true);
    setRun(null);
    setMemoryChanged(false);
    const { run_id } = await api.startRun(userId);
    // poll every 2s
    for (;;) {
      const r = await api.getRun(run_id);
      setRun(r);
      if (r.status === "done" || r.status === "failed") break;
      await new Promise((res) => setTimeout(res, 2000));
    }
    setRunning(false);
    await qc.invalidateQueries({ queryKey: ["brief", userId] });
  }

  function learned(r: FeedbackResult) {
    r.memory_added.forEach((m) => toast(`FirstIn learned: ${m.content}`));
    if (r.memory_added.length === 0) toast("Thanks — noted.");
    qc.invalidateQueries({ queryKey: ["user", userId] });
  }

  async function up(m: Match) {
    learned(await api.feedback({ user_id: Number(userId), target_type: "job", target_id: m.job.id, verdict: "up", reason: "" }));
  }

  const b = brief.data;
  const picks = b?.matches.filter((m) => m.status !== "dismissed" && !dismissed.has(m.id)).slice(0, 5) ?? [];
  const today = new Date().toLocaleDateString("en", { weekday: "long", day: "numeric", month: "long" });

  return (
    <TooltipProvider delayDuration={150}>
      <div className="mb-10 flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">{today}</p>
          <h1 className="mt-1 font-serif text-3xl font-medium tracking-tight">Good morning.</h1>
          {b ? (
            <p className="mt-4 max-w-xl text-lg leading-relaxed">
              Since last night: <b className="font-semibold">{b.stats.postings_checked}</b> postings checked,{" "}
              <b className="font-semibold">{b.stats.new_internships}</b> new internships,{" "}
              <b className="font-semibold">{b.stats.ghosts_skipped}</b> ghost jobs skipped.
            </p>
          ) : <Skeleton className="mt-4 h-6 w-96" />}
          {b?.generated_at && (
            <p className="mt-2 text-xs text-muted-foreground">
              replayed nightly run · generated {new Date(b.generated_at).toLocaleString("en", { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" })}
            </p>
          )}
        </div>
        <Button onClick={runNow} disabled={running}>
          {running ? <><Loader2 className="h-4 w-4 animate-spin" /> Running</> : "Run now"}
        </Button>
      </div>

      {run && (
        <div className="mb-10 rounded-2xl border border-border bg-muted p-5">
          <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Run #{run.id} · {run.status}
          </p>
          <ol className="space-y-1.5 text-sm">
            {run.trace.map((s, i) => (
              <li key={i} className="flex justify-between gap-4">
                <span>{s.step}</span>
                <span className="tabular-nums text-muted-foreground">{s.count_in} → {s.count_out} · {s.seconds}s</span>
              </li>
            ))}
            {run.status === "running" && <li className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> working…</li>}
          </ol>
        </div>
      )}

      {memoryChanged && !running && (
        <div className="mb-6 flex items-center gap-4 rounded-2xl border border-primary/30 bg-accent p-4 text-sm text-accent-foreground">
          <Sparkles className="h-4 w-4 shrink-0" />
          <p className="flex-1">Memory updated. Re-rank your brief with what FirstIn just learned.</p>
          <Button size="sm" onClick={runNow}>Re-rank now</Button>
        </div>
      )}

      <div className="space-y-5">
        {!b && [0, 1, 2].map((i) => <Skeleton key={i} className="h-56 w-full rounded-2xl" />)}
        {b && b.matches.length === 0 && !running && (
          <div className="rounded-2xl border border-dashed border-border p-10 text-center">
            <p className="font-serif text-xl">No brief yet.</p>
            <p className="mt-2 text-sm text-muted-foreground">FirstIn hasn't scouted for you yet. Run it now to get your first picks.</p>
            <Button className="mt-5" onClick={runNow}>Run my first scout</Button>
          </div>
        )}
        {picks.map((m) => {
          const ghost = m.job.ghost_score >= 0.6;
          const isApplied = applied.has(m.id) || m.status === "applied";
          return (
            <article key={m.id} className="rounded-2xl border border-border bg-card p-6">
              <div className="flex items-start gap-5">
                <div className="flex-1">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">#{m.rank}</span>
                    <span>· first seen {relTime(m.job.first_seen_at)}</span>
                    {ghost && (
                      <Tooltip>
                        <TooltipTrigger className="inline-flex items-center gap-1 rounded-full bg-danger-soft px-2 py-0.5 font-medium text-destructive">
                          <AlertTriangle className="h-3 w-3" /> likely ghost
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs">
                          <ul className="list-disc pl-4">{m.job.ghost_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                        </TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                  <h2 className="mt-2 text-lg font-semibold leading-snug">{m.job.title}</h2>
                  <p className="text-sm text-muted-foreground">{m.job.company} · {m.job.city}</p>
                  <a href={m.job.url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-sm text-primary hover:underline">
                    View posting <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <div className="text-right">
                  <div className="font-serif text-5xl font-medium leading-none text-primary tabular-nums">{m.fit_score}</div>
                  <div className="mt-1 text-[11px] uppercase tracking-wide text-muted-foreground">fit</div>
                </div>
              </div>

              <ul className="mt-5 space-y-3">
                {m.reasons.map((r, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className={`mt-0.5 shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase ${sourceCls[r.source] ?? "bg-muted text-muted-foreground"}`}>{r.source}</span>
                    <div className="text-sm">
                      <p>{r.claim}</p>
                      <p className="italic text-muted-foreground">“{r.evidence}”</p>
                    </div>
                  </li>
                ))}
              </ul>

              {m.gaps.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {m.gaps.map((g) => <span key={g} className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground">{g}</span>)}
                </div>
              )}

              {m.company_brief && (
                <p className="mt-4 border-t border-border pt-4 text-sm text-muted-foreground">
                  {m.company_brief.summary}{" "}
                  {m.company_brief.sources.map((s, i) => (
                    <a key={s} href={s} target="_blank" rel="noreferrer" className="text-primary hover:underline">[{i + 1}]</a>
                  ))}
                </p>
              )}

              <div className="mt-5 flex flex-wrap items-center gap-2">
                <Button variant="outline" size="icon" aria-label="Good match" onClick={() => up(m)}><ThumbsUp className="h-4 w-4" /></Button>
                <Button variant="outline" size="icon" aria-label="Bad match" onClick={() => setDownFor(m)}><ThumbsDown className="h-4 w-4" /></Button>
                <div className="flex-1" />
                <Button variant="outline" disabled={isApplied} onClick={async () => {
                  await api.setMatchStatus(m.id, "applied");
                  setApplied((s) => new Set(s).add(m.id));
                  toast.success("Marked as applied");
                }}>{isApplied ? "Applied" : "Mark applied"}</Button>
                <Button onClick={() => setKitFor(m)}>Prepare kit</Button>
              </div>
            </article>
          );
        })}
      </div>

      {b && b.events.length > 0 && (
        <section className="mt-14">
          <h2 className="mb-4 font-serif text-2xl font-medium">Events near you</h2>
          <div className="space-y-4">{b.events.map((e) => <EventCard key={e.id} em={e} compact />)}</div>
        </section>
      )}

      <KitDrawer match={kitFor} userId={Number(userId)} onClose={() => setKitFor(null)} />
      <DownDialog match={downFor} onClose={() => setDownFor(null)} onSubmit={async (reason) => {
        const m = downFor!;
        setDownFor(null);
        setDismissed((s) => new Set(s).add(m.id));
        setMemoryChanged(true);
        void api.setMatchStatus(m.id, "dismissed");
        learned(await api.feedback({ user_id: Number(userId), target_type: "job", target_id: m.job.id, verdict: "down", reason }));
      }} />
    </TooltipProvider>
  );
}

const PICKS = ["Too big a company", "Wrong role", "Wrong city", "Not interested in this domain"];

function DownDialog({ match, onClose, onSubmit }: { match: Match | null; onClose: () => void; onSubmit: (r: string) => void }) {
  const [pick, setPick] = useState<string | null>(null);
  const [text, setText] = useState("");
  const reason = [pick, text.trim()].filter(Boolean).join(" — ");
  return (
    <Dialog open={!!match} onOpenChange={(o) => { if (!o) { onClose(); setPick(null); setText(""); } }}>
      <DialogContent>
        <DialogHeader><DialogTitle className="font-serif text-xl font-medium">Why?</DialogTitle></DialogHeader>
        <div className="flex flex-wrap gap-2">
          {PICKS.map((p) => (
            <button key={p} onClick={() => setPick(pick === p ? null : p)}
              className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${pick === p ? "border-primary bg-accent text-accent-foreground" : "border-border hover:bg-muted"}`}>
              {p}
            </button>
          ))}
        </div>
        <Textarea placeholder="Anything else? (optional)" value={text} onChange={(e) => setText(e.target.value)} />
        <DialogFooter>
          <Button disabled={!reason} onClick={() => { onSubmit(reason); setPick(null); setText(""); }}>Send feedback</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
