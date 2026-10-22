import json
from pathlib import Path
import re
import zipfile

import pytest
from fastapi.testclient import TestClient

from job_cannon import cli, profiles
from job_cannon.repo import prep
from job_cannon.web.app import create_app


def _create_app(client, **fields):
    data = {"company": "Acme", "role": "Engineer", **fields}
    resp = client.post("/applications", data=data, follow_redirects=False)
    assert resp.status_code == 303
    return int(re.search(r"/applications/(\d+)$", resp.headers["location"]).group(1))


# --- registry -------------------------------------------------------------

def test_existing_data_folder_is_the_default_profile(cfg, conn):
    root = cfg.data_dir
    reg = profiles.load(root)
    assert [p.id for p in reg.profiles] == ["default"]
    assert reg.active_profile().config(root) == cfg
    assert not (root / profiles.REGISTRY).exists()  # reading never writes


def test_create_rename_delete(tmp_path):
    root = tmp_path / "jc"
    alex = profiles.create(root, "  Alex  Smith ")
    assert (alex.id, alex.name, alex.dir) == ("alex-smith", "Alex Smith", "profiles/alex-smith")
    assert alex.config(root).files_dir.is_dir()
    with pytest.raises(ValueError):
        profiles.create(root, "alex smith")
    with pytest.raises(ValueError):
        profiles.create(root, "   ")
    # Same slug, different name: the id is made unique.
    assert profiles.create(root, "Alex-Smith!").id == "alex-smith-2"

    assert profiles.rename(root, "alex-smith", "Alex").name == "Alex"
    assert profiles.get(root, "ALEX").id == "alex-smith"

    profiles.set_active(root, "alex")
    with pytest.raises(ValueError, match="main data folder"):
        profiles.delete(root, "default")
    with pytest.raises(ValueError, match="Switch to another"):
        profiles.delete(root, "alex")
    profiles.set_active(root, "default")
    profiles.delete(root, "alex")
    assert not alex.config(root).data_dir.exists()
    assert [p.id for p in profiles.load(root).profiles] == ["default", "alex-smith-2"]


def test_resolve_precedence(tmp_path, monkeypatch):
    root = tmp_path / "jc"
    profiles.create(root, "Alex")
    profiles.create(root, "Sam")
    profiles.set_active(root, "sam")
    monkeypatch.delenv(profiles.ENV_VAR, raising=False)
    assert profiles.resolve(root).data_dir.name == "sam"
    monkeypatch.setenv(profiles.ENV_VAR, "alex")
    assert profiles.resolve(root).data_dir.name == "alex"
    assert profiles.resolve(root, "default").data_dir == root.resolve()
    with pytest.raises(ValueError):
        profiles.resolve(root, "nobody")


# --- web ------------------------------------------------------------------

def test_profiles_keep_data_apart(client, cfg):
    _create_app(client, company="Acme")
    resp = client.post("/profiles", data={"name": "Alex"}, follow_redirects=False)
    assert resp.status_code == 303
    assert json.loads((cfg.data_dir / profiles.REGISTRY).read_text())["active"] == "alex"

    page = client.get("/applications").text
    assert "Acme" not in page and "Alex" in page
    _create_app(client, company="Globex")

    client.post("/profiles/default/switch", data={"next": "/applications"})
    page = client.get("/applications").text
    assert "Acme" in page and "Globex" not in page
    assert (cfg.data_dir / "profiles" / "alex" / "jobcannon.db").exists()


def test_switch_survives_restart(cfg):
    with TestClient(create_app(cfg.data_dir)) as c:
        c.post("/profiles", data={"name": "Alex"})
        _create_app(c, company="Globex")
    with TestClient(create_app(cfg.data_dir)) as c:
        assert "Globex" in c.get("/applications").text


def test_stale_tab_cannot_post_into_another_profile(client):
    app_id = _create_app(client)
    client.post("/profiles", data={"name": "Alex"})
    # Header (htmx, fetch) and query param (plain forms) both carry the page's profile.
    resp = client.post(f"/applications/{app_id}/archive", headers={"X-Job-Cannon-Profile": "default"})
    assert resp.status_code == 409 and "Alex" in resp.text
    resp = client.post("/applications?_profile=default", data={"company": "X", "role": "Y"})
    assert resp.status_code == 409
    resp = client.post("/applications?_profile=alex", data={"company": "X", "role": "Y"}, follow_redirects=False)
    assert resp.status_code == 303
    # Switching itself is always allowed from a stale page.
    resp = client.post("/profiles/default/switch?_profile=alex", follow_redirects=False)
    assert resp.status_code == 303


def test_pages_carry_the_profile(client):
    page = client.get("/").text
    assert 'data-profile="default"' in page and "Manage profiles" in page
    client.post("/profiles", data={"name": "Alex"})
    page = client.get("/board").text
    assert 'data-profile="alex"' in page and "· Alex · Job Cannon</title>" in page
    assert "Switch to Default" in page


def test_profile_form_errors(client):
    client.post("/profiles", data={"name": "Alex"})
    assert client.post("/profiles", data={"name": "alex"}).status_code == 422
    assert client.post("/profiles/alex/rename", data={"name": "Default"}).status_code == 422
    # Active profile, the root's own profile, and a missing confirmation are all refused.
    assert client.post("/profiles/alex/delete", data={"confirm": "Alex"}).status_code == 422
    client.post("/profiles/default/switch")
    assert client.post("/profiles/alex/delete", data={"confirm": "nope"}).status_code == 422
    assert client.post("/profiles/nobody/switch").status_code == 404
    resp = client.post("/profiles/alex/delete", data={"confirm": "alex"}, follow_redirects=False)
    assert resp.status_code == 303
    assert "Alex" not in client.get("/profiles").text


# --- CLI ------------------------------------------------------------------

def test_cli_profiles_and_backup(cfg, conn, tmp_path, capsys):
    root = cfg.data_dir
    alex = profiles.create(root, "Alex")
    cli.main(["--data-dir", str(root), "profiles", "use", "alex"])
    capsys.readouterr()

    cli.main(["--data-dir", str(root), "profiles", "--json"])
    info = json.loads(capsys.readouterr().out)
    assert info["id"] == "alex" and info["job_search_file"].endswith("profiles/alex/job-search.md")

    # Alex has no database yet, so --all only backs up the default profile.
    cli.main(["backup", "--all", "--out", str(tmp_path / "bk"), "--data-dir", str(root)])
    zips = sorted((tmp_path / "bk").glob("*.zip"))
    assert [z.name.split("-")[2] for z in zips] == ["default"]
    with zipfile.ZipFile(zips[0]) as zf:
        assert "jobcannon.db" in zf.namelist()

    with pytest.raises(SystemExit, match="No database"):
        cli.main(["--data-dir", str(root), "backup", "--profile", "alex", "--out", str(tmp_path / "bk")])
    with pytest.raises(SystemExit, match="No profile"):
        cli.main(["--data-dir", str(root), "--profile", "nobody", "profiles", "--json"])
    assert alex.config(root).data_dir.is_dir()


# --- sectors --------------------------------------------------------------

SECTOR_GUIDES = Path(__file__).resolve().parents[1] / ".claude" / "sectors"


def test_every_sector_has_a_guide():
    assert (SECTOR_GUIDES / "general.md").is_file()
    for key in profiles.SECTORS:
        assert (SECTOR_GUIDES / f"{key}.md").is_file(), key
    for key in prep.SECTOR_QUESTIONS:
        assert key in profiles.SECTORS, key


def test_sector_on_profiles(tmp_path):
    root = tmp_path / "jc"
    # A registry written before sectors existed still loads.
    root.mkdir()
    (root / profiles.REGISTRY).write_text(json.dumps(
        {"active": "default", "profiles": [{"id": "default", "name": "Default", "dir": "."}]}
    ))
    assert profiles.active(root).sector == ""
    assert profiles.active(root).sector_label == "General"

    alex = profiles.create(root, "Alex", "teaching")
    assert profiles.get(root, "alex").sector == "teaching" == alex.sector
    assert profiles.set_sector(root, "default", "software").sector_label == "Software engineering"
    assert profiles.set_sector(root, "default", "").sector == ""
    with pytest.raises(ValueError):
        profiles.set_sector(root, "alex", "astronaut")
    with pytest.raises(ValueError):
        profiles.create(root, "Sam", "astronaut")


def test_sector_web_and_cli(client, cfg, capsys):
    assert client.post("/profiles", data={"name": "Alex", "sector": "teaching"}).status_code == 200
    assert client.post("/profiles/default/sector", data={"sector": "software"}, follow_redirects=False).status_code == 303
    assert client.post("/profiles/default/sector", data={"sector": "nope"}).status_code == 422
    page = client.get("/profiles").text
    assert '<option value="teaching" selected>Teaching</option>' in page

    # Starter questions follow the active profile's sector (Alex, teaching).
    client.post("/prep/starter")
    page = client.get("/prep").text
    assert "disruptive class" in page and "production incident" not in page

    # A sector set from the CLI reaches the running app.
    cli.main(["--data-dir", str(cfg.data_dir), "profiles", "sector", "alex", "software"])
    cli.main(["--data-dir", str(cfg.data_dir), "profiles", "--json"])
    assert json.loads(capsys.readouterr().out.split("\n", 1)[1])["sector"] == "software"
    client.post("/prep/starter")
    assert "production incident" in client.get("/prep").text


# --- job-search notes and résumé ------------------------------------------

def _docx(path, *paragraphs):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", f'<w:document xmlns:w="x"><w:body>{body}</w:body></w:document>')
    return path


def test_job_search_round_trip(tmp_path):
    path = tmp_path / "job-search.md"
    assert profiles.read_job_search(path) == profiles.JobSearch()
    # The format written by hand before the editor existed.
    path.write_text(
        "# Job search profile\n\nRead by the skills.\n\n## Résumé\n\nhttps://example.com/cv\n\n"
        "## Notes\n\nRemote across Europe.\nNo agencies.\n\n## Targets\n\n- Acme\n"
    )
    js = profiles.read_job_search(path)
    assert (js.resume, js.notes) == ("https://example.com/cv", "Remote across Europe.\nNo agencies.")
    assert js.extra == "## Targets\n\n- Acme"

    profiles.write_job_search(path, " resume.pdf ", "Tuscany only.\r\n", js.extra)
    again = profiles.read_job_search(path)
    assert again == profiles.JobSearch("resume.pdf", "Tuscany only.", "## Targets\n\n- Acme")
    with pytest.raises(ValueError):
        profiles.write_job_search(path, "", "x\n## Sneaky heading")
    with pytest.raises(ValueError):
        profiles.write_job_search(path, "", "x" * (profiles.MAX_NOTES_CHARS + 1))


def test_resume_text_and_resolve(tmp_path):
    assert profiles.resume_text(_docx(tmp_path / "cv.docx", "Gixi Rossi", "Docente A022 &amp; sostegno")) == \
        "Gixi Rossi\nDocente A022 & sostegno"
    assert profiles.resolve_resume(tmp_path, "resume.pdf") == str(tmp_path.resolve() / "resume.pdf")
    assert profiles.resolve_resume(tmp_path, "HTTPS://example.com/cv") == "HTTPS://example.com/cv"
    assert profiles.resolve_resume(tmp_path, "  ") is None


def test_job_search_page(client, cfg):
    client.post("/profiles", data={"name": "Gixi", "sector": "teaching"})
    page = client.get("/profiles/gixi/job-search").text
    assert "classi di concorso" in page and "Job search notes" in page

    # Editing another (non-active) profile's notes only touches that folder.
    client.post("/profiles/default/switch")
    resp = client.post("/profiles/gixi/job-search", data={"resume": "https://example.com/cv", "notes": "Prato"},
                       follow_redirects=False)
    assert resp.status_code == 303
    gixi_dir = cfg.data_dir / "profiles" / "gixi"
    assert "Prato" in (gixi_dir / "job-search.md").read_text()
    assert not (cfg.data_dir / "job-search.md").exists()
    assert "Saved." in client.get("/profiles/gixi/job-search?saved=1").text
    assert client.post("/profiles/gixi/job-search", data={"notes": "x" * 60_000}).status_code == 422
    assert client.get("/profiles/nobody/job-search").status_code == 404


def test_resume_upload(client, cfg, tmp_path, capsys):
    root = cfg.data_dir
    client.post("/profiles/default/job-search", data={"resume": "", "notes": "Keep me"})
    resp = client.post("/profiles/default/resume", files={"file": ("My CV.pdf", b"%PDF-1.4 cv", "application/pdf")},
                       follow_redirects=False)
    assert resp.status_code == 303
    js = profiles.read_job_search(root / "job-search.md")
    assert (js.resume, js.notes) == ("resume.pdf", "Keep me")
    resp = client.get("/profiles/default/resume")
    assert resp.content == b"%PDF-1.4 cv" and resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["content-disposition"].startswith("inline")

    cli.main(["--data-dir", str(root), "profiles", "--json"])
    assert json.loads(capsys.readouterr().out)["resume"] == str((root / "resume.pdf").resolve())

    # A .docx replaces the PDF, and resume-text reads it.
    docx = _docx(tmp_path / "cv.docx", "Insegnante")
    client.post("/profiles/default/resume", files={"file": ("cv.docx", docx.read_bytes(), "application/octet-stream")})
    assert not (root / "resume.pdf").exists() and (root / "resume.docx").exists()
    cli.main(["--data-dir", str(root), "resume-text"])
    assert capsys.readouterr().out.strip() == "Insegnante"
    assert client.get("/profiles/default/resume").headers["content-disposition"].startswith("attachment")

    # Backups carry the notes and the résumé.
    zip_path = cli.backup(profiles.get(root, "default").config(root), tmp_path / "bk")
    with zipfile.ZipFile(zip_path) as zf:
        assert {"job-search.md", "resume.docx"} <= set(zf.namelist())

    assert client.post("/profiles/default/resume", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 422
    assert client.post("/profiles/default/resume", files={"file": ("empty.pdf", b"", "application/pdf")}).status_code == 422
    assert (root / "resume.docx").exists()  # a rejected upload keeps the old one

    client.post("/profiles/default/resume/delete")
    assert profiles.resume_file(root) is None
    assert profiles.read_job_search(root / "job-search.md") == profiles.JobSearch("", "Keep me")
    assert client.get("/profiles/default/resume").status_code == 404
