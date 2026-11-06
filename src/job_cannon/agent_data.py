"""JSON-ready views of a profile's data for Claude: used by the MCP server and the skill scripts.

Each function takes an open connection (and the profile's ``Config`` where file
paths are needed) and returns plain dicts and lists. Nothing here writes.
"""

import sqlite3

from job_cannon.config import Config
from job_cannon.repo import applications, attachments, contacts, cover_letters, interactions, prep

ANSWER_FIELDS = [
    "id", "mode", "body", "best", "ai_draft", "application_id", "company_name", "application_role", "created_at",
]


def application_summary(row: sqlite3.Row) -> dict:
    """One line of the application list."""
    return {
        "id": row["id"],
        "company": row["company_name"],
        "role": row["role"],
        "status": row["status"],
        "location": row["location"],
        "applied_on": row["applied_on"],
        "next_action": row["next_action"],
        "next_action_due": row["next_action_due"],
        "archived": row["archived_at"] is not None,
    }


def application_context(conn, cfg: Config, app_id: int) -> dict | None:
    """Everything known about one application, or None if there's no such application."""
    app = applications.get(conn, app_id)
    if app is None:
        return None
    company = conn.execute("SELECT * FROM companies WHERE id = ?", (app["company_id"],)).fetchone()
    draft = cover_letters.get_draft(conn, app_id)
    return {
        "application": dict(app),
        "company": dict(company) if company else None,
        "contacts": [dict(r) for r in contacts.for_application(conn, app_id)],
        "interactions": [dict(r) for r in interactions.for_application(conn, app_id)],
        "cover_letter_draft": draft["body"] if draft else None,
        "attachments": [
            {
                "kind": a["kind"],
                "name": a["original_name"],
                "mime": a["mime"],
                "path": str(attachments.path_for(cfg.files_dir, a)),
            }
            for a in attachments.for_application(conn, app_id)
        ],
        "status_history": [dict(r) for r in applications.history(conn, app_id)],
        "prep_answers": [
            {"question_id": a["question_id"], "question": a["prompt"], **answer_dict(a)}
            for a in prep.answers_for_application(conn, app_id)
            if a["body"]
        ],
    }


def answer_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in ANSWER_FIELDS}


def question_summary(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "prompt": row["prompt"], "tags": row["tags"].split(",") if row["tags"] else []}


def question_with_answers(conn, row: sqlite3.Row) -> dict:
    """A prep question with its notes and every answer that has text (newest first).

    Answers still without text (a recording waiting for its transcript) are left out.
    """
    return {
        **question_summary(row),
        "notes": row["notes"],
        "answers": [answer_dict(a) for a in prep.answers_for_question(conn, row["id"]) if a["body"]],
    }
