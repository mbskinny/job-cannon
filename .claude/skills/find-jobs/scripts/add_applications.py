"""Add job listings to Job Cannon from a JSON file, skipping ones already tracked.

Usage (from the repo root):
    uv run python .claude/skills/find-jobs/scripts/add_applications.py --list
    uv run python .claude/skills/find-jobs/scripts/add_applications.py jobs.json [--dry-run]
    uv run python .claude/skills/find-jobs/scripts/add_applications.py --rate 12=5 14=2 15=

--rate sets interest levels (1-5, blank to clear) on tracked applications by id.

jobs.json is a list of objects with "company" plus any of applications.FIELDS
(role is required; "interest" is an optional 1-5 level). Data folder and profile resolve the same way as
the app: --data-dir, then JOB_CANNON_DATA, then ~/JobCannon; --profile, then JOB_CANNON_PROFILE, then the
active profile.
"""

import argparse
import json
import subprocess
import sys

from job_cannon import db, profiles
from job_cannon.repo import applications


def existing(conn) -> list:
    return applications.list_applications(conn, archived=None)  # archived ones count as duplicates


def is_duplicate(rows, company: str, data: dict) -> bool:
    url = (data.get("posting_url") or "").strip()
    for r in rows:
        if url and r["posting_url"] == url:
            return True
        if (r["company_name"].lower() == company.strip().lower()
                and r["role"].lower() == data["role"].strip().lower()):
            return True
    return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("jobs", nargs="?", help="JSON file of listings to add")
    p.add_argument("--data-dir")
    p.add_argument("--profile")
    p.add_argument("--list", action="store_true", help="print tracked applications and exit")
    p.add_argument("--rate", nargs="+", metavar="ID=LEVEL", help="set interest levels and exit")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
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
    rows = existing(conn)

    if args.rate:
        by_id = {r["id"]: r for r in rows}
        for item in args.rate:
            app_id, _, level = item.partition("=")
            r = by_id.get(int(app_id))
            if r is None:
                print(f"no application #{app_id}", file=sys.stderr)
                return 1
            applications.update(conn, r["id"], {"interest": level})
            print(f"#{r['id']} {r['company_name']} - {r['role']}: interest {level or 'cleared'}")
        return 0

    if args.list or not args.jobs:
        print(f"# profile: {profile.name}")
        for r in rows:
            status = r["status"] + (" (archived)" if r["archived_at"] else "")
            print(f"{r['id']}\t{status}\t{r['interest'] or '-'}\t{r['company_name']}\t{r['role']}\t{r['posting_url'] or ''}")
        return 0

    with open(args.jobs) as f:
        jobs = json.load(f)

    to_add = []
    for job in jobs:
        company = job.pop("company")
        if is_duplicate(rows, company, job):
            print(f"skip (already tracked): {company} - {job['role']}")
        else:
            to_add.append((company, job))

    if args.dry_run or not to_add:
        for company, job in to_add:
            print(f"would add: {company} - {job['role']}")
        return 0

    if not args.no_backup:
        backup_dir = root.parent / f"{root.name}-backups" / profile.id
        backup_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["job-cannon", "--data-dir", str(root), "--profile", profile.id, "backup", "--out", str(backup_dir)],
            check=True,
        )

    print(f"profile: {profile.name}")
    for company, job in to_add:
        app_id = applications.create(conn, company, job)
        print(f"added #{app_id}: {company} - {job['role']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
