"""MCP server: a profile's applications and interview prep as tools for Claude.

Run with ``job-cannon mcp`` (needs the ``mcp`` extra); it talks MCP over stdio.
The profile is resolved on every call, the same way as the CLI (``--profile``,
then ``JOB_CANNON_PROFILE``, then the active one), so switching profiles in the
app is picked up without a restart, and every result names the profile it came
from. Each call opens its own connection and closes it, so the server can run
next to the app. It refuses to touch a database that newer code has migrated
(``db.check_schema``: this process is then older than the data, so ``/mcp`` must
reconnect it), and keeps hourly snapshots of it (``db.snapshot_if_due``). Writes only add rows (a question, an answer, a concept, a quiz question, a
question-concept link) through the ``repo`` functions; nothing here updates or deletes.
"""

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from job_cannon import agent_data, db, profiles
from job_cannon.config import Config
from job_cannon.repo import applications, prep

INSTRUCTIONS = """\
Job Cannon is the user's local job-search tracker: applications, and an
interview prep bank of questions with practice answers, plus concepts: short
explanations of a tool, method or idea that the user rehearses so they can
explain it quickly in any answer, quiz questions: multiple-choice questions
that test a concept, with the user's results, and experience notes: the user's own raw
notes about their work (jobs, projects, stories, numbers). Treat experience
notes as facts about the user alongside their résumé, and draw on them for
specifics when drafting answers. Every result names the
profile (several people can share one install); mention it if it isn't the
person you're helping. Prep answers with ai_draft=1 were written by an AI, not
the user: use them for content, but take the user's voice from their own
answers. When you save an answer you wrote, set ai_draft to true; set it to
false only when the text is essentially the user's own words. Ask the user
before saving anything."""

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
ADD = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


def build_server(data_dir: str | os.PathLike | None = None, profile: str | None = None) -> MCPServer:
    server = MCPServer("job-cannon", instructions=INSTRUCTIONS)

    @contextmanager
    def opened() -> Generator[tuple[str, Config, Any], None, None]:
        """(profile name, its Config, a migrated connection), closed afterwards."""
        try:
            root, p = profiles.resolve_profile(data_dir, profile)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        cfg = p.config(root)
        if not cfg.db_path.exists():
            raise ToolError(f"Profile {p.name} has no Job Cannon database yet ({cfg.db_path}).")
        conn = db.connect(cfg.db_path)
        try:
            try:
                db.check_schema(conn)
            except db.SchemaTooNew as exc:
                raise ToolError(str(exc)) from exc
            db.snapshot_if_due(conn, profiles.backup_dir(root, p) / "auto")
            db.migrate(conn)
            yield p.name, cfg, conn
        finally:
            conn.close()

    def question_or_error(conn, question_id: int):
        row = prep.get_question(conn, question_id)
        if row is None:
            raise ToolError(f"No prep question with id {question_id}.")
        return row

    def concept_or_error(conn, concept_id: int):
        row = prep.get_concept(conn, concept_id)
        if row is None:
            raise ToolError(f"No prep concept with id {concept_id}.")
        return row

    @server.tool(
        annotations=READ,
        description=(
            "List job applications, most recently updated first. "
            f"status: one of {', '.join(applications.STATUSES)}. "
            "search: matches role, company, location or notes. include_archived: also list archived applications."
        ),
    )
    def list_applications(status: str | None = None, search: str | None = None, include_archived: bool = False) -> dict[str, Any]:
        if status and status not in applications.STATUSES:
            raise ToolError(f"Unknown status {status!r}; use one of {', '.join(applications.STATUSES)}.")
        with opened() as (name, _cfg, conn):
            rows = applications.list_applications(
                conn, status=status or None, q=search or None, archived=None if include_archived else False,
            )
            return {"profile": name, "applications": [agent_data.application_summary(r) for r in rows]}

    @server.tool(annotations=READ)
    def get_application(application_id: int) -> dict[str, Any]:
        """Everything about one application: details and notes, company, contacts, interaction log,
        cover letter draft, attachments (with paths on disk), status history and linked prep answers."""
        with opened() as (name, cfg, conn):
            context = agent_data.application_context(conn, cfg, application_id)
            if context is None:
                raise ToolError(f"No application with id {application_id}.")
            return {"profile": name, **context}

    @server.tool(annotations=READ)
    def list_prep_questions(tags: list[str] | None = None, search: str | None = None) -> dict[str, Any]:
        """List interview prep questions with their tags. tags: only questions with all of these.
        search: matches the question text and notes. Use get_prep_question for notes and answers."""
        with opened() as (name, _cfg, conn):
            rows = prep.list_questions(conn, q=search or None, tags=prep.parse_tags(tags or []))
            return {"profile": name, "questions": [agent_data.question_summary(r) for r in rows]}

    @server.tool(annotations=READ)
    def get_prep_question(question_id: int) -> dict[str, Any]:
        """One interview prep question with its notes (talking points) and all its answers, newest first.
        Each answer says whether it's marked best, whether it's an AI draft, and which application it's for."""
        with opened() as (name, _cfg, conn):
            return {"profile": name, **agent_data.question_with_answers(conn, question_or_error(conn, question_id))}

    @server.tool(annotations=ADD)
    def save_prep_answer(question_id: int, text: str, ai_draft: bool, application_id: int | None = None) -> dict[str, Any]:
        """Add a typed answer to a prep question. ai_draft: true if you (an AI) wrote it, false only if it's
        essentially the user's own words. application_id: link it to an application. Ask the user first."""
        with opened() as (name, _cfg, conn):
            question = question_or_error(conn, question_id)
            if application_id is not None and applications.get(conn, application_id) is None:
                raise ToolError(f"No application with id {application_id}.")
            try:
                answer_id = prep.add_text_answer(conn, question_id, text, application_id, ai_draft=ai_draft)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
            return {
                "profile": name, "answer_id": answer_id, "question_id": question_id, "question": question["prompt"],
                "url": f"http://127.0.0.1:8765/prep/{question_id}#answer-{answer_id}",
            }

    @server.tool(annotations=ADD)
    def create_prep_question(
        prompt: str, notes: str = "", tags: list[str] | None = None, concept_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Add a question to the interview prep bank, worded generically ("Why do you want to work here?",
        not "Why Acme?"), with a few lowercase tags and optional notes (talking points). concept_ids: prep
        concepts that come up in it (see list_prep_concepts). If a question with the same wording exists,
        returns it unchanged instead (existing=true; use link_prep_concepts to link it). Ask the user first."""
        with opened() as (name, _cfg, conn):
            for concept_id in concept_ids or []:
                concept_or_error(conn, concept_id)
            wording = " ".join((prompt or "").split())
            same = [q for q in prep.list_questions(conn) if q["prompt"].casefold() == wording.casefold()]
            if same:
                question_id, existing = same[0]["id"], True
            else:
                try:
                    question_id, existing = prep.create_question(conn, wording, notes, tags or []), False
                except ValueError as exc:
                    raise ToolError(str(exc)) from exc
                for concept_id in concept_ids or []:
                    prep.link_concept(conn, question_id, concept_id)
            return {
                "profile": name, "question_id": question_id, "existing": existing,
                "url": f"http://127.0.0.1:8765/prep/{question_id}",
            }

    @server.tool(annotations=ADD)
    def link_prep_concepts(question_id: int, concept_ids: list[int]) -> dict[str, Any]:
        """Link prep concepts to a prep question, so the concepts show on the question's page and the
        question on each concept's page. Linking one that's already linked does nothing. Returns every
        concept now linked to the question, and which ids this call newly linked. Ask the user first."""
        with opened() as (name, _cfg, conn):
            question_or_error(conn, question_id)
            for concept_id in concept_ids:
                concept_or_error(conn, concept_id)
            before = {c["id"] for c in prep.concepts_for_question(conn, question_id)}
            for concept_id in concept_ids:
                prep.link_concept(conn, question_id, concept_id)
            concepts = prep.concepts_for_question(conn, question_id)
            return {
                "profile": name, "question_id": question_id,
                "newly_linked": [c["id"] for c in concepts if c["id"] not in before],
                "concepts": [{"id": c["id"], "name": c["name"]} for c in concepts],
                "url": f"http://127.0.0.1:8765/prep/{question_id}#concepts",
            }

    @server.tool(annotations=READ)
    def list_prep_concepts(search: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        """List interview prep concepts (short explanations of tools, methods or ideas the user rehearses),
        with their explanations and tags. search: matches the name, explanation and notes. tags: only
        concepts with all of these tags."""
        with opened() as (name, _cfg, conn):
            rows = prep.list_concepts(conn, q=search or None, tags=tags or [])
            return {"profile": name, "concepts": [agent_data.concept_summary(r) for r in rows]}

    @server.tool(annotations=READ)
    def get_prep_concept(concept_id: int) -> dict[str, Any]:
        """One interview prep concept with its explanation, notes and the questions it's linked to."""
        with opened() as (name, _cfg, conn):
            return {"profile": name, **agent_data.concept_with_questions(conn, concept_or_error(conn, concept_id))}

    @server.tool(annotations=ADD)
    def create_prep_concept(
        name: str, explanation: str, notes: str = "", question_ids: list[int] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Add a concept to interview prep: something the user needs to explain quickly (a tool, a method,
        a piece of their field), e.g. name "Benchling Analysis". explanation: the short version to rehearse
        and say from memory, about 30 seconds (~75 words) of plain spoken sentences. notes: optional details
        to draw on if asked more. question_ids: prep questions where it comes up. tags: a few short lowercase
        topics (reuse ones list_prep_concepts shows, e.g. "databases"). If a concept with the same
        name exists, returns it unchanged (existing=true). Ask the user first."""
        with opened() as (profile_name, _cfg, conn):
            for question_id in question_ids or []:
                question_or_error(conn, question_id)
            same = prep.find_concept(conn, name)
            if same:
                concept_id, existing = same["id"], True
            else:
                try:
                    concept_id = prep.create_concept(
                        conn, name, explanation, notes, question_ids=question_ids or [], tags=tags or [],
                    )
                except ValueError as exc:
                    raise ToolError(str(exc)) from exc
                existing = False
            return {
                "profile": profile_name, "concept_id": concept_id, "existing": existing,
                "url": f"http://127.0.0.1:8765/prep/concepts/{concept_id}",
            }

    @server.tool(annotations=READ)
    def list_quiz_questions(concept_id: int | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        """List the multiple-choice quiz questions on interview prep concepts, with their answers and the
        user's results (right_count, wrong_count, last_correct). concept_id: only that concept's.
        tags: only questions on concepts with all of these tags."""
        with opened() as (name, _cfg, conn):
            rows = prep.list_quiz_questions(conn, tags=tags or [], concept_id=concept_id)
            return {"profile": name, "quiz_questions": [agent_data.quiz_question_dict(r) for r in rows]}

    @server.tool(annotations=ADD)
    def create_quiz_question(
        concept_id: int, prompt: str, answer: str, wrong_answers: list[str], explanation: str, code: str = "",
    ) -> dict[str, Any]:
        """Add a multiple-choice quiz question that tests one prep concept (see list_prep_concepts).
        prompt: the question, testing understanding rather than recall of wording. answer: the correct
        option. wrong_answers: exactly 3 plausible wrong options, the mistakes of someone who half-knows the
        concept, about as long as the answer (options are shuffled). explanation: one or two sentences on
        why, shown after answering. code: an optional snippet shown under the question. Wrap code in
        backticks inside text. If the concept already has a question with the same prompt, returns it
        unchanged (existing=true). Ask the user first."""
        with opened() as (name, _cfg, conn):
            concept_or_error(conn, concept_id)
            same = prep.find_quiz_question(conn, concept_id, prompt)
            if same:
                question_id, existing = same["id"], True
            else:
                try:
                    question_id = prep.create_quiz_question(
                        conn, concept_id, prompt, answer, wrong_answers, explanation, code,
                    )
                except ValueError as exc:
                    raise ToolError(str(exc)) from exc
                existing = False
            return {
                "profile": name, "quiz_question_id": question_id, "existing": existing,
                "url": f"http://127.0.0.1:8765/prep/quiz?concept={concept_id}",
            }

    @server.tool(annotations=READ)
    def list_experience_notes(search: str | None = None) -> dict[str, Any]:
        """The user's experience notes: raw notes about their work history (jobs, projects, stories,
        tools, numbers), in full. They are facts about the user, written by them; use them for specifics
        when drafting answers. search: matches the title and body."""
        with opened() as (name, _cfg, conn):
            rows = prep.list_notes(conn, q=search or None)
            return {"profile": name, "notes": [agent_data.experience_note_dict(r) for r in rows]}

    @server.tool(annotations=ADD)
    def create_experience_note(title: str, body: str) -> dict[str, Any]:
        """Add an experience note: facts the user has told you about their work (a job, project or story),
        in their words, e.g. title "Lab technician at Acme (2021-23)". Only record what the user said;
        never invent. Ask the user first."""
        with opened() as (name, _cfg, conn):
            try:
                note_id = prep.create_note(conn, title, body)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
            return {"profile": name, "note_id": note_id, "url": f"http://127.0.0.1:8765/prep/experience/{note_id}"}

    return server


def run(data_dir: str | os.PathLike | None = None, profile: str | None = None) -> None:
    build_server(data_dir, profile).run("stdio")
