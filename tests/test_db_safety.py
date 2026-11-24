"""Stale processes must not write to a newer database, and databases get automatic snapshots."""

import asyncio
import sqlite3
from datetime import datetime, timedelta

import pytest

from job_cannon import db, profiles
from job_cannon.repo import prep


def _bump(conn, by=1):
    conn.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + by}")


def test_schema_version_is_the_newest_migration():
    assert db.SCHEMA_VERSION == db._migration_files()[-1][0]


def test_migrate_refuses_a_database_newer_than_the_code(conn):
    _bump(conn)
    with pytest.raises(db.SchemaTooNew, match="/mcp"):
        db.migrate(conn)
    with pytest.raises(db.SchemaTooNew):
        db.check_schema(conn)


def test_migrate_skips_migrations_added_after_the_process_started(tmp_path, monkeypatch):
    # A process started before migration N was written knows only N-1; it must not apply N.
    c = sqlite3.connect(tmp_path / "x.db")
    monkeypatch.setattr(db, "SCHEMA_VERSION", db.SCHEMA_VERSION - 1)
    assert db.migrate(c) == db.SCHEMA_VERSION
    monkeypatch.undo()
    assert db.migrate(c) == db.SCHEMA_VERSION


def test_web_app_answers_503_instead_of_writing(client, cfg):
    _bump(client.app.state.conns[client.app.state.active])
    for response in (client.get("/prep"), client.post("/prep", data={"prompt": "Why?"})):
        assert response.status_code == 503
        assert "schema version" in response.text
    c = db.connect(cfg.db_path)
    assert prep.list_questions(c) == []


def test_serve_refuses_to_start_on_a_newer_database(cfg, conn):
    from job_cannon import cli
    _bump(conn)
    conn.commit()
    with pytest.raises(SystemExit, match="git pull"):
        cli.main(["serve", "--no-browser", "--port", "0", "--data-dir", str(cfg.data_dir)])


def test_mcp_tool_errors_on_a_newer_database(cfg, conn):
    pytest.importorskip("mcp")
    from job_cannon import mcp_server
    _bump(conn)
    conn.commit()
    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError, match="/mcp"):
        asyncio.run(mcp_server.build_server(cfg.data_dir).call_tool("create_prep_question", {"prompt": "Why?"}))
    assert prep.list_questions(conn) == []


def test_snapshot_if_due_copies_and_waits_an_hour(conn, tmp_path):
    prep.create_question(conn, "Why us?")
    folder = tmp_path / "auto"
    t = datetime(2026, 11, 24, 12, 0, 0)
    first = db.snapshot_if_due(conn, folder, now=t)
    assert first is not None and first.name == "jobcannon-20261124-120000.db"
    copy = sqlite3.connect(first)
    assert copy.execute("SELECT prompt FROM prep_questions").fetchall() == [("Why us?",)]
    copy.close()
    assert db.snapshot_if_due(conn, folder, now=t + timedelta(minutes=59)) is None
    assert db.snapshot_if_due(conn, folder, now=t + timedelta(hours=1)) is not None
    assert not list(folder.glob(".*"))  # no partial files left behind


def test_snapshot_skips_a_brand_new_database(tmp_path):
    c = db.connect(tmp_path / "new.db")
    assert db.snapshot_if_due(c, tmp_path / "auto") is None


def test_prune_keeps_recent_and_one_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "SNAPSHOT_KEEP_RECENT", 3)
    monkeypatch.setattr(db, "SNAPSHOT_KEEP_DAYS", 2)
    folder = tmp_path / "auto"
    folder.mkdir()
    names = ["20261120-090000", "20261121-090000", "20261121-180000",
             "20261122-090000", "20261122-100000", "20261122-110000", "20261122-120000"]
    for n in names:
        (folder / f"jobcannon-{n}.db").touch()
    (folder / "notes.txt").touch()
    db.prune_snapshots(folder)
    left = sorted(f.name for f in folder.iterdir())
    # the 3 newest, plus the newest of the last 2 days (the 22nd is among the 3 newest)
    assert left == ["jobcannon-20261121-180000.db", "jobcannon-20261122-100000.db",
                    "jobcannon-20261122-110000.db", "jobcannon-20261122-120000.db", "notes.txt"]


def test_app_and_mcp_take_snapshots_beside_the_data_folder(cfg, conn):
    from fastapi.testclient import TestClient

    from job_cannon.web.app import create_app
    auto = profiles.backup_dir(cfg.data_dir, profiles.active(cfg.data_dir)) / "auto"
    assert auto == cfg.data_dir.parent / "data-backups" / "default" / "auto"
    with TestClient(create_app(cfg.data_dir)):
        pass
    assert len(list(auto.glob("jobcannon-*.db"))) == 1  # on opening the profile
    for f in auto.iterdir():
        f.unlink()
    with TestClient(create_app(cfg.data_dir)) as client:
        for f in auto.iterdir():
            f.unlink()
        client.get("/prep")
        assert not auto.exists() or not list(auto.iterdir())  # reads don't snapshot
        client.post("/prep", data={"prompt": "Why?"})
        assert len(list(auto.glob("jobcannon-*.db"))) == 1
    pytest.importorskip("mcp")
    from job_cannon import mcp_server
    for f in auto.iterdir():
        f.unlink()
    asyncio.run(mcp_server.build_server(cfg.data_dir).call_tool("list_prep_questions", {}))
    assert len(list(auto.glob("jobcannon-*.db"))) == 1
