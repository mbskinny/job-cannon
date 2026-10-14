from fastapi import APIRouter, HTTPException, Request

from job_cannon.repo import applications, contacts, interactions
from job_cannon.web.app import conn, redirect, render

router = APIRouter(prefix="/contacts")


def _form_values(form) -> dict:
    return {k: form.get(k, "") for k in [*contacts.FIELDS, "company"]}


def _get_or_404(request: Request, contact_id: int):
    row = contacts.get(conn(request), contact_id)
    if row is None:
        raise HTTPException(404, "Contact not found")
    return row


@router.get("")
async def index(request: Request, q: str = ""):
    return render(
        request, "contacts/index.html", rows=contacts.list_contacts(conn(request), q.strip() or None), q=q
    )


@router.get("/new")
async def new(request: Request):
    return render(
        request, "contacts/form.html", contact=None, values={},
        companies=applications.list_companies(conn(request)),
    )


@router.post("")
async def create(request: Request):
    values = _form_values(await request.form())
    try:
        contact_id = contacts.create(conn(request), values, company=values["company"])
    except ValueError as exc:
        return render(
            request, "contacts/form.html", status_code=422, contact=None, values=values,
            error=str(exc), companies=applications.list_companies(conn(request)),
        )
    return redirect(f"/contacts/{contact_id}")


@router.get("/{contact_id}")
async def detail(request: Request, contact_id: int):
    c = conn(request)
    return render(
        request,
        "contacts/detail.html",
        contact=_get_or_404(request, contact_id),
        linked_apps=contacts.applications_for(c, contact_id),
        interactions=interactions.for_contact(c, contact_id),
        now_local=interactions.local_now(),
    )


@router.get("/{contact_id}/edit")
async def edit(request: Request, contact_id: int):
    contact = _get_or_404(request, contact_id)
    values = dict(contact)
    values["company"] = contact["company_name"] or ""
    return render(
        request, "contacts/form.html", contact=contact, values=values,
        companies=applications.list_companies(conn(request)),
    )


@router.post("/{contact_id}")
async def update(request: Request, contact_id: int):
    contact = _get_or_404(request, contact_id)
    values = _form_values(await request.form())
    try:
        contacts.update(conn(request), contact_id, values, company=values["company"])
    except ValueError as exc:
        return render(
            request, "contacts/form.html", status_code=422, contact=contact, values=values,
            error=str(exc), companies=applications.list_companies(conn(request)),
        )
    return redirect(f"/contacts/{contact_id}")


@router.post("/{contact_id}/delete")
async def delete(request: Request, contact_id: int):
    _get_or_404(request, contact_id)
    contacts.delete(conn(request), contact_id)
    return redirect("/contacts")
