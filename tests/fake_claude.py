"""Stands in for `claude -p` in the find-jobs tests (JOB_CANNON_CLAUDE).

FAKE_CLAUDE_MODE: "ok" adds one application and reports, "fail" exits with an
error, "hang" waits to be stopped.
"""

import json
import os
import sys
import time

from job_cannon import db, profiles
from job_cannon.repo import applications


def emit(event):
    print(json.dumps(event), flush=True)


mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
emit({"type": "system", "subtype": "init", "argv": sys.argv[1:]})
emit({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Bash", "input": {"command": "uv run job-cannon profiles --json"}},
    {"type": "tool_use", "name": "mcp__claude-in-chrome__navigate",
     "input": {"url": "https://www.linkedin.com/jobs/search/?keywords=x"}},
]}})
if mode == "hang":
    time.sleep(60)
elif mode == "fail":
    print("Chrome extension not connected", file=sys.stderr)
    sys.exit(1)
else:
    conn = db.connect(profiles.resolve().db_path)
    applications.create(conn, "Fake Co", {"role": "Tester", "location": "Remote"})
    emit({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash",
         "input": {"command": "uv run python .claude/skills/find-jobs/scripts/add_applications.py x.json"}},
    ]}})
    emit({"type": "result", "subtype": "success", "is_error": False, "result": "Added Fake Co - Tester."})
