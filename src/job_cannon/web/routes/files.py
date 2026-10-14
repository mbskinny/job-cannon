from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from job_cannon.repo import applications, attachments
from job_cannon.web.app import config, conn, redirect

router = APIRouter()

# Types safe to show in the browser tab; anything else (e.g. a saved .html
# job posting) downloads instead, so it can't run scripts on this origin.
INLINE_TYPES = {"application/pdf", "text/plain", "image/png", "image/jpeg", "image/gif", "image/webp"}


@router.post("/applications/{app_id}/attachments")
async def upload(request: Request, app_id: int):
    c = conn(request)
    if applications.get(c, app_id) is None:
        raise HTTPException(404, "Application not found")
    form = await request.form()
    upload = form.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        raise HTTPException(400, "Choose a file to upload")
    try:
        attachments.save(
            c,
            config(request).files_dir,
            application_id=app_id,
            kind=form.get("kind", "other"),
            original_name=upload.filename,
            stream=upload.file,
            mime=upload.content_type,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return redirect(f"/applications/{app_id}#files")


@router.get("/attachments/{attachment_id}")
async def download(request: Request, attachment_id: int, download: bool = False):
    row = attachments.get(conn(request), attachment_id)
    if row is None:
        raise HTTPException(404, "File not found")
    path = attachments.path_for(config(request).files_dir, row)
    if not path.exists():
        raise HTTPException(404, "File is missing from the data folder")
    inline = not download and row["mime"] in INLINE_TYPES
    return FileResponse(
        path,
        media_type=row["mime"],
        filename=row["original_name"],
        content_disposition_type="inline" if inline else "attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/attachments/{attachment_id}/delete")
async def delete(request: Request, attachment_id: int):
    c = conn(request)
    row = attachments.get(c, attachment_id)
    if row is None:
        raise HTTPException(404, "File not found")
    attachments.delete(c, config(request).files_dir, attachment_id)
    return redirect(f"/applications/{row['application_id']}#files")
