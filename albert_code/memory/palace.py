"""Facade memoire persistante basee sur MemPalace."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .embeddings import AlbertEmbeddingFunction


@dataclass
class MemoryResult:
    text: str
    similarity: float
    source_file: str


class AlbertMemoryPalace:
    """Wrapper resilient autour de MemPalace + embedding Albert API."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        base_url: str = "https://albert.api.etalab.gouv.fr/v1",
        model: str = "BAAI/bge-m3",
        palace_path: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.enabled = enabled
        self._available = False
        self._warning = ""
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.palace_path = str(Path(palace_path or "~/.albert-code/palace").expanduser())
        self.api_key = api_key or os.getenv("ALBERT_API_KEY", "")
        self._embed_fn: AlbertEmbeddingFunction | None = None

        if self.enabled:
            self._boot()

    def _disable(self, warning: str) -> None:
        self._available = False
        self._warning = warning

    def _boot(self) -> None:
        try:
            import mempalace.embedding as mempalace_embedding
        except Exception as exc:  # pragma: no cover - dependance optionnelle
            self._disable(f"Memoire desactivee: import mempalace impossible ({exc}).")
            return

        try:
            self._embed_fn = AlbertEmbeddingFunction(
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model,
            )
        except Exception as exc:  # pragma: no cover - dependance optionnelle
            self._disable(f"Memoire desactivee: embedding indisponible ({exc}).")
            return

        # Force MemPalace a utiliser l'embedding Albert API.
        mempalace_embedding.get_embedding_function = lambda device=None: self._embed_fn
        try:
            import mempalace.backends.chroma as mempalace_chroma

            # Certaines versions conservent une reference locale: on force le resolver.
            mempalace_chroma.ChromaBackend._resolve_embedding_function = staticmethod(
                lambda: self._embed_fn
            )
        except Exception:
            pass

        try:
            Path(self.palace_path).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._disable(f"Memoire desactivee: impossible de creer le palace ({exc}).")
            return

        self._available = True
        self._warning = ""

    @property
    def available(self) -> bool:
        return self.enabled and self._available

    def _get_collection(self):
        from mempalace.palace import get_collection

        return get_collection(self.palace_path, create=True)

    def save_conversation(self, messages: list[dict]) -> bool:
        if not self.available:
            return False

        turns = [
            m for m in messages
            if m.get("role") in {"user", "assistant"}
            and str(m.get("content") or "").strip()
        ]
        if not turns:
            return False

        content_lines = [
            f"[{m['role']}] {str(m.get('content', '')).strip()}"
            for m in turns
        ]
        content = "\n\n".join(content_lines).strip()
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        now = datetime.now(timezone.utc).isoformat()
        doc_id = f"albert-{uuid.uuid4()}"
        metadata = {
            "wing": "albert-code",
            "room": "session",
            "source_file": "albert-session",
            "filed_at": now,
            "chunk_index": 0,
            "content_hash": content_hash,
        }

        try:
            col = self._get_collection()

            # Evite les doublons exacts quand /memory save est relance plusieurs fois.
            existing = col.get(where={"content_hash": content_hash}, limit=1, include=["metadatas"])
            existing_ids = []
            if isinstance(existing, dict):
                existing_ids = existing.get("ids", []) or []
            else:
                existing_ids = getattr(existing, "ids", []) or []
            if existing_ids:
                return True

            col.upsert(documents=[content], ids=[doc_id], metadatas=[metadata])
            return True
        except Exception as exc:
            self._disable(f"Memoire desactivee: reseau/index indisponible ({exc}).")
            return False

    def recall(self, query: str, top_k: int = 3) -> list[MemoryResult]:
        if not self.available:
            return []

        try:
            from mempalace.searcher import search_memories

            data = search_memories(
                query=query,
                palace_path=self.palace_path,
                n_results=max(1, int(top_k)),
            )
        except Exception as exc:
            self._disable(f"Memoire desactivee: recherche indisponible ({exc}).")
            return []

        if not isinstance(data, dict) or "error" in data:
            if isinstance(data, dict) and data.get("error"):
                self._warning = f"Memoire: recherche indisponible ({data.get('error')})"
            return []

        out: list[MemoryResult] = []
        seen: dict[tuple[str, str], int] = {}
        for row in data.get("results", []):
            item = MemoryResult(
                text=str(row.get("text", "")),
                similarity=float(row.get("similarity", 0.0)),
                source_file=str(row.get("source_file", "?")),
            )
            key = (item.source_file, item.text.strip())
            idx = seen.get(key)
            if idx is None:
                seen[key] = len(out)
                out.append(item)
            elif item.similarity > out[idx].similarity:
                out[idx] = item
        return out

    def clear(self) -> bool:
        try:
            shutil.rmtree(self.palace_path)
            Path(self.palace_path).mkdir(parents=True, exist_ok=True)
            return True
        except OSError:
            return False

    def get_status(self) -> dict[str, object]:
        status = {
            "enabled": self.enabled,
            "available": self.available,
            "palace_path": self.palace_path,
            "model": self.model,
            "warning": self._warning,
            "entries": 0,
        }

        if not self.available:
            return status

        try:
            status["entries"] = int(self._get_collection().count())
        except Exception as exc:
            self._disable(f"Memoire desactivee: lecture statut impossible ({exc}).")
            status["available"] = False
            status["warning"] = self._warning

        return status


_default_palace: AlbertMemoryPalace | None = None


def _get_default() -> AlbertMemoryPalace:
    global _default_palace
    if _default_palace is None:
        _default_palace = AlbertMemoryPalace()
    return _default_palace


def save_conversation(messages: list[dict]) -> bool:
    return _get_default().save_conversation(messages)


def recall(query: str, top_k: int = 3) -> list[MemoryResult]:
    return _get_default().recall(query, top_k=top_k)


def get_status() -> dict[str, object]:
    return _get_default().get_status()
