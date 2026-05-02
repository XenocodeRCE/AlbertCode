"""
Définitions partagées entre tous les modules de tools.

- DANGEROUS_TOOLS : outils qui modifient le système (nécessitent confirmation).
- make_function_tool() : helper pour construire un schéma OpenAI function-call.
"""

from __future__ import annotations
from typing import Any


# Outils qui nécessitent une confirmation utilisateur avant exécution
DANGEROUS_TOOLS: frozenset[str] = frozenset({"write_file", "edit_file", "multi_edit_file", "run_bash"})


def make_function_tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict:
    """Construit un outil au format OpenAI function-calling."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
