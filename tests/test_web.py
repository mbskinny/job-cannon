import re
import shutil
import zipfile

from fastapi.testclient import TestClient

from job_cannon import cli
from job_cannon.web.app import create_app


def _create_app(client, **fields):
    data = {"company": "Acme", "role": "Engineer", **fields}
    resp = client.post("/applications", data=data, follow_redirects=False)
    assert resp.status_code == 303
    return int(re.search(r"/applications/(\d+)$", resp.headers["location"]).group(1))


def test_pages_render_empty(client):
    for path in ["/", "/board", "/applications", "/applications/new", "/contacts", "/contacts/new",
                 "/cover-letters", "/cover-letters/new", "/prep", "/prep/new"]:
        assert client.get(path).status_code == 200, path


def test_application_crud_flow(client):
    app_id = _create_app(client, posting_url="https://example.com/job")
    page = client.get(f"/applications/{app_id}")
    assert "Engineer" in page.text and "Acme" in page.text

    resp = client.post(f"/applications/{app_id}", data={"company": "Acme Corp", "role": "Senior Engineer", "status": "applied"})
    assert resp.status_code == 200
    page = client.get(f"/applications/{app_id}").text
    assert "Senior Engineer" in page and "Acme Corp" in page

    client.post(f"/applications/{app_id}/status", data={"status": "interviewing"})
    assert "Interviewing" in client.get("/board").text

    client.post(f"/applications/{app_id}/delete")
    assert client.get(f"/applications/{app_id}").status_code == 404


def test_validation_error_rerenders_form(client):
    resp = client.post("/applications", data={"company": "Acme", "role": ""})
    assert resp.status_code == 422
    assert "role is required" in resp.text


def test_htmx_search_returns_partial(client):
    _create_app(client, role="Data Scientist")
    resp = client.get("/applications?q=data", headers={"HX-Request": "true"})
    assert "Data Scientist" in resp.text
    assert "<html" not in resp.text


def test_board_reorder_endpoint(client):
    a = _create_app(client)
    b = _create_app(client, role="Other")
    resp = client.post("/board/reorder", data={"status": "screening", "ids": [str(b), str(a)]})
    assert resp.status_code == 204
    board = client.get("/board").text
    assert board.index(f'data-id="{b}"') < board.index(f'data-id="{a}"')
    assert client.post("/board/reorder", data={"status": "bogus", "ids": [str(a)]}).status_code == 400


def test_contacts_and_interactions(client):
    app_id = _create_app(client)
    client.post(f"/applications/{app_id}/contacts", data={"new_name": "Dana", "role": "Recruiter"})
    page = client.get(f"/applications/{app_id}").text
    assert "Dana" in page and "Recruiter" in page

    client.post("/interactions", data={
        "application_id": app_id, "kind": "call", "summary": "Phone screen went well",
        "follow_up_due": "2000-01-01", "next": f"/applications/{app_id}",
    })
    assert "Phone screen went well" in client.get(f"/applications/{app_id}").text
    assert "Overdue" in client.get("/").text


def test_dashboard_next_action_done(client):
    app_id = _create_app(client, next_action="Chase recruiter", next_action_due="2000-01-01")
    page = client.get("/").text
    assert "Chase recruiter" in page and f"/applications/{app_id}/next-action/done" in page

    resp = client.post(f"/applications/{app_id}/next-action/done", data={"next": "/"}, follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/"
    page = client.get("/").text
    assert "Overdue" not in page and "Done: Chase recruiter" in page
    assert "Done: Chase recruiter" in client.get(f"/applications/{app_id}").text

    # htmx follows the redirect and swaps the follow-ups list from the dashboard it lands on
    app_id = _create_app(client, next_action="Send portfolio", next_action_due="2000-01-01")
    resp = client.post(f"/applications/{app_id}/next-action/done", data={"next": "/"},
                       headers={"HX-Request": "true"})
    assert 'id="follow-ups"' in resp.text and 'id="recent-interactions"' in resp.text
    assert client.post("/applications/999/next-action/done").status_code == 404


def test_open_redirect_blocked(client):
    app_id = _create_app(client)
    resp = client.post("/interactions", data={
        "application_id": app_id, "kind": "note", "summary": "x", "next": "//evil.example",
    }, follow_redirects=False)
    assert resp.headers["location"] == "/"


def test_attachment_upload_download_delete(client, cfg):
    app_id = _create_app(client)
    client.post(
        f"/applications/{app_id}/attachments",
        data={"kind": "resume"},
        files={"file": ("resume.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    att_id = re.search(r'/attachments/(\d+)"', client.get(f"/applications/{app_id}").text).group(1)
    resp = client.get(f"/attachments/{att_id}")
    assert resp.content == b"%PDF-1.4 test"
    assert resp.headers["content-disposition"].startswith("inline")
    assert len(list(cfg.files_dir.iterdir())) == 1

    client.post(f"/attachments/{att_id}/delete")
    assert client.get(f"/attachments/{att_id}").status_code == 404
    assert list(cfg.files_dir.iterdir()) == []


def test_html_attachment_forced_to_download(client):
    app_id = _create_app(client)
    client.post(
        f"/applications/{app_id}/attachments",
        data={"kind": "posting"},
        files={"file": ("posting.html", b"<script>alert(1)</script>", "text/html")},
    )
    att_id = re.search(r'/attachments/(\d+)"', client.get(f"/applications/{app_id}").text).group(1)
    assert client.get(f"/attachments/{att_id}").headers["content-disposition"].startswith("attachment")


def test_cross_origin_post_refused(client):
    resp = client.post("/applications", data={"company": "A", "role": "B"},
                       headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403


def test_unknown_host_refused(client):
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400


def test_backup_and_portability(client, cfg, tmp_path):
    app_id = _create_app(client)
    client.post(
        f"/applications/{app_id}/attachments",
        data={"kind": "resume"},
        files={"file": ("cv.pdf", b"%PDF data", "application/pdf")},
    )

    (cfg.data_dir / "job-search.md").write_text("## Résumé\n\nhttps://example.com/cv\n")
    zip_path = cli.backup(cfg, tmp_path / "backups")
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "jobcannon.db" in names
        assert any(n.startswith("files/") for n in names)
        assert "example.com/cv" in zf.read("job-search.md").decode()
        moved = tmp_path / "other-machine"
        zf.extractall(moved)

    # Simulate opening the copied folder on another computer.
    with TestClient(create_app(moved)) as other:
        page = other.get(f"/applications/{app_id}").text
        assert "Engineer" in page and "cv.pdf" in page
        att_id = re.search(r'/attachments/(\d+)"', page).group(1)
        assert other.get(f"/attachments/{att_id}").content == b"%PDF data"

    # A plain folder copy works too.
    copied = tmp_path / "copied"
    shutil.copytree(cfg.data_dir, copied)
    with TestClient(create_app(copied)) as other:
        assert other.get(f"/applications/{app_id}").status_code == 200


def test_branding_assets_served(client):
    page = client.get("/").text
    assert 'href="/static/favicon.svg"' in page and 'class="logo-mark"' in page
    for path, ctype in [("/static/favicon.svg", "image/svg+xml"), ("/static/logo.svg", "image/svg+xml"),
                        ("/static/fonts/rokkitt-latin.woff2", "font/woff2"),
                        ("/static/fonts/source-sans-3-latin.woff2", "font/woff2")]:
        resp = client.get(path)
        assert resp.status_code == 200 and resp.headers["content-type"].startswith(ctype), path


def test_cover_letter_template_draft_and_attach(client, cfg):
    resp = client.post("/cover-letters", data={
        "name": "Base", "body": "Dear {{company}} team,\n\nI want the {{role}} job. {{why: why them}}",
    }, follow_redirects=False)
    assert resp.status_code == 303
    index = client.get("/cover-letters").text
    assert "Base" in index and "why" in index
    tpl_id = re.search(r'/cover-letters/(\d+)"', index).group(1)
    assert client.post("/cover-letters", data={"name": "base", "body": ""}).status_code == 422

    app_id = _create_app(client)
    client.post(f"/applications/{app_id}/cover-letter", data={"template_id": tpl_id})
    page = client.get(f"/applications/{app_id}").text
    assert "Dear Acme team" in page and "Engineer job" in page and "Unfilled" in page

    resp = client.post(f"/applications/{app_id}/cover-letter/attach")
    assert resp.status_code == 422 and "Fill these placeholders first: why" in resp.text

    body = "Dear Acme team,\n\nI want the Engineer job. Perché il caffè costa €2.\n\nBest,\nMe"
    resp = client.post(f"/applications/{app_id}/cover-letter/attach", data={"body": body}, follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"].endswith("#files")
    page = client.get(f"/applications/{app_id}").text
    assert "Cover letter - Acme - Engineer.pdf" in page and "Unfilled" not in page
    att_id = re.search(r'/attachments/(\d+)"', page).group(1)
    pdf = client.get(f"/attachments/{att_id}")
    assert pdf.content.startswith(b"%PDF") and pdf.headers["content-type"] == "application/pdf"

    client.post(f"/applications/{app_id}/cover-letter/delete")
    assert "Start draft" in client.get(f"/applications/{app_id}").text
    client.post(f"/cover-letters/{tpl_id}/delete")
    assert "No base letters yet" in client.get("/cover-letters").text


def test_save_base_letter_as_new(client):
    client.post("/cover-letters", data={"name": "Base", "body": "Original"})
    tpl_id = re.search(r'/cover-letters/(\d+)"', client.get("/cover-letters").text).group(1)
    assert "Save as new" in client.get(f"/cover-letters/{tpl_id}").text

    resp = client.post(f"/cover-letters/{tpl_id}/copy", data={"name": "base", "body": "Changed"})
    assert resp.status_code == 422 and "different name" in resp.text and "Changed" in resp.text

    resp = client.post(f"/cover-letters/{tpl_id}/copy", data={"name": "Variant", "body": "Changed"},
                       follow_redirects=False)
    assert resp.status_code == 303
    new_id = resp.headers["location"].rsplit("/", 1)[1]
    assert new_id != tpl_id and "Changed" in client.get(f"/cover-letters/{new_id}").text
    original = client.get(f"/cover-letters/{tpl_id}").text
    assert 'value="Base"' in original and "Original" in original and "Changed" not in original
    assert client.post("/cover-letters/999/copy", data={"name": "X", "body": ""}).status_code == 404


def test_letter_style_settings_and_previews(client):
    assert "PDF style" in client.get("/cover-letters").text
    resp = client.post("/cover-letters/style", data={"show_letterhead": "1", "accent": "#123456"}, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/cover-letters?saved=1").text
    assert "#123456" in page and "Saved." in page and "checked" in page
    resp = client.post("/cover-letters/style", data={"accent": "blue"})
    assert resp.status_code == 422 and "accent colour" in resp.text
    assert client.post("/cover-letters/style/preview", data={"accent": "blue"}).status_code == 400

    resp = client.post("/cover-letters/style/preview", data={"accent": "#123456"})
    assert resp.headers["content-type"] == "application/pdf" and resp.content.startswith(b"%PDF")

    app_id = _create_app(client)
    assert client.post(f"/applications/{app_id}/cover-letter/preview").status_code == 404
    resp = client.post(f"/applications/{app_id}/cover-letter/save", data={"body": "Hi {{x}}"})
    resp = client.post(f"/applications/{app_id}/cover-letter/preview", data={"body": "Dear {{who}},"})
    assert resp.content.startswith(b"%PDF") and resp.headers["x-content-type-options"] == "nosniff"
    assert "Dear {{who}}," in client.get(f"/applications/{app_id}").text


def test_draft_hints_when_contact_details_missing(client):
    app_id = _create_app(client)
    client.post(f"/applications/{app_id}/cover-letter/save", data={"body": "Hi"})
    assert "No contact details yet" in client.get(f"/applications/{app_id}").text
    client.post("/cover-letters/style", data={"accent": "#123456"})  # letterhead off: nothing to fill in
    assert "No contact details yet" not in client.get(f"/applications/{app_id}").text
    client.post("/cover-letters/style", data={"show_letterhead": "1", "accent": "#123456"})
    client.post("/profiles/default/contact", data={"name": "Ada"})
    page = client.get(f"/applications/{app_id}").text
    assert "No contact details yet" not in page
    assert "Ada" in client.get("/cover-letters").text


def test_interest_set_and_shown(client):
    app_id = _create_app(client, interest="3")
    assert 'aria-label="Interest 3 of 5"' in client.get(f"/applications/{app_id}").text
    client.post(f"/applications/{app_id}/interest", data={"interest": "5"})
    assert 'aria-label="Interest 5 of 5"' in client.get("/board").text
    assert client.post(f"/applications/{app_id}/interest", data={"interest": "9"}).status_code == 400
    assert client.get("/applications?sort=interest").status_code == 200


def test_archive_and_unarchive(client):
    app_id = _create_app(client, role="Closed Posting")
    resp = client.post(f"/applications/{app_id}/archive", follow_redirects=False)
    assert resp.status_code == 303
    assert "Unarchive" in client.get(f"/applications/{app_id}").text
    assert "Closed Posting" not in client.get("/applications").text
    assert "Closed Posting" not in client.get("/board").text
    assert "Closed Posting" in client.get("/applications?archived=1", headers={"HX-Request": "true"}).text

    client.post(f"/applications/{app_id}/unarchive")
    assert "Closed Posting" in client.get("/board").text
    assert "Closed Posting" not in client.get("/applications?archived=1", headers={"HX-Request": "true"}).text
    assert client.post("/applications/999/archive").status_code == 404


def test_cannon_game_asset(client):
    assert '<script src="/static/cannon-game.js"' in client.get("/").text
    resp = client.get("/static/cannon-game.js")
    assert resp.status_code == 200 and "QUESTIONS" in resp.text


def test_prep_question_bank_and_text_answer(client):
    assert "Add starter questions" in client.get("/prep").text
    client.post("/prep/starter")
    page = client.get("/prep").text
    assert "Tell me about yourself." in page and 'value="behavioral"' in page

    assert client.post("/prep", data={"prompt": " "}).status_code == 422
    resp = client.post("/prep", data={"prompt": "Why did you leave Initech?", "tags": "Motivation, initech"}, follow_redirects=False)
    q_id = int(re.search(r"/prep/(\d+)$", resp.headers["location"]).group(1))
    partial = client.get("/prep?tag=initech", headers={"HX-Request": "true"}).text
    assert "Initech" in partial and "Tell me about yourself" not in partial and "<html" not in partial
    assert client.get("/prep/random?tag=initech", follow_redirects=False).headers["location"] == f"/prep/{q_id}"

    app_id = _create_app(client)
    resp = client.post(f"/prep/{q_id}/answers", data={"body": "I wanted to grow.", "application_id": str(app_id)}, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get(f"/prep/{q_id}").text
    assert "I wanted to grow." in page and "4 words" in page and "~0:02 to say" in page
    assert "Why did you leave Initech?" in client.get(f"/applications/{app_id}").text
    assert client.post(f"/prep/{q_id}/answers", data={"body": ""}).status_code == 422

    client.post(f"/prep/{q_id}", data={"prompt": "Why leave Initech?", "tags": "motivation"})
    assert "Why leave Initech?" in client.get(f"/prep/{q_id}").text
    client.post(f"/prep/{q_id}/delete")
    assert client.get(f"/prep/{q_id}").status_code == 404


def test_prep_recorded_answer_transcribed(client, cfg, monkeypatch):
    from job_cannon import transcribe

    monkeypatch.setattr(transcribe, "available", lambda: True)
    monkeypatch.setattr(transcribe, "transcribe", lambda path: f"I am a fake transcript of {path.suffix}")
    resp = client.post("/prep", data={"prompt": "Tell me about yourself."}, follow_redirects=False)
    q_id = resp.headers["location"].rsplit("/", 1)[1]

    resp = client.post(f"/prep/{q_id}/answers/record", data={"duration": "30"},
                       files={"audio": ("answer.webm", b"\x1aE\xdf\xa3fake", "audio/webm;codecs=opus")})
    assert resp.status_code == 201 and "Transcribing" in resp.text
    answer_id = re.search(r'id="answer-(\d+)"', resp.text).group(1)
    assert len(list(cfg.files_dir.glob("*.webm"))) == 1

    partial = client.get(f"/prep/answers/{answer_id}").text  # background task has run
    assert "fake transcript of .webm" in partial and "every 2s" not in partial and "14 wpm" in partial
    audio = client.get(f"/prep/answers/{answer_id}/audio")
    assert audio.content.endswith(b"fake") and audio.headers["content-type"] == "audio/webm"
    assert audio.headers["x-content-type-options"] == "nosniff"

    bad = client.post(f"/prep/{q_id}/answers/record", files={"audio": ("x.html", b"<script>", "text/html")})
    assert bad.status_code == 400

    client.post(f"/prep/answers/{answer_id}/delete")
    assert list(cfg.files_dir.glob("*.webm")) == []


def test_prep_recording_kept_without_voice_extra(client, monkeypatch):
    from job_cannon import transcribe

    monkeypatch.setattr(transcribe, "available", lambda: False)
    q_id = client.post("/prep", data={"prompt": "Pitch"}, follow_redirects=False).headers["location"].rsplit("/", 1)[1]
    resp = client.post(f"/prep/{q_id}/answers/record", files={"audio": ("a.ogg", b"OggS", "audio/ogg")})
    assert resp.status_code == 201 and "uv sync --extra voice" in resp.text and "<audio" in resp.text


def test_port_check_ignores_connections_left_by_a_stopped_server():
    import socket

    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # as uvicorn does
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]
    assert not cli.port_free("127.0.0.1", port)  # something really is listening

    # A browser keeps its connection open; the server closes first and stops,
    # leaving its side of the connection in FIN-WAIT/TIME_WAIT on the port.
    client = socket.create_connection(("127.0.0.1", port))
    conn, _ = server.accept()
    conn.close()
    server.close()
    try:
        assert cli.port_free("127.0.0.1", port)
    finally:
        client.close()
