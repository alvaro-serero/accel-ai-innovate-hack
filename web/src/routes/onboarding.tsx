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
            <div className="flex flex-wrap gap-1.5">{(user.profile?.skills ?? []).map((s) => <span key={s} className="rounded-full bg-accent px-2.5 py-0.5 text-sm text-accent-foreground">{s}</span>)}</div>
          </Group>
          <Group title="Projects">
            <ul className="space-y-2">{(user.profile?.projects ?? []).map((p) => (
              <li key={p.name} className="text-sm"><span className="font-medium">{p.name}</span> <span className="text-muted-foreground">— {p.one_line} ({p.stack.join(", ")})</span></li>
            ))}</ul>
          </Group>
          <Group title="Education">
            <ul className="space-y-1 text-sm">{(user.profile?.education ?? []).map((ed, i) => (
              <li key={i}>{typeof ed === "string" ? ed : Object.values(ed as Record<string, unknown>).filter(Boolean).join(" · ")}</li>
            ))}</ul>
            {!(user.profile?.education ?? []).length && <p className="text-sm text-muted-foreground">Nothing found.</p>}
          </Group>
          <Button asChild size="lg"><Link to="/u/$userId" params={{ userId: String(user.id) }}>Go to my brief</Link></Button>
        </div>
      )}
    </AppShell>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-border p-5">
      <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</h2>
      {children}
    </section>
  );
}
