# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Job Cannon is a local job-search manager (applications, kanban board, contacts, interaction log with follow-ups, file attachments). It's a FastAPI + Jinja + htmx app served on localhost, backed by one SQLite file per profile. Profiles let several people share one OS login, each with their own data. All of it lives in one portable data folder.

## Commands

Uses [uv](https://docs.astral.sh/uv/) (Python >= 3.12).

```sh
uv sync                                   # install deps (incl. dev group: pytest, httpx)
uv sync --extra voice                     # also faster-whisper, for transcribing recorded prep answers
uv run job-cannon                         # serve at http://127.0.0.1:8765/ and open a browser
uv run job-cannon serve --no-browser --port 9000 --data-dir /tmp/jc   # dev run against throwaway data
uv run job-cannon backup --out DIR        # zip of the active profile's DB snapshot + files/ (--profile X, or --all)
uv run job-cannon profiles [--json]       # list profiles / active profile as JSON; `profiles use NAME` switches
uv run job-cannon profiles sector NAME teaching   # set a profile's job sector ('' for general)
uv run pytest                             # all tests
uv run pytest tests/test_web.py::test_name   # single test
```

There is no linter/formatter configured and no frontend build step.

Data folder resolution: `--data-dir` flag → `JOB_CANNON_DATA` env var → `~/JobCannon`. That folder is the **root**: it holds `profiles.json` (the profile registry and the active profile) and the first profile's `jobcannon.db` and `files/` (that profile's `dir` is `"."`, so installs from before profiles keep working with nothing moved). Later profiles live in `profiles/<id>/`, each an ordinary data folder (`config.Config`). Profile selection: `--profile` → `JOB_CANNON_PROFILE` → the active one. Without a `profiles.json` there is one profile, `default`, and reading never creates the file. When running the app during development, pass `--data-dir` so you don't touch the user's real data in `~/JobCannon`.

## Architecture

Layers, top to bottom:

- `cli.py`: argparse entry point (`serve` is the default subcommand, plus `backup` and `profiles`). `--data-dir` and `--profile` are accepted before or after the subcommand.
- `profiles.py`: the registry (`load`, `create`, `rename`, `set_active`, `check_delete`/`delete`, `resolve_profile`). It has no web code; the skill scripts use it too.
- `web/app.py`: `create_app(root, profile=None)` factory. It keeps **one SQLite connection per opened profile** in `app.state.conns` (opened lazily by `open_profile`, which migrates and runs `prep.fail_pending`), and the active profile id in `app.state.active`. Route modules import shared helpers from here: `conn(request)` and `config(request)` (the **active** profile's connection and data folder; always go through these), `render(...)` (injects `today`, `profile`, `profiles`), `redirect(...)` (303), `safe_next(...)`.
- `web/routes/*.py`: one `APIRouter` per area. Each must be added to the `include_router` loop at the bottom of `create_app`.
- `repo/*.py`: plain-`sqlite3` data access. Each takes a `conn` as its first argument and returns `sqlite3.Row`s. Writes are wrapped in `with conn:` for the transaction. Repo functions raise `ValueError` for invalid input, and routes turn that into a 422 form re-render or a 400.
- `migrations/NNN_*.sql`: applied in order by `db.migrate()`, which tracks the applied version with `PRAGMA user_version`. To change the schema, add a new numbered file (e.g. `002_*.sql`). Never edit `001_init.sql`, because existing user databases have already applied it.

Key invariants and conventions:

- **Profiles**: only one is active at a time, for the whole app (switching in one tab switches every tab). Connections are **never closed on a switch**, so a background transcription still writes to the profile it started in. Only deleting a profile closes its connection. After changing `profiles.json`, call `load_profiles(app)`.
- **Sectors**: each profile has a `sector` (a `profiles.SECTORS` key, or `""` for general), stored in `profiles.json`. It picks the Claude skills' sector guide, `.claude/sectors/<key>.md` (`general.md` when empty), and the extra interview-prep starter questions in `prep.SECTOR_QUESTIONS`. The skills stay sector-neutral and defer to the guide's sections (*Profile cues*, *Search*, *Fit checks*, *Record*, *Writing*), and the person's `job-search.md` holds only personal facts. To add a sector: add it to `SECTORS`, write its guide with those headings (a test checks every sector has one), and optionally add starter questions. `load_profiles` keeps the app's active profile, so a CLI `profiles use` waits for a restart, but a CLI sector change is picked up.
- **All route handlers must be `async def`.** That keeps them on the event-loop thread so the single shared connection is used without locking (`check_same_thread=False`). A sync `def` handler would run in a threadpool and break this.
- **Enumerated values are defined twice**, once as Python lists (`applications.STATUSES`, `interactions.KINDS`, `attachments.KINDS`, `prep.ANSWER_MODES`, `prep.TRANSCRIPT_STATUSES`) and once as SQL `CHECK` constraints in the migration. Changing one requires a migration for the other. The Python lists are exposed to every template as Jinja globals in `web/app.py`.
- **Status changes** go through `applications.create`, `update`, or `reorder`. These append to `status_history` and reset `position` when the status changes. Don't update `status` directly.
- **Archiving** (migration `006`): `applications.archived_at` (NULL = active) hides an application from the board, list, status counts and dashboard follow-ups without touching its status, e.g. a posting that closed before applying. Set it via `applications.set_archived`. New queries over "active" applications should filter `archived_at IS NULL`; `list_applications(archived=None)` includes both (the find-jobs duplicate check uses this).
- **Kanban**: `static/board.js` (SortableJS) POSTs each affected column's full ordered id list to `/board/reorder` after a drop.
- **htmx**: some GET routes return a partial when the `HX-Request` header is set (e.g. `/applications` renders `applications/_rows.html` for live filtering). Partial templates are prefixed with `_`.
- **Attachments**: stored under `files/` with a UUID name. The original name and MIME type are kept in the `attachments` table. Deleting an application cascades the DB rows, and `repo.applications.delete` returns the stored names so the caller can remove the files from disk (`attachments.remove_files`).
- **Cover letters** (`repo/cover_letters.py`, migration `002`): `cover_letter_templates` are named base letters with placeholders `{{name}}` / `{{name: instruction}}`. `company`, `role` and `date` are filled when a draft starts (`fill_builtins`). Each application has at most one draft in `cover_letters`. "Attach as PDF" refuses while any placeholder remains, then renders the text with `pdf.render_letter` and stores it as an ordinary `cover_letter` attachment. "Preview PDF" renders without attaching. The PDF layout is code in `pdf.py`: fpdf2 with vendored Noto TTFs in `fonts/` (for non-Latin-1 characters), a letterhead and accent colour from the single-row `letterhead` table (migration `003`, edited on the Cover letters page), typographic quotes via `smarten`, and the date on the right (taken from a leading date line in the text, else today). Text is left-aligned on purpose because fpdf2 has no hyphenation, so justified text gets wide gaps; note that `multi_cell` justifies by default. The `tailor-cover-letter` skill fills drafts from the CLI (`.claude/skills/tailor-cover-letter/scripts/cover_letter.py`).
- **Interview prep** (`repo/prep.py`, `web/routes/prep.py`, migration `005`): a question bank (`prep_questions`) with free-form tags (`prep_tags` + `prep_question_tags`; `parse_tags` normalises to lowercase, and tags no question uses are deleted). Tag filters combine with AND. `prep_answers` are typed (`mode='text'`) or recorded (`mode='voice'`), and can optionally link to an application (`ON DELETE SET NULL`). `static/prep-recorder.js` records with `MediaRecorder` and POSTs to `/prep/{id}/answers/record`, which accepts only the `AUDIO_TYPES` allow-list, stores the audio flat in `files/` (UUID name, like attachments), and returns the `_answer.html` partial. A pending answer polls itself with htmx until its transcript lands. Transcription (`transcribe.py`) uses faster-whisper from the optional `voice` extra, locally, and the model is set by `JOB_CANNON_WHISPER_MODEL` (default `base.en`). It runs as a `BackgroundTasks` coroutine: `asyncio.to_thread` gets only the file path, and DB writes happen back on the event loop. Never pass the connection to the thread. Without the extra, recordings are kept with status `none`. At startup, `prep.fail_pending` marks interrupted transcriptions `failed` so they can be retried. Deleting a question or answer must also unlink its audio files. The extra caps `av<19` because PyAV 19 broke faster-whisper 1.2's decoder.
- Timestamps are stored as ISO-8601 TEXT: UTC via `db.now()` for record times, and local `datetime-local` format for user-entered interaction times.

Security measures to preserve (the app is localhost-only):
- `TrustedHostMiddleware` limits hosts to `127.0.0.1`, `localhost`, and `testserver` (blocks DNS rebinding).
- A middleware rejects non-GET requests whose `Origin` doesn't match `Host` (CSRF).
- Stale-tab guard: pages send the profile they were rendered for (`X-Job-Cannon-Profile` via `hx-headers` on `<body>`, `?_profile=` added to plain form posts by `static/profile-guard.js`, and an explicit header in `board.js`/`prep-recorder.js`). A middleware answers 409 to non-GET requests whose profile isn't the active one, so a tab left open can't write into another person's data. New `fetch` POSTs must send the header. `/profiles/*` is exempt.
- `safe_next` allows only relative redirects, and the `http_only` Jinja filter allows only http(s) links in user-supplied URLs.
- Attachments are served inline only for an allow-list of MIME types (`INLINE_TYPES` in `routes/files.py`), always with `nosniff`. Anything else is a download.

Frontend: Pico.css, htmx, and SortableJS are vendored in `static/` so the app works offline. Don't add CDN links. Easter egg: double-clicking the header logo opens a cannon duel minigame (`static/cannon-game.js`, self-contained; single clicks still navigate after a 250 ms delay).

Theme ("Ledger": navy ink, brass, cream paper; Rokkitt headings, Source Sans 3 body): `static/app.css` defines `--jc-*` colour tokens on `:root`, overrides them for dark mode, and maps them onto Pico's `--pico-*` variables in one block. Change colours through the tokens, not in individual rules. The fonts are vendored variable woff2 files in `static/fonts/`, with their OFL licences.

## Tests

`tests/conftest.py` provides `cfg` (a temp data dir, which is also the root of its default profile), `conn` (a migrated connection, for repo tests), and `client` (a FastAPI `TestClient` over `create_app(cfg.data_dir)`, for web tests). Profile tests are in `tests/test_profiles.py`. Tests never touch `~/JobCannon`.
