"""
Système de snapshots internes — protection contre les catastrophes.

Avant chaque écriture/suppression de fichier par Albert, un checkpoint est
créé avec le contenu AVANT modification. Les commandes /history et /undo N
permettent de naviguer et restaurer n'importe quel état passé.

Pas de dépendance à git — fonctionne sur n'importe quel projet.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Checkpoint:
    id: int
    timestamp: float
    description: str                         # ex : "write_file  src/main.py"
    files: dict[str, Optional[str]]          # chemin → contenu avant (None = fichier n'existait pas)


class SnapshotStore:
    """Store en mémoire des checkpoints de session."""

    def __init__(self) -> None:
        self._checkpoints: list[Checkpoint] = []
        self._next_id: int = 1

    # ──────────────────────────────────────────
    #  Prise de snapshot
    # ──────────────────────────────────────────

    def take(self, description: str, paths: list[str]) -> Checkpoint:
        """
        Sauvegarde l'état actuel des fichiers `paths` avant modification.
        Retourne le checkpoint créé.
        """
        files: dict[str, Optional[str]] = {}
        for raw in paths:
            p = Path(raw)
            if p.is_file():
                try:
                    files[str(p)] = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    files[str(p)] = None
            else:
                files[str(p)] = None   # fichier n'existait pas encore

        cp = Checkpoint(
            id=self._next_id,
            timestamp=time.time(),
            description=description,
            files=files,
        )
        self._checkpoints.append(cp)
        self._next_id += 1
        return cp

    # ──────────────────────────────────────────
    #  Consultation
    # ──────────────────────────────────────────

    def list(self) -> list[Checkpoint]:
        return list(self._checkpoints)

    def get(self, cp_id: int) -> Optional[Checkpoint]:
        for cp in self._checkpoints:
            if cp.id == cp_id:
                return cp
        return None

    def latest(self) -> Optional[Checkpoint]:
        return self._checkpoints[-1] if self._checkpoints else None

    # ──────────────────────────────────────────
    #  Restauration
    # ──────────────────────────────────────────

    def restore(self, cp_id: int) -> tuple[bool, str]:
        """
        Restaure tous les fichiers tels qu'ils étaient au moment du checkpoint.
        Retourne (succès, message).
        """
        cp = self.get(cp_id)
        if cp is None:
            return False, f"Checkpoint #{cp_id} introuvable."

        errors: list[str] = []
        restored: list[str] = []

        for path_str, content in cp.files.items():
            p = Path(path_str)
            try:
                if content is None:
                    # Le fichier n'existait pas → on le supprime s'il existe maintenant
                    if p.exists():
                        p.unlink()
                        restored.append(f"supprimé  {path_str}")
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(content, encoding="utf-8")
                    restored.append(f"restauré  {path_str}")
            except OSError as exc:
                errors.append(f"{path_str} : {exc}")

        if errors:
            return False, "Erreurs lors de la restauration :\n" + "\n".join(errors)

        summary = "\n".join(f"  ↩  {r}" for r in restored)
        return True, f"Checkpoint #{cp_id} restauré ({len(restored)} fichier(s))\n{summary}"

    def clear(self) -> None:
        self._checkpoints.clear()
        self._next_id = 1


# ──────────────────────────────────────────────────────────────────
#  Instance globale de session (réinitialisée dans AgentSession.initialize)
# ──────────────────────────────────────────────────────────────────

_store = SnapshotStore()


def get_store() -> SnapshotStore:
    return _store


def reset_store() -> None:
    """Appelé par AgentSession.initialize() pour repartir de zéro."""
    _store.clear()
