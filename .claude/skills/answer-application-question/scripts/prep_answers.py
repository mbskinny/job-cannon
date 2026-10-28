"""Read the interview prep bank and save answers to it in Job Cannon.

Usage (from the repo root):
    uv run python .claude/skills/answer-application-question/scripts/prep_answers.py list
    uv run python .claude/skills/answer-application-question/scripts/prep_answers.py save answer.txt --question ID [--app APP_ID]
    uv run python .claude/skills/answer-application-question/scripts/prep_answers.py save answer.txt --new-question TEXT [--tags a,b] [--app APP_ID]

list prints every prep question with its tags, notes and answers as JSON
(answers without text yet, e.g. a recording still being transcribed, are left
out). save stores the text as a typed answer, under an existing question or a
new one (reusing a question with the same wording if there is one), optionally
linked to an application. Data folder and profile resolve the same way as the
app: --data-dir, then JOB_CANNON_DATA, then ~/JobCannon; --profile, then
JOB_CANNON_PROFILE, then the active profile.
"""

import argparse
import json
import subprocess
import sys

from job_cannon import db, profiles
from job_cannon.repo import applications, prep

ANSWER_FIELDS = ["id", "mode", "body", "best", "application_id", "company_name", "application_role", "created_at"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir")
    p.add_argument("--profile")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="JSON: prep questions with tags, notes and answers")
    p_save = sub.add_parser("save", help="store a text answer in the prep bank")
    p_save.add_argument("file", help="text file with the answer")
    target = p_save.add_mutually_exclusive_group(required=True)
    target.add_argument("--question", type=int, help="id of an existing prep question")
    target.add_argument("--new-question", help="wording of a question to add")
    p_save.add_argument("--tags", default="", help="comma-separated tags for a new question")
    p_save.add_argument("--app", type=int, help="application id to link the answer to")
    p_save.add_argument("--no-backup", action="store_true")
    args = p.parse_args()

    try:
        root, profile = profiles.resolve_profile(args.data_dir, args.profile)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    cfg = profile.config(root)
    cfg.ensure_dirs()
    conn = db.connect(cfg.db_path)
    db.migrate(conn)

    if args.command == "list":
        out = {
            "profile": profile.name,
            "questions": [
                {
                    "id": q["id"],
                    "prompt": q["prompt"],
                    "notes": q["notes"],
                    "tags": q["tags"].split(",") if q["tags"] else [],
                    "answers": [
                        {k: a[k] for k in ANSWER_FIELDS}
                        for a in prep.answers_for_question(conn, q["id"])
                        if a["body"]
                    ],
                }
                for q in prep.list_questions(conn)
            ],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    # save
    with open(args.file, encoding="utf-8") as f:
        body = f.read()
    if not body.strip():
        print("the answer is empty", file=sys.stderr)
        return 1
    if args.question is not None and prep.get_question(conn, args.question) is None:
        print(f"no prep question with id {args.question}", file=sys.stderr)
        return 1
    if args.app is not None and applications.get(conn, args.app) is None:
        print(f"no application with id {args.app}", file=sys.stderr)
        return 1
    if not args.no_backup:
        backup_dir = root.parent / f"{root.name}-backups" / profile.id
        backup_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["job-cannon", "--data-dir", str(root), "--profile", profile.id, "backup", "--out", str(backup_dir)],
            check=True,
        )
    question_id = args.question
    if question_id is None:
        wording = " ".join(args.new_question.split())
        same = [q for q in prep.list_questions(conn) if q["prompt"].casefold() == wording.casefold()]
        question_id = same[0]["id"] if same else prep.create_question(conn, wording, tags=args.tags)
    answer_id = prep.add_text_answer(conn, question_id, body, args.app)
    question = prep.get_question(conn, question_id)
    print(f"saved answer {answer_id} to prep question {question_id} in profile {profile.name}: {question['prompt']}")
    print(f"http://127.0.0.1:8765/prep/{question_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
