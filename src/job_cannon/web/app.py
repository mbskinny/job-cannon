"""FastAPI application factory.

Handlers are ``async def`` so they all run on the event loop thread and share
one SQLite connection without locking.
"""

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from job_cannon import db, profiles
from job_cannon.config import Config
from job_cannon.repo import applications, attachments, interactions, prep

PKG_DIR = Path(__file__).resolve().parent.parent
LOCAL_HOSTS = ["127.0.0.1", "localhost", "testserver"]
PROFILE_HEADER = "X-Job-Cannon-Profile"

templates = Jinja2Templates(directory=PKG_DIR / "templates")
templates.env.globals.update(
    STATUSES=applications.STATUSES,
    STATUS_LABELS=applications.STATUS_LABELS,
    INTEREST_LEVELS=applications.INTEREST_LEVELS,
    INTEREST_LABELS=applications.INTEREST_LABELS,
    ATTACHMENT_KINDS=attachments.KIND_LABELS,
    INTERACTION_KINDS=interactions.KINDS,
    ANSWER_MODES=prep.ANSWER_MODES,
    TRANSCRIPT_STATUSES=prep.TRANSCRIPT_STATUSES,
)



def http_only(url: str) -> str:
    """Link filter: only follow http(s) URLs (blocks javascript: and friends)."""
    return url if urlsplit(url).scheme in ("http", "https") else "#"


templates.env.filters["http_only"] = http_only


def render(request: Request, name: str, status_code: int = 200, **context):
    context.setdefault("today", date.today().isoformat())
    state = request.app.state
    context.setdefault("profile", state.profiles[state.active])
    context.setdefault("profiles", list(state.profiles.values()))
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def safe_next(value: str | None, fallback: str) -> str:
    """Only allow same-site relative redirects."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return fallback


def conn(request: Request):
    """The active profile's connection."""
    state = request.app.state
    return state.conns[state.active]


def config(request: Request) -> Config:
    """The active profile's data folder."""
    state = request.app.state
    return state.profiles[state.active].config(state.root)


def load_profiles(app: FastAPI) -> None:
    """Re-read profiles.json into app state (after any change to it)."""
    reg = profiles.load(app.state.root)
    app.state.profiles = {p.id: p for p in reg.profiles}
    app.state.active = reg.active_profile().id


def open_profile(app: FastAPI, profile_id: str) -> None:
    """Connect to a profile's database once and keep it open.

    Connections stay open after switching away, so a background transcription
    started under one profile still finishes against that profile's database.
    """
    if profile_id in app.state.conns:
        return
    cfg = app.state.profiles[profile_id].config(app.state.root)
    cfg.ensure_dirs()
    connection = db.connect(cfg.db_path)
    db.migrate(connection)
    prep.fail_pending(connection)
    app.state.conns[profile_id] = connection


def close_profile(app: FastAPI, profile_id: str) -> None:
    connection = app.state.conns.pop(profile_id, None)
    if connection is not None:
        connection.close()


def create_app(root: Path, profile: str | None = None) -> FastAPI:
    """App over the data folder ``root``; ``profile`` switches to that profile first."""
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        for connection in _app.state.conns.values():
            connection.close()

    app = FastAPI(title="Job Cannon", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.root = root
    app.state.conns = {}
    if profile:
        profiles.set_active(root, profile)
    load_profiles(app)
    open_profile(app, app.state.active)

    # Only answer to localhost names (blocks DNS-rebinding), and reject
    # form posts that originate from some other website.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)

    @app.middleware("http")
    async def same_origin_posts(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return PlainTextResponse("Cross-origin request refused", status_code=403)
        return await call_next(request)

    # A page opened under one profile must not post into another after a
    # switch in some other tab (ids would land on the wrong person's data).
    # Pages send the profile they were rendered for; requests without it pass,
    # and so do the profile routes, which act on the registry, not the data.
    @app.middleware("http")
    async def same_profile_posts(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS") and not request.url.path.startswith("/profiles"):
            sent = request.headers.get(PROFILE_HEADER) or request.query_params.get("_profile")
            active = request.app.state.active
            if sent and sent != active:
                name = request.app.state.profiles[active].name
                return PlainTextResponse(
                    f"Job Cannon switched to the profile {name!r} in another tab, so this wasn't saved. "
                    "Go back and reload the page to continue as that profile, or switch back first.",
                    status_code=409,
                )
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=PKG_DIR / "static"), name="static")

    from job_cannon.web.routes import applications as r_apps
    from job_cannon.web.routes import board, contacts, cover_letters, dashboard, files
    from job_cannon.web.routes import prep as r_prep
    from job_cannon.web.routes import profiles as r_profiles
    from job_cannon.web.routes import interactions as r_interactions

    for module in (dashboard, r_apps, board, contacts, r_interactions, files, cover_letters, r_prep, r_profiles):
        app.include_router(module.router)

    return app
