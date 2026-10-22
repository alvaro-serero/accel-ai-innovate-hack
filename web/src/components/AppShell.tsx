import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { BookOpen, CalendarDays, Database, FlaskConical, Mail, UserPlus } from "lucide-react";
import { useLastUserId, useUsingMocks } from "@/lib/api";

export function AppShell({ userId: fromUrl, children }: { userId?: string; children: ReactNode }) {
  const mocks = useUsingMocks();
  const lastUserId = useLastUserId();
  const userId = fromUrl ?? lastUserId;
  const items = [
    { to: "/u/$userId", params: { userId }, label: "Morning brief", icon: Mail, exact: true },
    { to: "/u/$userId/events", params: { userId }, label: "Events", icon: CalendarDays },
    { to: "/u/$userId/memory", params: { userId }, label: "Memory", icon: BookOpen },
    { to: "/data", label: "Data layer", icon: Database },
    { to: "/evidence", label: "Evidence", icon: FlaskConical },
    { to: "/onboarding", label: "Onboarding", icon: UserPlus },
  ] as const;
  return (
    <div className="flex min-h-screen bg-background">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-4 py-8 md:flex">
        <Link to="/u/$userId" params={{ userId }} className="mb-10 px-3 font-serif text-2xl font-semibold tracking-tight text-primary">
          FirstIn
        </Link>
        <nav className="flex flex-col gap-1">
          {items.map((it) => (
            <Link
              key={it.label}
              to={it.to}
              params={{ userId } as never}
              activeOptions={{ exact: "exact" in it }}
              className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              activeProps={{ className: "bg-sidebar-accent !text-sidebar-accent-foreground font-medium" }}
            >
              <it.icon className="h-4 w-4" />
              {it.label}
            </Link>
          ))}
        </nav>
        <p className="mt-auto px-3 text-xs leading-relaxed text-muted-foreground">
          FirstIn prepares. You send. Nothing goes out without you.
        </p>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-border px-6 md:justify-end">
          <span className="font-serif text-xl font-semibold text-primary md:hidden">FirstIn</span>
          {mocks && (
            <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground ring-1 ring-border">demo data</span>
          )}
        </header>
        <main className="mx-auto w-full max-w-3xl px-6 py-10">{children}</main>
      </div>
    </div>
  );
}

export function PageTitle({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-8 flex items-start justify-between gap-4">
      <div>
        <h1 className="font-serif text-3xl font-medium tracking-tight">{title}</h1>
        {sub && <p className="mt-2 text-sm text-muted-foreground">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        const { toast } = await import("sonner");
        toast.success("Copied");
      }}
      className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
    >
      {label}
    </button>
  );
}
