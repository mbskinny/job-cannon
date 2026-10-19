"""Print everything Job Cannon knows about one application, as JSON. Read-only.

Usage (from the repo root):
    uv run python .claude/skills/answer-application-question/scripts/app_context.py APP_ID

Includes the application, its company, linked contacts, the interaction log,
the cover letter draft and the attachment list (with paths on disk, so a
résumé or sent cover letter PDF can be read). Data folder resolves the same
way as the app: --data-dir, then JOB_CANNON_DATA, then ~/JobCannon.
"""

import argparse
import json
import sys

from job_cannon import config, db
from job_cannon.repo import applications, attachments, contacts, cover_letters, interactions


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir")
    p.add_argument("app_id", type=int)
    args = p.parse_args()

    cfg = config.resolve(args.data_dir)
    if not cfg.db_path.exists():
        print(f"no Job Cannon database at {cfg.db_path}", file=sys.stderr)
        return 1
    conn = db.connect(cfg.db_path)
    db.migrate(conn)

    app = applications.get(conn, args.app_id)
    if app is None:
        print(f"no application with id {args.app_id}", file=sys.stderr)
        return 1

    company = conn.execute("SELECT * FROM companies WHERE id = ?", (app["company_id"],)).fetchone()
    draft = cover_letters.get_draft(conn, args.app_id)
    out = {
        "application": dict(app),
        "company": dict(company) if company else None,
        "contacts": [dict(r) for r in contacts.for_application(conn, args.app_id)],
        "interactions": [dict(r) for r in interactions.for_application(conn, args.app_id)],
        "cover_letter_draft": draft["body"] if draft else None,
        "attachments": [
            {
                "kind": a["kind"],
                "name": a["original_name"],
                "mime": a["mime"],
                "path": str(attachments.path_for(cfg.files_dir, a)),
            }
            for a in attachments.for_application(conn, args.app_id)
        ],
        "status_history": [dict(r) for r in applications.history(conn, args.app_id)],
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
