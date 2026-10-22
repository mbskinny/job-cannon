import json
import re
import zipfile

import pytest
from fastapi.testclient import TestClient

from job_cannon import cli, profiles
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
