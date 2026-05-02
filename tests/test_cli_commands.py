"""Tests des helpers de commandes CLI."""

from pathlib import Path

from albert_code.cli import _default_albert_md_content, _extract_command_arg, _normalize_path_input


def test_extract_command_arg_keeps_spaces():
    line = '/cd "C:/Users/Shadow/Documents/tictactoe game"'
    arg = _extract_command_arg(line, "/cd")
    assert arg == '"C:/Users/Shadow/Documents/tictactoe game"'


def test_normalize_path_input_strips_quotes():
    raw = '"C:/Users/Shadow/Documents/tictactoe game"'
    norm = _normalize_path_input(raw)
    assert norm == "C:/Users/Shadow/Documents/tictactoe game"


def test_default_albert_md_content_contains_sections():
    content = _default_albert_md_content(Path("C:/Users/Shadow/Documents/AlbertCode"))
    assert "# ALBERT.md" in content
    assert "## Objectif" in content
    assert "## Contraintes" in content
    assert "## Commandes utiles" in content
