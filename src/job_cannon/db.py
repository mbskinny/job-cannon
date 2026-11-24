"""SQLite connection handling and schema migrations.

Migrations are numbered SQL files in ``migrations/``; the applied version is
tracked with ``PRAGMA user_version``.

``SCHEMA_VERSION`` is the newest migration this process's code knows, fixed when
the module is imported. A long-running process (the MCP server, the app) started
before an update must not write to a database that newer code has migrated: its
old code doesn't know the new tables (old prep code once deleted every concept tag
that way). ``check_schema`` refuses, and ``migrate`` never applies a migration file
that appeared on disk after the process started.

Automatic snapshots (``snapshot_if_due``) keep recent copies of a database, so a bad
write can be undone without a manual backup.
"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path


def now() -> str:
    """Current UTC time as ISO-8601 text (seconds precision)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migration_files() -> list[tuple[int, str]]:
    pkg = resources.files("job_cannon") / "migrations"
    found = []
    for entry in pkg.iterdir():
        name = entry.name
        if name.endswith(".sql") and name[:3].isdigit():
            found.append((int(name[:3]), entry.read_text(encoding="utf-8")))
    return sorted(found)


SCHEMA_VERSION = _migration_files()[-1][0]


class SchemaTooNew(RuntimeError):
    """The database was migrated by newer code than this process is running."""

    def __init__(self, version: int):
        self.version = version
        super().__init__(
            f"The Job Cannon database is at schema version {version}, but this process's code only knows "
            f"version {SCHEMA_VERSION}: it was started before Job Cannon was updated. Nothing was changed. "
            "Restart it: for the MCP server, run /mcp in Claude Code and reconnect job-cannon; "
            "for the app, stop it and start it again."
        )


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def check_schema(conn: sqlite3.Connection) -> None:
    """Raise ``SchemaTooNew`` if newer code has migrated this database."""
    version = schema_version(conn)
    if version > SCHEMA_VERSION:
        raise SchemaTooNew(version)


def migrate(conn: sqlite3.Connection) -> int:
    """Apply any migrations newer than the database's user_version (up to ``SCHEMA_VERSION``)."""
    check_schema(conn)
    current = schema_version(conn)
    for version, sql in _migration_files():
        if version <= current or version > SCHEMA_VERSION:
            continue
        with conn:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {version}")
        current = version
    return current


def backup_to(conn: sqlite3.Connection, dest: Path) -> None:
    """Consistent copy of the live database, safe while the app is running."""
    target = sqlite3.connect(dest)
    try:
        conn.backup(target)
    finally:
        target.close()


# Automatic snapshots: at most one per SNAPSHOT_INTERVAL. Pruning keeps the newest
# SNAPSHOT_KEEP_RECENT, plus the newest of each of the last SNAPSHOT_KEEP_DAYS days,
# so a burst of activity can't rotate out every copy from before a problem.
SNAPSHOT_INTERVAL = timedelta(hours=1)
SNAPSHOT_KEEP_RECENT = 10
SNAPSHOT_KEEP_DAYS = 14
_SNAPSHOT_NAME = re.compile(r"jobcannon-(\d{8}-\d{6})\.db")


def _snapshots(folder: Path) -> list[tuple[datetime, Path]]:
    """(time, path) of the snapshots in ``folder``, oldest first."""
    found = []
    if folder.is_dir():
        for f in folder.iterdir():
            m = _SNAPSHOT_NAME.fullmatch(f.name)
            if m:
                found.append((datetime.strptime(m[1], "%Y%m%d-%H%M%S"), f))
    return sorted(found)


def snapshot_if_due(conn: sqlite3.Connection, folder: Path, now: datetime | None = None) -> Path | None:
    """Copy the database into ``folder`` unless the newest copy there is recent; returns the new file.

    Skips a database no migration has touched yet (a brand-new profile), and prunes old copies.
    """
    if schema_version(conn) == 0:
        return None
    now = (now or datetime.now()).replace(microsecond=0)
    existing = _snapshots(folder)
    if existing and now - existing[-1][0] < SNAPSHOT_INTERVAL:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"jobcannon-{now:%Y%m%d-%H%M%S}.db"
    partial = folder / f".{dest.name}.partial"
    partial.unlink(missing_ok=True)
    backup_to(conn, partial)
    partial.replace(dest)  # never leave a half-written file under a snapshot's name
    prune_snapshots(folder)
    return dest


def prune_snapshots(folder: Path) -> None:
    snaps = _snapshots(folder)
    keep = {path for _, path in snaps[-SNAPSHOT_KEEP_RECENT:]}
    newest_per_day: dict = {}
    for when, path in snaps:
        newest_per_day[when.date()] = path
    keep.update(newest_per_day[day] for day in sorted(newest_per_day)[-SNAPSHOT_KEEP_DAYS:])
    for _, path in snaps:
        if path not in keep:
            path.unlink(missing_ok=True)
