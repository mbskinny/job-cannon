from fastapi import APIRouter, HTTPException, Request

from job_cannon.repo import applications, attachments, contacts, cover_letters, interactions, prep
from job_cannon.web.app import config, conn, redirect, render

router = APIRouter(prefix="/applications")


def _form_values(form) -> dict:
    return {k: form.get(k, "") for k in [*applications.FIELDS, "company"]}


def _get_or_404(request: Request, app_id: int):
    row = applications.get(conn(request), app_id)
    if row is None:
        raise HTTPException(404, "Application not found")
    return row


@router.get("")
async def index(
    request: Request, status: str = "", q: str = "", sort: str = "updated", archived: str = ""
):
    rows = applications.list_applications(
        conn(request), status or None, q.strip() or None, sort, archived=bool(archived)
    )
    template = "applications/_rows.html" if request.headers.get("hx-request") else "applications/index.html"
    return render(request, template, rows=rows, status=status, q=q, sort=sort, archived=bool(archived))


@router.get("/new")
async def new(request: Request, status: str = "wishlist"):
    return render(
        request,
        "applications/form.html",
        app=None,
        values={"status": status},
        companies=applications.list_companies(conn(request)),
    )


@router.post("")
async def create(request: Request):
    form = await request.form()
    values = _form_values(form)
    try:
        app_id = applications.create(conn(request), values["company"], values)
    except ValueError as exc:
        return render(
            request, "applications/form.html", status_code=422, app=None, values=values,
            error=str(exc), companies=applications.list_companies(conn(request)),
        )
    return redirect(f"/applications/{app_id}")


def detail_page(request: Request, app, status_code: int = 200, **extra):
    """Render the application page; also used by other routes to re-render with an error."""
    c = conn(request)
    app_id = app["id"]
    draft = cover_letters.get_draft(c, app_id)
    return render(
        request,
        "applications/detail.html",
        status_code=status_code,
        app=app,
        history=applications.history(c, app_id),
        linked_contacts=contacts.for_application(c, app_id),
        all_contacts=contacts.list_contacts(c),
        interactions=interactions.for_application(c, app_id),
        files=attachments.for_application(c, app_id),
        now_local=interactions.local_now(),
        draft=draft,
        draft_unfilled=cover_letters.unfilled(draft["body"]) if draft else [],
        letter_templates=cover_letters.list_templates(c),
        has_letterhead=bool(cover_letters.get_letterhead(c)["name"]),
        prep_answers=prep.answers_for_application(c, app_id),
        **extra,
    )


@router.get("/{app_id}")
async def detail(request: Request, app_id: int):
    return detail_page(request, _get_or_404(request, app_id))


@router.get("/{app_id}/edit")
async def edit(request: Request, app_id: int):
    app = _get_or_404(request, app_id)
    values = dict(app)
    values["company"] = app["company_name"]
    return render(
        request, "applications/form.html", app=app, values=values,
        companies=applications.list_companies(conn(request)),
    )


@router.post("/{app_id}")
async def update(request: Request, app_id: int):
    app = _get_or_404(request, app_id)
    form = await request.form()
    values = _form_values(form)
    try:
        applications.update(conn(request), app_id, values, company=values["company"])
    except ValueError as exc:
        return render(
            request, "applications/form.html", status_code=422, app=app, values=values,
            error=str(exc), companies=applications.list_companies(conn(request)),
        )
    return redirect(f"/applications/{app_id}")


@router.post("/{app_id}/status")
async def set_status(request: Request, app_id: int):
    _get_or_404(request, app_id)
    form = await request.form()
    try:
        applications.update(conn(request), app_id, {"status": form.get("status", "")})
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return redirect(f"/applications/{app_id}")


@router.post("/{app_id}/interest")
async def set_interest(request: Request, app_id: int):
    _get_or_404(request, app_id)
    form = await request.form()
    try:
        applications.update(conn(request), app_id, {"interest": form.get("interest", "")})
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return redirect(f"/applications/{app_id}")


@router.post("/{app_id}/archive")
async def archive(request: Request, app_id: int):
    _get_or_404(request, app_id)
    applications.set_archived(conn(request), app_id, True)
    return redirect(f"/applications/{app_id}")


@router.post("/{app_id}/unarchive")
async def unarchive(request: Request, app_id: int):
    _get_or_404(request, app_id)
    applications.set_archived(conn(request), app_id, False)
    return redirect(f"/applications/{app_id}")


@router.post("/{app_id}/delete")
async def delete(request: Request, app_id: int):
    _get_or_404(request, app_id)
    stored = applications.delete(conn(request), app_id)
    attachments.remove_files(config(request).files_dir, stored)
    return redirect("/applications")


@router.post("/{app_id}/contacts")
async def link_contact(request: Request, app_id: int):
    _get_or_404(request, app_id)
    form = await request.form()
    c = conn(request)
    contact_id = form.get("contact_id", "")
    new_name = (form.get("new_name") or "").strip()
    if new_name:
        app = applications.get(c, app_id)
        contact_id = contacts.create(c, {"name": new_name}, company=app["company_name"])
    if contact_id:
        contacts.link(c, app_id, int(contact_id), form.get("role", ""))
    return redirect(f"/applications/{app_id}#contacts")


@router.post("/{app_id}/contacts/{contact_id}/delete")
async def unlink_contact(request: Request, app_id: int, contact_id: int):
    contacts.unlink(conn(request), app_id, contact_id)
    return redirect(f"/applications/{app_id}#contacts")
