import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { AppShell, PageTitle } from "@/components/AppShell";
import { api, relTime, useLastUserId } from "@/lib/api";

export const Route = createFileRoute("/data")({
  head: () => ({
    meta: [
      { title: "Data layer — FirstIn" },
      { name: "description", content: "Live view of the companies and postings FirstIn watches." },
      { property: "og:title", content: "Data layer — FirstIn" },
      { property: "og:description", content: "Live posting feed, ghost rate and the latest agent run." },
    ],
  }),
  component: DataPage,
});

const kindCls: Record<string, string> = {
  opened: "bg-success-soft text-success",
  edited: "bg-warning-soft text-warning",
  closed: "bg-muted text-muted-foreground",
  reposted: "bg-danger-soft text-destructive",
};

function DataPage() {
  const qc = useQueryClient();
  const live = { refetchInterval: 10_000 };
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats, ...live });
  const feed = useQuery({ queryKey: ["feed"], queryFn: () => api.feed(50), ...live });
  const userId = useLastUserId();
  const brief = useQuery({ queryKey: ["brief", userId], queryFn: () => api.getBrief(userId) });
  const runId = brief.data?.run_id;
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.getRun(runId!), enabled: runId != null, ...live });
  const s = stats.data;
  const tiles = s ? [
    ["Companies watched", s.companies.toLocaleString()],
    ["Open jobs", s.jobs_open.toLocaleString()],
    ["Open internships", s.internships_open.toLocaleString()],
    ["Ghost", `${s.ghost_pct}%`],
    ["New in last 24 h", s.new_last_24h],
    ["Last poll", relTime(s.last_poll_at)],
  ] : [];

  return (
    <AppShell>
      <PageTitle title="Data layer"
        sub={<span className="inline-flex items-center gap-2"><span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" /><span className="relative inline-flex h-2 w-2 rounded-full bg-success" /></span>live · refreshes every 10 s</span>}
        right={<Button variant="outline" onClick={async () => {
          const r = await api.poll();
          toast(`Polled ${r.polled}: ${r.opened} opened, ${r.edited} edited, ${r.closed} closed`);
          qc.invalidateQueries({ queryKey: ["stats"] });
          qc.invalidateQueries({ queryKey: ["feed"] });
        }}>Poll now</Button>} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {tiles.map(([l, v]) => (
          <div key={l} className="rounded-2xl border border-border p-4">
            <p className="text-xs text-muted-foreground">{l}</p>
            <p className="mt-1 font-serif text-2xl tabular-nums">{v}</p>
          </div>
        ))}
      </div>

      <h2 className="mb-3 mt-12 font-serif text-xl font-medium">Feed</h2>
      {feed.data?.length === 0 && (
        <p className="rounded-2xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          No postings opened, edited or closed since the first poll. FirstIn checks every board every 10 minutes.
        </p>
      )}
      <ul className="divide-y divide-border rounded-2xl border border-border empty:hidden">
        {feed.data?.map((f, i) => (
          <li key={i} className="flex items-center gap-3 px-4 py-3 text-sm">
            <span className="w-20 shrink-0 text-xs tabular-nums text-muted-foreground">{relTime(f.at)}</span>
            <span className={`w-20 shrink-0 rounded-full px-2 py-0.5 text-center text-[11px] font-medium ${kindCls[f.kind] ?? "bg-muted"}`}>{f.kind}</span>
            <span className="shrink-0 font-medium">{f.company}</span>
            <span className="min-w-0 flex-1 truncate text-muted-foreground">{f.title}</span>
            <a href={f.url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">open</a>
          </li>
        ))}
      </ul>

      <h2 className="mb-3 mt-12 font-serif text-xl font-medium">Latest run{run.data ? ` #${run.data.id}` : ""}</h2>
      <ol className="space-y-3 border-l border-border pl-5">
        {run.data?.trace.map((t, i) => (
          <li key={i} className="relative text-sm">
            <span className="absolute -left-[25px] top-1.5 h-2 w-2 rounded-full bg-primary" />
            <p>{t.step}: <span className="tabular-nums">{t.count_in} → {t.count_out}</span> <span className="text-muted-foreground">({t.seconds}s)</span></p>
            {t.note && <p className="text-xs text-muted-foreground">{t.note}</p>}
          </li>
        ))}
      </ol>
    </AppShell>
  );
}
