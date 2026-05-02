"""Embedding function ChromaDB basee sur Albert API (BAAI/bge-m3)."""

from __future__ import annotations

from typing import Sequence


class AlbertEmbeddingFunction:
    """Embedding function compatible ChromaDB, routee vers Albert API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = "BAAI/bge-m3",
        timeout: float = 20.0,
    ) -> None:
        if not api_key:
            raise ValueError("ALBERT_API_KEY manquante pour les embeddings")

        from openai import OpenAI

        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    @staticmethod
    def name() -> str:
        # Chroma persiste l'identite de l'embedding function.
        return "default"

    @staticmethod
    def is_legacy() -> bool:
        return True

    def __call__(self, input: Sequence[str] | str) -> list[list[float]]:
        texts = [input] if isinstance(input, str) else [str(x) for x in input]
        if not texts:
            return []

        response = self._client.embeddings.create(
            model=self.model,
            input=texts,
            encoding_format="float",
        )
        return [row.embedding for row in response.data]

    # Compatibilite avec les interfaces attendues par certains wrappers.
    def embed_documents(self, texts: Sequence[str] | None = None, **kwargs) -> list[list[float]]:
        payload = texts if texts is not None else kwargs.get("input", [])
        return self(payload)

    def embed_query(self, text: str | None = None, **kwargs) -> list[list[float]]:
        payload = text if text is not None else kwargs.get("input", "")
        return self([str(payload)])
