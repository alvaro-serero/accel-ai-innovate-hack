import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageTitle } from "@/components/AppShell";
import { EventCard } from "@/components/EventCard";
import { api } from "@/lib/api";

export const Route = createFileRoute("/u/$userId/events")({
  head: () => ({
    meta: [
      { title: "Events — FirstIn" },
      { name: "description", content: "Verified events where you can meet people who are hiring." },
      { property: "og:title", content: "Events — FirstIn" },
      { property: "og:description", content: "Meetups and talks with people from your target companies." },
    ],
  }),
  component: EventsPage,
});

function EventsPage() {
  const { userId } = Route.useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["events", userId], queryFn: () => api.events(userId) });
  const [busy, setBusy] = useState(false);
  return (
    <>
      <PageTitle title="Events" sub="Where you can meet people who are hiring."
        right={<Button variant="outline" disabled={busy} onClick={async () => {
          setBusy(true);
          const r = await api.refreshEvents(userId);
          toast(`${r.found} found, ${r.verified} verified, ${r.kept} kept`);
          await qc.invalidateQueries({ queryKey: ["events", userId] });
          setBusy(false);
        }}>{busy ? "Refreshing…" : "Refresh"}</Button>} />
      <div className="space-y-4">
        {!q.data && <Skeleton className="h-48 w-full rounded-2xl" />}
        {q.data?.length === 0 && <p className="text-sm text-muted-foreground">No events yet.</p>}
        {q.data?.map((e) => <EventCard key={e.id} em={e} />)}
      </div>
    </>
  );
}
