"""The MCP server's tools, called through the server so argument schemas are exercised too."""

import asyncio

import pytest

pytest.importorskip("mcp")

from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from job_cannon import mcp_server, profiles  # noqa: E402
from job_cannon.repo import applications, prep  # noqa: E402


@pytest.fixture
def call(cfg, conn):
    server = mcp_server.build_server(cfg.data_dir)

    def _call(name, **arguments):
        result = asyncio.run(server.call_tool(name, arguments))
        assert not result.is_error, result.content
        return result.structured_content

    _call.server = server
    return _call


def test_tools_listed_with_read_only_hints(call):
    tools = {t.name: t for t in asyncio.run(call.server.list_tools())}
    assert set(tools) == {
        "list_applications", "get_application", "list_prep_questions", "get_prep_question",
        "save_prep_answer", "create_prep_question",
    }
    assert tools["get_prep_question"].annotations.read_only_hint is True
    assert tools["save_prep_answer"].annotations.read_only_hint is False
    assert "interviewing" in tools["list_applications"].description


def test_applications(call, conn):
    acme = applications.create(conn, "Acme", {"role": "Engineer", "status": "interviewing"})
    old = applications.create(conn, "Initech", {"role": "Tester"})
    applications.set_archived(conn, old, True)
    q = prep.create_question(conn, "Why us?")
    prep.add_text_answer(conn, q, "Rockets.", application_id=acme, ai_draft=True)

    out = call("list_applications")
    assert out["profile"] == "Default"
    assert [(a["company"], a["status"]) for a in out["applications"]] == [("Acme", "interviewing")]
    assert len(call("list_applications", include_archived=True)["applications"]) == 2
    assert call("list_applications", search="initech")["applications"] == []
    assert call("list_applications", status="offer")["applications"] == []
    with pytest.raises(ToolError, match="Unknown status"):
        asyncio.run(call.server.call_tool("list_applications", {"status": "hired"}))

    detail = call("get_application", application_id=acme)
    assert detail["application"]["role"] == "Engineer" and detail["company"]["name"] == "Acme"
    assert detail["prep_answers"][0]["question"] == "Why us?" and detail["prep_answers"][0]["ai_draft"] == 1
    with pytest.raises(ToolError, match="No application"):
        asyncio.run(call.server.call_tool("get_application", {"application_id": 999}))


def test_prep_questions_and_saving(call, conn):
    q = prep.create_question(conn, "Tell me about a conflict.", notes="the billing rewrite", tags="behavioral, conflict")
    prep.create_question(conn, "Tell me about yourself.", tags="intro")
    app_id = applications.create(conn, "Acme", {"role": "Engineer"})

    out = call("list_prep_questions", tags=["Behavioral"])
    assert out["questions"] == [{"id": q, "prompt": "Tell me about a conflict.", "tags": ["behavioral", "conflict"]}]
    assert len(call("list_prep_questions")["questions"]) == 2

    saved = call("save_prep_answer", question_id=q, text="  We talked it through.  ", ai_draft=True, application_id=app_id)
    assert saved["url"].endswith(f"/prep/{q}#answer-{saved['answer_id']}")
    mine = call("save_prep_answer", question_id=q, text="My words.", ai_draft=False)
    question = call("get_prep_question", question_id=q)
    assert question["notes"] == "the billing rewrite"
    assert [(a["id"], a["body"], a["ai_draft"], a["application_id"]) for a in question["answers"]] == [
        (mine["answer_id"], "My words.", 0, None),
        (saved["answer_id"], "We talked it through.", 1, app_id),
    ]

    for args, message in [
        ({"question_id": 999, "text": "x", "ai_draft": True}, "No prep question"),
        ({"question_id": q, "text": "x", "ai_draft": True, "application_id": 999}, "No application"),
        ({"question_id": q, "text": " ", "ai_draft": True}, "empty"),
    ]:
        with pytest.raises(ToolError, match=message):
            asyncio.run(call.server.call_tool("save_prep_answer", args))
    with pytest.raises(ToolError):  # ai_draft is required, so the caller has to decide
        asyncio.run(call.server.call_tool("save_prep_answer", {"question_id": q, "text": "x"}))


def test_create_prep_question_reuses_same_wording(call, conn):
    first = call("create_prep_question", prompt="Why  do you want to work here?", tags=["Motivation"])
    assert first["existing"] is False
    assert prep.get_question(conn, first["question_id"])["tags"] == "motivation"
    again = call("create_prep_question", prompt="why do you want to work here?")
    assert again == {**first, "existing": True}


def test_profile_resolved_on_each_call(call, cfg):
    other = profiles.create(cfg.data_dir, "Sam")
    assert call("list_prep_questions")["profile"] == "Default"
    profiles.set_active(cfg.data_dir, other.id)
    with pytest.raises(ToolError, match="no Job Cannon database"):
        asyncio.run(call.server.call_tool("list_prep_questions", {}))
