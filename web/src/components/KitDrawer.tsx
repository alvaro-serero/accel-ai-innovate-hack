import { useQuery } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { Match } from "@/lib/types";
import { CopyButton } from "./AppShell";

export function KitDrawer({ match, userId, onClose }: { match: Match | null; userId: number; onClose: () => void }) {
  const q = useQuery({
    queryKey: ["kit", match?.job.id, userId],
    queryFn: () => api.kit(match!.job.id, userId),
    enabled: !!match,
    staleTime: Infinity,
  });
  const k = q.data;
  return (
    <Sheet open={!!match} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
        <SheetHeader>
          <SheetTitle className="font-serif text-xl font-medium">Application kit</SheetTitle>
          {match && <p className="text-sm text-muted-foreground">{match.job.title} · {match.job.company}</p>}
        </SheetHeader>
        <div className="mt-5 rounded-xl bg-primary p-4 text-center text-sm font-medium text-primary-foreground">
          You send it. FirstIn never sends anything for you.
        </div>
        {q.isLoading || !k ? (
          <div className="mt-6 space-y-6">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="space-y-2"><Skeleton className="h-4 w-28" /><Skeleton className="h-16 w-full" /></div>
            ))}
          </div>
        ) : (
          <div className="mt-6 space-y-6">
            <Section title="CV bullets" copy={k.cv_bullets.map((b) => `• ${b}`).join("\n")}>
              <ul className="list-disc space-y-1.5 pl-5 text-sm">{k.cv_bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>
            </Section>
            <Section title="Cover letter" copy={k.cover_letter}>
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{k.cover_letter}</p>
            </Section>
            <Section title="LinkedIn note" copy={k.linkedin_note}
              extra={<span className={`text-xs ${k.linkedin_note.length > 300 ? "text-destructive" : "text-muted-foreground"}`}>{k.linkedin_note.length}/300</span>}>
              <p className="text-sm leading-relaxed">{k.linkedin_note}</p>
            </Section>
            <Section title="Contact hint" copy={k.contact_hint}>
              <p className="text-sm text-muted-foreground">{k.contact_hint}</p>
            </Section>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Section({ title, copy, extra, children }: { title: string; copy: string; extra?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</h4>
        <div className="flex items-center gap-3">{extra}<CopyButton text={copy} /></div>
      </div>
      {children}
    </section>
  );
}
