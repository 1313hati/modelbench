"""Minimal, dependency-free client for OpenAI-compatible chat endpoints.

Why hand-rolled instead of the ``openai`` package:

* the benchmark must be reproducible on a bare Python install;
* we need exact control over streaming (TTFT, per-chunk timing) and over the
  request body, because local servers accept fields (``top_k``, ``min_p``,
  ``chat_template_kwargs``) that hosted APIs reject;
* failures must be visible and honest, not retried into a different result.
"""

from __future__ import annotations

import http.client
import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .config import Target
from .errors import TargetUnavailable

RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}
USER_AGENT = f"modelbench/{__version__}"


@dataclass
class ChatResult:
    """Everything measured about a single completion."""

    content: str
    reasoning: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    ttft_s: float | None = None
    total_s: float = 0.0
    finish_reason: str | None = None
    model: str | None = None
    chunks: int = 0
    streamed: bool = True
    http_status: int = 200

    # -- derived --------------------------------------------------------- #
    @property
    def prompt_tokens(self) -> int | None:
        value = self.usage.get("prompt_tokens") or self.usage.get("input_tokens")
        return int(value) if isinstance(value, (int, float)) else None

    @property
    def completion_tokens(self) -> int | None:
        value = self.usage.get("completion_tokens") or self.usage.get("output_tokens")
        return int(value) if isinstance(value, (int, float)) else None

    @property
    def reasoning_tokens(self) -> int | None:
        details = self.usage.get("completion_tokens_details") or self.usage.get("output_tokens_details") or {}
        value = details.get("reasoning_tokens") if isinstance(details, dict) else None
        return int(value) if isinstance(value, (int, float)) else None

    @property
    def cached_tokens(self) -> int | None:
        details = self.usage.get("prompt_tokens_details") or self.usage.get("input_tokens_details") or {}
        value = details.get("cached_tokens") if isinstance(details, dict) else None
        return int(value) if isinstance(value, (int, float)) else None

    @property
    def gen_seconds(self) -> float:
        return max(self.total_s - (self.ttft_s or 0.0), 1e-6)

    @property
    def tok_per_s(self) -> float | None:
        tokens = self.completion_tokens
        if not tokens:
            return None
        return tokens / self.gen_seconds

    @property
    def truncated(self) -> bool:
        return (self.finish_reason or "").lower() in {"length", "max_tokens", "max_output_tokens"}

    def metrics(self) -> dict[str, Any]:
        """Timing/token block stored next to a graded attempt."""
        return {
            "usage": self.usage,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cached_tokens": self.cached_tokens,
            "ttft_s": round(self.ttft_s, 3) if self.ttft_s is not None else None,
            "total_s": round(self.total_s, 2),
            "tok_per_s": round(self.tok_per_s, 1) if self.tok_per_s is not None else None,
            "finish_reason": self.finish_reason,
            "answer_chars": len(self.content),
            "reasoning_chars": len(self.reasoning),
            "chunks": self.chunks,
            "streamed": self.streamed,
            "served_model": self.model,
        }

    def write_raw(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            if self.reasoning:
                fh.write("### reasoning\n" + self.reasoning + "\n\n")
            fh.write("### answer\n" + self.content + "\n")


def _text_of(value: Any) -> str:
    """Normalise delta content: string, list of parts, or None."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        out = []
        for part in value:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                out.append(str(part.get("text") or part.get("content") or ""))
        return "".join(out)
    return str(value)


class ChatClient:
    """Talks to one :class:`Target`."""

    def __init__(self, target: Target, on_event: Callable[[str], None] | None = None):
        self.target = target
        self.on_event = on_event

    # ------------------------------------------------------------------ #
    # discovery
    # ------------------------------------------------------------------ #
    def _get_json(self, url: str, timeout: float = 10.0) -> dict:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        if self.target.api_key:
            req.add_header("Authorization", f"Bearer {self.target.api_key}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - http(s) by config
            return json.loads(resp.read().decode("utf-8", "replace"))

    def list_models(self) -> list[str]:
        payload = self._get_json(self.target.models_url, timeout=self.target.connect_timeout_s)
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            return [str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")]
        return []

    def health(self) -> dict | None:
        """llama.cpp/Ollama-style health probe; ``None`` when unsupported."""
        try:
            payload = self._get_json(self.target.health_url, timeout=3)
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError, http.client.HTTPException):
            return None
        return payload if isinstance(payload, dict) else {"status": "ok"}

    def wait_ready(self, timeout: float | None = None, poll: float = 1.0) -> str:
        """Block until the endpoint answers, return the served model id."""
        limit = timeout if timeout is not None else self.target.ready_timeout_s
        deadline = time.monotonic() + limit
        last: str | None = None
        while time.monotonic() < deadline:
            try:
                models = self.list_models()
            except Exception as exc:  # noqa: BLE001 - any network error means "not yet"
                last = f"{type(exc).__name__}: {exc}"
            else:
                if models:
                    return models[0]
                last = "endpoint answered but /v1/models is empty"
            time.sleep(poll)
        raise TargetUnavailable(
            f"{self.target.base_url} did not become ready in {limit:.0f}s ({last or 'no response'})"
        )

    # ------------------------------------------------------------------ #
    # completion
    # ------------------------------------------------------------------ #
    def chat(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
        raw_path: Path | None = None,
    ) -> ChatResult:
        body = self.target.request_body(messages, max_tokens=max_tokens)
        payload = json.dumps(body).encode("utf-8")
        attempt = 0
        delay = 1.0
        while True:
            attempt += 1
            try:
                result = self._once(payload)
                break
            except _Retryable as exc:
                if attempt > self.target.max_retries:
                    raise TargetUnavailable(
                        f"{self.target.name}: giving up after {attempt} attempts: {exc}"
                    ) from exc
                if self.on_event:
                    self.on_event(f"retry {attempt}/{self.target.max_retries} after {exc}; sleeping {delay:.0f}s")
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
        if raw_path is not None:
            result.write_raw(raw_path)
        return result

    def _once(self, payload: bytes) -> ChatResult:
        req = urllib.request.Request(
            self.target.url,
            data=payload,
            headers=self.target.headers_for_request(),
            method="POST",
        )
        req.add_header("User-Agent", USER_AGENT)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.target.timeout_s) as resp:  # noqa: S310
                status = getattr(resp, "status", 200) or 200
                content_type = (resp.headers.get("Content-Type") or "").lower()
                if "text/event-stream" in content_type or self.target.stream:
                    return self._read_stream(resp, t0, status)
                return self._read_json(resp, t0, status)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:2000]
            message = f"HTTP {exc.code} from {self.target.url}: {body}"
            if exc.code in RETRY_STATUS:
                raise _Retryable(message) from None
            raise TargetUnavailable(message) from None
        except (urllib.error.URLError, ConnectionError, socket.timeout, http.client.HTTPException, OSError) as exc:
            raise _Retryable(f"{type(exc).__name__}: {exc}") from None

    # -- streaming ------------------------------------------------------- #
    def _read_stream(self, resp: Any, t0: float, status: int) -> ChatResult:
        content: list[str] = []
        reasoning: list[str] = []
        usage: dict[str, Any] = {}
        finish: str | None = None
        served: str | None = None
        ttft: float | None = None
        chunks = 0
        pending: list[str] = []  # chunks seen before the first delta

        for raw_line in resp:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line:
                continue
            if line.startswith(":"):  # SSE comment / keep-alive
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line in {"[DONE]", "DONE"}:
                break
            if line.startswith("event:"):
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                pending.append(line)
                continue
            if not isinstance(chunk, dict):
                continue
            chunks += 1
            if chunk.get("error"):
                raise TargetUnavailable(f"{self.target.name}: stream error: {chunk['error']}")
            if chunk.get("model"):
                served = str(chunk["model"])
            if isinstance(chunk.get("usage"), dict):
                usage = chunk["usage"]
            for choice in chunk.get("choices") or []:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta") or choice.get("message") or {}
                piece = _text_of(delta.get("content"))
                think = _text_of(delta.get("reasoning_content") or delta.get("reasoning") or delta.get("thinking"))
                if piece or think:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    if piece:
                        content.append(piece)
                    if think:
                        reasoning.append(think)
                reason = choice.get("finish_reason")
                if reason:
                    finish = str(reason)

        total = time.perf_counter() - t0
        if not content and not reasoning and pending:
            # Some servers stream bare JSON objects without the SSE prefix.
            blob = "\n".join(pending)
            try:
                data = json.loads(blob)
            except json.JSONDecodeError:
                content.append(blob)
            else:
                return self._from_json_payload(data, t0, status, streamed=True)

        return ChatResult(
            content="".join(content),
            reasoning="".join(reasoning),
            usage=usage,
            ttft_s=ttft,
            total_s=total,
            finish_reason=finish,
            model=served or self.target.model,
            chunks=chunks,
            streamed=True,
            http_status=status,
        )

    # -- non-streaming --------------------------------------------------- #
    def _read_json(self, resp: Any, t0: float, status: int) -> ChatResult:
        data = json.loads(resp.read().decode("utf-8", "replace"))
        return self._from_json_payload(data, t0, status, streamed=False)

    def _from_json_payload(self, data: Any, t0: float, status: int, streamed: bool) -> ChatResult:
        if not isinstance(data, dict):
            raise TargetUnavailable(f"{self.target.name}: unexpected response type {type(data).__name__}")
        if data.get("error"):
            raise TargetUnavailable(f"{self.target.name}: {data['error']}")
        choices = data.get("choices") or []
        choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = choice.get("message") or {}
        content = _text_of(message.get("content"))
        reasoning = _text_of(
            message.get("reasoning_content") or message.get("reasoning") or message.get("thinking")
        )
        total = time.perf_counter() - t0
        return ChatResult(
            content=content,
            reasoning=reasoning,
            usage=data.get("usage") or {},
            ttft_s=total if content else None,
            total_s=total,
            finish_reason=choice.get("finish_reason"),
            model=str(data.get("model") or self.target.model),
            chunks=1,
            streamed=streamed,
            http_status=status,
        )


class _Retryable(Exception):
    """Internal marker for transient failures."""


def probe(target: Target) -> dict[str, Any]:
    """One tiny completion, used by ``modelbench doctor``."""
    client = ChatClient(target)
    started = time.perf_counter()
    models = client.list_models()
    health = client.health()
    result = client.chat([{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=16)
    return {
        "base_url": target.base_url,
        "models": models,
        "health": health,
        "reply": result.content.strip()[:120],
        "ttft_s": round(result.ttft_s or 0, 3),
        "total_s": round(result.total_s, 2),
        "tok_per_s": round(result.tok_per_s, 1) if result.tok_per_s else None,
        "finish_reason": result.finish_reason,
        "probe_s": round(time.perf_counter() - started, 2),
    }
