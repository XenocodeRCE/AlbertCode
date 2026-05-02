"""
Client HTTP pour l'API Albert.

Gère : authentification, retry avec backoff exponentiel,
comptabilisation des tokens, appel sans outils (plan-first).
"""

from __future__ import annotations

from collections import deque
import random
import re
import time

import httpx

from .config import C, DEFAULT_TIMEOUT
from .tools import TOOLS as _DEFAULT_TOOLS


_MODEL_ALIAS_TO_FULL: dict[str, str] = {
    "openweight-large": "openai/gpt-oss-120b",
    "openweight-medium": "mistralai/mistral-small-3.2-24b-instruct-2506",
    "openweight-small": "mistralai/ministral-3-8b-instruct-2512",
    "openweight-code": "qwen/qwen3-coder-30b-a3b-instruct",
    "openweight-audio": "openai/whisper-large-v3",
    "openweight-embeddings": "baai/bge-m3",
    "openweight-rerank": "baai/bge-reranker-v2-m3",
}

_MODEL_FULL_TO_ALIAS: dict[str, str] = {
    full: alias for alias, full in _MODEL_ALIAS_TO_FULL.items()
}

_RPM_LIMITS_EXP: dict[str, int] = {
    "openweight-large": 10,
    "openweight-medium": 50,
    "openweight-small": 50,
    "openweight-code": 50,
    "openweight-audio": 50,
    "openweight-embeddings": 500,
    "openweight-rerank": 500,
}


class AlbertClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = DEFAULT_TIMEOUT,
        max_requests_per_minute: int = 10,
        debounce_seconds: float | None = None,
        auto_fallback_429: bool = False,
        fallback_duration_seconds: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model    = model
        self.timeout  = timeout
        self.max_requests_per_minute = max(1, int(max_requests_per_minute))
        self.debounce_seconds = (
            float(debounce_seconds)
            if debounce_seconds is not None
            else (60.0 / self.max_requests_per_minute) + 0.05
        )
        self.headers  = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        }
        self.total_input_tokens  = 0
        self.total_output_tokens = 0
        self.total_requests      = 0
        self._last_request_at    = -self.debounce_seconds
        self._blocked_until      = 0.0
        self.auto_fallback_429   = auto_fallback_429
        self.fallback_duration_seconds = max(1, int(fallback_duration_seconds))
        self._fallback_target_alias = "openweight-medium"
        self._fallback_until = 0.0
        self._fallback_from_model: str | None = None
        self._consecutive_429 = 0
        self._rpm_window_seconds = 60.0
        self._request_times_by_model: dict[str, deque[float]] = {}

    @staticmethod
    def _canonical_model_alias(model: str) -> str:
        m = (model or "").strip().lower()
        if m in _MODEL_ALIAS_TO_FULL:
            return m
        return _MODEL_FULL_TO_ALIAS.get(m, m)

    def _rpm_limit_for_model(self, model: str) -> int:
        alias = self._canonical_model_alias(model)
        if alias in _RPM_LIMITS_EXP:
            return _RPM_LIMITS_EXP[alias]
        return self.max_requests_per_minute

    def _record_request_attempt(self, model: str) -> None:
        now = time.monotonic()
        bucket = self._request_times_by_model.setdefault(model, deque())
        bucket.append(now)
        cutoff = now - self._rpm_window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

    def get_rpm_usage(self, model: str | None = None) -> dict[str, float | int | str]:
        current = model or self.model
        now = time.monotonic()
        bucket = self._request_times_by_model.setdefault(current, deque())
        cutoff = now - self._rpm_window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        used = len(bucket)
        limit = self._rpm_limit_for_model(current)
        pct = (used / limit * 100.0) if limit > 0 else 0.0
        return {
            "model": current,
            "used": used,
            "limit": limit,
            "percent": pct,
            "window_seconds": int(self._rpm_window_seconds),
        }

    def get_fallback_status(self) -> dict[str, object]:
        now = time.monotonic()
        active = self._fallback_until > now
        remaining = max(0, int(self._fallback_until - now)) if active else 0
        return {
            "enabled": self.auto_fallback_429,
            "active": active,
            "remaining_seconds": remaining,
            "target": self._fallback_target_alias,
            "from_model": self._fallback_from_model,
        }

    def _maybe_restore_fallback(self) -> None:
        if self._fallback_until <= 0:
            return
        now = time.monotonic()
        if now < self._fallback_until:
            return
        if self._fallback_from_model and self.model == self._fallback_target_alias:
            old = self.model
            self.model = self._fallback_from_model
            print(
                f"\n  {C.CYAN}ℹ️  Fin de fallback: retour automatique "
                f"{old} -> {self.model}{C.RESET}"
            )
        self._fallback_until = 0.0
        self._fallback_from_model = None
        self._consecutive_429 = 0

    def _maybe_activate_fallback(self) -> None:
        if not self.auto_fallback_429:
            return
        if self._consecutive_429 < 2:
            return
        alias = self._canonical_model_alias(self.model)
        if alias != "openweight-large":
            return
        if self._fallback_until > time.monotonic():
            return

        self._fallback_from_model = self.model
        self.model = self._fallback_target_alias
        self._fallback_until = time.monotonic() + self.fallback_duration_seconds
        print(
            f"\n  {C.ORANGE}⚠️  Trop de 429: fallback automatique active "
            f"{self._fallback_from_model} -> {self.model} "
            f"pendant {self.fallback_duration_seconds}s.{C.RESET}"
        )

    def _wait_for_slot(self) -> None:
        """Débounce global: espace les appels pour éviter les rafales (HTTP 429)."""
        now = time.monotonic()
        min_next = self._last_request_at + self.debounce_seconds
        target = max(min_next, self._blocked_until)
        if now < target:
            wait = target - now
            print(
                f"\n  {C.DIM}⏱ Debounce actif: attente {wait:.1f}s avant le prochain appel API…{C.RESET}"
            )
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    @staticmethod
    def _extract_retry_after(resp: httpx.Response) -> float | None:
        """Détermine un délai de retry à partir des headers ou du message d'erreur."""
        hdr = resp.headers.get("Retry-After")
        if hdr:
            try:
                return max(0.0, float(hdr))
            except ValueError:
                pass

        text = (resp.text or "")[:500]
        m = re.search(r"(\d+)\s*requests?\s*per\s*minute", text, re.IGNORECASE)
        if m:
            rpm = max(1, int(m.group(1)))
            return (60.0 / rpm) + 0.1
        return None

    # ──────────────────────────────────────────
    #  Appel principal
    # ──────────────────────────────────────────

    def chat(
        self,
        messages: list,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        tools: list | None = None,
        max_retries: int = 3,
    ) -> dict:
        """Envoie une requête chat/completions avec retry sur erreurs transitoires."""
        if tools is None:
            tools = _DEFAULT_TOOLS

        body: dict = {
            "model":       self.model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
            "stream":      False,
        }
        if tools:
            body["tools"] = tools

        last_exc: Exception = Exception("unknown")

        for attempt in range(max_retries):
            try:
                self._maybe_restore_fallback()
                body["model"] = self.model
                self._wait_for_slot()
                self._record_request_attempt(self.model)
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self.headers,
                        json=body,
                    )

                # Erreurs transitoires : retry avec backoff
                if resp.status_code in (429, 500, 502, 503, 504):
                    retry_after = self._extract_retry_after(resp) if resp.status_code == 429 else None
                    wait = retry_after if retry_after is not None else (2 ** attempt) + random.uniform(0, 1)
                    if resp.status_code == 429:
                        self._consecutive_429 += 1
                        self._maybe_activate_fallback()
                        self._blocked_until = max(self._blocked_until, time.monotonic() + wait)
                    else:
                        self._consecutive_429 = 0
                    print(
                        f"\n  {C.YELLOW}⚠️  HTTP {resp.status_code}, "
                        f"retry {attempt + 1}/{max_retries} dans {wait:.1f}s…{C.RESET}"
                    )
                    time.sleep(wait)
                    last_exc = Exception(
                        f"Albert API error HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                    continue

                if resp.status_code != 200:
                    raise Exception(
                        f"Albert API error HTTP {resp.status_code}: {resp.text[:500]}"
                    )

                data = resp.json()
                self._consecutive_429 = 0

                usage = data.get("usage", {})
                self.total_input_tokens  += usage.get("prompt_tokens", 0)
                self.total_output_tokens += usage.get("completion_tokens", 0)
                self.total_requests      += 1

                return data

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(
                    f"\n  {C.YELLOW}⚠️  Timeout/réseau, "
                    f"retry {attempt + 1}/{max_retries} dans {wait:.1f}s…{C.RESET}"
                )
                time.sleep(wait)
                last_exc = exc

        raise Exception(
            f"Albert API inaccessible après {max_retries} tentatives : {last_exc}"
        )

    # ──────────────────────────────────────────
    #  Appel sans outils (mode plan-first)
    # ──────────────────────────────────────────

    def chat_no_tools(
        self,
        messages: list,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        """Appel sans tools — utilisé pour générer un plan avant d'agir."""
        data = self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=[],
        )
        return data["choices"][0]["message"].get("content", "").strip()
