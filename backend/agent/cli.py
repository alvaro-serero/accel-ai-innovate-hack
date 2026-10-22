"""Terminal entry point for the agent.

    python -m backend.agent.cli onboard --cv path.pdf --city Paris --roles "ML engineer intern" --companies "Datadog,Mistral AI"
    python -m backend.agent.cli qualify --user 1     (dry run: ranks and prints, writes nothing)
    python -m backend.agent.cli research --company "Mistral AI"
    python -m backend.agent.cli run --user 1
"""
import argparse
import asyncio
import json
from pathlib import Path

from backend.agent import profile, qualify, research, run


def cmd_onboard(args) -> None:
    user = profile.onboard_user(
        Path(args.cv).read_bytes(),
        name=args.name,
        email=args.email,
        city=args.city,
        target_roles=args.roles,
        target_companies=args.companies,
        start_date=args.start,
    )
    print(f"user id: {user['id']}  ({len(user['cv_text'])} chars of CV text)")
    print(json.dumps(user["profile"], indent=2, ensure_ascii=False))
    print("memory:")
    for m in user["memory"]:
        print(f"  [{m['id']}] {m['kind']}: {m['content']}  ({m['source']})")


def print_trace(trace: list[dict]) -> None:
    print("trace:")
    for s in trace:
        print(f"  {s['step']:<28} {s['count_in']!s:>5} -> {s['count_out']!s:<5} {s['seconds']:>6}s  {s.get('note') or ''}")


def print_picks(picks: list[dict]) -> None:
    for rank, job in enumerate(picks, 1):
        print(f"\n#{rank}  {job['fit_score']}/100  {job['title']} @ {job['company']}  (quick {job.get('quick_score')})")
        print(f"    {job.get('url') or ''}")
        for r in job["reasons"]:
            print(f"    + {r['claim']}  [{r['source']}: \"{r['evidence']}\"]")
        for g in job.get("gaps", []):
            print(f"    - gap: {g}")
        for f in job.get("red_flags", []):
            print(f"    ! {f}")


def cmd_qualify(args) -> None:
    user = profile.load_user(args.user)
    if user is None:
        raise SystemExit(f"no user {args.user}")
    candidates, ghosts = qualify.load_candidates(user)
    print(f"{len(candidates)} candidates, {ghosts} ghosts skipped")
    if not candidates:
        return
    picks, stats, trace = asyncio.run(qualify.rank_jobs(candidates, user["profile"], user["memory"], user["cv_text"]))
    print_trace(trace)
    print("stats:", stats)
    print_picks(picks)


def cmd_research(args) -> None:
    async def go():  # one event loop: the cached async Anthropic client can't move between loops
        results = await research.search_company(args.company)
        print(f"{len(results)} Keenable results")
        for r in results:
            print(f"  {r['url']}  {r['title'][:80]}")
        return await research.write_brief(args.company, results)

    brief = asyncio.run(go())
    print("brief:", brief.model_dump_json(indent=2) if brief else None)


def print_brief(brief) -> None:
    for m in brief.matches:
        print(f"\n#{m.rank}  {m.fit_score}/100  {m.job.title} @ {m.job.company}  (ghost {m.job.ghost_score:.1f})")
        print(f"    {m.job.url or ''}")
        for r in m.reasons:
            print(f"    + {r.claim}  [{r.source}: \"{r.evidence}\"]")
        for g in m.gaps:
            print(f"    - gap: {g}")
        if m.company_brief:
            print(f"    i {m.company_brief.summary}  {m.company_brief.sources}")
    print(f"\n{len(brief.events)} events")


def cmd_run(args) -> None:
    if profile.load_user(args.user) is None:
        raise SystemExit(f"no user {args.user}")
    run_id = run.create_run(args.user, args.kind)
    print(f"run {run_id} started")
    asyncio.run(run.execute_run(run_id, args.user))
    result = run.load_run(run_id)
    print(f"status: {result['status']}")
    print_trace(result["trace"])
    print("stats:", json.dumps(result["stats"], indent=2))
    if result["status"] == "done":
        print_brief(run.load_brief(args.user))


def main() -> None:
    parser = argparse.ArgumentParser(prog="backend.agent.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("onboard", help="parse a CV and create a user")
    p.add_argument("--cv", required=True, help="path to the CV PDF")
    p.add_argument("--city", default="Paris")
    p.add_argument("--roles", default="", help="comma-separated target roles")
    p.add_argument("--companies", default="", help="comma-separated target companies")
    p.add_argument("--start", default="", help="start date, YYYY-MM-DD or YYYY-MM")
    p.add_argument("--name", default="")
    p.add_argument("--email", default="")
    p.set_defaults(func=cmd_onboard)

    p = sub.add_parser("qualify", help="rank jobs for a user without writing to the DB")
    p.add_argument("--user", type=int, required=True)
    p.set_defaults(func=cmd_qualify)

    p = sub.add_parser("research", help="Keenable search + Haiku brief for one company")
    p.add_argument("--company", required=True)
    p.set_defaults(func=cmd_research)

    p = sub.add_parser("run", help="full run: rank, research, save matches, events, n8n")
    p.add_argument("--user", type=int, required=True)
    p.add_argument("--kind", default="manual", choices=["nightly", "manual", "eval"])
    p.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
