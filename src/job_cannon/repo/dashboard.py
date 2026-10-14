"""Queries behind the dashboard: what needs attention today."""

from datetime import date

from job_cannon.repo.applications import ACTIVE_STATUSES


def follow_ups(conn, today: date | None = None) -> dict[str, list[dict]]:
    """Open follow-ups split into overdue / today / upcoming (next 7 days)."""
    today_s = (today or date.today()).isoformat()
    active = ",".join("?" for _ in ACTIVE_STATUSES)
    items: list[dict] = []

    for row in conn.execute(
        f"""
        SELECT a.id, a.role, a.next_action, a.next_action_due, c.name AS company_name
        FROM applications a JOIN companies c ON c.id = a.company_id
        WHERE a.next_action_due IS NOT NULL AND a.status IN ({active})
        """,
        ACTIVE_STATUSES,
    ):
        items.append({
            "source": "application",
            "due": row["next_action_due"],
            "what": row["next_action"] or "Next action",
            "application_id": row["id"],
            "label": f"{row['company_name']} — {row['role']}",
        })

    for row in conn.execute(
        """
        SELECT i.id, i.summary, i.kind, i.follow_up_due, i.application_id, i.contact_id,
               p.name AS contact_name, a.role, c.name AS company_name
        FROM interactions i
        LEFT JOIN contacts p ON p.id = i.contact_id
        LEFT JOIN applications a ON a.id = i.application_id
        LEFT JOIN companies c ON c.id = a.company_id
        WHERE i.follow_up_due IS NOT NULL AND i.follow_up_done = 0
        """
    ):
        label = " — ".join(x for x in (row["company_name"], row["role"]) if x) or row["contact_name"]
        items.append({
            "source": "interaction",
            "interaction_id": row["id"],
            "due": row["follow_up_due"],
            "what": f"Follow up on {row['kind']}: {row['summary']}".rstrip(": "),
            "application_id": row["application_id"],
            "contact_id": row["contact_id"],
            "label": label or "",
        })

    items.sort(key=lambda i: i["due"])
    week_end = date.fromordinal((today or date.today()).toordinal() + 7).isoformat()
    return {
        "overdue": [i for i in items if i["due"] < today_s],
        "today": [i for i in items if i["due"] == today_s],
        "upcoming": [i for i in items if today_s < i["due"] <= week_end],
    }


def recent_status_changes(conn, limit: int = 10):
    return conn.execute(
        """
        SELECT h.*, a.role, c.name AS company_name
        FROM status_history h
        JOIN applications a ON a.id = h.application_id
        JOIN companies c ON c.id = a.company_id
        ORDER BY h.changed_at DESC, h.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
