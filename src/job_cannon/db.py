"""SQLite connection handling and schema migrations.

Migrations are numbered SQL files in ``migrations/``; the applied version is
tracked with ``PRAGMA user_version``.
"""

import sqlite3
from datetime import datetime, timezone
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


def migrate(conn: sqlite3.Connection) -> int:
    """Apply any migrations newer than the database's user_version."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in _migration_files():
        if version <= current:
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
