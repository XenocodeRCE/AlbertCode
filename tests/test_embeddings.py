"""Tests des embeddings Albert API pour MemPalace."""

from __future__ import annotations

import sys
import types

from albert_code.memory.embeddings import AlbertEmbeddingFunction


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.last_model = ""
        self.last_input = []
        self.last_encoding_format = ""

    def create(self, *, model: str, input: list[str], encoding_format: str):
        self.last_model = model
        self.last_input = input
        self.last_encoding_format = encoding_format
        return types.SimpleNamespace(
            data=[
                types.SimpleNamespace(embedding=[0.1, 0.2]),
                types.SimpleNamespace(embedding=[0.3, 0.4]),
            ]
        )


class _FakeOpenAIClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.embeddings = _FakeEmbeddings()


def test_albert_embedding_function_calls_openai(monkeypatch):
    fake_module = types.SimpleNamespace(OpenAI=_FakeOpenAIClient)
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    ef = AlbertEmbeddingFunction(
        api_key="k",
        base_url="https://albert.api.etalab.gouv.fr/v1",
        model="BAAI/bge-m3",
    )

    out = ef(["hello", "world"])

    assert out == [[0.1, 0.2], [0.3, 0.4]]
    assert ef.name() == "default"
    assert ef._client.embeddings.last_model == "BAAI/bge-m3"
    assert ef._client.embeddings.last_input == ["hello", "world"]
    assert ef._client.embeddings.last_encoding_format == "float"


def test_albert_embedding_function_accepts_single_string(monkeypatch):
    fake_module = types.SimpleNamespace(OpenAI=_FakeOpenAIClient)
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    ef = AlbertEmbeddingFunction(
        api_key="k",
        base_url="https://albert.api.etalab.gouv.fr/v1",
    )

    out = ef("bonjour")

    assert out[0] == [0.1, 0.2]
    assert ef._client.embeddings.last_input == ["bonjour"]


def test_albert_embedding_function_compat_embed_methods(monkeypatch):
    fake_module = types.SimpleNamespace(OpenAI=_FakeOpenAIClient)
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    ef = AlbertEmbeddingFunction(
        api_key="k",
        base_url="https://albert.api.etalab.gouv.fr/v1",
    )

    docs = ef.embed_documents(["alpha", "beta"])
    qry = ef.embed_query("jeanne")
    qry_kw = ef.embed_query(input="soeur")
    docs_kw = ef.embed_documents(input=["x", "y"])

    assert docs == [[0.1, 0.2], [0.3, 0.4]]
    assert len(qry) >= 1
    assert qry[0] == [0.1, 0.2]
    assert len(qry_kw) >= 1
    assert qry_kw[0] == [0.1, 0.2]
    assert docs_kw == [[0.1, 0.2], [0.3, 0.4]]
