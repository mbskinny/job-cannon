import shlex
import sys
import time
from pathlib import Path

import pytest

from job_cannon import job_search_run, profiles
from job_cannon.repo import applications, search_runs

FAKE = Path(__file__).with_name("fake_claude.py")


@pytest.fixture
def fake_claude(monkeypatch, cfg):
    monkeypatch.setenv(job_search_run.COMMAND_ENV, shlex.join([sys.executable, str(FAKE)]))
    profiles.write_job_search(cfg.data_dir / profiles.JOB_SEARCH_FILE, "resume.pdf", "")
    return monkeypatch


def _wait(client, run_id):
    for _ in range(100):
        page = client.get(f"/find-jobs/runs/{run_id}", headers={"HX-Request": "true"})
        if "every 3s" not in page.text:
            return page
        time.sleep(0.1)
    raise AssertionError("search never finished")


def _start(client, **data):
    resp = client.post("/find-jobs", data={"job_count": "3", "focus": "", **data}, follow_redirects=False)
    assert resp.status_code == 303, resp.text
    return int(resp.headers["location"].rsplit("/", 1)[1])


def test_search_runs_and_lists_added_jobs(client, fake_claude, conn):
    applications.create(conn, "Old Co", {"role": "Earlier"})
    run_id = _start(client, focus="remote")
    page = _wait(client, run_id)
    assert "Done" in page.text and "Added Fake Co - Tester." in page.text
    assert "Fake Co — Tester" in page.text and "Old Co" not in page.text
    run = search_runs.get(conn, run_id)
    assert run["status"] == "done" and run["focus"] == "remote"
    assert search_runs.steps(run) == ["Reading your profile", "Searching LinkedIn jobs", "Adding jobs to your board"]
    assert "Last search" in client.get("/").text


def test_failed_search_shows_the_error(client, fake_claude):
    fake_claude.setenv("FAKE_CLAUDE_MODE", "fail")
    page = _wait(client, _start(client))
    assert "didn’t finish" in page.text and "Chrome extension not connected" in page.text


def test_one_search_at_a_time_and_stop(client, fake_claude, conn):
    fake_claude.setenv("FAKE_CLAUDE_MODE", "hang")
    run_id = _start(client)
    assert client.post("/find-jobs", data={"job_count": "3"}).status_code == 409
    assert "Stop the search" in client.get(f"/find-jobs/runs/{run_id}").text
    client.post(f"/find-jobs/runs/{run_id}/cancel")
    _wait(client, run_id)
    assert search_runs.get(conn, run_id)["status"] == "cancelled"


def test_needs_resume_and_claude(client, monkeypatch):
    monkeypatch.setenv(job_search_run.COMMAND_ENV, "")
    monkeypatch.setattr(job_search_run.shutil, "which", lambda _: None)
    page = client.get("/find-jobs").text
    assert "installed on this computer" in page and "Add your résumé first" in page and 'action="/find-jobs"' not in page
    assert client.post("/find-jobs", data={"job_count": "3"}).status_code == 422
    assert "Find new jobs" not in client.get("/").text


def test_invalid_count_is_refused(client, fake_claude):
    assert client.post("/find-jobs", data={"job_count": "50"}).status_code == 422


def test_args_pin_profile_and_limit_tools(cfg, tmp_path):
    run_dir = tmp_path / "run"
    args = job_search_run.build_args(["claude"], 4, "remote; rm -rf /", run_dir, cfg.data_dir, None)
    assert args[:2] == ["claude", "-p"] and "remote; rm -rf /" in args[2]
    tools = args[args.index("--allowedTools") + 1:]
    assert f"Write(/{run_dir}/**)" in tools and "Bash" not in tools and "Read" not in tools
    assert all(not t.startswith("Bash(") or t.startswith("Bash(uv run ") for t in tools)
    env = job_search_run.build_env(cfg.data_dir, "alice")
    assert env["JOB_CANNON_PROFILE"] == "alice" and env["JOB_CANNON_DATA"] == str(cfg.data_dir)


def test_fail_running_and_steps(conn):
    run_id = search_runs.start(conn, 2, "  part   time ")
    search_runs.add_step(conn, run_id, "Reading your résumé")
    search_runs.fail_running(conn)
    run = search_runs.get(conn, run_id)
    assert run["status"] == "failed" and run["focus"] == "part time"
    assert search_runs.steps(run) == ["Reading your résumé"]
    with pytest.raises(ValueError):
        search_runs.start(conn, 0)


def test_batched_browser_actions_and_notes_become_steps():
    event = {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Two good matches so far."},
        {"type": "tool_use", "name": "mcp__claude-in-chrome__browser_batch", "input": {"actions": [
            {"name": "navigate", "input": {"url": "https://www.linkedin.com/jobs/view/123/"}},
            {"name": "get_page_text", "input": {}},
        ]}},
    ]}}
    assert job_search_run.events_to_steps(event) == ["Two good matches so far.", "Reading a LinkedIn posting"]
