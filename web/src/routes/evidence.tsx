import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, XAxis, YAxis, LabelList } from "recharts";
import { AppShell, PageTitle } from "@/components/AppShell";
import { api } from "@/lib/api";

export const Route = createFileRoute("/evidence")({
  head: () => ({
    meta: [
      { title: "Evidence — FirstIn" },
      { name: "description", content: "How well FirstIn works: precision, grounding, freshness and ghost detection." },
      { property: "og:title", content: "Evidence — FirstIn" },
      { property: "og:description", content: "Blind human labels and an independent judge measure FirstIn's matches." },
    ],
  }),
  component: EvidencePage,
});

const LABELS: Record<string, string> = {
  postings_detected: "Postings detected",
  median_lag_hours: "Median lag (hours)",
  not_on_linkedin_pct: "Not on LinkedIn (%)",
  internships_flagged_pct: "Internships flagged (%)",
};
const label = (k: string) => LABELS[k] ?? k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const pct = (n: number) => `${Math.round(n * 100)}%`;

function Block({ title, mock, children }: { title: string; mock?: boolean; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-border p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-medium">{title}</h2>
        {mock && <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">sample data</span>}
      </div>
      {children}
    </section>
  );
}

function Bars({ data }: { data: { name: string; v: number }[] }) {
  const colors = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)"];
  return (
    <div className="h-44">
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 40 }}>
          <XAxis type="number" domain={[0, 1]} hide />
          <YAxis type="category" dataKey="name" width={140} tickLine={false} axisLine={false} tick={{ fontSize: 13, fill: "var(--muted-foreground)" }} />
          <Bar dataKey="v" radius={6} barSize={22}>
            {data.map((_, i) => <Cell key={i} fill={colors[data.length === 2 ? i + 1 : i]} />)}
            <LabelList dataKey="v" position="right" formatter={(v: number) => pct(v)} style={{ fontSize: 12, fill: "var(--foreground)" }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function EvidencePage() {
  const q = useQuery({ queryKey: ["eval"], queryFn: api.eval });
  const e = q.data;
  const isMock = (b?: { source?: unknown }) => b?.source === "mock";
  const entries = (o: Record<string, unknown>) => Object.entries(o).filter(([, v]) => typeof v === "number") as [string, number][];
  return (
    <AppShell>
      <PageTitle title="Evidence" sub={e ? `Blind human labels, ${e.jobs.users ?? "?"} users; OpenAI as independent judge` : undefined} />
      {e && (
        <div className="space-y-5">
          <Block title="Precision@5 — internship matches" mock={isMock(e.jobs)}>
            <Bars data={[
              { name: "Keyword baseline", v: e.jobs.baseline_p5 },
              { name: "Agent", v: e.jobs.agent_p5 },
              { name: "Agent + memory", v: e.jobs.with_memory_p5 },
            ]} />
          </Block>
          <Block title="Event precision" mock={isMock(e.events)}>
            <Bars data={[
              { name: "Raw search", v: e.events.raw_precision },
              { name: "Verified", v: e.events.agent_precision },
            ]} />
          </Block>
          <div className="grid gap-5 sm:grid-cols-2">
            {e.grounding && e.grounding.reasons_kept + e.grounding.reasons_dropped > 0 && (
              <Block title="Grounding" mock={isMock(e.grounding)}>
                <p className="font-serif text-4xl">{pct(e.grounding.reasons_kept / (e.grounding.reasons_kept + e.grounding.reasons_dropped))}</p>
                <p className="mt-1 text-sm text-muted-foreground">of shown reasons verified in the posting or CV</p>
              </Block>
            )}
            {e.jobs.judge_agreement != null && (
              <Block title="Judge agreement" mock={isMock(e.jobs)}>
                <p className="font-serif text-4xl">{pct(e.jobs.judge_agreement)}</p>
                <p className="mt-1 text-sm text-muted-foreground">agreement between human labels and the judge</p>
              </Block>
            )}
            <Block title="Freshness" mock={isMock(e.freshness)}>
              <dl className="space-y-2">
                {entries(e.freshness).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-sm"><dt className="text-muted-foreground">{label(k)}</dt><dd className="tabular-nums font-medium">{v}</dd></div>
                ))}
              </dl>
            </Block>
            <Block title="Ghost jobs" mock={isMock(e.ghost)}>
              <dl className="space-y-2">
                {entries(e.ghost).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-sm"><dt className="text-muted-foreground">{label(k)}</dt><dd className="tabular-nums font-medium">{v}</dd></div>
                ))}
              </dl>
            </Block>
          </div>
        </div>
      )}
    </AppShell>
  );
}
