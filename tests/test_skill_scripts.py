"""The skills' helper scripts, run as the skills run them (as a subprocess)."""

import json
import subprocess
import sys
from pathlib import Path

from job_cannon.repo import prep

AUDIT = Path(__file__).resolve().parent.parent / ".claude/skills/audit-quiz-questions/scripts/quiz_audit.py"


def run(cfg, *args, ok=True):
    result = subprocess.run(
        [sys.executable, str(AUDIT), "--data-dir", str(cfg.data_dir), *map(str, args)],
        capture_output=True, text=True,
    )
    assert (result.returncode == 0) == ok, result.stderr
    return result


def test_quiz_audit_script(cfg, conn, tmp_path):
    k = prep.create_concept(conn, "WAL", "Log first.", "Some notes.", tags="databases")
    q1 = prep.create_quiz_question(conn, k, "When does COMMIT return?", "After the flush", ["a", "b", "c"], "Because.")
    q2 = prep.create_quiz_question(conn, k, "What is replayed?", "The WAL", ["d", "e", "f"])
    prep.record_quiz_answer(conn, q1, False)

    out = json.loads(run(cfg, "list").stdout)
    assert (out["due"], out["total"]) == (2, 2)
    assert out["concepts"][0]["explanation"] == "Log first." and out["concepts"][0]["notes"] == "Some notes."
    assert [q["wrong_answers"] for q in out["questions"]] == [["a", "b", "c"], ["d", "e", "f"]]

    changes = tmp_path / "fix.json"
    changes.write_text(json.dumps({"answer": "Once the WAL is flushed", "explanation": "Durability."}))
    run(cfg, "fix", q1, changes, "--no-backup")
    row = prep.get_quiz_question(conn, q1)
    assert (row["answer"], row["explanation"], row["prompt"], row["wrong_count"]) == (
        "Once the WAL is flushed", "Durability.", "When does COMMIT return?", 1)
    assert row["checked_at"]

    run(cfg, "mark", q2)
    assert json.loads(run(cfg, "list").stdout)["due"] == 0
    assert json.loads(run(cfg, "list", "--all").stdout)["due"] == 2
    assert json.loads(run(cfg, "list", "--older-than", "0").stdout)["due"] == 0
    assert json.loads(run(cfg, "list", "--tag", "ai", "--all").stdout)["due"] == 0

    concept_fix = tmp_path / "concept.json"
    concept_fix.write_text(json.dumps({"notes": "Better notes."}))
    run(cfg, "fix-concept", k, concept_fix, "--no-backup")
    concept = prep.get_concept(conn, k)
    assert (concept["explanation"], concept["notes"], concept["tags"]) == ("Log first.", "Better notes.", "databases")

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"wrong_answers": ["x", "y"]}))
    assert "3 wrong" in run(cfg, "fix", q1, bad, "--no-backup", ok=False).stderr
    bad.write_text(json.dumps({"answr": "typo"}))
    assert "unknown field" in run(cfg, "fix", q1, bad, "--no-backup", ok=False).stderr
    assert "no quiz question" in run(cfg, "mark", 999, ok=False).stderr
