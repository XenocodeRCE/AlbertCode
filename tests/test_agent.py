"""Tests de la boucle agent (AgentSession)."""

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from albert_code.agent import AgentSession
from albert_code.api import AlbertClient
from albert_code.skills import Skill


def _make_session(**kwargs) -> AgentSession:
    client = MagicMock(spec=AlbertClient)
    client.model = "test-model"
    client.total_requests = 0
    client.total_input_tokens = 0
    client.total_output_tokens = 0
    return AgentSession(client=client, auto_approve=True, **kwargs)


def test_initialize_sets_system_message():
    session = _make_session()
    session.initialize()
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "system"


def test_add_user_message():
    session = _make_session()
    session.initialize()
    session.add_user_message("hello")
    assert session.messages[-1] == {"role": "user", "content": "hello"}


def test_compact_history_no_op_when_short():
    session = _make_session()
    session.initialize()
    session.add_user_message("hi")
    before = list(session.messages)
    session.compact_history()
    assert session.messages == before


def test_compact_history_reduces_long_history(capsys):
    session = _make_session(verbosity=0)
    session.initialize()
    for i in range(30):
        session.messages.append({"role": "user", "content": f"msg {i}"})
        session.messages.append({"role": "assistant", "content": f"reply {i}"})
    session.compact_history()
    # Doit conserver : system (1) + résumé (1) + keep_recent=12 msgs => 14 max
    assert len(session.messages) <= 15


def test_run_returns_on_final_response():
    session = _make_session()
    session.initialize()
    session.add_user_message("bonjour")

    session.client.chat.return_value = {
        "choices": [{
            "message": {"role": "assistant", "content": "Bonjour !", "tool_calls": []},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    result = session.run()
    assert result == "Bonjour !"
    assert session.step_count == 1


def test_pinned_skill_is_used_even_without_keyword_match():
    session = _make_session()
    session.initialize()
    session.add_user_message("c'est quoi la justice ?")

    sk = Skill(
        name="explain-like-socrates",
        title="Explain Like Socrates",
        path=Path("."),
        skill_file=Path("SKILL.md"),
        summary="Ask questions first",
        content="# Explain Like Socrates\n\nAsk questions first.",
        keywords={"socrates", "questions"},
    )

    session.skill_registry.skills = [sk]
    session.pinned_skills = ["explain-like-socrates"]

    out = session._messages_with_active_skills()
    assert session.active_skills == ["explain-like-socrates"]
    assert any(m.get("role") == "system" and "Activated Skills" in m.get("content", "") for m in out)


def test_set_todo_from_plan_builds_checklist():
    session = _make_session()
    session.initialize()

    plan = """
1. Lire le projet
2. Identifier les bugs
3. Corriger les tests
[FIN DU PLAN]
"""
    n = session.set_todo_from_plan(plan)
    assert n == 3
    done, total = session.todo_counts()
    assert (done, total) == (0, 3)
    md = session.todo_markdown()
    assert "- [ ] Lire le projet" in md


def test_todo_progress_marks_next_item_done():
    session = _make_session()
    session.initialize()
    session.set_todo_from_plan("1. A\n2. B\n3. C")

    assert session.mark_next_todo_done() is True
    done, total = session.todo_counts()
    assert (done, total) == (1, 3)


def test_messages_include_todo_context_when_available():
    session = _make_session()
    session.initialize()
    session.add_user_message("continue")
    session.set_todo_from_plan("1. faire A\n2. faire B")

    msgs = session._messages_with_active_skills()
    assert any(m.get("role") == "system" and "## TODO" in m.get("content", "") for m in msgs)


def test_todo_persistence_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    s1 = _make_session(persist_todo=True)
    s1.initialize()
    s1.set_todo_from_plan("1. Etape A\n2. Etape B")
    ok, _ = s1.mark_todo_done(1)
    assert ok is True
    todo_file = tmp_path / ".albert-code.todo.md"
    assert todo_file.exists()

    s2 = _make_session(persist_todo=True)
    s2.initialize()
    assert len(s2.todo_items) == 2
    assert s2.todo_items[0]["done"] is True
    assert s2.todo_items[1]["done"] is False


def test_clear_todo_removes_persisted_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    session = _make_session(persist_todo=True)
    session.initialize()
    session.set_todo_from_plan("1. Nettoyer")
    todo_file = tmp_path / ".albert-code.todo.md"
    assert todo_file.exists()

    session.clear_todo()
    assert session.todo_items == []
    assert not todo_file.exists()
