"""
Auto-commit git après chaque action d'écriture de l'agent.

Chaque fichier modifié par write_file / edit_file / multi_edit_file
est immédiatement stagé et commité avec un message structuré.
Si le répertoire n'est pas un dépôt git, le module est silencieux.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import C

# Outils qui produisent un commit (écritures fichier, pas run_bash)
_COMMIT_TOOLS: frozenset[str] = frozenset({
    "write_file",
    "edit_file",
    "multi_edit_file",
})

# Préfixes de message selon l'outil
_VERB: dict[str, str] = {
    "write_file":      "create",
    "edit_file":       "edit",
    "multi_edit_file": "patch",
}


def _run(*args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", *args],
            capture_output=True, text=True,
            timeout=15, encoding="utf-8", errors="replace",
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as exc:
        return -1, str(exc)


def _in_git_repo() -> bool:
    rc, _ = _run("rev-parse", "--is-inside-work-tree")
    return rc == 0


def _configure_identity_if_needed() -> None:
    """Configure une identité git minimale si aucune n'existe (environnement CI)."""
    rc, _ = _run("config", "user.email")
    if rc != 0:
        _run("config", "user.email", "albert-code@local")
        _run("config", "user.name",  "Albert Code")


def auto_commit(
    tool_name: str,
    fn_args: dict,
    tool_result: str,
    verbosity: int = 1,
) -> None:
    """
    Crée un commit atomique si le tool a réussi et modifié un fichier.

    Appelé par agent.py après chaque exécution de tool réussie.
    Ne fait rien si :
    - l'outil n'est pas dans _COMMIT_TOOLS
    - le résultat contient une erreur (commence par ❌ ou ⚠️)
    - le répertoire courant n'est pas dans un dépôt git
    """
    if tool_name not in _COMMIT_TOOLS:
        return
    if tool_result.startswith(("❌", "⚠️")):
        return
    if not _in_git_repo():
        return

    path = fn_args.get("path", "")
    if not path:
        return

    _configure_identity_if_needed()

    # Stage le fichier
    rc_add, err_add = _run("add", "--", path)
    if rc_add != 0:
        if verbosity >= 1:
            print(f"  {C.YELLOW}⚠️  git add {path} échoué : {err_add}{C.RESET}")
        return

    # Vérifier qu'il y a bien quelque chose à commiter
    rc_diff, _ = _run("diff", "--staged", "--quiet")
    if rc_diff == 0:
        # Rien de stagé (fichier identique ou déjà commité)
        return

    # Construire le message de commit
    verb = _VERB.get(tool_name, "update")
    patches = fn_args.get("patches", [])
    detail  = f" ({len(patches)} changes)" if patches else ""
    message = f"albert: {verb} {path}{detail}"

    rc_commit, err_commit = _run("commit", "-m", message)
    if rc_commit != 0:
        if verbosity >= 1:
            print(f"  {C.YELLOW}⚠️  git commit échoué : {err_commit}{C.RESET}")
        return

    if verbosity >= 1:
        # Récupérer le hash court du commit
        _, short_hash = _run("rev-parse", "--short", "HEAD")
        print(f"  {C.DIM}🔖 commit {short_hash}  {message}{C.RESET}")
