"""
Outil d'exécution de commandes shell : run_bash.
"""

import os
import subprocess
import sys

from .base import make_function_tool

# ──────────────────────────────────────────────
#  Schéma OpenAI
# ──────────────────────────────────────────────

TOOL_SCHEMA = make_function_tool(
    name="run_bash",
    description=(
        "Execute a non-interactive bash/shell command and return stdout and stderr. "
        "Use this for: running tests, installing packages, git operations, "
        "checking file existence, running scripts, etc. "
        "Commands run in the current working directory."
    ),
    properties={
        "command": {"type": "string",  "description": "The shell command to execute."},
        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)."},
    },
    required=["command"],
)

# ──────────────────────────────────────────────
#  Exécuteur
# ──────────────────────────────────────────────


def _normalize_windows_command(command: str) -> tuple[str, str | None]:
    """Mappe quelques commandes Unix vers équivalents cmd sur Windows."""
    raw = command.strip()
    low = raw.lower()
    if low == "pwd":
        return "cd", "pwd"
    return command, None


def execute_run_bash(args: dict) -> str:
    command = args.get("command", "")
    timeout = args.get("timeout", 30)

    try:
        normalized_from = None
        if sys.platform == "win32":
            run_command, normalized_from = _normalize_windows_command(command)
            result = subprocess.run(
                run_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd(),
                stdin=subprocess.DEVNULL,
                encoding="utf-8",
                errors="replace",
            )
        else:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd(),
                stdin=subprocess.DEVNULL,
                executable="/bin/bash",
            )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n--- stderr ---\n"
            output += result.stderr

        if not output.strip():
            output = "(no output)"

        max_chars = 10_000
        if len(output) > max_chars:
            output = output[:max_chars] + f"\n\n... (truncated, {len(output)} total chars)"

        prefix = ""
        if normalized_from:
            prefix = f"[normalized from: {normalized_from}]\n"

        return f"[exit code: {result.returncode}]\n{prefix}{output}"

    except subprocess.TimeoutExpired:
        return f"❌ Command timed out after {timeout}s: {command}"
    except Exception as exc:
        return f"❌ Error running command: {exc}"
