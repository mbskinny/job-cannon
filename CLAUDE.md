# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Job Cannon is a local, single-user job-search manager (applications, kanban board, contacts, interaction log with follow-ups, file attachments). It's a FastAPI + Jinja + htmx app served on localhost, backed by one SQLite file. All user data lives in one portable data folder.

## Commands

Uses [uv](https://docs.astral.sh/uv/) (Python >= 3.12).

```sh
uv sync                                   # install deps (incl. dev group: pytest, httpx)
uv run job-cannon                         # serve at http://127.0.0.1:8765/ and open a browser
uv run job-cannon serve --no-browser --port 9000 --data-dir /tmp/jc   # dev run against throwaway data
uv run job-cannon backup --out DIR        # zip of DB snapshot + files/
uv run pytest                             # all tests
uv run pytest tests/test_web.py::test_name   # single test
```

There is no linter/formatter configured and no frontend build step.

Data folder resolution: `--data-dir` flag → `JOB_CANNON_DATA` env var → `~/JobCannon`. It contains `jobcannon.db` and `files/`. When running the app during development, pass `--data-dir` so you don't touch the user's real data in `~/JobCannon`.

## Architecture

Layers, top to bottom:

- `cli.py`: argparse entry point (`serve` is the default subcommand, plus `backup`). `--data-dir` is accepted before or after the subcommand.
- `web/app.py`: `create_app(cfg)` factory. It opens **one shared SQLite connection** at startup, runs migrations, and stores it on `app.state.conn`. Route modules import shared helpers from here: `conn(request)`, `config(request)`, `render(...)` (injects `today`), `redirect(...)` (303), `safe_next(...)`.
- `web/routes/*.py`: one `APIRouter` per area. Each must be added to the `include_router` loop at the bottom of `create_app`.
- `repo/*.py`: plain-`sqlite3` data access. Each takes a `conn` as its first argument and returns `sqlite3.Row`s. Writes are wrapped in `with conn:` for the transaction. Repo functions raise `ValueError` for invalid input, and routes turn that into a 422 form re-render or a 400.
- `migrations/NNN_*.sql`: applied in order by `db.migrate()`, which tracks the applied version with `PRAGMA user_version`. To change the schema, add a new numbered file (e.g. `002_*.sql`). Never edit `001_init.sql`, because existing user databases have already applied it.

Key invariants and conventions:

- **All route handlers must be `async def`.** That keeps them on the event-loop thread so the single shared connection is used without locking (`check_same_thread=False`). A sync `def` handler would run in a threadpool and break this.
- **Enumerated values are defined twice**, once as Python lists (`applications.STATUSES`, `interactions.KINDS`, `attachments.KINDS`) and once as SQL `CHECK` constraints in the migration. Changing one requires a migration for the other. The Python lists are exposed to every template as Jinja globals in `web/app.py`.
- **Status changes** go through `applications.create`, `update`, or `reorder`. These append to `status_history` and reset `position` when the status changes. Don't update `status` directly.
- **Kanban**: `static/board.js` (SortableJS) POSTs each affected column's full ordered id list to `/board/reorder` after a drop.
- **htmx**: some GET routes return a partial when the `HX-Request` header is set (e.g. `/applications` renders `applications/_rows.html` for live filtering). Partial templates are prefixed with `_`.
- **Attachments**: stored under `files/` with a UUID name. The original name and MIME type are kept in the `attachments` table. Deleting an application cascades the DB rows, and `repo.applications.delete` returns the stored names so the caller can remove the files from disk (`attachments.remove_files`).
- **Cover letters** (`repo/cover_letters.py`, migration `002`): `cover_letter_templates` are named base letters with placeholders `{{name}}` / `{{name: instruction}}`. `company`, `role` and `date` are filled when a draft starts (`fill_builtins`). Each application has at most one draft in `cover_letters`. "Attach as PDF" refuses while any placeholder remains, then renders the text with `pdf.render_letter` and stores it as an ordinary `cover_letter` attachment. "Preview PDF" renders without attaching. The PDF layout is code in `pdf.py`: fpdf2 with vendored Noto TTFs in `fonts/` (for non-Latin-1 characters), a letterhead and accent colour from the single-row `letterhead` table (migration `003`, edited on the Cover letters page), typographic quotes via `smarten`, and the date on the right (taken from a leading date line in the text, else today). Text is left-aligned on purpose because fpdf2 has no hyphenation, so justified text gets wide gaps; note that `multi_cell` justifies by default. The `tailor-cover-letter` skill fills drafts from the CLI (`.claude/skills/tailor-cover-letter/scripts/cover_letter.py`).
- Timestamps are stored as ISO-8601 TEXT: UTC via `db.now()` for record times, and local `datetime-local` format for user-entered interaction times.

Security measures to preserve (the app is localhost-only):
- `TrustedHostMiddleware` limits hosts to `127.0.0.1`, `localhost`, and `testserver` (blocks DNS rebinding).
- A middleware rejects non-GET requests whose `Origin` doesn't match `Host` (CSRF).
- `safe_next` allows only relative redirects, and the `http_only` Jinja filter allows only http(s) links in user-supplied URLs.
- Attachments are served inline only for an allow-list of MIME types (`INLINE_TYPES` in `routes/files.py`), always with `nosniff`. Anything else is a download.

Frontend: Pico.css, htmx, and SortableJS are vendored in `static/` so the app works offline. Don't add CDN links.

Theme ("Ledger": navy ink, brass, cream paper; Rokkitt headings, Source Sans 3 body): `static/app.css` defines `--jc-*` colour tokens on `:root`, overrides them for dark mode, and maps them onto Pico's `--pico-*` variables in one block. Change colours through the tokens, not in individual rules. The fonts are vendored variable woff2 files in `static/fonts/`, with their OFL licences.

## Tests

`tests/conftest.py` provides `cfg` (a temp data dir), `conn` (a migrated connection, for repo tests), and `client` (a FastAPI `TestClient` over `create_app`, for web tests). Tests never touch `~/JobCannon`.
