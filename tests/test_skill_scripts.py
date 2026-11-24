"""The skills' helper scripts, run as the skills run them (as a subprocess)."""

import json
import subprocess
import sys
from pathlib import Path

from job_cannon.repo import prep

SKILLS = Path(__file__).resolve().parent.parent / ".claude/skills"
AUDIT = SKILLS / "audit-quiz-questions/scripts/quiz_audit.py"
CONCEPT_AUDIT = SKILLS / "audit-concepts/scripts/concept_audit.py"


def run(cfg, *args, ok=True, script=AUDIT):
    result = subprocess.run(
        [sys.executable, str(script), "--data-dir", str(cfg.data_dir), *map(str, args)],
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
    assert json.loads(run(cfg, "list", "--older-than", "1").stdout)["due"] == 0
    assert json.loads(run(cfg, "list", "--tag", "ai", "--all").stdout)["due"] == 0

    concept_fix = tmp_path / "concept.json"
    concept_fix.write_text(json.dumps({"notes": "Better notes."}))
    run(cfg, "fix-concept", k, concept_fix, "--no-backup")
    concept = prep.get_concept(conn, k)
    assert (concept["explanation"], concept["notes"], concept["tags"]) == ("Log first.", "Better notes.", "databases")
    assert concept["checked_at"]

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"wrong_answers": ["x", "y"]}))
    assert "3 wrong" in run(cfg, "fix", q1, bad, "--no-backup", ok=False).stderr
    bad.write_text(json.dumps({"answr": "typo"}))
    assert "unknown field" in run(cfg, "fix", q1, bad, "--no-backup", ok=False).stderr
    assert "no quiz question" in run(cfg, "mark", 999, ok=False).stderr


def test_concept_audit_script(cfg, conn, tmp_path):
    run_c = lambda *a, ok=True: run(cfg, *a, ok=ok, script=CONCEPT_AUDIT)
    q = prep.create_question(conn, "How does Postgres stay consistent?")
    wal = prep.create_concept(conn, "WAL", "Log first.", "- notes", question_ids=[q], tags="databases")
    rag = prep.create_concept(conn, "RAG", "Retrieve, then generate.", tags="ai")
    z = prep.create_quiz_question(conn, wal, "When does COMMIT return?", "After the flush", ["a", "b", "c"])

    out = json.loads(run_c("list").stdout)
    assert (out["due"], out["total"]) == (2, 2)
    by_name = {c["name"]: c for c in out["concepts"]}
    assert by_name["WAL"]["interview_questions"] == ["How does Postgres stay consistent?"]
    assert by_name["WAL"]["quiz_questions"] == [{"id": z, "prompt": "When does COMMIT return?", "answer": "After the flush"}]
    assert by_name["WAL"]["notes"] == "- notes" and by_name["RAG"]["checked_at"] is None
    assert [c["name"] for c in json.loads(run_c("list", "--tag", "ai").stdout)["concepts"]] == ["RAG"]
    assert [c["name"] for c in json.loads(run_c("list", "--concept", wal).stdout)["concepts"]] == ["WAL"]

    changes = tmp_path / "fix.json"
    changes.write_text(json.dumps({"explanation": "Log first, flush on commit."}))
    run_c("fix", wal, changes, "--no-backup")
    concept = prep.get_concept(conn, wal)
    assert (concept["explanation"], concept["notes"], concept["tags"]) == ("Log first, flush on commit.", "- notes", "databases")
    assert concept["checked_at"]

    run_c("mark", rag)
    assert json.loads(run_c("list").stdout)["due"] == 0
    assert json.loads(run_c("list", "--all").stdout)["due"] == 2
    changes.write_text(json.dumps({"name": "x"}))
    assert "unknown field" in run_c("fix", wal, changes, "--no-backup", ok=False).stderr
    assert "no concept" in run_c("mark", 999, ok=False).stderr
