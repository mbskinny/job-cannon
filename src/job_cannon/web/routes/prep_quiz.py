"""Interview prep quiz: multiple-choice questions on the concepts, with results kept per question.

Registered before ``routes.prep`` so ``/prep/quiz`` isn't read as a question id. The
play page carries the whole deck as JSON; ``static/prep-quiz.js`` shuffles it, runs
the quiz and posts each result to ``/prep/quiz/{id}/answer``.
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from job_cannon.repo import prep
from job_cannon.web.app import conn, redirect, render, safe_next

router = APIRouter(prefix="/prep/quiz")

FIELDS = ["concept_id", "prompt", "code", "answer", "explanation"]
WRONG = [f"wrong_{i}" for i in range(1, prep.QUIZ_WRONG_ANSWERS + 1)]


def _question_or_404(request: Request, question_id: int):
    row = prep.get_quiz_question(conn(request), question_id)
    if row is None:
        raise HTTPException(404, "Quiz question not found")
    return row


def _concept_page(concept_id) -> str:
    return f"/prep/concepts/{concept_id}#quiz" if str(concept_id).isdigit() else "/prep/quiz"


def _deck_item(row) -> dict:
    return {
        "id": row["id"], "concept_id": row["concept_id"], "concept": row["concept_name"],
        "prompt": row["prompt"], "code": row["code"], "answer": row["answer"],
        "wrong": prep.quiz_wrong_answers(row), "explanation": row["explanation"],
    }


@router.get("")
async def play(request: Request, tag: list[str] = Query([]), concept: str = "", focus: str = ""):
    c = conn(request)
    tags = prep.parse_tags(tag)
    concept_row = prep.get_concept(c, int(concept)) if concept.isdigit() else None
    concept_id = concept_row["id"] if concept_row else None
    focusing = focus == "1"
    rows = prep.list_quiz_questions(c, tags, concept_id, focus=focusing)
    matching = len(rows) if not focusing else len(prep.list_quiz_questions(c, tags, concept_id))
    return render(
        request, "prep/quiz.html", deck=[_deck_item(r) for r in rows], matching=matching,
        total=len(prep.list_quiz_questions(c)), all_tags=prep.quiz_tags(c), selected_tags=tags,
        concept=concept_row, focus=focusing,
    )


def _form_values(form) -> dict:
    return {k: form.get(k, "") for k in FIELDS + WRONG + ["next"]}


def _form(request: Request, question, values: dict, status_code: int = 200, error: str | None = None):
    return render(
        request, "prep/quiz_form.html", status_code=status_code, question=question, values=values, error=error,
        concepts=prep.list_concepts(conn(request)),
    )


@router.get("/new")
async def new(request: Request, concept: str = "", next: str = ""):
    return _form(request, None, {"concept_id": concept, "next": next})


@router.post("")
async def create(request: Request):
    values = _form_values(await request.form())
    try:
        prep.create_quiz_question(
            conn(request), values["concept_id"], values["prompt"], values["answer"],
            [values[w] for w in WRONG], values["explanation"], values["code"],
        )
    except ValueError as exc:
        return _form(request, None, values, status_code=422, error=str(exc))
    return redirect(safe_next(values["next"], _concept_page(values["concept_id"])))


@router.get("/{question_id}/edit")
async def edit(request: Request, question_id: int, next: str = ""):
    question = _question_or_404(request, question_id)
    return _form(request, question, {k: question[k] for k in FIELDS + WRONG} | {"next": next})


@router.post("/{question_id}")
async def update(request: Request, question_id: int):
    question = _question_or_404(request, question_id)
    values = _form_values(await request.form())
    try:
        prep.update_quiz_question(
            conn(request), question_id, values["concept_id"], values["prompt"], values["answer"],
            [values[w] for w in WRONG], values["explanation"], values["code"],
        )
    except ValueError as exc:
        return _form(request, question, values, status_code=422, error=str(exc))
    return redirect(safe_next(values["next"], _concept_page(values["concept_id"])))


@router.post("/{question_id}/delete")
async def delete(request: Request, question_id: int):
    question = _question_or_404(request, question_id)
    prep.delete_quiz_question(conn(request), question_id)
    form = await request.form()
    return redirect(safe_next(form.get("next"), _concept_page(question["concept_id"])))


@router.post("/{question_id}/answer")
async def answer(request: Request, question_id: int):
    _question_or_404(request, question_id)
    form = await request.form()
    if form.get("correct") not in ("0", "1"):
        raise HTTPException(400, "correct must be 0 or 1")
    prep.record_quiz_answer(conn(request), question_id, form.get("correct") == "1")
    return Response(status_code=204)
