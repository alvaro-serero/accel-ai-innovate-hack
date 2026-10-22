import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AppShell, PageTitle } from "@/components/AppShell";
import { api, rememberUser } from "@/lib/api";
import type { User } from "@/lib/types";

export const Route = createFileRoute("/onboarding")({
  head: () => ({
    meta: [
      { title: "Get started — FirstIn" },
      { name: "description", content: "Upload your CV and tell FirstIn what internships you're looking for." },
      { property: "og:title", content: "Get started — FirstIn" },
      { property: "og:description", content: "Set up your internship scout in two minutes." },
    ],
  }),
  component: Onboarding,
});

function Onboarding() {
  const [busy, setBusy] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    const created = await api.createUser(new FormData(e.currentTarget));
    rememberUser(String(created.id));
    setUser(created);
    setBusy(false);
  }

  const field = (name: string, label: string, props: React.ComponentProps<typeof Input> = {}) => (
    <div className="space-y-1.5"><Label htmlFor={name}>{label}</Label><Input id={name} name={name} {...props} /></div>
  );

  return (
    <AppShell>
      <PageTitle title={user ? `Welcome, ${(user.name ?? "").split(" ")[0]}` : "Get started"}
        sub={user ? "Here's what FirstIn read from your CV." : "Tell FirstIn who you are and what you want. It does the watching."} />
      {!user ? (
        <form onSubmit={submit} className="space-y-5">
          <div className="space-y-1.5">
            <Label htmlFor="cv">CV (PDF)</Label>
            <Input id="cv" name="cv" type="file" accept="application/pdf" required />
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            {field("name", "Name", { required: true })}
            {field("email", "Email", { type: "email", required: true })}
            {field("city", "City", { placeholder: "Paris" })}
            {field("start_date", "Start date", { type: "date" })}
          </div>
          {field("target_roles", "Target roles", { placeholder: "ML engineer intern, Data engineer intern" })}
          {field("target_companies", "Target companies", { placeholder: "Amazon, Datadog, Mistral AI" })}
          <Button type="submit" disabled={busy} size="lg">{busy ? "Reading your CV…" : "Create my scout"}</Button>
        </form>
      ) : (
        <div className="space-y-6">
          <Group title="Skills">
            <div className="flex flex-wrap gap-1.5">{asList(user.profile?.skills).map((s, i) => <span key={i} className="rounded-full bg-accent px-2.5 py-0.5 text-sm text-accent-foreground">{asText(s)}</span>)}</div>
          </Group>
          <Group title="Projects">
            <ul className="space-y-2">{asList(user.profile?.projects).map((raw, i) => {
              if (typeof raw !== "object" || raw === null) return <li key={i} className="text-sm">{asText(raw)}</li>;
              const p = raw as Item;
              const stack = asList(p.stack).map(asText).join(", ");
              return (
                <li key={i} className="text-sm"><span className="font-medium">{asText(p.name)}</span>
                  {p.one_line != null && <span className="text-muted-foreground"> — {asText(p.one_line)}</span>}
                  {stack && <span className="text-muted-foreground"> ({stack})</span>}
                </li>
              );
            })}</ul>
          </Group>
          {asList(user.profile?.experiences).length > 0 && (
            <Group title="Experience">
              <ul className="space-y-2">{asList(user.profile?.experiences).map((raw, i) => {
                const x = (typeof raw === "object" && raw !== null ? raw : {}) as Item;
                return (
                  <li key={i} className="text-sm">
                    {typeof raw === "object" && raw !== null
                      ? <><span className="font-medium">{asText(x.role)}</span>{x.org != null && <>, {asText(x.org)}</>}{x.one_line != null && <span className="text-muted-foreground"> — {asText(x.one_line)}</span>}</>
                      : asText(raw)}
                  </li>
                );
              })}</ul>
            </Group>
          )}
          <Group title="Education">
            <ul className="space-y-1 text-sm">{asList(user.profile?.education).map((ed, i) => <li key={i}>{asText(ed)}</li>)}</ul>
            {!asList(user.profile?.education).length && <p className="text-sm text-muted-foreground">Nothing found.</p>}
          </Group>
          <Button asChild size="lg"><Link to="/u/$userId" params={{ userId: String(user.id) }}>Go to my brief</Link></Button>
        </div>
      )}
    </AppShell>
  );
}

// The CV profile is LLM output: a field can be a string, a list, an object or missing.
const asList = (v: unknown): unknown[] => (Array.isArray(v) ? v : v == null || v === "" ? [] : [v]);
const asText = (v: unknown): string =>
  typeof v === "string" ? v
  : v && typeof v === "object" ? Object.values(v as Record<string, unknown>).filter((x) => typeof x === "string" || typeof x === "number").join(" · ")
  : String(v ?? "");
type Item = { name?: unknown; org?: unknown; role?: unknown; one_line?: unknown; stack?: unknown };

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-border p-5">
      <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</h2>
      {children}
    </section>
  );
}
