"""Interview prep concepts: short explanations to rehearse, linked to questions.

Registered before ``routes.prep`` so ``/prep/concepts`` isn't read as a question id.
"""

from fastapi import APIRouter, HTTPException, Query, Request

from job_cannon.repo import prep
from job_cannon.web.app import conn, redirect, render, safe_next

router = APIRouter(prefix="/prep/concepts")


def _concept_or_404(request: Request, concept_id: int):
    row = prep.get_concept(conn(request), concept_id)
    if row is None:
        raise HTTPException(404, "Concept not found")
    return row


def _form_values(form) -> dict:
    return {k: form.get(k, "") for k in ["name", "explanation", "notes", "tags"]}


def _form(request: Request, concept, values: dict, status_code: int = 200, error: str | None = None):
    return render(
        request, "prep/concept_form.html", status_code=status_code, concept=concept, values=values, error=error,
        all_tags=prep.list_tags(conn(request), of="concepts"),
    )


@router.get("")
async def index(request: Request, q: str = "", tag: list[str] = Query([])):
    c = conn(request)
    tags = prep.parse_tags(tag)
    rows = prep.list_concepts(c, q.strip() or None, tags)
    template = "prep/_concepts.html" if request.headers.get("hx-request") else "prep/concepts.html"
    return render(
        request, template, rows=rows, q=q, total=len(prep.list_concepts(c)),
        selected_tags=tags, all_tags=prep.list_tags(c, of="concepts"),
    )


@router.get("/random")
async def random_concept(request: Request, q: str = "", tag: list[str] = Query([])):
    concept_id = prep.random_concept_id(conn(request), q.strip() or None, tag)
    return redirect(f"/prep/concepts/{concept_id}?test=1" if concept_id else "/prep/concepts")


@router.get("/new")
async def new(request: Request, question: str = ""):
    return _form(request, None, {"question": question if question.isdigit() else ""})


@router.post("")
async def create(request: Request):
    form = await request.form()
    values = _form_values(form) | {"question": form.get("question", "")}
    question_ids = [int(values["question"])] if values["question"].isdigit() else []
    try:
        concept_id = prep.create_concept(
            conn(request), values["name"], values["explanation"], values["notes"],
            question_ids=question_ids, tags=values["tags"],
        )
    except ValueError as exc:
        return _form(request, None, values, status_code=422, error=str(exc))
    return redirect(f"/prep/{question_ids[0]}#concepts" if question_ids else f"/prep/concepts/{concept_id}")


@router.get("/{concept_id}")
async def detail(request: Request, concept_id: int):
    concept = _concept_or_404(request, concept_id)
    c = conn(request)
    linked = prep.questions_for_concept(c, concept_id)
    linked_ids = {q["id"] for q in linked}
    return render(
        request, "prep/concept.html", concept=concept, questions=linked, tags=prep.parse_tags(concept["tags"]),
        other_questions=[q for q in prep.list_questions(c) if q["id"] not in linked_ids],
        test=request.query_params.get("test") == "1",
        quiz=prep.list_quiz_questions(c, concept_id=concept_id), quiz_stats=prep.quiz_stats(c, concept_id),
    )


@router.get("/{concept_id}/edit")
async def edit(request: Request, concept_id: int):
    concept = _concept_or_404(request, concept_id)
    values = {k: concept[k] for k in ["name", "explanation", "notes"]}
    return _form(request, concept, values | {"tags": ", ".join(prep.parse_tags(concept["tags"]))})


@router.post("/{concept_id}")
async def update(request: Request, concept_id: int):
    concept = _concept_or_404(request, concept_id)
    form = await request.form()
    values = _form_values(form)
    try:
        prep.update_concept(
            conn(request), concept_id, values["name"], values["explanation"], values["notes"], tags=values["tags"],
        )
    except ValueError as exc:
        return _form(request, concept, values, status_code=422, error=str(exc))
    return redirect(f"/prep/concepts/{concept_id}")


@router.post("/{concept_id}/delete")
async def delete(request: Request, concept_id: int):
    _concept_or_404(request, concept_id)
    prep.delete_concept(conn(request), concept_id)
    return redirect("/prep/concepts")


async def _link_args(request: Request, concept_id: int) -> tuple[int, str]:
    _concept_or_404(request, concept_id)
    form = await request.form()
    question_id = form.get("question_id", "")
    if not question_id.isdigit() or prep.get_question(conn(request), int(question_id)) is None:
        raise HTTPException(400, "Choose a question")
    return int(question_id), safe_next(form.get("next"), f"/prep/concepts/{concept_id}#questions")


@router.post("/{concept_id}/link")
async def link(request: Request, concept_id: int):
    question_id, next_url = await _link_args(request, concept_id)
    prep.link_concept(conn(request), question_id, concept_id)
    return redirect(next_url)


@router.post("/{concept_id}/unlink")
async def unlink(request: Request, concept_id: int):
    question_id, next_url = await _link_args(request, concept_id)
    prep.unlink_concept(conn(request), question_id, concept_id)
    return redirect(next_url)
