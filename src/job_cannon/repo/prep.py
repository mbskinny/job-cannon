"""Interview prep: a tagged question bank, practice answers, and concepts.

Concepts are short explanations to rehearse (what a tool is, how a method
works) that can be linked to any number of questions.

Experience notes are free-form notes about the user's work history (jobs,
projects, stories, numbers), for Claude to draw on when drafting answers.

Answers are typed, or recorded in the browser. Recordings are stored under
``files/`` and transcribed locally (see ``job_cannon.transcribe``).
"""

import random
import sqlite3

from job_cannon.db import now

ANSWER_MODES = ["text", "voice"]
TRANSCRIPT_STATUSES = ["none", "pending", "done", "failed"]

# Asked in any field; SECTOR_QUESTIONS adds the ones for a profile's sector
# (keys are profiles.SECTORS keys).
STARTER_QUESTIONS = [
    ("Tell me about yourself.", ["intro", "pitch"]),
    ("Walk me through your résumé.", ["intro"]),
    ("Why are you looking for a new role?", ["intro", "motivation"]),
    ("Why do you want to work here?", ["motivation"]),
    ("What are you looking for in your next role?", ["motivation"]),
    ("Tell me about a time you disagreed with a teammate or manager. How did you resolve it?", ["behavioral", "conflict"]),
    ("Tell me about a project that failed or didn't go as planned. What did you learn?", ["behavioral", "failure"]),
    ("Describe a time you had to deliver under a tight deadline.", ["behavioral", "pressure"]),
    ("Tell me about a time you led a project or initiative without formal authority.", ["behavioral", "leadership"]),
    ("Give an example of a time you received difficult feedback. What did you do with it?", ["behavioral", "growth"]),
    ("What project are you most proud of, and why?", ["experience"]),
    ("Looking back at a past project, what would you do differently now?", ["experience", "growth"]),
]

SECTOR_QUESTIONS = {
    "software": [
        ("Describe the most complex system you've worked on. What was your part in it?", ["experience", "technical"]),
        ("Tell me about a hard technical decision you made. What trade-offs did you weigh?", ["experience", "technical"]),
        ("Tell me about a production incident or difficult bug you handled.", ["experience", "technical"]),
    ],
    "teaching": [
        ("How do you manage a disruptive class? Give a concrete example.", ["teaching", "classroom"]),
        ("How do you adapt a lesson for students with different abilities, including students with DSA or BES?", ["teaching", "inclusion"]),
        ("Describe a lesson that didn't work. What did you change?", ["teaching", "failure"]),
        ("How do you assess learning, beyond tests and marks?", ["teaching", "assessment"]),
        ("Tell me about a difficult conversation with a parent. How did you handle it?", ["teaching", "parents"]),
        ("How do you work with colleagues and the class council (consiglio di classe)?", ["teaching", "teamwork"]),
        ("How do you use technology in your teaching?", ["teaching", "methods"]),
        ("Walk me through how you would teach a topic from your subject to this age group.", ["teaching", "methods"]),
        ("Why do you want to teach at this school, and at this level?", ["teaching", "motivation"]),
    ],
}


def _opt_id(value) -> int | None:
    return int(value) if value not in (None, "") else None


def parse_tags(text: str | list[str] | None) -> list[str]:
    """Comma-separated text (or a list) to distinct, lowercase, tidy tag names."""
    parts = text if isinstance(text, list) else (text or "").split(",")
    tags = (" ".join(p.split()).lower() for p in parts)
    return list(dict.fromkeys(t for t in tags if t))


# --- questions ---

_QUESTION_SELECT = """
    SELECT q.*,
        (SELECT group_concat(name, ',') FROM (
            SELECT t.name FROM prep_question_tags qt JOIN prep_tags t ON t.id = qt.tag_id
            WHERE qt.question_id = q.id ORDER BY t.name)) AS tags,
        (SELECT count(*) FROM prep_answers a WHERE a.question_id = q.id) AS answer_count,
        (SELECT max(created_at) FROM prep_answers a WHERE a.question_id = q.id) AS last_practiced
    FROM prep_questions q
"""


def _filter(q: str | None, tags: list[str]) -> tuple[str, list]:
    where, params = [], []
    if q:
        where.append("(q.prompt LIKE ? OR q.notes LIKE ?)")
        params += [f"%{q}%"] * 2
    for tag in parse_tags(tags):
        where.append(
            "EXISTS (SELECT 1 FROM prep_question_tags qt JOIN prep_tags t ON t.id = qt.tag_id"
            " WHERE qt.question_id = q.id AND t.name = ?)"
        )
        params.append(tag)
    return (" WHERE " + " AND ".join(where) if where else ""), params


def list_questions(conn, q: str | None = None, tags: list[str] | None = None) -> list[sqlite3.Row]:
    """Questions matching the search text and *all* of ``tags``."""
    where, params = _filter(q, tags or [])
    return conn.execute(_QUESTION_SELECT + where + " ORDER BY q.created_at, q.id", params).fetchall()


def random_question_id(conn, q: str | None = None, tags: list[str] | None = None) -> int | None:
    where, params = _filter(q, tags or [])
    ids = [r[0] for r in conn.execute("SELECT q.id FROM prep_questions q" + where, params)]
    return random.choice(ids) if ids else None


def get_question(conn, question_id: int) -> sqlite3.Row | None:
    return conn.execute(_QUESTION_SELECT + " WHERE q.id = ?", (question_id,)).fetchone()


def list_tags(conn) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT t.name, count(qt.question_id) AS n FROM prep_tags t"
        " LEFT JOIN prep_question_tags qt ON qt.tag_id = t.id GROUP BY t.id ORDER BY t.name"
    ).fetchall()


def _clean_question(prompt: str, notes: str) -> tuple[str, str]:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("question is required")
    return prompt, (notes or "").replace("\r\n", "\n").strip()


def _set_tags(conn, question_id: int, tags: list[str]) -> None:
    """Replace a question's tags and drop tags no question uses any more. Call inside ``with conn``."""
    conn.execute("DELETE FROM prep_question_tags WHERE question_id = ?", (question_id,))
    for name in parse_tags(tags):
        conn.execute("INSERT OR IGNORE INTO prep_tags (name) VALUES (?)", (name,))
        conn.execute(
            "INSERT INTO prep_question_tags (question_id, tag_id)"
            " SELECT ?, id FROM prep_tags WHERE name = ?",
            (question_id, name),
        )
    conn.execute("DELETE FROM prep_tags WHERE id NOT IN (SELECT tag_id FROM prep_question_tags)")


def create_question(conn, prompt: str, notes: str = "", tags: str | list[str] | None = None) -> int:
    prompt, notes = _clean_question(prompt, notes)
    with conn:
        question_id = conn.execute(
            "INSERT INTO prep_questions (prompt, notes, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (prompt, notes, now(), now()),
        ).lastrowid
        _set_tags(conn, question_id, parse_tags(tags))
    return question_id


def update_question(conn, question_id: int, prompt: str, notes: str = "", tags: str | list[str] | None = None) -> None:
    prompt, notes = _clean_question(prompt, notes)
    with conn:
        conn.execute(
            "UPDATE prep_questions SET prompt = ?, notes = ?, updated_at = ? WHERE id = ?",
            (prompt, notes, now(), question_id),
        )
        _set_tags(conn, question_id, parse_tags(tags))


def delete_question(conn, question_id: int) -> list[str]:
    """Delete a question and its answers; returns stored audio names for file cleanup."""
    with conn:
        stored = [
            r[0]
            for r in conn.execute(
                "SELECT audio_stored_name FROM prep_answers"
                " WHERE question_id = ? AND audio_stored_name IS NOT NULL",
                (question_id,),
            )
        ]
        conn.execute("DELETE FROM prep_questions WHERE id = ?", (question_id,))
        conn.execute("DELETE FROM prep_tags WHERE id NOT IN (SELECT tag_id FROM prep_question_tags)")
    return stored


def add_starter_questions(conn, sector: str = "") -> int:
    """Add the general and ``sector`` starter questions not already in the bank; returns how many were added."""
    existing = {r[0].casefold() for r in conn.execute("SELECT prompt FROM prep_questions")}
    added = 0
    for prompt, tags in STARTER_QUESTIONS + SECTOR_QUESTIONS.get(sector, []):
        if prompt.casefold() not in existing:
            create_question(conn, prompt, tags=tags)
            added += 1
    return added


# --- answers ---

_ANSWER_SELECT = """
    SELECT a.*, q.prompt, ap.role AS application_role, c.name AS company_name
    FROM prep_answers a
    JOIN prep_questions q ON q.id = a.question_id
    LEFT JOIN applications ap ON ap.id = a.application_id
    LEFT JOIN companies c ON c.id = ap.company_id
"""


def get_answer(conn, answer_id: int) -> sqlite3.Row | None:
    return conn.execute(_ANSWER_SELECT + " WHERE a.id = ?", (answer_id,)).fetchone()


def answers_for_question(conn, question_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        _ANSWER_SELECT + " WHERE a.question_id = ? ORDER BY a.created_at DESC, a.id DESC", (question_id,)
    ).fetchall()


def answers_for_application(conn, app_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        _ANSWER_SELECT + " WHERE a.application_id = ? ORDER BY a.created_at DESC, a.id DESC", (app_id,)
    ).fetchall()


def add_text_answer(conn, question_id: int, body: str, application_id=None, ai_draft: bool = False) -> int:
    """Add a typed answer. ``ai_draft`` marks one written by an AI (e.g. Claude) rather than the user."""
    body = (body or "").replace("\r\n", "\n").strip()
    if not body:
        raise ValueError("the answer is empty")
    with conn:
        return conn.execute(
            "INSERT INTO prep_answers (question_id, application_id, mode, body, ai_draft, created_at, updated_at)"
            " VALUES (?, ?, 'text', ?, ?, ?, ?)",
            (question_id, _opt_id(application_id), body, int(bool(ai_draft)), now(), now()),
        ).lastrowid


def add_voice_answer(
    conn,
    question_id: int,
    *,
    stored_name: str,
    mime: str,
    duration: float | None = None,
    status: str = "none",
    application_id=None,
) -> int:
    if status not in TRANSCRIPT_STATUSES:
        raise ValueError(f"unknown transcript status: {status}")
    with conn:
        return conn.execute(
            "INSERT INTO prep_answers (question_id, application_id, mode, audio_stored_name, audio_mime,"
            " duration_seconds, transcript_status, created_at, updated_at)"
            " VALUES (?, ?, 'voice', ?, ?, ?, ?, ?, ?)",
            (question_id, _opt_id(application_id), stored_name, mime, duration, status, now(), now()),
        ).lastrowid


def set_transcript_status(conn, answer_id: int, status: str) -> None:
    if status not in TRANSCRIPT_STATUSES:
        raise ValueError(f"unknown transcript status: {status}")
    with conn:
        conn.execute(
            "UPDATE prep_answers SET transcript_status = ?, updated_at = ? WHERE id = ?",
            (status, now(), answer_id),
        )


def set_transcript(conn, answer_id: int, text: str) -> None:
    with conn:
        conn.execute(
            "UPDATE prep_answers SET body = ?, transcript_status = 'done', updated_at = ? WHERE id = ?",
            (text.strip(), now(), answer_id),
        )


def update_answer(conn, answer_id: int, body: str, application_id=None, ai_draft: bool | None = None) -> None:
    """Update an answer's text and application; ``ai_draft`` is left as it was when None."""
    with conn:
        conn.execute(
            "UPDATE prep_answers SET body = ?, application_id = ?, ai_draft = COALESCE(?, ai_draft), updated_at = ?"
            " WHERE id = ?",
            (
                (body or "").replace("\r\n", "\n").strip(), _opt_id(application_id),
                None if ai_draft is None else int(bool(ai_draft)), now(), answer_id,
            ),
        )


def toggle_best(conn, answer_id: int) -> None:
    with conn:
        conn.execute("UPDATE prep_answers SET best = 1 - best WHERE id = ?", (answer_id,))


def delete_answer(conn, answer_id: int) -> str | None:
    """Delete an answer; returns its stored audio name (if any) for file cleanup."""
    row = conn.execute("SELECT audio_stored_name FROM prep_answers WHERE id = ?", (answer_id,)).fetchone()
    with conn:
        conn.execute("DELETE FROM prep_answers WHERE id = ?", (answer_id,))
    return row[0] if row else None


# --- concepts ---

_CONCEPT_SELECT = """
    SELECT c.*, (SELECT count(*) FROM prep_question_concepts qc WHERE qc.concept_id = c.id) AS question_count
    FROM prep_concepts c
"""


def _concept_filter(q: str | None) -> tuple[str, list]:
    if not q:
        return "", []
    return " WHERE (c.name LIKE ? OR c.explanation LIKE ? OR c.notes LIKE ?)", [f"%{q}%"] * 3


def list_concepts(conn, q: str | None = None) -> list[sqlite3.Row]:
    where, params = _concept_filter(q)
    return conn.execute(_CONCEPT_SELECT + where + " ORDER BY c.name COLLATE NOCASE", params).fetchall()


def random_concept_id(conn, q: str | None = None) -> int | None:
    where, params = _concept_filter(q)
    ids = [r[0] for r in conn.execute("SELECT c.id FROM prep_concepts c" + where, params)]
    return random.choice(ids) if ids else None


def get_concept(conn, concept_id: int) -> sqlite3.Row | None:
    return conn.execute(_CONCEPT_SELECT + " WHERE c.id = ?", (concept_id,)).fetchone()


def find_concept(conn, name: str) -> sqlite3.Row | None:
    """The concept with this name, ignoring case and extra spaces."""
    return conn.execute(_CONCEPT_SELECT + " WHERE c.name = ?", (" ".join((name or "").split()),)).fetchone()


def _tidy(text: str | None) -> str:
    return (text or "").replace("\r\n", "\n").strip()


def _clean_concept(name: str, explanation: str, notes: str) -> tuple[str, str, str]:
    name = " ".join((name or "").split())
    if not name:
        raise ValueError("a name is required")
    return name, _tidy(explanation), _tidy(notes)


def create_concept(conn, name: str, explanation: str = "", notes: str = "", question_ids=()) -> int:
    name, explanation, notes = _clean_concept(name, explanation, notes)
    try:
        with conn:
            concept_id = conn.execute(
                "INSERT INTO prep_concepts (name, explanation, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (name, explanation, notes, now(), now()),
            ).lastrowid
            for question_id in question_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO prep_question_concepts (question_id, concept_id)"
                    " SELECT id, ? FROM prep_questions WHERE id = ?",
                    (concept_id, int(question_id)),
                )
    except sqlite3.IntegrityError:
        raise ValueError(f"there is already a concept called {name}") from None
    return concept_id


def update_concept(conn, concept_id: int, name: str, explanation: str = "", notes: str = "") -> None:
    name, explanation, notes = _clean_concept(name, explanation, notes)
    try:
        with conn:
            conn.execute(
                "UPDATE prep_concepts SET name = ?, explanation = ?, notes = ?, updated_at = ? WHERE id = ?",
                (name, explanation, notes, now(), concept_id),
            )
    except sqlite3.IntegrityError:
        raise ValueError(f"there is already a concept called {name}") from None


def delete_concept(conn, concept_id: int) -> None:
    """Delete a concept; the questions it was linked to are kept."""
    with conn:
        conn.execute("DELETE FROM prep_concepts WHERE id = ?", (concept_id,))


def link_concept(conn, question_id: int, concept_id: int) -> None:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO prep_question_concepts (question_id, concept_id) VALUES (?, ?)",
            (question_id, concept_id),
        )


def unlink_concept(conn, question_id: int, concept_id: int) -> None:
    with conn:
        conn.execute(
            "DELETE FROM prep_question_concepts WHERE question_id = ? AND concept_id = ?", (question_id, concept_id)
        )


def concepts_for_question(conn, question_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        _CONCEPT_SELECT + " JOIN prep_question_concepts l ON l.concept_id = c.id WHERE l.question_id = ?"
        " ORDER BY c.name COLLATE NOCASE",
        (question_id,),
    ).fetchall()


def questions_for_concept(conn, concept_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        _QUESTION_SELECT + " JOIN prep_question_concepts l ON l.question_id = q.id WHERE l.concept_id = ?"
        " ORDER BY q.created_at, q.id",
        (concept_id,),
    ).fetchall()


# --- experience notes ---


def _note_filter(q: str | None) -> tuple[str, list]:
    if not q:
        return "", []
    return " WHERE (title LIKE ? OR body LIKE ?)", [f"%{q}%"] * 2


def list_notes(conn, q: str | None = None) -> list[sqlite3.Row]:
    where, params = _note_filter(q)
    return conn.execute(
        "SELECT * FROM experience_notes" + where + " ORDER BY updated_at DESC, id DESC", params
    ).fetchall()


def get_note(conn, note_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM experience_notes WHERE id = ?", (note_id,)).fetchone()


def _clean_note(title: str, body: str) -> tuple[str, str]:
    title = " ".join((title or "").split())
    if not title:
        raise ValueError("a title is required")
    return title, _tidy(body)


def create_note(conn, title: str, body: str = "") -> int:
    title, body = _clean_note(title, body)
    with conn:
        return conn.execute(
            "INSERT INTO experience_notes (title, body, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (title, body, now(), now()),
        ).lastrowid


def update_note(conn, note_id: int, title: str, body: str = "") -> None:
    title, body = _clean_note(title, body)
    with conn:
        conn.execute(
            "UPDATE experience_notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
            (title, body, now(), note_id),
        )


def delete_note(conn, note_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM experience_notes WHERE id = ?", (note_id,))


def fail_pending(conn) -> None:
    """Transcriptions interrupted by a shutdown never finish; mark them so they can be retried."""
    with conn:
        conn.execute("UPDATE prep_answers SET transcript_status = 'failed' WHERE transcript_status = 'pending'")
