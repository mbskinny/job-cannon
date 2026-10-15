"""Cover letter templates (base letters with placeholders) and per-application drafts.

Placeholders are ``{{name}}`` or ``{{name: instruction for whoever fills it}}``.
``company``, ``role`` and ``date`` are filled automatically when a draft starts.
"""

import re
import sqlite3
from datetime import date

from job_cannon.db import now

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z0-9_]+)\s*(?::\s*(.*?))?\s*\}\}", re.DOTALL)
BUILTINS = ["company", "role", "date"]


def placeholders(body: str) -> list[tuple[str, str]]:
    """(name, instruction) for each placeholder, in order of appearance."""
    return [(m.group(1), " ".join((m.group(2) or "").split())) for m in PLACEHOLDER_RE.finditer(body)]


def unfilled(body: str) -> list[str]:
    """Distinct placeholder names still in ``body``."""
    return list(dict.fromkeys(name for name, _ in placeholders(body)))


def long_date(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def fill_builtins(body: str, app: sqlite3.Row, today: date | None = None) -> str:
    values = {
        "company": app["company_name"],
        "role": app["role"],
        "date": long_date(today or date.today()),
    }

    def sub(m: re.Match) -> str:
        return values.get(m.group(1), m.group(0))

    return PLACEHOLDER_RE.sub(sub, body)


# --- templates ---

def list_templates(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM cover_letter_templates ORDER BY name").fetchall()


def get_template(conn, template_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM cover_letter_templates WHERE id = ?", (template_id,)).fetchone()


def _clean_template(name: str, body: str) -> tuple[str, str]:
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    return name, (body or "").replace("\r\n", "\n")


def create_template(conn, name: str, body: str) -> int:
    name, body = _clean_template(name, body)
    try:
        with conn:
            return conn.execute(
                "INSERT INTO cover_letter_templates (name, body, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)",
                (name, body, now(), now()),
            ).lastrowid
    except sqlite3.IntegrityError:
        raise ValueError(f"a template named {name!r} already exists")


def update_template(conn, template_id: int, name: str, body: str) -> None:
    name, body = _clean_template(name, body)
    try:
        with conn:
            conn.execute(
                "UPDATE cover_letter_templates SET name = ?, body = ?, updated_at = ? WHERE id = ?",
                (name, body, now(), template_id),
            )
    except sqlite3.IntegrityError:
        raise ValueError(f"a template named {name!r} already exists")


def delete_template(conn, template_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM cover_letter_templates WHERE id = ?", (template_id,))


# --- drafts ---

def get_draft(conn, app_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT d.*, t.name AS template_name FROM cover_letters d"
        " LEFT JOIN cover_letter_templates t ON t.id = d.template_id"
        " WHERE d.application_id = ?",
        (app_id,),
    ).fetchone()


def save_draft(conn, app_id: int, body: str, template_id: int | None = None) -> None:
    """Create or replace the application's draft. ``template_id`` None keeps the current one."""
    body = (body or "").replace("\r\n", "\n")
    with conn:
        conn.execute(
            "INSERT INTO cover_letters (application_id, template_id, body, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (application_id) DO UPDATE SET body = excluded.body,"
            " template_id = COALESCE(excluded.template_id, template_id), updated_at = excluded.updated_at",
            (app_id, template_id, body, now(), now()),
        )


def start_draft(conn, app: sqlite3.Row, template_id: int) -> None:
    template = get_template(conn, template_id)
    if template is None:
        raise ValueError("choose a template")
    save_draft(conn, app["id"], fill_builtins(template["body"], app), template_id)


def delete_draft(conn, app_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM cover_letters WHERE application_id = ?", (app_id,))


# --- letterhead (single row of PDF settings) ---

LETTERHEAD_FIELDS = ["name", "location", "email", "phone", "website", "accent"]
DEFAULT_ACCENT = "#184078"
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")


def get_letterhead(conn) -> dict:
    row = conn.execute("SELECT * FROM letterhead WHERE id = 1").fetchone()
    if row is None:
        return {**{k: "" for k in LETTERHEAD_FIELDS}, "accent": DEFAULT_ACCENT}
    return {k: row[k] for k in LETTERHEAD_FIELDS}


def clean_letterhead(data: dict) -> dict:
    out = {k: (data.get(k) or "").strip() for k in LETTERHEAD_FIELDS}
    out["accent"] = out["accent"] or DEFAULT_ACCENT
    if not _HEX_RE.fullmatch(out["accent"]):
        raise ValueError("accent colour must look like #1a2b3c")
    out["accent"] = out["accent"].lower()
    return out


def save_letterhead(conn, data: dict) -> None:
    values = clean_letterhead(data)
    cols = ", ".join(LETTERHEAD_FIELDS)
    marks = ", ".join("?" for _ in LETTERHEAD_FIELDS)
    updates = ", ".join(f"{k} = excluded.{k}" for k in [*LETTERHEAD_FIELDS, "updated_at"])
    with conn:
        conn.execute(
            f"INSERT INTO letterhead (id, {cols}, updated_at) VALUES (1, {marks}, ?)"
            f" ON CONFLICT (id) DO UPDATE SET {updates}",
            [*values.values(), now()],
        )
