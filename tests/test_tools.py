"""Tests des outils (tools/)."""

import os
import tempfile
import sys
from pathlib import Path

import pytest

from albert_code.tools.files import (
    execute_edit_file,
    execute_list_files,
    execute_read_file,
    execute_write_file,
)
from albert_code.tools.bash import execute_run_bash
from albert_code.tools.search import execute_grep_search


# ── Fichiers ──────────────────────────────────────────────────────────────────

def test_write_and_read_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = "hello.txt"

    result = execute_write_file({"path": path, "content": "Hello\nWorld\n"})
    assert "Created" in result

    result = execute_read_file({"path": path})
    assert "Hello" in result
    assert "World" in result


def test_read_file_not_found():
    result = execute_read_file({"path": "/nonexistent/path/file.txt"})
    assert "❌" in result


def test_edit_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "sample.py"
    p.write_text("def foo():\n    return 1\n")

    result = execute_edit_file({
        "path": "sample.py",
        "old_text": "    return 1\n",
        "new_text": "    return 42\n",
    })
    assert "✅" in result
    assert "42" in p.read_text()


def test_edit_file_old_text_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "sample.py"
    p.write_text("def foo():\n    return 1\n")

    result = execute_edit_file({
        "path": "sample.py",
        "old_text": "THIS DOES NOT EXIST",
        "new_text": "anything",
    })
    assert "❌" in result


def test_list_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")

    result = execute_list_files({"path": "."})
    assert "a.py" in result
    assert "b.py" in result


# ── Bash ──────────────────────────────────────────────────────────────────────

def test_run_bash_echo():
    result = execute_run_bash({"command": "echo hello"})
    assert "hello" in result
    assert "[exit code: 0]" in result


def test_run_bash_timeout():
    result = execute_run_bash({"command": "python -c \"import time; time.sleep(10)\"", "timeout": 1})
    assert "timed out" in result.lower() or "❌" in result


def test_run_bash_non_interactive_stdin():
    result = execute_run_bash({"command": "python -c \"input()\"", "timeout": 3})
    assert "timed out" not in result.lower()
    assert "[exit code:" in result


def test_run_bash_pwd_windows_compat():
    if sys.platform != "win32":
        pytest.skip("Windows-specific command compatibility test")
    result = execute_run_bash({"command": "pwd", "timeout": 5})
    assert "[exit code: 0]" in result


# ── Recherche ─────────────────────────────────────────────────────────────────

def test_grep_search_finds_pattern(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "code.py").write_text("def main():\n    print('hello')\n")

    result = execute_grep_search({"pattern": "def main", "path": "."})
    assert "code.py" in result
    assert "def main" in result


def test_grep_search_no_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "code.py").write_text("def main(): pass\n")

    result = execute_grep_search({"pattern": "ZZZNOTFOUND", "path": "."})
    assert "No matches" in result
