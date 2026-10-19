import io
from datetime import date

import pytest

from job_cannon import db
from job_cannon.repo import applications, attachments, contacts, cover_letters, dashboard, interactions


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


def test_applied_on_set_when_moved_to_applied(conn):
    today = date.today().isoformat()
    created = applications.create(conn, "A", {"role": "r", "status": "applied"})
    edited = applications.create(conn, "B", {"role": "r"})
    dragged = applications.create(conn, "C", {"role": "r"})
    dated = applications.create(conn, "D", {"role": "r", "applied_on": "2026-01-02"})
    assert applications.get(conn, edited)["applied_on"] is None
    applications.update(conn, edited, {"status": "applied", "applied_on": ""})
    applications.reorder(conn, "applied", [dragged, dated])
    for app_id in (created, edited, dragged):
        assert applications.get(conn, app_id)["applied_on"] == today
    assert applications.get(conn, dated)["applied_on"] == "2026-01-02"
    # Clearing the date later, without a status change, sticks.
    applications.update(conn, edited, {"status": "applied", "applied_on": ""})
    assert applications.get(conn, edited)["applied_on"] is None


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


def test_placeholders_parse_names_and_multiline_instructions():
    body = "Hi {{recipient}},\n{{why_company: two sentences\n  on the product}} and {{ role }}."
    assert cover_letters.placeholders(body) == [
        ("recipient", ""), ("why_company", "two sentences on the product"), ("role", ""),
    ]
    assert cover_letters.unfilled(body + "{{recipient}}") == ["recipient", "why_company", "role"]


def test_fill_builtins_leaves_custom_placeholders(conn):
    app = applications.get(conn, applications.create(conn, "Acme", {"role": "Engineer"}))
    out = cover_letters.fill_builtins(
        "{{date}}: {{role}} at {{company}}. {{why: say why}}", app, today=date(2026, 10, 5)
    )
    assert out == "5 October 2026: Engineer at Acme. {{why: say why}}"


def test_template_names_unique_and_required(conn):
    cover_letters.create_template(conn, "Full-stack", "x")
    with pytest.raises(ValueError):
        cover_letters.create_template(conn, "full-stack", "y")
    with pytest.raises(ValueError):
        cover_letters.create_template(conn, " ", "y")


def test_draft_upsert_cascade_and_template_delete(conn):
    app_id = applications.create(conn, "Acme", {"role": "Engineer"})
    tpl = cover_letters.create_template(conn, "Base", "Dear {{company}},\r\n{{why}}")
    cover_letters.start_draft(conn, applications.get(conn, app_id), tpl)
    draft = cover_letters.get_draft(conn, app_id)
    assert draft["body"] == "Dear Acme,\n{{why}}" and draft["template_name"] == "Base"

    cover_letters.save_draft(conn, app_id, "Dear Acme,\nBecause.")
    draft = cover_letters.get_draft(conn, app_id)
    assert draft["body"] == "Dear Acme,\nBecause." and draft["template_id"] == tpl

    cover_letters.delete_template(conn, tpl)
    assert cover_letters.get_draft(conn, app_id)["template_id"] is None

    applications.delete(conn, app_id)
    assert cover_letters.get_draft(conn, app_id) is None


def test_letterhead_defaults_save_and_validation(conn):
    assert cover_letters.get_letterhead(conn)["name"] == ""
    assert cover_letters.get_letterhead(conn)["accent"] == cover_letters.DEFAULT_ACCENT
    cover_letters.save_letterhead(conn, {"name": " Ada ", "email": "a@b.c", "accent": "#AABBCC"})
    cover_letters.save_letterhead(conn, {"name": "Ada L", "accent": ""})
    lh = cover_letters.get_letterhead(conn)
    assert lh["name"] == "Ada L" and lh["email"] == "" and lh["accent"] == cover_letters.DEFAULT_ACCENT
    with pytest.raises(ValueError):
        cover_letters.save_letterhead(conn, {"accent": "red"})


def test_smarten_quotes_and_dashes():
    from job_cannon.pdf import smarten
    assert smarten("I'm \"here\" -- now") == "I’m “here” – now"
    assert smarten("teams' work - done") == "teams’ work – done"


def test_render_letter_with_full_letterhead():
    from job_cannon.pdf import render_letter
    lh = {"name": "Ada", "location": "Firenze", "email": "a@b.c", "phone": "+39 1",
          "website": "https://example.com/", "accent": "#336699"}
    assert render_letter("15 October 2026\n\nDear X,\n\nè €\n\nBest,\nAda", lh).startswith(b"%PDF")
    assert render_letter("No date here").startswith(b"%PDF")


def test_interest_level(conn):
    a = applications.create(conn, "Acme", {"role": "Eng", "interest": "4"})
    b = applications.create(conn, "Globex", {"role": "Eng"})
    c = applications.create(conn, "Initech", {"role": "Eng", "interest": 2})
    assert applications.get(conn, a)["interest"] == 4
    assert applications.get(conn, b)["interest"] is None
    assert [r["id"] for r in applications.list_applications(conn, sort="interest")] == [a, c, b]
    applications.update(conn, a, {"interest": ""})
    assert applications.get(conn, a)["interest"] is None
    for bad in ("0", "6", "high"):
        with pytest.raises(ValueError):
            applications.update(conn, b, {"interest": bad})


def test_prep_tags_parsed_and_filtered(conn):
    from job_cannon.repo import prep

    assert prep.parse_tags(" Behavioral,  team  work,behavioral,, ") == ["behavioral", "team work"]
    a = prep.create_question(conn, "Tell me about a conflict.", tags="behavioral, conflict")
    b = prep.create_question(conn, "Describe a system you built.", notes="the billing rewrite", tags=["experience"])
    prep.create_question(conn, "Tell me about yourself.", tags="intro")
    assert [r["id"] for r in prep.list_questions(conn, tags=["behavioral", "conflict"])] == [a]
    assert prep.list_questions(conn, tags=["behavioral", "intro"]) == []
    assert [r["id"] for r in prep.list_questions(conn, q="billing")] == [b]
    assert prep.get_question(conn, a)["tags"] == "behavioral,conflict"
    assert prep.random_question_id(conn, tags=["experience"]) == b
    with pytest.raises(ValueError):
        prep.create_question(conn, "  ")

    prep.update_question(conn, a, "Tell me about a conflict.", tags="behavioral")
    assert "conflict" not in [t["name"] for t in prep.list_tags(conn)]  # orphaned tag removed


def test_prep_answers_and_cleanup(conn):
    from job_cannon.repo import prep

    q = prep.create_question(conn, "Why us?")
    app_id = applications.create(conn, "Acme", {"role": "Engineer"})
    prep.add_text_answer(conn, q, "Because.", application_id=str(app_id))
    v = prep.add_voice_answer(conn, q, stored_name="abc.webm", mime="audio/webm", duration=12.5, status="pending")
    with pytest.raises(ValueError):
        prep.add_text_answer(conn, q, " ")
    assert [a["company_name"] for a in prep.answers_for_application(conn, app_id)] == ["Acme"]

    prep.fail_pending(conn)
    assert prep.get_answer(conn, v)["transcript_status"] == "failed"
    prep.set_transcript(conn, v, " hello there ")
    assert prep.get_answer(conn, v)["body"] == "hello there"

    applications.delete(conn, app_id)
    assert prep.answers_for_question(conn, q)[-1]["application_id"] is None  # answer kept, link cleared
    assert prep.delete_question(conn, q) == ["abc.webm"]
    assert prep.list_tags(conn) == []
