import io
from datetime import date

import pytest

from job_cannon import db
from job_cannon.repo import applications, attachments, contacts, dashboard, interactions


def test_migrate_is_idempotent(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 1
    assert db.migrate(conn) == version


def test_create_reuses_company_case_insensitively(conn):
    a = applications.create(conn, "Acme", {"role": "Engineer"})
    b = applications.create(conn, "acme", {"role": "Staff Engineer"})
    assert applications.get(conn, a)["company_id"] == applications.get(conn, b)["company_id"]
    assert len(applications.list_companies(conn)) == 1


def test_create_requires_role_and_company(conn):
    with pytest.raises(ValueError):
        applications.create(conn, "Acme", {"role": " "})
    with pytest.raises(ValueError):
        applications.create(conn, "", {"role": "Engineer"})


def test_status_change_records_history(conn):
    app_id = applications.create(conn, "Acme", {"role": "Engineer"})
    applications.update(conn, app_id, {"status": "applied"})
    applications.update(conn, app_id, {"notes": "no status change"})
    hist = applications.history(conn, app_id)
    assert [(h["from_status"], h["to_status"]) for h in hist] == [("wishlist", "applied"), (None, "wishlist")]


def test_invalid_status_rejected(conn):
    app_id = applications.create(conn, "Acme", {"role": "Engineer"})
    with pytest.raises(ValueError):
        applications.update(conn, app_id, {"status": "hired!"})


def test_empty_dates_stored_as_null(conn):
    app_id = applications.create(conn, "Acme", {"role": "Eng", "applied_on": "", "next_action_due": ""})
    row = applications.get(conn, app_id)
    assert row["applied_on"] is None and row["next_action_due"] is None


def test_search_and_filter(conn):
    applications.create(conn, "Acme", {"role": "Backend Engineer", "location": "Remote"})
    applications.create(conn, "Globex", {"role": "Designer", "status": "applied"})
    assert [r["role"] for r in applications.list_applications(conn, q="remote")] == ["Backend Engineer"]
    assert [r["company_name"] for r in applications.list_applications(conn, status="applied")] == ["Globex"]


def test_reorder_moves_between_columns(conn):
    a = applications.create(conn, "A", {"role": "r"})
    b = applications.create(conn, "B", {"role": "r"})
    c = applications.create(conn, "C", {"role": "r", "status": "applied"})
    applications.reorder(conn, "applied", [b, c])
    board = applications.board(conn)
    assert [r["id"] for r in board["wishlist"]] == [a]
    assert [r["id"] for r in board["applied"]] == [b, c]
    assert applications.history(conn, b)[0]["to_status"] == "applied"
    applications.reorder(conn, "applied", [c, b])
    assert [r["id"] for r in applications.board(conn)["applied"]] == [c, b]


def test_contacts_link_and_unlink(conn):
    app_id = applications.create(conn, "Acme", {"role": "Eng"})
    pid = contacts.create(conn, {"name": "Dana Recruiter"}, company="Acme")
    contacts.link(conn, app_id, pid, "Recruiter")
    contacts.link(conn, app_id, pid, "Hiring manager")  # upsert, not duplicate
    linked = contacts.for_application(conn, app_id)
    assert len(linked) == 1 and linked[0]["link_role"] == "Hiring manager"
    assert contacts.applications_for(conn, pid)[0]["id"] == app_id
    contacts.unlink(conn, app_id, pid)
    assert contacts.for_application(conn, app_id) == []


def test_interaction_requires_target(conn):
    with pytest.raises(ValueError):
        interactions.create(conn, kind="note", summary="orphan")


def test_dashboard_follow_ups(conn):
    today = date(2026, 10, 14)
    a = applications.create(conn, "Acme", {"role": "Eng", "next_action": "Email", "next_action_due": "2026-10-10"})
    applications.create(conn, "Gone", {"role": "Eng", "status": "rejected", "next_action_due": "2026-10-01"})
    i = interactions.create(conn, kind="call", summary="Screen", application_id=a, follow_up_due="2026-10-14")
    interactions.create(conn, kind="email", summary="Later", application_id=a, follow_up_due="2026-10-18")
    interactions.create(conn, kind="email", summary="Far", application_id=a, follow_up_due="2026-12-01")

    fu = dashboard.follow_ups(conn, today)
    assert [f["what"] for f in fu["overdue"]] == ["Email"]  # rejected app excluded
    assert [f["interaction_id"] for f in fu["today"]] == [i]
    assert len(fu["upcoming"]) == 1

    interactions.set_follow_up_done(conn, i)
    assert dashboard.follow_ups(conn, today)["today"] == []


def test_attachment_round_trip_and_cascade_cleanup(conn, cfg):
    app_id = applications.create(conn, "Acme", {"role": "Eng"})
    att = attachments.save(
        conn, cfg.files_dir, application_id=app_id, kind="resume",
        original_name="../../resume.pdf", stream=io.BytesIO(b"%PDF-1.4 hi"),
    )
    row = attachments.get(conn, att)
    assert row["original_name"] == "resume.pdf"
    assert row["mime"] == "application/pdf"
    path = attachments.path_for(cfg.files_dir, row)
    assert path.read_bytes() == b"%PDF-1.4 hi"
    assert path.parent == cfg.files_dir

    stored = applications.delete(conn, app_id)
    attachments.remove_files(cfg.files_dir, stored)
    assert not path.exists()
    assert attachments.get(conn, att) is None
