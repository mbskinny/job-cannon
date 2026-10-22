# Job Cannon

Most important thing first: the name is a reference to [this](https://www.youtube.com/watch?v=wbq571QME2Y&t=28s).

A local job-search manager: applications, a kanban board, contacts, interaction
log with follow-ups, and attached files (resumes, cover letters, postings).
Cover letters can start from named base letters with `{{placeholders}}`. Fill
them in on the application page (or have Claude Code do it with the
`tailor-cover-letter` skill), then attach the result as a PDF.

For interview prep, keep a tagged bank of intro, behavioural and experience
questions. Practise each one by typing an answer or recording it with your
microphone. Recordings are kept and transcribed on your own machine.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/board-dark.png">
  <img alt="The Job Cannon board: applications as cards in Wishlist, Applied, Screening, Interviewing, Offer, Rejected and Withdrawn columns, with interest stars and next-action due dates" src="docs/board-light.png">
</picture>

The Claude Code skills (`find-jobs`, `tailor-cover-letter`) read your résumé
location from `.claude/job-search.local.md`; copy
`.claude/job-search.example.md` to get started.

It runs on your own machine and opens in your browser. **All of your data lives
in one folder**, so moving to another computer means copying that folder.

## Setup

Needs [uv](https://docs.astral.sh/uv/), which installs the right Python for you.

**Linux**
```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**macOS**
```sh
brew install uv          # or: curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then, from this repo:
```sh
uv sync
uv run job-cannon        # opens http://127.0.0.1:8765/
```

Options: `--port 9000`, `--no-browser`, `--data-dir PATH`.

To transcribe recorded interview answers, install the optional voice extra:
`uv sync --extra voice`. It runs Whisper locally (the model, about 150 MB, is
downloaded once on first use). Set `JOB_CANNON_WHISPER_MODEL` to pick another
model, e.g. `small.en` for better accuracy or `base` for languages other than English.

## Your data folder

Default location is `~/JobCannon` (override with `--data-dir` or the
`JOB_CANNON_DATA` environment variable).

```
~/JobCannon/
  jobcannon.db     # everything structured (SQLite)
  files/           # uploaded attachments
  profiles.json    # only once there's more than one profile
  job-search.md    # your résumé location and notes, for the Claude skills
  profiles/alex/   # another person's jobcannon.db, files/ and job-search.md
```

### Profiles

Several people can share one computer login: open the profile menu in the
header (it shows the current name) and choose **Manage profiles…** to add one.
Each profile has its own applications, contacts, cover letters, letterhead,
interview prep and files. One profile is active at a time for the whole app,
and the app remembers it between runs. A tab left open on another profile
refuses to save until you reload it, so nothing lands in the wrong person's data.

From the command line, `uv run job-cannon profiles` lists them,
`uv run job-cannon profiles use alex` switches, and `--profile alex` picks one
for a single command (for example `uv run job-cannon backup --profile alex`).
The Claude skills use the active profile and read that person's résumé
details from `job-search.md` in their profile folder.

Each profile can also have a **sector** (Software engineering or Teaching for
now), set on the Profiles page or with `uv run job-cannon profiles sector alex teaching`.
The skills follow that sector's guide in `.claude/sectors/` (where to search,
what makes a posting a fit, how letters are written), and interview prep
offers starter questions for it.

### Moving to a new computer

1. On the old machine, make a backup (safe to run while the app is open):
   ```sh
   uv run job-cannon backup --out ~/Desktop
   ```
   This writes `jobcannon-backup-<profile>-YYYYMMDD-HHMMSS.zip` for the active
   profile. Add `--all` for one zip per profile, and unzip each into its own
   profile folder.
2. On the new machine, clone this repo, run `uv sync`, and unzip the backup
   into `~/JobCannon` (or anywhere, then point `--data-dir` at it).
3. `uv run job-cannon`.

Copying the whole `~/JobCannon` folder works too, as long as the app is stopped.

## Development

```sh
uv run pytest
```

- `src/job_cannon/repo/` — data access (plain `sqlite3`)
- `src/job_cannon/migrations/` — numbered SQL files, tracked with `PRAGMA user_version`;
  add the next `NNN_*.sql` for schema changes, and existing databases upgrade on next start
- `src/job_cannon/web/` — FastAPI routes; `templates/` Jinja + htmx; `static/` vendored
  Pico.css, htmx, and SortableJS (no build step, works offline)

## License

MIT. Vendored libraries and fonts keep their own licences (see the files in
`src/job_cannon/static/` and the `fonts/` folders).
