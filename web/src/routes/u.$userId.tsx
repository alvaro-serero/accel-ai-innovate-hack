import { createFileRoute, Outlet } from "@tanstack/react-router";
import { useEffect } from "react";
import { AppShell } from "@/components/AppShell";
import { rememberUser } from "@/lib/api";

export const Route = createFileRoute("/u/$userId")({
  component: UserLayout,
});

function UserLayout() {
  const { userId } = Route.useParams();
  useEffect(() => rememberUser(userId), [userId]);
  return (
    <AppShell userId={userId}>
      <Outlet />
    </AppShell>
  );
}
