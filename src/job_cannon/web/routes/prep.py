import asyncio
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import FileResponse

from job_cannon import transcribe
from job_cannon.repo import applications, prep
from job_cannon.web.app import config, conn, redirect, render, safe_next

router = APIRouter(prefix="/prep")

# Recording types the browser's MediaRecorder produces, with the file suffix to store them under.
AUDIO_TYPES = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/wav": ".wav"}


def _question_or_404(request: Request, question_id: int):
    row = prep.get_question(conn(request), question_id)
    if row is None:
        raise HTTPException(404, "Question not found")
    return row


def _answer_or_404(request: Request, answer_id: int):
    row = prep.get_answer(conn(request), answer_id)
    if row is None:
        raise HTTPException(404, "Answer not found")
    return row


def _form_values(form) -> dict:
    return {k: form.get(k, "") for k in ["prompt", "notes", "tags"]}


def _active_applications(request: Request):
    return [a for a in applications.list_applications(conn(request)) if a["status"] in applications.ACTIVE_STATUSES]


def _answer_partial(request: Request, answer, status_code: int = 200):
    return render(
        request, "prep/_answer.html", status_code=status_code, a=answer,
        voice_available=transcribe.available(), applications=_active_applications(request),
    )


async def _transcribe_answer(c, files_dir: Path, answer_id: int) -> None:
    """Background task: transcribe off the event loop, then store the result back on it."""
    answer = prep.get_answer(c, answer_id)
    if answer is None or not answer["audio_stored_name"]:
        return
    try:
        text = await asyncio.to_thread(transcribe.transcribe, files_dir / answer["audio_stored_name"])
    except Exception:
        prep.set_transcript_status(c, answer_id, "failed")
        return
    if prep.get_answer(c, answer_id) is not None:
        prep.set_transcript(c, answer_id, text)


# --- question bank ---

@router.get("")
async def index(request: Request, q: str = "", tag: list[str] = Query([]), application: str = ""):
    c = conn(request)
    tags = prep.parse_tags(tag)
    rows = prep.list_questions(c, q.strip() or None, tags)
    template = "prep/_questions.html" if request.headers.get("hx-request") else "prep/index.html"
    return render(
        request, template, rows=rows, q=q, selected_tags=tags, all_tags=prep.list_tags(c),
        application=application, total=len(prep.list_questions(c)),
    )


@router.get("/random")
async def random_question(request: Request, q: str = "", tag: list[str] = Query([]), application: str = ""):
    question_id = prep.random_question_id(conn(request), q.strip() or None, tag)
    if question_id is None:
        return redirect("/prep")
    return redirect(f"/prep/{question_id}" + (f"?application={int(application)}" if application.isdigit() else ""))


@router.get("/new")
async def new(request: Request):
    return render(request, "prep/form.html", question=None, values={}, all_tags=prep.list_tags(conn(request)))


@router.post("")
async def create(request: Request):
    form = await request.form()
    values = _form_values(form)
    try:
        question_id = prep.create_question(conn(request), values["prompt"], values["notes"], values["tags"])
    except ValueError as exc:
        return render(
            request, "prep/form.html", status_code=422, question=None, values=values,
            all_tags=prep.list_tags(conn(request)), error=str(exc),
        )
    return redirect(f"/prep/{question_id}")


@router.post("/starter")
async def add_starter(request: Request):
    prep.add_starter_questions(conn(request))
    return redirect("/prep")


# --- answers (declared before /prep/{question_id} routes) ---

@router.get("/answers/{answer_id}")
async def answer(request: Request, answer_id: int):
    return _answer_partial(request, _answer_or_404(request, answer_id))


@router.get("/answers/{answer_id}/audio")
async def answer_audio(request: Request, answer_id: int):
    row = _answer_or_404(request, answer_id)
    if not row["audio_stored_name"]:
        raise HTTPException(404, "This answer has no recording")
    path = config(request).files_dir / row["audio_stored_name"]
    if not path.exists():
        raise HTTPException(404, "Recording is missing from the data folder")
    return FileResponse(
        path, media_type=row["audio_mime"], content_disposition_type="inline",
        filename=f"answer-{answer_id}{path.suffix}", headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/answers/{answer_id}")
async def update_answer(request: Request, answer_id: int):
    row = _answer_or_404(request, answer_id)
    form = await request.form()
    prep.update_answer(conn(request), answer_id, form.get("body", ""), form.get("application_id", ""))
    return redirect(safe_next(form.get("next"), f"/prep/{row['question_id']}#answer-{answer_id}"))


@router.post("/answers/{answer_id}/best")
async def toggle_best(request: Request, answer_id: int):
    row = _answer_or_404(request, answer_id)
    form = await request.form()
    prep.toggle_best(conn(request), answer_id)
    return redirect(safe_next(form.get("next"), f"/prep/{row['question_id']}#answer-{answer_id}"))


@router.post("/answers/{answer_id}/retranscribe")
async def retranscribe(request: Request, answer_id: int, background: BackgroundTasks):
    row = _answer_or_404(request, answer_id)
    if not row["audio_stored_name"] or not transcribe.available():
        raise HTTPException(400, "Nothing to transcribe")
    c = conn(request)
    prep.set_transcript_status(c, answer_id, "pending")
    background.add_task(_transcribe_answer, c, config(request).files_dir, answer_id)
    return redirect(f"/prep/{row['question_id']}#answer-{answer_id}")


@router.post("/answers/{answer_id}/delete")
async def delete_answer(request: Request, answer_id: int):
    row = _answer_or_404(request, answer_id)
    form = await request.form()
    stored = prep.delete_answer(conn(request), answer_id)
    if stored:
        (config(request).files_dir / stored).unlink(missing_ok=True)
    return redirect(safe_next(form.get("next"), f"/prep/{row['question_id']}#answers"))


# --- one question ---

def detail_page(request: Request, question, status_code: int = 200, **extra):
    c = conn(request)
    extra.setdefault("application", request.query_params.get("application", ""))
    return render(
        request, "prep/detail.html", status_code=status_code, question=question,
        tags=prep.parse_tags(question["tags"]), answers=prep.answers_for_question(c, question["id"]),
        applications=_active_applications(request), voice_available=transcribe.available(), **extra,
    )


@router.get("/{question_id}")
async def detail(request: Request, question_id: int):
    return detail_page(request, _question_or_404(request, question_id))


@router.get("/{question_id}/edit")
async def edit(request: Request, question_id: int):
    question = _question_or_404(request, question_id)
    values = {"prompt": question["prompt"], "notes": question["notes"], "tags": ", ".join(prep.parse_tags(question["tags"]))}
    return render(request, "prep/form.html", question=question, values=values, all_tags=prep.list_tags(conn(request)))


@router.post("/{question_id}")
async def update(request: Request, question_id: int):
    question = _question_or_404(request, question_id)
    form = await request.form()
    values = _form_values(form)
    try:
        prep.update_question(conn(request), question_id, values["prompt"], values["notes"], values["tags"])
    except ValueError as exc:
        return render(
            request, "prep/form.html", status_code=422, question=question, values=values,
            all_tags=prep.list_tags(conn(request)), error=str(exc),
        )
    return redirect(f"/prep/{question_id}")


@router.post("/{question_id}/delete")
async def delete(request: Request, question_id: int):
    _question_or_404(request, question_id)
    files_dir = config(request).files_dir
    for name in prep.delete_question(conn(request), question_id):
        (files_dir / name).unlink(missing_ok=True)
    return redirect("/prep")


@router.post("/{question_id}/answers")
async def add_text_answer(request: Request, question_id: int):
    question = _question_or_404(request, question_id)
    form = await request.form()
    try:
        answer_id = prep.add_text_answer(conn(request), question_id, form.get("body", ""), form.get("application_id", ""))
    except ValueError as exc:
        return detail_page(
            request, question, status_code=422, answer_error=str(exc),
            draft=form.get("body", ""), application=form.get("application_id", ""),
        )
    return redirect(f"/prep/{question_id}#answer-{answer_id}")


@router.post("/{question_id}/answers/record")
async def add_voice_answer(request: Request, question_id: int, background: BackgroundTasks):
    """Store a browser recording and queue its transcription; returns the new answer's partial."""
    _question_or_404(request, question_id)
    form = await request.form()
    upload = form.get("audio")
    if upload is None or not hasattr(upload, "file"):
        raise HTTPException(400, "No recording received")
    mime = (upload.content_type or "").split(";")[0].strip().lower()
    if mime not in AUDIO_TYPES:
        raise HTTPException(400, f"Unsupported recording type: {mime or 'unknown'}")
    try:
        duration = round(float(form.get("duration") or 0), 1) or None
    except ValueError:
        duration = None

    c = conn(request)
    files_dir = config(request).files_dir
    files_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{AUDIO_TYPES[mime]}"
    dest = files_dir / stored_name
    with dest.open("wb") as out:
        shutil.copyfileobj(upload.file, out)
    try:
        answer_id = prep.add_voice_answer(
            c, question_id, stored_name=stored_name, mime=mime, duration=duration,
            status="pending" if transcribe.available() else "none",
            application_id=form.get("application_id", ""),
        )
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    if transcribe.available():
        background.add_task(_transcribe_answer, c, files_dir, answer_id)
    return _answer_partial(request, prep.get_answer(c, answer_id), status_code=201)
