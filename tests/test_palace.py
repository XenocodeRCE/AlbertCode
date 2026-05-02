"""Tests du wrapper MemPalace pour Albert Code."""

from __future__ import annotations

from albert_code.memory.palace import AlbertMemoryPalace


class _FakeCollection:
    def __init__(self) -> None:
        self.upserts = []

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    def count(self) -> int:
        return len(self.upserts)

    def get(self, include=None, **kwargs):
        where = kwargs.get("where")
        if where is not None:
            # Chemin anti-doublon: simuler "pas encore present".
            return {"ids": []}
        return {"ids": ["a", "b"]}

    def delete(self, ids=None):
        return None


def test_palace_disables_when_embedding_init_fails(monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("albert_code.memory.palace.AlbertEmbeddingFunction", _raise)

    palace = AlbertMemoryPalace(enabled=True, api_key="k")
    status = palace.get_status()
    assert status["enabled"] is True
    assert status["available"] is False
    assert "Memoire desactivee" in str(status["warning"])


def test_palace_save_and_recall_with_mocked_mempalace(monkeypatch, tmp_path):
    fake_collection = _FakeCollection()

    class _FakeEmbedding:
        def __init__(self, **kwargs) -> None:
            pass

    monkeypatch.setattr("albert_code.memory.palace.AlbertEmbeddingFunction", _FakeEmbedding)

    monkeypatch.setattr(
        "mempalace.palace.get_collection",
        lambda path, create=True: fake_collection,
    )

    def _search_memories(query: str, palace_path: str, n_results: int = 3):
        return {
            "query": query,
            "results": [
                {
                    "text": "On a choisi FastAPI pour l'API.",
                    "similarity": 0.92,
                    "source_file": "albert-session",
                }
            ],
        }

    monkeypatch.setattr("mempalace.searcher.search_memories", _search_memories)

    palace = AlbertMemoryPalace(
        enabled=True,
        api_key="k",
        palace_path=str(tmp_path / "palace"),
    )

    ok = palace.save_conversation(
        [
            {"role": "user", "content": "Quel framework web on garde ?"},
            {"role": "assistant", "content": "On garde FastAPI."},
        ]
    )

    assert ok is True
    assert len(fake_collection.upserts) == 1

    res = palace.recall("framework web", top_k=1)
    assert len(res) == 1
    assert res[0].similarity == 0.92

    status = palace.get_status()
    assert status["available"] is True
    assert status["entries"] == 1


def test_palace_recall_surfaces_search_error_warning(monkeypatch, tmp_path):
    class _FakeEmbedding:
        def __init__(self, **kwargs) -> None:
            pass

    monkeypatch.setattr("albert_code.memory.palace.AlbertEmbeddingFunction", _FakeEmbedding)
    monkeypatch.setattr(
        "mempalace.palace.get_collection",
        lambda path, create=True: _FakeCollection(),
    )
    monkeypatch.setattr(
        "mempalace.searcher.search_memories",
        lambda *args, **kwargs: {"error": "Search error: boom"},
    )

    palace = AlbertMemoryPalace(
        enabled=True,
        api_key="k",
        palace_path=str(tmp_path / "palace"),
    )

    res = palace.recall("jeanne", top_k=3)
    assert res == []
    status = palace.get_status()
    assert "recherche indisponible" in str(status.get("warning", "")).lower()


def test_palace_clear_returns_true_when_path_missing(tmp_path):
    palace = AlbertMemoryPalace(
        enabled=False,
        palace_path=str(tmp_path / "missing-palace"),
    )

    assert palace.clear() is True


def test_palace_clear_falls_back_to_collection_purge(monkeypatch, tmp_path):
    palace_dir = tmp_path / "palace"
    palace_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("albert_code.memory.palace.shutil.rmtree", lambda p: (_ for _ in ()).throw(OSError("locked")))

    fake_col = _FakeCollection()
    monkeypatch.setattr("albert_code.memory.palace.AlbertMemoryPalace._get_collection", lambda self: fake_col)
    monkeypatch.setattr("mempalace.palace.get_closets_collection", lambda path, create=True: fake_col)

    palace = AlbertMemoryPalace(
        enabled=False,
        palace_path=str(palace_dir),
    )

    assert palace.clear() is True
