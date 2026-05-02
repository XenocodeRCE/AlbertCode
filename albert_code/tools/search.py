"""
Outil de recherche textuelle dans les fichiers : grep_search.
"""

import fnmatch
import re
from pathlib import Path

from .base import make_function_tool

# ──────────────────────────────────────────────
#  Schéma OpenAI
# ──────────────────────────────────────────────

TOOL_SCHEMA = make_function_tool(
    name="grep_search",
    description=(
        "Search for a text pattern in files. Returns matching lines with file paths and line numbers. "
        "Use this to find where something is defined, used, or imported."
    ),
    properties={
        "pattern": {"type": "string", "description": "The text or regex pattern to search for."},
        "path":    {"type": "string", "description": "Directory or file to search in (default: current directory)."},
        "include": {"type": "string", "description": "File pattern to include, e.g. '*.py' or '*.ts'."},
    },
    required=["pattern"],
)

# ──────────────────────────────────────────────
#  Exécuteur
# ──────────────────────────────────────────────

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", "dist", "build", ".next", ".mypy_cache",
}


def execute_grep_search(args: dict) -> str:
    pattern         = args.get("pattern", "")
    path            = args.get("path", ".")
    include         = args.get("include", "")
    ignore_patterns = args.get("_ignore_patterns", [])

    def _is_ignored(p: Path) -> bool:
        name = p.name
        rel  = str(p)
        return any(
            fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat)
            for pat in ignore_patterns
        )

    try:
        search_path = Path(path)
        if not search_path.exists():
            return f"❌ Path not found: {path}"

        if search_path.is_file():
            files: list[Path] = [search_path]
        else:
            files = list(search_path.rglob(include) if include else search_path.rglob("*"))

        # Filtrer les dossiers système, les fichiers cachés et les patterns ignorés
        filtered: list[Path] = []
        for f in files:
            if f.is_file() and not any(d in f.parts for d in _SKIP_DIRS) and not _is_ignored(f):
                filtered.append(f)
        files = filtered[:500]

        try:
            regex = re.compile(pattern)
        except re.error:
            regex = re.compile(re.escape(pattern))

        results: list[str] = []
        max_results = 50

        for filepath in files:
            try:
                text = filepath.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(text.split("\n"), 1):
                    if regex.search(line):
                        try:
                            rel = filepath.relative_to(Path(".").resolve())
                        except ValueError:
                            rel = filepath
                        results.append(f"  {rel}:{i}: {line.strip()}")
                        if len(results) >= max_results:
                            break
            except (OSError, UnicodeDecodeError):
                continue
            if len(results) >= max_results:
                break

        if not results:
            return f"No matches found for '{pattern}' in {path}"

        header = f"Found {len(results)} matches for '{pattern}':"
        if len(results) >= max_results:
            header += f" (showing first {max_results})"
        return header + "\n" + "\n".join(results)

    except Exception as exc:
        return f"❌ Error searching: {exc}"
