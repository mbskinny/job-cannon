"""Logged interactions (emails, calls, interviews, notes) and their follow-ups."""

import sqlite3
from datetime import datetime

KINDS = ["email", "call", "interview", "meeting", "note"]

_SELECT = """
    SELECT i.*, p.name AS contact_name, a.role AS application_role, c.name AS company_name
    FROM interactions i
    LEFT JOIN contacts p ON p.id = i.contact_id
    LEFT JOIN applications a ON a.id = i.application_id
    LEFT JOIN companies c ON c.id = a.company_id
"""


def local_now() -> str:
    """Local time in the format an HTML datetime-local input uses."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def _opt_id(value) -> int | None:
    return int(value) if value not in (None, "") else None


def create(
    conn,
    *,
    kind: str,
    summary: str,
    occurred_at: str | None = None,
    application_id=None,
    contact_id=None,
    follow_up_due: str | None = None,
) -> int:
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    application_id, contact_id = _opt_id(application_id), _opt_id(contact_id)
    if application_id is None and contact_id is None:
        raise ValueError("an interaction needs an application or a contact")
    with conn:
        return conn.execute(
            "INSERT INTO interactions"
            " (application_id, contact_id, kind, occurred_at, summary, follow_up_due)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                application_id,
                contact_id,
                kind,
                (occurred_at or "").strip() or local_now(),
                summary.strip(),
                (follow_up_due or "").strip() or None,
            ),
        ).lastrowid


def get(conn, interaction_id: int) -> sqlite3.Row | None:
    return conn.execute(_SELECT + " WHERE i.id = ?", (interaction_id,)).fetchone()


def for_application(conn, app_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        _SELECT + " WHERE i.application_id = ? ORDER BY i.occurred_at DESC", (app_id,)
    ).fetchall()


def for_contact(conn, contact_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        _SELECT + " WHERE i.contact_id = ? ORDER BY i.occurred_at DESC", (contact_id,)
    ).fetchall()


def recent(conn, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(_SELECT + " ORDER BY i.occurred_at DESC LIMIT ?", (limit,)).fetchall()


def set_follow_up_done(conn, interaction_id: int, done: bool = True) -> None:
    with conn:
        conn.execute(
            "UPDATE interactions SET follow_up_done = ? WHERE id = ?", (int(done), interaction_id)
        )


def delete(conn, interaction_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM interactions WHERE id = ?", (interaction_id,))
