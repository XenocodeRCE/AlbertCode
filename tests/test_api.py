"""Tests du client API (debounce + retry 429)."""

import httpx

from albert_code.api import AlbertClient


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
    )


def test_chat_applies_debounce_between_calls(monkeypatch):
    clock = {"t": 0.0}
    sleeps: list[float] = []

    def fake_monotonic() -> float:
        return clock["t"]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            return _ok_response()

    monkeypatch.setattr("albert_code.api.time.monotonic", fake_monotonic)
    monkeypatch.setattr("albert_code.api.time.sleep", fake_sleep)
    monkeypatch.setattr("albert_code.api.httpx.Client", FakeClient)

    client = AlbertClient(
        base_url="https://example.test/v1",
        api_key="x",
        model="m",
        debounce_seconds=1.0,
    )

    client.chat([{"role": "user", "content": "a"}], tools=[], max_retries=1)
    client.chat([{"role": "user", "content": "b"}], tools=[], max_retries=1)

    assert len(sleeps) == 1
    assert sleeps[0] == 1.0


def test_chat_retries_429_with_delay_from_error_message(monkeypatch):
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    class FakeClient:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            FakeClient.calls += 1
            if FakeClient.calls == 1:
                return httpx.Response(
                    429,
                    text='{"detail":"10 requests per minute exceeded (remaining: 0)."}',
                )
            return _ok_response()

    monkeypatch.setattr("albert_code.api.time.sleep", fake_sleep)
    monkeypatch.setattr("albert_code.api.httpx.Client", FakeClient)

    client = AlbertClient(
        base_url="https://example.test/v1",
        api_key="x",
        model="m",
        debounce_seconds=0.0,
    )

    data = client.chat([{"role": "user", "content": "x"}], tools=[], max_retries=2)

    assert data["choices"][0]["message"]["content"] == "ok"
    assert len(sleeps) >= 1
    assert sleeps[0] >= 6.0


def test_get_rpm_usage_tracks_window(monkeypatch):
    clock = {"t": 0.0}

    def fake_monotonic() -> float:
        return clock["t"]

    monkeypatch.setattr("albert_code.api.time.monotonic", fake_monotonic)

    client = AlbertClient(
        base_url="https://example.test/v1",
        api_key="x",
        model="openweight-large",
        debounce_seconds=0.0,
    )

    client._record_request_attempt("openweight-large")
    clock["t"] = 10.0
    client._record_request_attempt("openweight-large")

    rpm = client.get_rpm_usage("openweight-large")
    assert rpm["used"] == 2
    assert rpm["limit"] == 10

    clock["t"] = 70.1
    rpm2 = client.get_rpm_usage("openweight-large")
    assert rpm2["used"] == 0


def test_auto_fallback_switches_large_to_medium_on_repeated_429(monkeypatch):
    clock = {"t": 0.0}
    sleeps: list[float] = []

    def fake_monotonic() -> float:
        return clock["t"]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    class FakeClient:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            FakeClient.calls += 1
            if FakeClient.calls <= 2:
                return httpx.Response(
                    429,
                    text='{"detail":"10 requests per minute exceeded (remaining: 0)."}',
                )
            return _ok_response()

    monkeypatch.setattr("albert_code.api.time.monotonic", fake_monotonic)
    monkeypatch.setattr("albert_code.api.time.sleep", fake_sleep)
    monkeypatch.setattr("albert_code.api.httpx.Client", FakeClient)

    client = AlbertClient(
        base_url="https://example.test/v1",
        api_key="x",
        model="openweight-large",
        debounce_seconds=0.0,
        auto_fallback_429=True,
    )

    data = client.chat([{"role": "user", "content": "x"}], tools=[], max_retries=3)

    assert data["choices"][0]["message"]["content"] == "ok"
    assert client.model == "openweight-medium"
    fb = client.get_fallback_status()
    assert fb["active"] is True
    assert fb["enabled"] is True
