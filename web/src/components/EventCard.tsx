import type { ReactNode } from "react";
import type { EventMatch } from "@/lib/types";
import { CopyButton } from "./AppShell";

// The backend `why` is a terse machine line ("Thales is sponsor; hackathon on 02 Dec; in Paris; students welcome"),
// and date, kind and city are already on the card. We rebuild a readable sentence from `involvement` instead,
// and only read `why` to know which companies are the student's targets and whether students are welcome.
const ROLES: [string, string][] = [
  ["host", "Hosted by"],
  ["speaker", "Talk by"],
  ["recruiting", "Recruiting on site:"],
  ["sponsor", "Sponsored by"],
];
const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function names(list: string[], isTarget: (c: string) => boolean): ReactNode {
  return list.map((c, i) => (
    <span key={c}>
      {i > 0 && (i === list.length - 1 ? " and " : ", ")}
      <span className={isTarget(c) ? "font-semibold text-primary" : "font-medium text-foreground"}>{c}</span>
    </span>
  ));
}

export function EventCard({ em, compact }: { em: EventMatch; compact?: boolean }) {
  const e = em.event;
  const d = e.starts_at ? new Date(e.starts_at) : null;
  // Date-only events come back as midnight UTC: show the day without a fake "01:00 AM".
  const hasTime = d != null && (d.getUTCHours() !== 0 || d.getUTCMinutes() !== 0);
  const tz = hasTime ? undefined : "UTC";
  const kind = (e.kind ?? "event").replace(/_/g, " ");

  const why = norm(em.why ?? "");
  const isTarget = (c: string) => why.includes(norm(c));
  const studentsWelcome = why.includes("students welcome");
  const byRole = ROLES.map(([role, label]) => [label, Object.keys(e.involvement).filter((c) => e.involvement[c] === role)] as const)
    .filter(([, list]) => list.length > 0);
  const others = e.companies.filter((c) => !(c in e.involvement));
  const targetsHere = e.companies.filter(isTarget);

  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <div className="flex gap-4">
        <div className="flex w-14 shrink-0 flex-col items-center rounded-xl bg-accent py-2 text-accent-foreground">
          <span className="text-[10px] font-medium uppercase">{d ? d.toLocaleDateString("en", { month: "short", timeZone: tz }) : "Date"}</span>
          <span className="font-serif text-2xl leading-none">{d ? d.toLocaleDateString("en", { day: "numeric", timeZone: tz }) : "TBA"}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium capitalize text-secondary-foreground">{kind}</span>
            {studentsWelcome && <span className="rounded-full bg-success-soft px-2 py-0.5 text-[11px] font-medium text-success">Students welcome</span>}
            <span className="text-xs text-muted-foreground">
              {d ? `${d.toLocaleString("en", hasTime ? { weekday: "short", hour: "2-digit", minute: "2-digit" } : { weekday: "short", timeZone: "UTC" })} · ` : ""}{e.city}{e.venue ? ` · ${e.venue}` : ""}
            </span>
          </div>
          <h3 className="mt-1.5 font-medium">{e.title}</h3>

          {(byRole.length > 0 || others.length > 0) && (
            <ul className="mt-2 space-y-0.5 text-sm text-muted-foreground">
              {byRole.map(([label, list]) => <li key={label}>{label} {names([...list], isTarget)}</li>)}
              {others.length > 0 && <li>With {names(others, isTarget)}</li>}
            </ul>
          )}
          {targetsHere.length > 0 && (
            <p className="mt-2 text-sm">A chance to meet {names(targetsHere, () => true)}, {targetsHere.length > 1 ? "among your target companies" : "one of your target companies"}.</p>
          )}

          {!compact && em.who_to_meet.length > 0 && (
            <div className="mt-4 space-y-3">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Who to meet</p>
              {em.who_to_meet.map((p, i) => {
                const meta = [p.role, p.company].filter(Boolean).join(", ");
                const opener = (p.opener ?? "").trim();
                return (
                  <div key={i}>
                    <p className="text-sm"><span className="font-medium">{p.name}</span>{meta && <span className="text-muted-foreground"> · {meta}</span>}</p>
                    {opener ? (
                      <div className="mt-2 flex items-start gap-3 rounded-xl border-l-2 border-primary bg-muted p-3">
                        <p className="min-w-0 flex-1 whitespace-pre-wrap break-words text-sm italic">“{opener}”</p>
                        <CopyButton text={opener} />
                      </div>
                    ) : (
                      <p className="mt-1 text-xs text-muted-foreground">No opener prepared for this person yet.</p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {e.url && (
            <a href={e.url} target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm font-medium text-primary hover:underline">
              Register →
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
