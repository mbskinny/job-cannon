import io

from fastapi import APIRouter, HTTPException, Request

from job_cannon import pdf
from job_cannon.repo import applications, attachments, cover_letters
from job_cannon.web.app import config, conn, redirect, render
from job_cannon.web.routes.applications import detail_page

router = APIRouter()


def _template_or_404(request: Request, template_id: int):
    row = cover_letters.get_template(conn(request), template_id)
    if row is None:
        raise HTTPException(404, "Template not found")
    return row


def _app_or_404(request: Request, app_id: int):
    row = applications.get(conn(request), app_id)
    if row is None:
        raise HTTPException(404, "Application not found")
    return row


# --- base letters ---

@router.get("/cover-letters")
async def index(request: Request):
    rows = cover_letters.list_templates(conn(request))
    slots = {r["id"]: cover_letters.unfilled(r["body"]) for r in rows}
    return render(request, "cover_letters/index.html", rows=rows, slots=slots)


@router.get("/cover-letters/new")
async def new(request: Request):
    return render(request, "cover_letters/form.html", template=None, values={}, slots=[])


@router.post("/cover-letters")
async def create(request: Request):
    form = await request.form()
    values = {"name": form.get("name", ""), "body": form.get("body", "")}
    try:
        cover_letters.create_template(conn(request), values["name"], values["body"])
    except ValueError as exc:
        return render(
            request, "cover_letters/form.html", status_code=422, template=None, values=values,
            slots=cover_letters.placeholders(values["body"]), error=str(exc),
        )
    return redirect("/cover-letters")


@router.get("/cover-letters/{template_id}")
async def edit(request: Request, template_id: int):
    template = _template_or_404(request, template_id)
    return render(
        request, "cover_letters/form.html", template=template, values=dict(template),
        slots=cover_letters.placeholders(template["body"]),
    )


@router.post("/cover-letters/{template_id}")
async def update(request: Request, template_id: int):
    template = _template_or_404(request, template_id)
    form = await request.form()
    values = {"name": form.get("name", ""), "body": form.get("body", "")}
    try:
        cover_letters.update_template(conn(request), template_id, values["name"], values["body"])
    except ValueError as exc:
        return render(
            request, "cover_letters/form.html", status_code=422, template=template, values=values,
            slots=cover_letters.placeholders(values["body"]), error=str(exc),
        )
    return redirect(f"/cover-letters/{template_id}")


@router.post("/cover-letters/{template_id}/delete")
async def delete(request: Request, template_id: int):
    _template_or_404(request, template_id)
    cover_letters.delete_template(conn(request), template_id)
    return redirect("/cover-letters")


# --- per-application draft ---

@router.post("/applications/{app_id}/cover-letter")
async def start_draft(request: Request, app_id: int):
    app = _app_or_404(request, app_id)
    form = await request.form()
    try:
        cover_letters.start_draft(conn(request), app, int(form.get("template_id") or 0))
    except ValueError as exc:
        return detail_page(request, app, status_code=422, letter_error=str(exc))
    return redirect(f"/applications/{app_id}#cover-letter")


@router.post("/applications/{app_id}/cover-letter/save")
async def save_draft(request: Request, app_id: int):
    _app_or_404(request, app_id)
    form = await request.form()
    cover_letters.save_draft(conn(request), app_id, form.get("body", ""))
    return redirect(f"/applications/{app_id}#cover-letter")


@router.post("/applications/{app_id}/cover-letter/attach")
async def attach(request: Request, app_id: int):
    """Save the textarea, then render it to PDF and store it as a cover_letter attachment."""
    app = _app_or_404(request, app_id)
    form = await request.form()
    c = conn(request)
    body = form.get("body")
    if body is not None:
        cover_letters.save_draft(c, app_id, body)
    draft = cover_letters.get_draft(c, app_id)
    if draft is None or not draft["body"].strip():
        return detail_page(request, app, status_code=422, letter_error="The draft is empty.")
    missing = cover_letters.unfilled(draft["body"])
    if missing:
        return detail_page(
            request, app, status_code=422,
            letter_error="Fill these placeholders first: " + ", ".join(missing),
        )
    name = f"Cover letter - {app['company_name']} - {app['role']}.pdf".replace("/", "-")
    attachments.save(
        c,
        config(request).files_dir,
        application_id=app_id,
        kind="cover_letter",
        original_name=name,
        stream=io.BytesIO(pdf.render_letter(draft["body"])),
        mime="application/pdf",
    )
    return redirect(f"/applications/{app_id}#files")


@router.post("/applications/{app_id}/cover-letter/delete")
async def discard_draft(request: Request, app_id: int):
    _app_or_404(request, app_id)
    cover_letters.delete_draft(conn(request), app_id)
    return redirect(f"/applications/{app_id}#cover-letter")
