"""Run the find-jobs skill from the app: headless Claude Code driving Chrome.

The app starts ``claude -p --chrome`` in the repository (where the project
skills live), pinned to one profile through JOB_CANNON_DATA and
JOB_CANNON_PROFILE, and reads its stream-json output on the event loop: tool
calls become progress steps, and the final result is the report. Headless
Claude Code denies any tool not in ``allowed_tools``, so nothing waits on a
permission prompt, and a web page can't talk it into other commands.

Needs ``claude`` logged in, and Chrome open with the Claude extension
connected and the job sites signed in. JOB_CANNON_CLAUDE overrides the command
(the tests use a fake).
"""

import asyncio
import json
import os
import shlex
import shutil
import signal
from pathlib import Path
from urllib.parse import urlsplit

from job_cannon import config as config_mod
from job_cannon import profiles
from job_cannon.repo import search_runs

COMMAND_ENV = "JOB_CANNON_CLAUDE"
TIMEOUT_ENV = "JOB_CANNON_SEARCH_TIMEOUT"
DEFAULT_TIMEOUT = 30 * 60
REPO_DIR = Path(__file__).resolve().parent.parent.parent
SKILL_DIR = Path(".claude/skills/find-jobs")
ADD_SCRIPT = SKILL_DIR / "scripts/add_applications.py"
RUNS_DIR = "runs"
KEEP_RUNS = 10
LINE_LIMIT = 16 * 1024 * 1024  # stream-json lines carry whole page texts


def claude_command() -> list[str] | None:
    raw = os.environ.get(COMMAND_ENV)
    if raw:
        return shlex.split(raw)
    found = shutil.which("claude")
    return [found] if found else None


def repo_dir() -> Path | None:
    """The checkout holding the skills, or None when installed without it."""
    return REPO_DIR if (REPO_DIR / SKILL_DIR / "SKILL.md").is_file() else None


def timeout_seconds() -> int:
    try:
        return int(os.environ.get(TIMEOUT_ENV, DEFAULT_TIMEOUT))
    except ValueError:
        return DEFAULT_TIMEOUT


def resume_location(root: Path, profile: profiles.Profile) -> str | None:
    """The profile's résumé, as the skill will find it (including the old default-profile file)."""
    data_dir = profile.config(root).data_dir
    resume = profiles.resolve_resume(data_dir, profiles.read_job_search(profile.job_search_file(root)).resume)
    if resume is None and profile.id == "default" and (REPO_DIR / ".claude/job-search.local.md").is_file():
        return str(REPO_DIR / ".claude/job-search.local.md")
    return resume


def new_run_dir(data_dir: Path, run_id: int) -> Path:
    """A folder for the run's jobs.json and logs; older ones beyond KEEP_RUNS are removed."""
    base = data_dir / RUNS_DIR
    run_dir = base / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    old = sorted((d for d in base.iterdir() if d.is_dir() and d.name.isdigit()), key=lambda d: int(d.name))
    for d in old[:-KEEP_RUNS]:
        shutil.rmtree(d, ignore_errors=True)
    return run_dir


def prompt(job_count: int, focus: str, run_dir: Path) -> str:
    lines = [
        f"Use the find-jobs skill to find {job_count} jobs for the active Job Cannon profile"
        + (f", focusing on: {focus}" if focus else "") + ".",
        "The user started this from a button in Job Cannon and asked for the jobs to be added, "
        "so insert them without asking for confirmation.",
        "You are running unattended: never ask a question. If something blocks you (no résumé, "
        "Chrome or the Claude extension not connected, LinkedIn signed out), stop and explain it "
        "in your final message, with what the person should do about it.",
        f"Write jobs.json in {run_dir}. Don't pass --profile or --data-dir to the scripts; "
        "the environment already selects the profile.",
        "Your final message is shown in the app to a non-technical person: plain sentences and "
        "simple '- ' bullet lists only, no Markdown tables, headings, bold or links syntax. Say what "
        "you added (company and role, one line each, with why it fits), what you left out and why, "
        "and that nothing was applied for or sent.",
    ]
    return "\n\n".join(lines)


def allowed_tools(run_dir: Path, data_dir: Path, resume: str | None) -> list[str]:
    readable = [REPO_DIR / ".claude", data_dir]
    if resume and not resume.startswith(("http://", "https://")):
        readable.append(Path(resume).parent)
    return [
        "Skill",
        "ToolSearch",
        *(f"Read(/{d}/**)" for d in readable),  # "//" + absolute path
        f"Write(/{run_dir}/**)",
        f"Edit(/{run_dir}/**)",
        "WebFetch",
        "WebSearch",
        "mcp__claude-in-chrome__*",
        "Bash(uv run job-cannon profiles:*)",
        "Bash(uv run job-cannon resume-text:*)",
        f"Bash(uv run python {ADD_SCRIPT}:*)",
    ]


def build_args(command: list[str], job_count: int, focus: str, run_dir: Path, data_dir: Path,
               resume: str | None) -> list[str]:
    return [
        *command,
        "-p", prompt(job_count, focus, run_dir),
        "--chrome",
        "--output-format", "stream-json", "--verbose",
        "--no-session-persistence",
        "--add-dir", str(run_dir),
        "--allowedTools", *allowed_tools(run_dir, data_dir, resume),
    ]


def build_env(root: Path, profile_id: str) -> dict[str, str]:
    return {**os.environ, config_mod.ENV_VAR: str(root), profiles.ENV_VAR: profile_id}


# --- progress -------------------------------------------------------------

def _host(url: str) -> str:
    host = urlsplit(url or "").hostname or ""
    host = host.removeprefix("www.")
    return "LinkedIn" if host.endswith("linkedin.com") else host


def describe(name: str, args: dict) -> str | None:
    """A tool call as a short step a non-technical person can follow (None to leave it out)."""
    if name == "Skill":
        return "Starting the job search"
    if name == "Bash":
        cmd = args.get("command", "")
        if "resume-text" in cmd:
            return "Reading your résumé"
        if "job-cannon profiles" in cmd:
            return "Reading your profile"
        if "add_applications.py" in cmd:
            return "Checking what's already on your board" if "--list" in cmd else "Adding jobs to your board"
        return None
    if name == "Read":
        path = args.get("file_path", "")
        if "/sectors/" in path:
            return "Reading the search guide for your field"
        if "job-search" in path:
            return "Reading your job-search notes"
        if "/skills/" in path:
            return None
        return "Reading your résumé" if "resume" in path.lower() else f"Reading {Path(path).name}"
    if name in ("Write", "Edit"):
        return "Writing up the shortlist"
    if name == "WebSearch":
        return f"Searching the web for “{args.get('query', '')}”"
    if name == "WebFetch":
        return f"Reading a page on {_host(args.get('url', ''))}"
    if name == "mcp__claude-in-chrome__navigate":
        url = args.get("url", "")
        if "linkedin.com/jobs/search" in url:
            return "Searching LinkedIn jobs"
        if "/jobs/view/" in url:
            return "Reading a LinkedIn posting"
        return f"Opening {_host(url)}" if _host(url) else "Browsing"
    if name in ("mcp__claude-in-chrome__get_page_text", "mcp__claude-in-chrome__read_page"):
        return "Reading the page"
    if name == "mcp__claude-in-chrome__find":
        return "Looking through the results"
    if name == "mcp__claude-in-chrome__browser_batch":
        # Several browser actions in one call: describe the most telling one.
        steps = [describe(f"mcp__claude-in-chrome__{a.get('name', '')}", a.get("input") or {})
                 for a in args.get("actions", [])]
        steps = [s for s in steps if s]
        return next((s for s in steps if s != "Reading the page"), steps[0] if steps else "Browsing")
    if name == "mcp__claude-in-chrome__computer" and "job card" in args.get("action_summary", ""):
        return "Opening a job listing"
    return None


def events_to_steps(event: dict) -> list[str]:
    if event.get("type") != "assistant":
        return []
    found = []
    for block in event.get("message", {}).get("content", []):
        # Claude's own short progress notes ("Two good matches so far") read well as steps.
        text = " ".join((block.get("text") or "").split()) if block.get("type") == "text" else ""
        if text and len(text) <= 240:
            found.append(text)
        elif block.get("type") == "tool_use":
            step = describe(block.get("name", ""), block.get("input") or {})
            if step:
                found.append(step)
    return found


# --- the process ----------------------------------------------------------

class SearchProcess:
    """One running search. Its DB writes happen on the event loop, in ``watch``."""

    def __init__(self, conn, run_id: int, profile_id: str, proc: asyncio.subprocess.Process, run_dir: Path):
        self.conn = conn
        self.run_id = run_id
        self.profile_id = profile_id
        self.proc = proc
        self.run_dir = run_dir
        self.cancelled = False
        self.task: asyncio.Task | None = None

    @classmethod
    async def start(cls, conn, run_id: int, profile_id: str, args: list[str], env: dict, run_dir: Path):
        stderr = (run_dir / "stderr.log").open("wb")
        try:
            proc = await asyncio.create_subprocess_exec(
                *args, cwd=REPO_DIR, env=env, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=stderr, limit=LINE_LIMIT,
                start_new_session=os.name == "posix",  # so a stop also ends its helpers
            )
        finally:
            stderr.close()
        self = cls(conn, run_id, profile_id, proc, run_dir)
        self.task = asyncio.create_task(self.watch(timeout_seconds()))
        return self

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def stop(self) -> None:
        if self.proc.returncode is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(self.proc.pid, signal.SIGTERM)
            else:
                self.proc.terminate()
        except ProcessLookupError:
            pass

    def cancel(self) -> None:
        self.cancelled = True
        self.stop()

    async def _read(self, result: dict) -> None:
        last = None
        with (self.run_dir / "events.jsonl").open("ab") as log:
            async for line in self.proc.stdout:
                log.write(line)
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "result":
                    result.update(event)
                for step in events_to_steps(event):
                    if step != last:
                        search_runs.add_step(self.conn, self.run_id, step)
                        last = step
        await self.proc.wait()

    async def watch(self, timeout: int) -> None:
        result: dict = {}
        timed_out = False
        try:
            async with asyncio.timeout(timeout):
                await self._read(result)
        except TimeoutError:
            timed_out = True
            self.stop()
            await self.proc.wait()
        report = str(result.get("result") or "")
        if self.cancelled:
            search_runs.finish(self.conn, self.run_id, "cancelled", report)
        elif timed_out:
            search_runs.finish(self.conn, self.run_id, "failed", report,
                               f"Stopped after {timeout // 60} minutes without finishing.")
        elif self.proc.returncode == 0 and result and not result.get("is_error"):
            search_runs.finish(self.conn, self.run_id, "done", report)
        else:
            search_runs.finish(self.conn, self.run_id, "failed", report, self._error(result))

    def _error(self, result: dict) -> str:
        if result.get("is_error") and result.get("result"):
            return ""  # the report already says what went wrong
        try:
            tail = (self.run_dir / "stderr.log").read_text(encoding="utf-8", errors="replace").strip()[-1500:]
        except OSError:
            tail = ""
        return tail or f"Claude stopped unexpectedly (exit code {self.proc.returncode})."
