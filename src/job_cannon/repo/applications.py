"""Applications and companies."""

import sqlite3
from datetime import date

from job_cannon.db import now

STATUSES = ["wishlist", "applied", "screening", "interviewing", "offer", "rejected", "withdrawn"]
STATUS_LABELS = {s: s.capitalize() for s in STATUSES}
ACTIVE_STATUSES = ["wishlist", "applied", "screening", "interviewing", "offer"]
INTEREST_LEVELS = [1, 2, 3, 4, 5]
INTEREST_LABELS = {1: "Low", 2: "Some", 3: "Interested", 4: "Keen", 5: "Dream job"}
SORTS = {"updated": "a.updated_at DESC", "interest": "a.interest IS NULL, a.interest DESC, a.updated_at DESC"}

FIELDS = [
    "role", "posting_url", "location", "salary_range", "status", "source",
    "applied_on", "next_action", "next_action_due", "notes", "interest",
]
DATE_FIELDS = {"applied_on", "next_action_due"}

_SELECT = """
    SELECT a.*, c.name AS company_name
    FROM applications a JOIN companies c ON c.id = a.company_id
"""


def _interest(value) -> int | None:
    """Parse an interest level; blank means unrated."""
    if value is None or str(value).strip() == "":
        return None
    try:
        level = int(str(value).strip())
    except ValueError:
        raise ValueError(f"interest must be 1-5: {value}") from None
    if level not in INTEREST_LEVELS:
        raise ValueError(f"interest must be 1-5: {value}")
    return level


def _clean(data: dict) -> dict:
    out = {}
    for key in FIELDS:
        if key not in data:
            continue
        if key == "interest":
            out[key] = _interest(data[key])
            continue
        value = (data[key] or "").strip()
        out[key] = (value or None) if key in DATE_FIELDS else value
    if out.get("status") == "":
        del out["status"]  # missing from the form: keep the current/default status
    if "status" in out and out["status"] not in STATUSES:
        raise ValueError(f"unknown status: {out['status']}")
    return out


def get_or_create_company(conn: sqlite3.Connection, name: str) -> int:
    name = name.strip()
    if not name:
        raise ValueError("company name is required")
    row = conn.execute("SELECT id FROM companies WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    return conn.execute("INSERT INTO companies (name) VALUES (?)", (name,)).lastrowid


def list_companies(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM companies ORDER BY name").fetchall()


def list_applications(
    conn, status: str | None = None, q: str | None = None, sort: str = "updated"
) -> list[sqlite3.Row]:
    where, params = [], []
    if status:
        where.append("a.status = ?")
        params.append(status)
    if q:
        where.append("(a.role LIKE ? OR c.name LIKE ? OR a.location LIKE ? OR a.notes LIKE ?)")
        params += [f"%{q}%"] * 4
    sql = _SELECT + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY " + SORTS.get(sort, SORTS["updated"])
    return conn.execute(sql, params).fetchall()


def get(conn, app_id: int) -> sqlite3.Row | None:
    return conn.execute(_SELECT + " WHERE a.id = ?", (app_id,)).fetchone()


def _next_position(conn, status: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM applications WHERE status = ?", (status,)
    ).fetchone()
    return row[0]


def _record_status(conn, app_id: int, from_status: str | None, to_status: str) -> None:
    conn.execute(
        "INSERT INTO status_history (application_id, from_status, to_status, changed_at)"
        " VALUES (?, ?, ?, ?)",
        (app_id, from_status, to_status, now()),
    )


def create(conn, company: str, data: dict) -> int:
    fields = _clean(data)
    if not fields.get("role"):
        raise ValueError("role is required")
    fields.setdefault("status", "wishlist")
    if fields["status"] == "applied" and not fields.get("applied_on"):
        fields["applied_on"] = date.today().isoformat()
    with conn:
        fields["company_id"] = get_or_create_company(conn, company)
        fields["position"] = _next_position(conn, fields["status"])
        fields["created_at"] = fields["updated_at"] = now()
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        app_id = conn.execute(
            f"INSERT INTO applications ({cols}) VALUES ({marks})", list(fields.values())
        ).lastrowid
        _record_status(conn, app_id, None, fields["status"])
    return app_id


def update(conn, app_id: int, data: dict, company: str | None = None) -> None:
    current = get(conn, app_id)
    if current is None:
        raise KeyError(app_id)
    fields = _clean(data)
    if "role" in fields and not fields["role"]:
        raise ValueError("role is required")
    with conn:
        if company is not None:
            fields["company_id"] = get_or_create_company(conn, company)
        new_status = fields.get("status")
        if new_status and new_status != current["status"]:
            fields["position"] = _next_position(conn, new_status)
            _record_status(conn, app_id, current["status"], new_status)
            if new_status == "applied" and not fields.get("applied_on", current["applied_on"]):
                fields["applied_on"] = date.today().isoformat()
        fields["updated_at"] = now()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE applications SET {assignments} WHERE id = ?", [*fields.values(), app_id]
        )


def reorder(conn, status: str, ordered_ids: list[int]) -> None:
    """Kanban drop: put ``ordered_ids`` into ``status`` in the given order."""
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    with conn:
        for position, app_id in enumerate(ordered_ids):
            row = conn.execute(
                "SELECT status, applied_on FROM applications WHERE id = ?", (app_id,)
            ).fetchone()
            if row is None:
                continue
            if row["status"] != status:
                _record_status(conn, app_id, row["status"], status)
                applied_on = row["applied_on"]
                if status == "applied" and not applied_on:
                    applied_on = date.today().isoformat()
                conn.execute(
                    "UPDATE applications SET status = ?, position = ?, applied_on = ?, updated_at = ?"
                    " WHERE id = ?",
                    (status, position, applied_on, now(), app_id),
                )
            else:
                conn.execute(
                    "UPDATE applications SET position = ? WHERE id = ?", (position, app_id)
                )


def delete(conn, app_id: int) -> list[str]:
    """Delete an application; returns stored attachment names for file cleanup."""
    with conn:
        stored = [
            r["stored_name"]
            for r in conn.execute(
                "SELECT stored_name FROM attachments WHERE application_id = ?", (app_id,)
            )
        ]
        conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    return stored


def board(conn) -> dict[str, list[sqlite3.Row]]:
    columns: dict[str, list[sqlite3.Row]] = {s: [] for s in STATUSES}
    for row in conn.execute(_SELECT + " ORDER BY a.position, a.id"):
        columns[row["status"]].append(row)
    return columns


def status_counts(conn) -> dict[str, int]:
    counts = {s: 0 for s in STATUSES}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM applications GROUP BY status"):
        counts[row["status"]] = row["n"]
    return counts


def history(conn, app_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM status_history WHERE application_id = ? ORDER BY changed_at DESC, id DESC",
        (app_id,),
    ).fetchall()
