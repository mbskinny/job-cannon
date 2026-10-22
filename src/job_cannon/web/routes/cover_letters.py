import io

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

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


SAMPLE_LETTER = (
    "Dear Hiring Team,\n\nThis is a preview of how your cover letters will look. "
    "Create a base letter to see one of your own here.\n\nBest regards,\nYour name"
)


def _pdf_response(content: bytes) -> Response:
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": 'inline; filename="cover-letter-preview.pdf"',
        "X-Content-Type-Options": "nosniff",
    })


def _app_or_404(request: Request, app_id: int):
    row = applications.get(conn(request), app_id)
    if row is None:
        raise HTTPException(404, "Application not found")
    return row


# --- base letters ---

def _index_page(request: Request, status_code: int = 200, **extra):
    c = conn(request)
    rows = cover_letters.list_templates(c)
    slots = {r["id"]: cover_letters.unfilled(r["body"]) for r in rows}
    letterhead = cover_letters.get_letterhead(c)
    extra.setdefault("style", letterhead)
    contact = [letterhead[k] for k in cover_letters.CONTACT_FIELDS if letterhead[k]]
    return render(
        request, "cover_letters/index.html", status_code=status_code, rows=rows, slots=slots, contact=contact, **extra
    )


@router.get("/cover-letters")
async def index(request: Request, saved: bool = False):
    return _index_page(request, saved=saved)


# Declared before /cover-letters/{template_id} so "style" isn't parsed as an id.
@router.post("/cover-letters/style")
async def save_style(request: Request):
    form = await request.form()
    values = {k: form.get(k, "") for k in cover_letters.STYLE_FIELDS}
    try:
        cover_letters.save_letter_style(conn(request), values)
    except ValueError as exc:
        style = {"show_letterhead": bool(values["show_letterhead"]), "accent": values["accent"]}
        return _index_page(request, status_code=422, style=style, style_error=str(exc))
    return redirect("/cover-letters?saved=1#letter-style")


@router.post("/cover-letters/style/preview")
async def preview_style(request: Request):
    """Render the (unsaved) style with the saved contact details and the first base letter, or a sample."""
    form = await request.form()
    try:
        style = cover_letters.clean_letter_style({k: form.get(k, "") for k in cover_letters.STYLE_FIELDS})
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    c = conn(request)
    templates = cover_letters.list_templates(c)
    return _pdf_response(
        pdf.render_letter(templates[0]["body"] if templates else SAMPLE_LETTER, cover_letters.pdf_letterhead(c, style))
    )


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


@router.post("/cover-letters/{template_id}/copy")
async def save_as_new(request: Request, template_id: int):
    """Save the edit form as a new base letter, leaving the original untouched."""
    template = _template_or_404(request, template_id)
    form = await request.form()
    values = {"name": form.get("name", ""), "body": form.get("body", "")}
    try:
        new_id = cover_letters.create_template(conn(request), values["name"], values["body"])
    except ValueError as exc:
        return render(
            request, "cover_letters/form.html", status_code=422, template=template, values=values,
            slots=cover_letters.placeholders(values["body"]),
            error=f"{exc}. Give the new base letter a different name.",
        )
    return redirect(f"/cover-letters/{new_id}")


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
    letter = pdf.render_letter(draft["body"], cover_letters.pdf_letterhead(c))
    name = f"Cover letter - {app['company_name']} - {app['role']}.pdf".replace("/", "-")
    attachments.save(
        c,
        config(request).files_dir,
        application_id=app_id,
        kind="cover_letter",
        original_name=name,
        stream=io.BytesIO(letter),
        mime="application/pdf",
    )
    return redirect(f"/applications/{app_id}#files")


@router.post("/applications/{app_id}/cover-letter/preview")
async def preview_draft(request: Request, app_id: int):
    """Save the textarea and show the PDF without attaching it (placeholders allowed)."""
    _app_or_404(request, app_id)
    form = await request.form()
    c = conn(request)
    body = form.get("body")
    if body is not None:
        cover_letters.save_draft(c, app_id, body)
    draft = cover_letters.get_draft(c, app_id)
    if draft is None:
        raise HTTPException(404, "No draft to preview")
    return _pdf_response(pdf.render_letter(draft["body"], cover_letters.pdf_letterhead(c)))


@router.post("/applications/{app_id}/cover-letter/delete")
async def discard_draft(request: Request, app_id: int):
    _app_or_404(request, app_id)
    cover_letters.delete_draft(conn(request), app_id)
    return redirect(f"/applications/{app_id}#cover-letter")
