"""Find jobs from a button: runs the find-jobs skill (see job_cannon.job_search_run)."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from job_cannon import job_search_run
from job_cannon.repo import search_runs
from job_cannon.web.app import config, conn, profile_conn, redirect, render

router = APIRouter(prefix="/find-jobs")


def available() -> bool:
    return job_search_run.claude_command() is not None and job_search_run.repo_dir() is not None


def current(request: Request):
    """The search in progress, if any (one at a time: there is one Chrome)."""
    search = request.app.state.search
    return search if search is not None and search.running else None


def problems(request: Request) -> list[tuple[str, str | None]]:
    """What stops a search from starting: (message, link to fix it)."""
    state = request.app.state
    found = []
    if job_search_run.claude_command() is None:
        found.append(("Claude Code isn't installed on this computer (the claude command wasn't found).", None))
    if job_search_run.repo_dir() is None:
        found.append(("This copy of Job Cannon doesn't include the find-jobs skill.", None))
    if job_search_run.resume_location(state.root, state.profiles[state.active]) is None:
        found.append(("Add your résumé first, so Claude knows what jobs fit you.", f"/profiles/{state.active}#notes"))
    return found


def _minutes_since(iso: str) -> int:
    return int((datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() // 60)


def run_page(request: Request, c, run, profile_id: str, partial: bool = False):
    search = current(request)
    return render(
        request, "find_jobs/_run.html" if partial else "find_jobs/run.html",
        run=run, steps=search_runs.steps(run), added=search_runs.added_applications(c, run),
        minutes=_minutes_since(run["started_at"]),
        run_profile=profile_id,
        live=search is not None and search.run_id == run["id"] and search.profile_id == profile_id,
    )


@router.get("")
async def index(request: Request):
    return _index(request)


def _index(request: Request, status_code: int = 200, error: str | None = None, form: dict | None = None):
    state = request.app.state
    search = current(request)
    return render(
        request, "find_jobs/index.html", status_code=status_code,
        problems=problems(request), error=error, form=form or {"job_count": 5, "focus": ""},
        busy_profile=state.profiles[search.profile_id] if search else None,
        busy_run=search.run_id if search else None,
        last=search_runs.latest(conn(request)), max_jobs=search_runs.MAX_JOBS,
    )


@router.post("")
async def start(request: Request):
    state = request.app.state
    form = await request.form()
    values = {"job_count": form.get("job_count", ""), "focus": form.get("focus", "")}
    if problems(request):
        return _index(request, 422, form=values)
    if current(request):
        return _index(request, 409, "A search is already running. Wait for it to finish, or stop it.", values)
    c = conn(request)
    try:
        run_id = search_runs.start(c, values["job_count"], values["focus"])
    except ValueError as exc:
        return _index(request, 422, str(exc), values)
    run = search_runs.get(c, run_id)
    profile = state.profiles[state.active]
    data_dir = config(request).data_dir
    run_dir = job_search_run.new_run_dir(data_dir, run_id)
    args = job_search_run.build_args(
        job_search_run.claude_command(), run["job_count"], run["focus"], run_dir, data_dir,
        job_search_run.resume_location(state.root, profile),
    )
    try:
        state.search = await job_search_run.SearchProcess.start(
            c, run_id, profile.id, args, job_search_run.build_env(state.root, profile.id), run_dir,
        )
    except OSError as exc:
        search_runs.finish(c, run_id, "failed", error=f"Couldn't start Claude: {exc}")
    return redirect(f"/find-jobs/runs/{run_id}")


@router.get("/runs/{run_id}")
async def show(request: Request, run_id: int, profile: str = ""):
    """The run page; htmx polls it for the progress partial, naming the profile it was opened under."""
    state = request.app.state
    profile_id = profile if profile in state.profiles else state.active
    c = profile_conn(request.app, profile_id)
    run = search_runs.get(c, run_id)
    if run is None:
        raise HTTPException(404, "Search not found")
    return run_page(request, c, run, profile_id, partial=bool(request.headers.get("HX-Request")))


@router.post("/runs/{run_id}/cancel")
async def cancel(request: Request, run_id: int):
    search = current(request)
    if search is not None and search.run_id == run_id and search.profile_id == request.app.state.active:
        search.cancel()
    return redirect(f"/find-jobs/runs/{run_id}")
