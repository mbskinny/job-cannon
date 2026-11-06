"""MCP server: a profile's applications and interview prep as tools for Claude.

Run with ``job-cannon mcp`` (needs the ``mcp`` extra); it talks MCP over stdio.
The profile is resolved on every call, the same way as the CLI (``--profile``,
then ``JOB_CANNON_PROFILE``, then the active one), so switching profiles in the
app is picked up without a restart, and every result names the profile it came
from. Each call opens its own connection and closes it, so the server can run
next to the app. Writes only add rows (a question or an answer) through the
``repo`` functions; nothing here updates or deletes.
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
interview prep bank of questions with practice answers. Every result names the
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
            db.migrate(conn)
            yield p.name, cfg, conn
        finally:
            conn.close()

    def question_or_error(conn, question_id: int):
        row = prep.get_question(conn, question_id)
        if row is None:
            raise ToolError(f"No prep question with id {question_id}.")
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
    def create_prep_question(prompt: str, notes: str = "", tags: list[str] | None = None) -> dict[str, Any]:
        """Add a question to the interview prep bank, worded generically ("Why do you want to work here?",
        not "Why Acme?"), with a few lowercase tags and optional notes (talking points). If a question with
        the same wording exists, returns it instead (existing=true). Ask the user first."""
        with opened() as (name, _cfg, conn):
            wording = " ".join((prompt or "").split())
            same = [q for q in prep.list_questions(conn) if q["prompt"].casefold() == wording.casefold()]
            if same:
                question_id, existing = same[0]["id"], True
            else:
                try:
                    question_id, existing = prep.create_question(conn, wording, notes, tags or []), False
                except ValueError as exc:
                    raise ToolError(str(exc)) from exc
            return {
                "profile": name, "question_id": question_id, "existing": existing,
                "url": f"http://127.0.0.1:8765/prep/{question_id}",
            }

    return server


def run(data_dir: str | os.PathLike | None = None, profile: str | None = None) -> None:
    build_server(data_dir, profile).run("stdio")
