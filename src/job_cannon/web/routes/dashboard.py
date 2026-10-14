from fastapi import APIRouter, Request

from job_cannon.repo import applications, dashboard, interactions
from job_cannon.web.app import conn, render

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
    )
