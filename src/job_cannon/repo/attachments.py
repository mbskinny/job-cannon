"""Files attached to applications, stored under ``<data-dir>/files``."""

import mimetypes
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import BinaryIO

from job_cannon.db import now

KINDS = ["resume", "cover_letter", "posting", "other"]
KIND_LABELS = {"resume": "Resume", "cover_letter": "Cover letter", "posting": "Job posting", "other": "Other"}


def save(
    conn,
    files_dir: Path,
    *,
    application_id: int,
    kind: str,
    original_name: str,
    stream: BinaryIO,
    mime: str | None = None,
) -> int:
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    original_name = Path(original_name or "file").name
    suffix = Path(original_name).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    files_dir.mkdir(parents=True, exist_ok=True)
    dest = files_dir / stored_name
    with dest.open("wb") as out:
        shutil.copyfileobj(stream, out)
    mime = mime or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    try:
        with conn:
            return conn.execute(
                "INSERT INTO attachments"
                " (application_id, kind, original_name, stored_name, mime, size, added_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (application_id, kind, original_name, stored_name, mime, dest.stat().st_size, now()),
            ).lastrowid
    except Exception:
        dest.unlink(missing_ok=True)
        raise


def get(conn, attachment_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()


def for_application(conn, app_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM attachments WHERE application_id = ? ORDER BY added_at DESC", (app_id,)
    ).fetchall()


def path_for(files_dir: Path, row: sqlite3.Row) -> Path:
    return files_dir / row["stored_name"]


def delete(conn, files_dir: Path, attachment_id: int) -> None:
    row = get(conn, attachment_id)
    if row is None:
        return
    with conn:
        conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    path_for(files_dir, row).unlink(missing_ok=True)


def remove_files(files_dir: Path, stored_names: list[str]) -> None:
    for name in stored_names:
        (files_dir / name).unlink(missing_ok=True)
