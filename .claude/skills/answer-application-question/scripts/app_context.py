"""Print everything Job Cannon knows about one application, as JSON. Read-only.

Usage (from the repo root):
    uv run python .claude/skills/answer-application-question/scripts/app_context.py APP_ID

Includes the application, its company, linked contacts, the interaction log,
the cover letter draft, the attachment list (with paths on disk, so a
résumé or sent cover letter PDF can be read) and linked interview prep
answers. Data folder and profile resolve the same way as the app: --data-dir,
then JOB_CANNON_DATA, then ~/JobCannon; --profile, then JOB_CANNON_PROFILE,
then the active profile.
"""

import argparse
import json
import sys

from job_cannon import agent_data, db, profiles


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir")
    p.add_argument("--profile")
    p.add_argument("app_id", type=int)
    args = p.parse_args()

    try:
        root, profile = profiles.resolve_profile(args.data_dir, args.profile)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    cfg = profile.config(root)
    if not cfg.db_path.exists():
        print(f"no Job Cannon database at {cfg.db_path}", file=sys.stderr)
        return 1
    conn = db.connect(cfg.db_path)
    db.migrate(conn)

    context = agent_data.application_context(conn, cfg, args.app_id)
    if context is None:
        print(f"no application with id {args.app_id}", file=sys.stderr)
        return 1
    out = {"profile": profile.name, **context}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
