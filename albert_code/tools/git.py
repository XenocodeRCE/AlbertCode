"""
Outils git en lecture pour l'agent : git_status, git_diff, git_log.

Ces outils sont en lecture seule — ils ne modifient jamais le dépôt.
Les commits sont gérés séparément par git_autocommit.py.
"""

import subprocess
import sys
from pathlib import Path

from .base import make_function_tool

# ──────────────────────────────────────────────
#  Schémas OpenAI
# ──────────────────────────────────────────────

TOOL_SCHEMAS = [
    make_function_tool(
        name="git_status",
        description=(
            "Show the working tree status (modified, staged, untracked files). "
            "Use this to understand what has changed in the repository before or after edits."
        ),
        properties={},
        required=[],
    ),
    make_function_tool(
        name="git_diff",
        description=(
            "Show changes in the working tree or between commits. "
            "Use this to review exactly what was modified. "
            "Without arguments shows all unstaged changes. "
            "Pass a file path to diff a specific file. "
            "Pass 'staged' as path to see staged changes. "
            "Pass a commit ref (e.g. 'HEAD~1') to diff against a commit."
        ),
        properties={
            "path": {
                "type": "string",
                "description": (
                    "File path, 'staged' (for staged changes), "
                    "or a commit ref like 'HEAD~1'. Omit for all unstaged changes."
                ),
            },
            "stat": {
                "type": "boolean",
                "description": "If true, show a summary (--stat) instead of the full diff.",
            },
        },
        required=[],
    ),
    make_function_tool(
        name="git_log",
        description=(
            "Show the recent commit history. "
            "Use this to understand what was done recently, "
            "find a commit to revert, or get context on the project evolution."
        ),
        properties={
            "n": {
                "type": "integer",
                "description": "Number of commits to show (default: 10).",
            },
            "oneline": {
                "type": "boolean",
                "description": "If true, show one line per commit (default: true).",
            },
            "path": {
                "type": "string",
                "description": "Limit log to commits touching this file path.",
            },
        },
        required=[],
    ),
]

# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _run_git(*args: str, timeout: int = 15) -> tuple[int, str]:
    """Exécute une commande git, retourne (returncode, output)."""
    cmd = ["git", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout
        if result.stderr:
            output = (output + "\n" + result.stderr).strip()
        return result.returncode, output.strip()
    except FileNotFoundError:
        return -1, "❌ git n'est pas installé ou introuvable dans le PATH."
    except subprocess.TimeoutExpired:
        return -1, f"❌ Commande git timeout après {timeout}s."
    except Exception as exc:
        return -1, f"❌ Erreur git : {exc}"


def is_git_repo() -> bool:
    """Retourne True si le répertoire courant est dans un dépôt git."""
    rc, _ = _run_git("rev-parse", "--is-inside-work-tree")
    return rc == 0


# ──────────────────────────────────────────────
#  Exécuteurs
# ──────────────────────────────────────────────

def execute_git_status(_args: dict) -> str:
    rc, out = _run_git("status", "--short", "--branch")
    if rc != 0:
        return out or "❌ git status a échoué."
    return out or "(working tree clean)"


def execute_git_diff(args: dict) -> str:
    path   = args.get("path", "")
    stat   = args.get("stat", False)

    cmd_args = ["diff"]
    if stat:
        cmd_args.append("--stat")

    if path == "staged":
        cmd_args.append("--staged")
    elif path:
        # Peut être un chemin ou un ref de commit (HEAD~1, abc123…)
        cmd_args.append(path)

    rc, out = _run_git(*cmd_args)
    if rc != 0:
        return out or "❌ git diff a échoué."

    if not out:
        return "(aucun changement)"

    # Limiter la taille
    max_chars = 12_000
    if len(out) > max_chars:
        out = out[:max_chars] + f"\n… (tronqué, {len(out)} caractères au total)"
    return out


def execute_git_log(args: dict) -> str:
    n       = args.get("n", 10)
    oneline = args.get("oneline", True)
    path    = args.get("path", "")

    cmd_args = ["log", f"-{n}"]
    if oneline:
        cmd_args += ["--oneline", "--decorate"]
    else:
        cmd_args += ["--pretty=format:%h %ad %an: %s", "--date=short"]

    if path:
        cmd_args += ["--", path]

    rc, out = _run_git(*cmd_args)
    if rc != 0:
        return out or "❌ git log a échoué."
    return out or "(aucun commit)"
