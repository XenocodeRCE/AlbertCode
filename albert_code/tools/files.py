"""
Outils de manipulation de fichiers : read_file, write_file, edit_file, list_files.
"""

import os
import fnmatch
import re
from pathlib import Path

from .base import make_function_tool

# ──────────────────────────────────────────────
#  Schémas OpenAI
# ──────────────────────────────────────────────

TOOL_SCHEMAS = [
    make_function_tool(
        name="read_file",
        description=(
            "Read the contents of a file at the given path. "
            "Use this to understand existing code before making changes. "
            "The path can be relative or absolute."
        ),
        properties={
            "path": {
                "type": "string",
                "description": (
                    "The file path to read (relative or absolute). "
                    "If the user gave an absolute path, use it exactly."
                ),
            },
            "start_line": {"type": "integer", "description": "Optional: start reading from this line (1-indexed)."},
            "end_line":   {"type": "integer", "description": "Optional: stop reading at this line (inclusive)."},
        },
        required=["path"],
    ),
    make_function_tool(
        name="write_file",
        description=(
            "Create a new file or completely overwrite an existing file with the given content. "
            "Use this for creating new files. For modifying existing files, prefer edit_file."
        ),
        properties={
            "path": {
                "type": "string",
                "description": (
                    "The file path to write to (relative or absolute). "
                    "If the user gave an absolute destination, use it exactly."
                ),
            },
            "content": {"type": "string", "description": "The complete content to write to the file."},
        },
        required=["path", "content"],
    ),
    make_function_tool(
        name="edit_file",
        description=(
            "Edit a file by replacing an exact text match with new text. "
            "You MUST read the file first to get the exact text to replace. "
            "old_text must match exactly (including whitespace and indentation)."
        ),
        properties={
            "path": {
                "type": "string",
                "description": (
                    "The file path to edit (relative or absolute). "
                    "If the user gave an absolute path, use it exactly."
                ),
            },
            "old_text": {"type": "string", "description": "The exact text to find and replace. Must match exactly."},
            "new_text": {"type": "string", "description": "The replacement text."},
        },
        required=["path", "old_text", "new_text"],
    ),
    make_function_tool(
        name="list_files",
        description=(
            "List files and directories at the given path. "
            "Use this to explore the project structure."
        ),
        properties={
            "path": {
                "type": "string",
                "description": (
                    "The directory path to list (default: current directory), relative or absolute. "
                    "If the user gave an absolute path, use it exactly."
                ),
            },
            "pattern":   {"type": "string",  "description": "Optional glob pattern to filter, e.g. '**/*.py'."},
            "max_depth": {"type": "integer", "description": "Maximum directory depth to recurse (default: 3)."},
        },
        required=[],
    ),
    make_function_tool(
        name="multi_edit_file",
        description=(
            "Apply multiple targeted replacements to a single file in one call. "
            "PREFER this over write_file when editing an existing file: it only touches "
            "the changed sections and wastes zero tokens on unchanged code. "
            "Each patch specifies an old_text (must match exactly) and its new_text. "
            "Patches are applied in order; earlier patches must not overlap later ones. "
            "You MUST read the file first to get exact old_text values."
        ),
        properties={
            "path": {
                "type": "string",
                "description": (
                    "The file path to edit (relative or absolute). "
                    "If the user gave an absolute path, use it exactly."
                ),
            },
            "patches": {
                "type": "array",
                "description": "Ordered list of replacements to apply.",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_text": {"type": "string", "description": "Exact text to replace (must match exactly, including whitespace)."},
                        "new_text": {"type": "string", "description": "Replacement text."},
                    },
                    "required": ["old_text", "new_text"],
                },
            },
        },
        required=["path", "patches"],
    ),
]

# ──────────────────────────────────────────────
#  Exécuteurs
# ──────────────────────────────────────────────

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", "dist", "build", ".next", ".mypy_cache",
}


def execute_read_file(args: dict) -> str:
    path  = args.get("path", "")
    start = args.get("start_line")
    end   = args.get("end_line")

    try:
        p = Path(path).resolve()
        if not p.exists():
            return f"❌ File not found: {path}"
        if not p.is_file():
            return f"❌ Not a file: {path}"
        if p.stat().st_size > 500_000:
            return (
                f"❌ File too large ({p.stat().st_size} bytes). "
                "Use start_line/end_line to read a portion."
            )

        content = p.read_text(encoding="utf-8", errors="replace")
        lines   = content.split("\n")

        if start or end:
            s        = max((start or 1) - 1, 0)
            e        = min(end or len(lines), len(lines))
            selected = lines[s:e]
            numbered = [f"{i + s + 1:4d} │ {line}" for i, line in enumerate(selected)]
            header   = f"[{path}] Lines {s + 1}-{e} of {len(lines)}"
        else:
            numbered = [f"{i + 1:4d} │ {line}" for i, line in enumerate(lines)]
            header   = f"[{path}] {len(lines)} lines"

        return header + "\n" + "\n".join(numbered)

    except Exception as exc:
        return f"❌ Error reading {path}: {exc}"


def execute_write_file(args: dict) -> str:
    path    = args.get("path", "")
    content = args.get("content", "")

    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists()
        p.write_text(content, encoding="utf-8")
        action = "Overwrote" if existed else "Created"
        lines  = content.count("\n") + 1
        return f"✅ {action} {path} ({lines} lines, {len(content)} chars)"
    except Exception as exc:
        return f"❌ Error writing {path}: {exc}"


def execute_edit_file(args: dict) -> str:
    path     = args.get("path", "")
    old_text = args.get("old_text", "")
    new_text = args.get("new_text", "")

    try:
        p = Path(path)
        if not p.exists():
            return f"❌ File not found: {path}"

        content = p.read_text(encoding="utf-8", errors="replace")

        if old_text not in content:
            # Essayer en normalisant les fins de ligne
            normalized     = content.replace("\r\n", "\n")
            old_normalized = old_text.replace("\r\n", "\n")
            if old_normalized in normalized:
                content  = normalized
                old_text = old_normalized
            else:
                old_lines  = old_text.strip().split("\n")
                first_line = old_lines[0].strip() if old_lines else ""
                candidates = [
                    (i + 1, line)
                    for i, line in enumerate(content.split("\n"))
                    if first_line and first_line in line
                ]
                hint = ""
                if candidates:
                    hint = "\nSimilar lines found:\n" + "\n".join(
                        f"  L{n}: {line}" for n, line in candidates[:5]
                    )
                return (
                    f"❌ old_text not found in {path}. "
                    f"Make sure it matches exactly (including whitespace).{hint}"
                )

        count = content.count(old_text)
        if count > 1:
            matches = list(re.finditer(re.escape(old_text), content))
            return (
                f"⚠️ old_text found {count} times in {path}. "
                "Please use a more specific match. Showing first 3 occurrences:\n"
                + "\n".join(f"  Occurrence at char {m.start()}" for m in matches[:3])
            )

        new_content = content.replace(old_text, new_text, 1)
        p.write_text(new_content, encoding="utf-8")

        old_lines = len(old_text.split("\n"))
        new_lines = len(new_text.split("\n"))
        return f"✅ Edited {path}: replaced {old_lines} lines with {new_lines} lines"

    except Exception as exc:
        return f"❌ Error editing {path}: {exc}"


def execute_list_files(args: dict) -> str:
    path            = args.get("path", ".")
    pattern         = args.get("pattern", "")
    max_depth       = args.get("max_depth", 3)
    ignore_patterns = args.get("_ignore_patterns", [])

    def _is_ignored(p: Path) -> bool:
        name = p.name
        rel  = str(p)
        return any(
            fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat)
            for pat in ignore_patterns
        )

    try:
        base = Path(path)
        if not base.exists():
            return f"❌ Path not found: {path}"

        if pattern:
            items = [i for i in sorted(base.glob(pattern)) if not _is_ignored(i)]
        else:
            items = []
            for root, dirs, files in os.walk(base):
                depth = Path(root).relative_to(base).parts
                if len(depth) >= max_depth:
                    dirs.clear()
                    continue
                dirs[:] = sorted([
                    d for d in dirs
                    if d not in _SKIP_DIRS
                    and not d.startswith(".")
                    and not _is_ignored(Path(root) / d)
                ])
                for d in dirs:
                    items.append(Path(root) / d)
                for f in sorted(files):
                    fp = Path(root) / f
                    if not f.startswith(".") and not _is_ignored(fp):
                        items.append(fp)

        if not items:
            return f"Empty directory or no matches: {path}"

        lines = []
        for item in items[:200]:
            try:
                rel = item.relative_to(base)
            except ValueError:
                rel = item
            if item.is_dir():
                lines.append(f"  📁 {rel}/")
            else:
                size = item.stat().st_size if item.exists() else 0
                if size > 1_000_000:
                    size_str = f"{size / 1_000_000:.1f}MB"
                elif size > 1000:
                    size_str = f"{size / 1000:.1f}KB"
                else:
                    size_str = f"{size}B"
                lines.append(f"  📄 {rel} ({size_str})")

        header = f"[{path}] {len(lines)} items"
        if len(items) > 200:
            header += " (showing first 200)"
        return header + "\n" + "\n".join(lines)

    except Exception as exc:
        return f"❌ Error listing: {exc}"


def execute_multi_edit_file(args: dict) -> str:
    """
    Applique une liste de patches (old_text → new_text) sur un seul fichier.

    Les patches sont appliqués dans l'ordre. Si un old_text est introuvable
    ou ambigu, la fonction s'arrête et signale l'erreur sans écrire le fichier
    (opération atomique : tout ou rien).
    """
    path    = args.get("path", "")
    patches = args.get("patches", [])

    if not patches:
        return "⚠️ multi_edit_file: aucun patch fourni."

    try:
        p = Path(path)
        if not p.exists():
            return f"❌ File not found: {path}"

        content = p.read_text(encoding="utf-8", errors="replace")
        applied: list[str] = []

        for i, patch in enumerate(patches):
            old_text = patch.get("old_text", "")
            new_text = patch.get("new_text", "")

            if not old_text:
                return f"❌ Patch #{i + 1}: old_text est vide."

            # Normalisation CRLF
            if old_text not in content:
                normalized     = content.replace("\r\n", "\n")
                old_normalized = old_text.replace("\r\n", "\n")
                if old_normalized in normalized:
                    content  = normalized
                    old_text = old_normalized
                else:
                    old_lines  = old_text.strip().split("\n")
                    first_line = old_lines[0].strip() if old_lines else ""
                    candidates = [
                        (j + 1, line)
                        for j, line in enumerate(content.split("\n"))
                        if first_line and first_line in line
                    ]
                    hint = ""
                    if candidates:
                        hint = "\nLignes similaires trouvées :\n" + "\n".join(
                            f"  L{n}: {line}" for n, line in candidates[:5]
                        )
                    return (
                        f"❌ Patch #{i + 1}: old_text introuvable dans {path}. "
                        f"Vérifiez les espaces/indentation.{hint}\n"
                        f"⚠️ Fichier NON modifié (opération annulée)."
                    )

            count = content.count(old_text)
            if count > 1:
                return (
                    f"❌ Patch #{i + 1}: old_text trouvé {count} fois dans {path}. "
                    f"Soyez plus spécifique.\n"
                    f"⚠️ Fichier NON modifié (opération annulée)."
                )

            content  = content.replace(old_text, new_text, 1)
            old_lines_n = len(old_text.split("\n"))
            new_lines_n = len(new_text.split("\n"))
            applied.append(f"  patch #{i + 1}: {old_lines_n} → {new_lines_n} lignes")

        p.write_text(content, encoding="utf-8")
        summary = "\n".join(applied)
        return f"✅ {path} modifié ({len(patches)} patch{'es' if len(patches) > 1 else ''}) :\n{summary}"

    except Exception as exc:
        return f"❌ Error in multi_edit_file: {exc}"
