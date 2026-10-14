from fastapi import APIRouter, HTTPException, Request

from job_cannon.repo import interactions
from job_cannon.web.app import conn, redirect, safe_next

router = APIRouter(prefix="/interactions")


@router.post("")
async def create(request: Request):
    form = await request.form()
    try:
        interactions.create(
            conn(request),
            kind=form.get("kind", "note"),
            summary=form.get("summary", ""),
            occurred_at=form.get("occurred_at"),
            application_id=form.get("application_id"),
            contact_id=form.get("contact_id"),
            follow_up_due=form.get("follow_up_due"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return redirect(safe_next(form.get("next"), "/"))


@router.post("/{interaction_id}/done")
async def done(request: Request, interaction_id: int):
    form = await request.form()
    interactions.set_follow_up_done(conn(request), interaction_id)
    return redirect(safe_next(form.get("next"), "/"))


@router.post("/{interaction_id}/delete")
async def delete(request: Request, interaction_id: int):
    form = await request.form()
    interactions.delete(conn(request), interaction_id)
    return redirect(safe_next(form.get("next"), "/"))
