"""Contacts and their links to applications."""

import sqlite3

from job_cannon.repo.applications import get_or_create_company

FIELDS = ["name", "title", "email", "phone", "linkedin", "notes"]

_SELECT = """
    SELECT p.*, c.name AS company_name
    FROM contacts p LEFT JOIN companies c ON c.id = p.company_id
"""


def _clean(data: dict) -> dict:
    return {k: (data[k] or "").strip() for k in FIELDS if k in data}


def _company_id(conn, company: str | None) -> int | None:
    company = (company or "").strip()
    return get_or_create_company(conn, company) if company else None


def list_contacts(conn, q: str | None = None) -> list[sqlite3.Row]:
    if q:
        return conn.execute(
            _SELECT + " WHERE p.name LIKE ? OR c.name LIKE ? OR p.title LIKE ? ORDER BY p.name",
            [f"%{q}%"] * 3,
        ).fetchall()
    return conn.execute(_SELECT + " ORDER BY p.name").fetchall()


def get(conn, contact_id: int) -> sqlite3.Row | None:
    return conn.execute(_SELECT + " WHERE p.id = ?", (contact_id,)).fetchone()


def create(conn, data: dict, company: str | None = None) -> int:
    fields = _clean(data)
    if not fields.get("name"):
        raise ValueError("name is required")
    with conn:
        fields["company_id"] = _company_id(conn, company)
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        return conn.execute(
            f"INSERT INTO contacts ({cols}) VALUES ({marks})", list(fields.values())
        ).lastrowid


def update(conn, contact_id: int, data: dict, company: str | None = None) -> None:
    fields = _clean(data)
    if "name" in fields and not fields["name"]:
        raise ValueError("name is required")
    with conn:
        fields["company_id"] = _company_id(conn, company)
        assignments = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE contacts SET {assignments} WHERE id = ?", [*fields.values(), contact_id]
        )


def delete(conn, contact_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def link(conn, app_id: int, contact_id: int, role: str = "") -> None:
    with conn:
        conn.execute(
            "INSERT INTO application_contacts (application_id, contact_id, role) VALUES (?, ?, ?)"
            " ON CONFLICT (application_id, contact_id) DO UPDATE SET role = excluded.role",
            (app_id, contact_id, role.strip()),
        )


def unlink(conn, app_id: int, contact_id: int) -> None:
    with conn:
        conn.execute(
            "DELETE FROM application_contacts WHERE application_id = ? AND contact_id = ?",
            (app_id, contact_id),
        )


def for_application(conn, app_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT p.*, ac.role AS link_role, c.name AS company_name
        FROM application_contacts ac
        JOIN contacts p ON p.id = ac.contact_id
        LEFT JOIN companies c ON c.id = p.company_id
        WHERE ac.application_id = ?
        ORDER BY p.name
        """,
        (app_id,),
    ).fetchall()


def applications_for(conn, contact_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT a.id, a.role, a.status, c.name AS company_name, ac.role AS link_role
        FROM application_contacts ac
        JOIN applications a ON a.id = ac.application_id
        JOIN companies c ON c.id = a.company_id
        WHERE ac.contact_id = ?
        ORDER BY a.updated_at DESC
        """,
        (contact_id,),
    ).fetchall()
