"""
Configuration par projet via .albert-code.toml.

Le fichier est recherché en remontant depuis le répertoire courant jusqu'à
la racine (comme git). Il n'est jamais obligatoire — tout est optionnel.

Voir .albert-code.toml.example à la racine du dépôt pour un exemple complet.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

# tomllib est dans la stdlib depuis Python 3.11.
# Pour 3.10, on utilise tomli (installé en dev extra).
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            tomllib = None  # type: ignore[assignment]

# Nom canonique du fichier de config
CONFIG_FILENAME = ".albert-code.toml"


@dataclass
class ProjectConfig:
    """Configuration chargée depuis .albert-code.toml."""

    # Chemin du fichier trouvé (None si absent)
    config_path: Path | None = None

    # Instructions spécifiques au projet (injectées dans le system prompt)
    instructions: str = ""

    # Surcharges de modèle (None = utiliser les valeurs CLI/défaut)
    model_name:  str | None = None
    base_url:    str | None = None
    timeout:     float | None = None

    # Patterns glob de fichiers à ignorer dans list_files et grep_search
    ignore_patterns: list[str] = field(default_factory=list)


def _find_config(start: Path | None = None) -> Path | None:
    """Remonte l'arborescence depuis `start` pour trouver .albert-code.toml."""
    current = (start or Path.cwd()).resolve()
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            # Racine du système de fichiers atteinte
            return None
        current = parent


def load_project_config(start: Path | None = None) -> ProjectConfig:
    """
    Charge et retourne la configuration projet.

    Retourne un ProjectConfig vide (valeurs par défaut) si aucun fichier
    n'est trouvé ou si tomllib n'est pas disponible.
    """
    config_path = _find_config(start)

    if config_path is None:
        return ProjectConfig()

    if tomllib is None:
        # tomllib absent et Python < 3.11 sans tomli installé
        _warn(
            f"⚠️  {CONFIG_FILENAME} trouvé mais tomllib/tomli introuvable. "
            "Installez tomli : pip install tomli"
        )
        return ProjectConfig(config_path=config_path)

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        _warn(f"⚠️  Erreur de lecture de {config_path} : {exc}")
        return ProjectConfig(config_path=config_path)

    cfg = ProjectConfig(config_path=config_path)

    # [project]
    project = data.get("project", {})
    cfg.instructions = str(project.get("instructions", "")).strip()

    # [model]
    model = data.get("model", {})
    if "name"     in model: cfg.model_name = str(model["name"])
    if "base_url" in model: cfg.base_url   = str(model["base_url"])
    if "timeout"  in model:
        try:
            cfg.timeout = float(model["timeout"])
        except (TypeError, ValueError):
            pass

    # [ignore]
    ignore = data.get("ignore", {})
    patterns = ignore.get("patterns", [])
    if isinstance(patterns, list):
        cfg.ignore_patterns = [str(p) for p in patterns]

    return cfg


def _warn(msg: str) -> None:
    import sys
    print(f"  {msg}", file=sys.stderr)


def format_for_prompt(cfg: ProjectConfig) -> str:
    """
    Retourne le bloc d'instructions projet à injecter dans le system prompt.
    Retourne une chaîne vide si aucune instruction n'est définie.
    """
    if not cfg.instructions:
        return ""
    return (
        "\n## Project-specific instructions\n"
        f"{cfg.instructions}\n"
    )
