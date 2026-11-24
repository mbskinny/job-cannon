"""Read interview prep concepts for an accuracy audit, and apply its results.

Usage (from the repo root):
    uv run python .claude/skills/audit-concepts/scripts/concept_audit.py list [--older-than DAYS | --all] [--concept ID] [--tag T ...]
    uv run python .claude/skills/audit-concepts/scripts/concept_audit.py fix ID changes.json
    uv run python .claude/skills/audit-concepts/scripts/concept_audit.py mark ID [ID ...]

list prints JSON: the concepts due for a check (by default those never checked;
--older-than DAYS adds those last checked more than DAYS ago; --all lists every
one), each with its explanation, notes, tags, the interview questions it's
linked to, and its quiz questions (prompt and answer, to keep them consistent).
Read-only.

fix applies changes.json (explanation and/or notes) to one concept, keeping its
name and tags, and marks it checked.

mark records that the given concepts were checked and found correct.

fix backs up the profile first (job-cannon backup, into the profile's backup
folder) unless --no-backup. Data folder and profile resolve the same way as the
app: --data-dir, then JOB_CANNON_DATA, then ~/JobCannon; --profile, then
JOB_CANNON_PROFILE, then the active profile.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from job_cannon import agent_data, db, profiles
from job_cannon.repo import prep

FIELDS = {"explanation", "notes"}


def concept_for_audit(conn, row) -> dict:
    return {
        **agent_data.concept_summary(row),
        "notes": row["notes"],
        "checked_at": row["checked_at"],
        "interview_questions": [q["prompt"] for q in prep.questions_for_concept(conn, row["id"])],
        "quiz_questions": [
            {"id": z["id"], "prompt": z["prompt"], "answer": z["answer"]}
            for z in prep.list_quiz_questions(conn, concept_id=row["id"])
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir")
    p.add_argument("--profile")
    sub = p.add_subparsers(dest="command", required=True)
    p_list = sub.add_parser("list", help="JSON: concepts due for a check")
    due = p_list.add_mutually_exclusive_group()
    due.add_argument("--older-than", type=int, metavar="DAYS", help="also those last checked more than DAYS ago")
    due.add_argument("--all", action="store_true", help="every concept")
    p_list.add_argument("--concept", type=int, help="only this concept")
    p_list.add_argument("--tag", action="append", default=[], help="only concepts with this tag (repeatable)")
    p_fix = sub.add_parser("fix", help="change a concept's explanation or notes and mark it checked")
    p_fix.add_argument("id", type=int)
    p_fix.add_argument("file", help="JSON file with explanation and/or notes")
    p_fix.add_argument("--no-backup", action="store_true")
    p_mark = sub.add_parser("mark", help="record that these concepts were checked")
    p_mark.add_argument("ids", type=int, nargs="+")
    args = p.parse_args()

    try:
        root, profile = profiles.resolve_profile(args.data_dir, args.profile)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    cfg = profile.config(root)
    if not cfg.db_path.exists():
        print(f"profile {profile.name} has no Job Cannon database yet", file=sys.stderr)
        return 1
    conn = db.connect(cfg.db_path)
    db.migrate(conn)

    if args.command == "list":
        if args.all:
            checked_before = None
        elif args.older_than is not None:
            cutoff = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=args.older_than)
            checked_before = cutoff.isoformat()
        else:
            checked_before = ""  # no check time sorts before "", so only never-checked concepts are due
        rows = prep.list_concepts(conn, tags=args.tag, checked_before=checked_before)
        if args.concept is not None:
            rows = [r for r in rows if r["id"] == args.concept]
        out = {
            "profile": profile.name,
            "due": len(rows),
            "total": len(prep.list_concepts(conn)),
            "concepts": [concept_for_audit(conn, r) for r in rows],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.command == "mark":
        missing = [i for i in args.ids if prep.get_concept(conn, i) is None]
        if missing:
            print(f"no concept with id {', '.join(map(str, missing))}; nothing marked", file=sys.stderr)
            return 1
        prep.mark_concepts_checked(conn, args.ids)
        print(f"marked {len(args.ids)} concept(s) checked in profile {profile.name}")
        return 0

    # fix
    try:
        with open(args.file, encoding="utf-8") as f:
            changes = json.load(f)
        if not isinstance(changes, dict) or not changes:
            raise ValueError("the changes file must hold a JSON object with explanation and/or notes")
        unknown = set(changes) - FIELDS
        if unknown:
            raise ValueError(f"unknown field(s): {', '.join(sorted(unknown))}; allowed: explanation, notes")
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    concept = prep.get_concept(conn, args.id)
    if concept is None:
        print(f"no concept with id {args.id}", file=sys.stderr)
        return 1
    if not args.no_backup:
        out_dir = profiles.backup_dir(root, profile)
        out_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["job-cannon", "--data-dir", str(root), "--profile", profile.id, "backup", "--out", str(out_dir)],
            check=True,
        )
    prep.update_concept(
        conn, args.id, concept["name"], changes.get("explanation", concept["explanation"]),
        changes.get("notes", concept["notes"]),
    )
    prep.mark_concepts_checked(conn, [args.id])
    print(f"updated concept {args.id} ({concept['name']}) in profile {profile.name}: {', '.join(sorted(changes))}; marked it checked")
    print(f"http://127.0.0.1:8765/prep/concepts/{args.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
