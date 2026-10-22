import type { EventMatch } from "@/lib/types";
import { CopyButton } from "./AppShell";

export function EventCard({ em, compact }: { em: EventMatch; compact?: boolean }) {
  const e = em.event;
  const d = e.starts_at ? new Date(e.starts_at) : null;
  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <div className="flex gap-4">
        <div className="flex w-14 shrink-0 flex-col items-center rounded-xl bg-accent py-2 text-accent-foreground">
          <span className="text-[10px] font-medium uppercase">{d ? d.toLocaleDateString("en", { month: "short" }) : "Date"}</span>
          <span className="font-serif text-2xl leading-none">{d ? d.getDate() : "TBA"}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium capitalize text-secondary-foreground">{e.kind}</span>
            <span className="text-xs text-muted-foreground">
              {d ? `${d.toLocaleString("en", { weekday: "short", hour: "2-digit", minute: "2-digit" })} · ` : ""}{e.city}{e.venue ? ` · ${e.venue}` : ""}
            </span>
          </div>
          <h3 className="mt-1.5 font-medium">{e.title}</h3>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {e.companies.map((c) => (
              <span key={c} className="rounded-md border border-border px-2 py-0.5 text-xs">{c}{e.involvement[c] ? ` · ${e.involvement[c]}` : ""}</span>
            ))}
          </div>
          <p className="mt-3 text-sm text-muted-foreground">{em.why}</p>
          {!compact && em.who_to_meet.length > 0 && (
            <div className="mt-4 space-y-3">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Who to meet</p>
              {em.who_to_meet.map((p, i) => (
                <div key={i}>
                  <p className="text-sm"><span className="font-medium">{p.name}</span> <span className="text-muted-foreground">· {p.role}, {p.company}</span></p>
                  <div className="mt-2 flex items-start gap-3 rounded-xl border-l-2 border-primary bg-muted p-3">
                    <p className="flex-1 text-sm italic">“{p.opener}”</p>
                    <CopyButton text={p.opener} />
                  </div>
                </div>
              ))}
            </div>
          )}
          <a href={e.url} target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm font-medium text-primary hover:underline">
            Register →
          </a>
        </div>
      </div>
    </div>
  );
}
