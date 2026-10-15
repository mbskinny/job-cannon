"""Read application context and save cover letter drafts in Job Cannon.

Usage (from the repo root):
    uv run python .claude/skills/tailor-cover-letter/scripts/cover_letter.py templates
    uv run python .claude/skills/tailor-cover-letter/scripts/cover_letter.py context APP_ID
    uv run python .claude/skills/tailor-cover-letter/scripts/cover_letter.py save-draft APP_ID --template ID letter.txt

save-draft stores the text as the application's draft (replacing any existing
one); the user reviews it and clicks "Attach as PDF" in the app. Data folder
resolves the same way as the app: --data-dir, then JOB_CANNON_DATA, then ~/JobCannon.
"""

import argparse
import json
import subprocess
import sys

from job_cannon import config, db
from job_cannon.repo import applications, cover_letters

APP_FIELDS = ["id", "company_name", "role", "status", "posting_url", "location", "salary_range", "source", "notes"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("templates", help="list base letters and their placeholders")
    p_ctx = sub.add_parser("context", help="JSON: application, current draft, base letters")
    p_ctx.add_argument("app_id", type=int)
    p_save = sub.add_parser("save-draft", help="store a filled letter as the application's draft")
    p_save.add_argument("app_id", type=int)
    p_save.add_argument("file", help="text file with the filled letter")
    p_save.add_argument("--template", type=int, help="id of the base letter it was made from")
    p_save.add_argument("--no-backup", action="store_true")
    args = p.parse_args()

    cfg = config.resolve(args.data_dir)
    cfg.ensure_dirs()
    conn = db.connect(cfg.db_path)
    db.migrate(conn)

    if args.command == "templates":
        for t in cover_letters.list_templates(conn):
            names = ", ".join(cover_letters.unfilled(t["body"])) or "(none)"
            print(f"{t['id']}\t{t['name']}\t{names}")
        return 0

    app = applications.get(conn, args.app_id)
    if app is None:
        print(f"no application with id {args.app_id}", file=sys.stderr)
        return 1

    if args.command == "context":
        draft = cover_letters.get_draft(conn, args.app_id)
        out = {
            "application": {k: app[k] for k in APP_FIELDS},
            "draft": dict(draft) if draft else None,
            "templates": [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "body": cover_letters.fill_builtins(t["body"], app),
                    "placeholders": [
                        {"name": n, "instruction": i} for n, i in cover_letters.placeholders(t["body"])
                        if n not in cover_letters.BUILTINS
                    ],
                }
                for t in cover_letters.list_templates(conn)
            ],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    # save-draft
    with open(args.file, encoding="utf-8") as f:
        body = f.read()
    if args.template is not None and cover_letters.get_template(conn, args.template) is None:
        print(f"no base letter with id {args.template}", file=sys.stderr)
        return 1
    if not args.no_backup:
        backup_dir = cfg.data_dir.parent / f"{cfg.data_dir.name}-backups"
        backup_dir.mkdir(exist_ok=True)
        subprocess.run(
            ["job-cannon", "--data-dir", str(cfg.data_dir), "backup", "--out", str(backup_dir)],
            check=True,
        )
    cover_letters.save_draft(conn, args.app_id, body, args.template)
    missing = cover_letters.unfilled(body)
    print(f"saved draft for #{args.app_id}: {app['company_name']} - {app['role']}")
    if missing:
        print("still unfilled: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
