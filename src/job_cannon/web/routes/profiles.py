from fastapi import APIRouter, HTTPException, Request

from job_cannon import profiles
from job_cannon.web.app import close_profile, load_profiles, open_profile, redirect, render, safe_next

router = APIRouter(prefix="/profiles")


def _root(request: Request):
    return request.app.state.root


def _get_or_404(request: Request, profile_id: str) -> profiles.Profile:
    profile = request.app.state.profiles.get(profile_id)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    return profile


def _index(request: Request, status_code: int = 200, **context):
    root = _root(request)
    load_profiles(request.app)  # pick up changes made from the CLI
    folders = {p.id: p.config(root).data_dir for p in request.app.state.profiles.values()}
    return render(
        request, "profiles/index.html", status_code=status_code, folders=folders, sectors=profiles.SECTORS, **context
    )


def _switch(request: Request, profile_id: str) -> None:
    profiles.set_active(_root(request), profile_id)
    load_profiles(request.app)
    request.app.state.active = profile_id
    open_profile(request.app, profile_id)


@router.get("")
async def index(request: Request):
    return _index(request)


@router.post("")
async def create(request: Request):
    form = await request.form()
    try:
        profile = profiles.create(_root(request), form.get("name", ""), form.get("sector", ""))
    except ValueError as exc:
        return _index(
            request, status_code=422, error=str(exc), new_name=form.get("name", ""), new_sector=form.get("sector", "")
        )
    load_profiles(request.app)
    _switch(request, profile.id)
    return redirect("/")


@router.post("/{profile_id}/switch")
async def switch(request: Request, profile_id: str):
    _get_or_404(request, profile_id)
    form = await request.form()
    _switch(request, profile_id)
    return redirect(safe_next(form.get("next"), "/"))


@router.post("/{profile_id}/rename")
async def rename(request: Request, profile_id: str):
    _get_or_404(request, profile_id)
    form = await request.form()
    try:
        profiles.rename(_root(request), profile_id, form.get("name", ""))
    except ValueError as exc:
        return _index(request, status_code=422, error=str(exc))
    load_profiles(request.app)
    return redirect("/profiles")


@router.post("/{profile_id}/sector")
async def set_sector(request: Request, profile_id: str):
    _get_or_404(request, profile_id)
    form = await request.form()
    try:
        profiles.set_sector(_root(request), profile_id, form.get("sector", ""))
    except ValueError as exc:
        return _index(request, status_code=422, error=str(exc))
    load_profiles(request.app)
    return redirect("/profiles")


@router.post("/{profile_id}/delete")
async def delete(request: Request, profile_id: str):
    profile = _get_or_404(request, profile_id)
    form = await request.form()
    if form.get("confirm", "").strip().lower() != profile.name.lower():
        return _index(request, status_code=422, error=f"Type {profile.name!r} to confirm deleting it.")
    try:
        profiles.check_delete(_root(request), profile.id)  # before closing its connection
        close_profile(request.app, profile.id)
        profiles.delete(_root(request), profile.id)
    except ValueError as exc:
        return _index(request, status_code=422, error=str(exc))
    load_profiles(request.app)
    return redirect("/profiles")
