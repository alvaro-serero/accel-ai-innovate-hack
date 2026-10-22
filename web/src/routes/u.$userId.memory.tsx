import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { PageTitle } from "@/components/AppShell";
import { api } from "@/lib/api";

export const Route = createFileRoute("/u/$userId/memory")({
  head: () => ({
    meta: [
      { title: "Memory — FirstIn" },
      { name: "description", content: "What FirstIn has learned about your preferences." },
      { property: "og:title", content: "Memory — FirstIn" },
      { property: "og:description", content: "Your preferences, facts and dislikes, as FirstIn understands them." },
    ],
  }),
  component: MemoryPage,
});

const kindCls: Record<string, string> = {
  preference: "bg-src-posting text-src-posting-fg",
  fact: "bg-src-cv text-src-cv-fg",
  dislike: "bg-danger-soft text-destructive",
};

function MemoryPage() {
  const { userId } = Route.useParams();
  const q = useQuery({ queryKey: ["user", userId], queryFn: () => api.getUser(userId) });
  const lines = q.data?.memory ?? [];
  return (
    <>
      <PageTitle title="Memory" sub="What FirstIn has learned about you." />
      {!q.data && <Skeleton className="h-40 w-full rounded-2xl" />}
      <ul className="divide-y divide-border rounded-2xl border border-border">
        {lines.map((m) => {
          const old = m.superseded_by != null;
          return (
            <li key={m.id} className={`flex items-start gap-3 p-4 ${old ? "opacity-55" : ""}`}>
              <span className="w-8 shrink-0 pt-0.5 text-xs tabular-nums text-muted-foreground">#{m.id}</span>
              <div className="flex-1">
                <p className={old ? "text-muted-foreground line-through" : ""}>{m.content}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  from {m.source}{old && <> · replaced by #{m.superseded_by}</>}
                </p>
              </div>
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${old ? "bg-muted text-muted-foreground" : kindCls[m.kind] ?? "bg-muted"}`}>{m.kind}</span>
            </li>
          );
        })}
      </ul>
    </>
  );
}
