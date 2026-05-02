"""
Package tools — agrège tous les outils disponibles pour l'agent.

Exports publics :
    TOOLS           — liste des schémas OpenAI (pour le corps de la requête API)
    TOOL_EXECUTORS  — dict {nom: fonction} pour l'exécution locale
    DANGEROUS_TOOLS — frozenset des outils nécessitant une confirmation
"""

from .base import DANGEROUS_TOOLS, make_function_tool  # noqa: F401
from .files import (
    TOOL_SCHEMAS as _FILE_SCHEMAS,
    execute_edit_file,
    execute_list_files,
    execute_multi_edit_file,
    execute_read_file,
    execute_write_file,
)
from .bash import TOOL_SCHEMA as _BASH_SCHEMA, execute_run_bash
from .search import TOOL_SCHEMA as _SEARCH_SCHEMA, execute_grep_search
from .git import (
    TOOL_SCHEMAS as _GIT_SCHEMAS,
    execute_git_diff,
    execute_git_log,
    execute_git_status,
)

# Liste ordonnée de tous les schémas envoyés à l'API
TOOLS: list[dict] = [*_FILE_SCHEMAS, _BASH_SCHEMA, _SEARCH_SCHEMA, *_GIT_SCHEMAS]

# Registre d'exécution local
TOOL_EXECUTORS: dict[str, object] = {
    "read_file":       execute_read_file,
    "write_file":      execute_write_file,
    "edit_file":       execute_edit_file,
    "multi_edit_file": execute_multi_edit_file,
    "list_files":      execute_list_files,
    "run_bash":        execute_run_bash,
    "grep_search":     execute_grep_search,
    "git_status":      execute_git_status,
    "git_diff":        execute_git_diff,
    "git_log":         execute_git_log,
}

__all__ = ["TOOLS", "TOOL_EXECUTORS", "DANGEROUS_TOOLS", "make_function_tool"]
