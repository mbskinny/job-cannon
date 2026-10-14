from fastapi import APIRouter, HTTPException, Request, Response

from job_cannon.repo import applications
from job_cannon.web.app import conn, render

router = APIRouter(prefix="/board")


@router.get("")
async def index(request: Request):
    return render(request, "board.html", columns=applications.board(conn(request)))


@router.post("/reorder")
async def reorder(request: Request):
    """Called by SortableJS after a drop with the column's new card order."""
    form = await request.form()
    try:
        ids = [int(i) for i in form.getlist("ids")]
        applications.reorder(conn(request), form.get("status", ""), ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return Response(status_code=204)
