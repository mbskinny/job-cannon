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

from job_cannon import db
from job_cannon.config import Config
from job_cannon.repo import applications, attachments, interactions, prep

PKG_DIR = Path(__file__).resolve().parent.parent
LOCAL_HOSTS = ["127.0.0.1", "localhost", "testserver"]

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
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def safe_next(value: str | None, fallback: str) -> str:
    """Only allow same-site relative redirects."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return fallback


def conn(request: Request):
    return request.app.state.conn


def config(request: Request) -> Config:
    return request.app.state.config


def create_app(cfg: Config) -> FastAPI:
    cfg.ensure_dirs()
    connection = db.connect(cfg.db_path)
    db.migrate(connection)
    prep.fail_pending(connection)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        connection.close()

    app = FastAPI(title="Job Cannon", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.config = cfg
    app.state.conn = connection

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

    app.mount("/static", StaticFiles(directory=PKG_DIR / "static"), name="static")

    from job_cannon.web.routes import applications as r_apps
    from job_cannon.web.routes import board, contacts, cover_letters, dashboard, files
    from job_cannon.web.routes import prep as r_prep
    from job_cannon.web.routes import interactions as r_interactions

    for module in (dashboard, r_apps, board, contacts, r_interactions, files, cover_letters, r_prep):
        app.include_router(module.router)

    return app
