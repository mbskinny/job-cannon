"""Read interview prep quiz questions for an accuracy audit, and apply its results.

Usage (from the repo root):
    uv run python .claude/skills/audit-quiz-questions/scripts/quiz_audit.py list [--older-than DAYS | --all] [--concept ID] [--tag T ...]
    uv run python .claude/skills/audit-quiz-questions/scripts/quiz_audit.py fix ID changes.json
    uv run python .claude/skills/audit-quiz-questions/scripts/quiz_audit.py fix-concept ID changes.json
    uv run python .claude/skills/audit-quiz-questions/scripts/quiz_audit.py mark ID [ID ...]

list prints JSON: the quiz questions due for a check (by default those never
checked; --older-than DAYS adds those last checked more than DAYS ago; --all lists
every one) and the concepts they test, with explanations and notes. Read-only.

fix applies changes.json to one quiz question: any of prompt, answer,
wrong_answers (exactly 3), explanation, code, concept_id. Fields left out are kept;
the results (right/wrong counts) always are. The question is then marked checked.

fix-concept applies changes.json (explanation and/or notes) to a concept, keeping its
name and tags, and marks the concept checked (as the audit-concepts skill does).

mark records that the given quiz questions were checked and found correct.

fix and fix-concept back up the profile first (job-cannon backup, into the
profile's backup folder) unless --no-backup. Data folder and profile resolve the
same way as the app: --data-dir, then JOB_CANNON_DATA, then ~/JobCannon;
--profile, then JOB_CANNON_PROFILE, then the active profile.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from job_cannon import agent_data, db, profiles
from job_cannon.repo import prep

QUESTION_FIELDS = {"prompt", "answer", "wrong_answers", "explanation", "code", "concept_id"}
CONCEPT_FIELDS = {"explanation", "notes"}


def load_changes(path: str, allowed: set[str]) -> dict:
    with open(path, encoding="utf-8") as f:
        changes = json.load(f)
    if not isinstance(changes, dict) or not changes:
        raise ValueError("the changes file must hold a JSON object with at least one field")
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(sorted(unknown))}; allowed: {', '.join(sorted(allowed))}")
    return changes


def backup(root, profile) -> None:
    out = profiles.backup_dir(root, profile)
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["job-cannon", "--data-dir", str(root), "--profile", profile.id, "backup", "--out", str(out)], check=True,
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir")
    p.add_argument("--profile")
    sub = p.add_subparsers(dest="command", required=True)
    p_list = sub.add_parser("list", help="JSON: quiz questions due for a check, and their concepts")
    due = p_list.add_mutually_exclusive_group()
    due.add_argument("--older-than", type=int, metavar="DAYS", help="also those last checked more than DAYS ago")
    due.add_argument("--all", action="store_true", help="every quiz question")
    p_list.add_argument("--concept", type=int, help="only this concept's questions")
    p_list.add_argument("--tag", action="append", default=[], help="only concepts with this tag (repeatable)")
    p_fix = sub.add_parser("fix", help="change one quiz question and mark it checked")
    p_fix.add_argument("id", type=int)
    p_fix.add_argument("file", help="JSON file with the fields to change")
    p_fix.add_argument("--no-backup", action="store_true")
    p_fc = sub.add_parser("fix-concept", help="change a concept's explanation or notes")
    p_fc.add_argument("id", type=int)
    p_fc.add_argument("file", help="JSON file with explanation and/or notes")
    p_fc.add_argument("--no-backup", action="store_true")
    p_mark = sub.add_parser("mark", help="record that these quiz questions were checked")
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
            checked_before = ""  # no check time sorts before "", so only never-checked questions are due
        rows = prep.list_quiz_questions(conn, tags=args.tag, concept_id=args.concept, checked_before=checked_before)
        concept_ids = sorted({r["concept_id"] for r in rows})
        concepts = [prep.get_concept(conn, cid) for cid in concept_ids]
        out = {
            "profile": profile.name,
            "due": len(rows),
            "total": len(prep.list_quiz_questions(conn)),
            "concepts": [
                {**agent_data.concept_summary(c), "notes": c["notes"], "checked_at": c["checked_at"]} for c in concepts
            ],
            "questions": [agent_data.quiz_question_dict(r) for r in rows],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.command == "mark":
        missing = [i for i in args.ids if prep.get_quiz_question(conn, i) is None]
        if missing:
            print(f"no quiz question with id {', '.join(map(str, missing))}; nothing marked", file=sys.stderr)
            return 1
        prep.mark_quiz_checked(conn, args.ids)
        print(f"marked {len(args.ids)} quiz question(s) checked in profile {profile.name}")
        return 0

    try:
        changes = load_changes(args.file, QUESTION_FIELDS if args.command == "fix" else CONCEPT_FIELDS)
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.command == "fix":
        row = prep.get_quiz_question(conn, args.id)
        if row is None:
            print(f"no quiz question with id {args.id}", file=sys.stderr)
            return 1
        current = {
            "concept_id": row["concept_id"], "prompt": row["prompt"], "answer": row["answer"],
            "wrong_answers": prep.quiz_wrong_answers(row), "explanation": row["explanation"], "code": row["code"],
        }
        new = current | changes
        if not args.no_backup:
            backup(root, profile)
        try:
            prep.update_quiz_question(
                conn, args.id, new["concept_id"], new["prompt"], new["answer"], new["wrong_answers"],
                new["explanation"], new["code"],
            )
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
        prep.mark_quiz_checked(conn, [args.id])
        print(f"updated quiz question {args.id} in profile {profile.name} ({', '.join(sorted(changes))}) and marked it checked")
        print(f"http://127.0.0.1:8765/prep/quiz/{args.id}/edit")
        return 0

    # fix-concept
    concept = prep.get_concept(conn, args.id)
    if concept is None:
        print(f"no concept with id {args.id}", file=sys.stderr)
        return 1
    if not args.no_backup:
        backup(root, profile)
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
