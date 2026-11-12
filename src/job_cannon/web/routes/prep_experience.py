"""Interview prep experience notes: raw notes about the user's work for Claude to draw on.

Registered before ``routes.prep`` so ``/prep/experience`` isn't read as a question id.
"""

from fastapi import APIRouter, HTTPException, Request

from job_cannon.repo import prep
from job_cannon.web.app import conn, redirect, render

router = APIRouter(prefix="/prep/experience")


def _note_or_404(request: Request, note_id: int):
    row = prep.get_note(conn(request), note_id)
    if row is None:
        raise HTTPException(404, "Note not found")
    return row


def _form_values(form) -> dict:
    return {k: form.get(k, "") for k in ["title", "body"]}


def _form(request: Request, note, values: dict, status_code: int = 200, error: str | None = None):
    return render(request, "prep/experience_form.html", status_code=status_code, note=note, values=values, error=error)


@router.get("")
async def index(request: Request, q: str = ""):
    c = conn(request)
    rows = prep.list_notes(c, q.strip() or None)
    template = "prep/_experience.html" if request.headers.get("hx-request") else "prep/experience.html"
    return render(request, template, rows=rows, q=q, total=len(prep.list_notes(c)))


@router.get("/new")
async def new(request: Request):
    return _form(request, None, {})


@router.post("")
async def create(request: Request):
    values = _form_values(await request.form())
    try:
        note_id = prep.create_note(conn(request), values["title"], values["body"])
    except ValueError as exc:
        return _form(request, None, values, status_code=422, error=str(exc))
    return redirect(f"/prep/experience/{note_id}")


@router.get("/{note_id}")
async def detail(request: Request, note_id: int):
    return render(request, "prep/experience_note.html", note=_note_or_404(request, note_id))


@router.get("/{note_id}/edit")
async def edit(request: Request, note_id: int):
    note = _note_or_404(request, note_id)
    return _form(request, note, {k: note[k] for k in ["title", "body"]})


@router.post("/{note_id}")
async def update(request: Request, note_id: int):
    note = _note_or_404(request, note_id)
    values = _form_values(await request.form())
    try:
        prep.update_note(conn(request), note_id, values["title"], values["body"])
    except ValueError as exc:
        return _form(request, note, values, status_code=422, error=str(exc))
    return redirect(f"/prep/experience/{note_id}")


@router.post("/{note_id}/delete")
async def delete(request: Request, note_id: int):
    _note_or_404(request, note_id)
    prep.delete_note(conn(request), note_id)
    return redirect("/prep/experience")
