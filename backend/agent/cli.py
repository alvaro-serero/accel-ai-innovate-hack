"""Terminal entry point for the agent.

    python -m backend.agent.cli onboard --cv path.pdf --city Paris --roles "ML engineer intern" --companies "Datadog,Mistral AI"
    python -m backend.agent.cli run --user 1
"""
import argparse
import json
from pathlib import Path

from backend.agent import profile


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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
