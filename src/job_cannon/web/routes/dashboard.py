from fastapi import APIRouter, Request

from job_cannon.repo import applications, dashboard, interactions, search_runs
from job_cannon.web.app import conn, render
from job_cannon.web.routes import find_jobs

router = APIRouter()


@router.get("/")
async def index(request: Request):
    c = conn(request)
    return render(
        request,
        "dashboard.html",
        follow_ups=dashboard.follow_ups(c),
        counts=applications.status_counts(c),
        active=applications.ACTIVE_STATUSES,
        status_changes=dashboard.recent_status_changes(c),
        recent_interactions=interactions.recent(c, limit=8),
        find_jobs=find_jobs.available(),
        last_search=search_runs.latest(c),
    )
