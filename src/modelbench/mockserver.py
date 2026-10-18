"""A mock OpenAI-compatible server that answers with reference solutions.

It exists so that the benchmark can be verified without a GPU: ``modelbench
self-test`` starts this server, runs the whole suite, and checks that every
reference solution grades 100%.  Because the mock streams real SSE chunks and
token usage, it also exercises the client, the extractor, the repair loop and
the report — everything except the model.

Modes:
  ``ref``       return the task's reference answer (a perfect run)
  ``truncate``  return a cut-off answer with ``finish_reason=length``
  ``garbage``   return prose with no code (a failing run)
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .tasks import Suite

REPAIR_MARKER = "failed some of the hidden tests"


class _Handler(BaseHTTPRequestHandler):
    server_version = "modelbench-mock/1.0"
    protocol_version = "HTTP/1.1"

    # -- plumbing -------------------------------------------------------- #
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - stdlib API
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- routes ---------------------------------------------------------- #
    def do_GET(self) -> None:  # noqa: N802 - stdlib API
        if self.path.rstrip("/") in {"/health", "/healthz"}:
            self._json(200, {"status": "ok"})
        elif self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": "mock-model", "object": "model"}]})
        else:
            self._json(404, {"error": {"message": f"no route {self.path}"}})

    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": {"message": f"no route {self.path}"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "invalid JSON"}})
            return

        messages = body.get("messages") or []
        prompt = "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "user")
        is_repair = any(REPAIR_MARKER in str(m.get("content") or "") for m in messages)
        task = self.server.pick_task(prompt)  # type: ignore[attr-defined]
        content, finish = self.server.answer(task, self.server.mode)  # type: ignore[attr-defined]

        max_tokens = int(body.get("max_tokens") or body.get("max_completion_tokens") or 0)
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(content) // 4)
        payload_meta = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model") or "mock-model",
        }
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_tokens_details": {"cached_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 0},
        }

        if not body.get("stream"):
            self._json(
                200,
                {
                    **payload_meta,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": finish,
                        }
                    ],
                    "usage": usage,
                },
            )
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        delay = float(getattr(self.server, "delay", 0.0))

        def emit(chunk: dict) -> None:
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.flush()
            if delay:
                time.sleep(delay)

        if getattr(self.server, "reasoning", True) and not is_repair:
            for piece in ("Reading the task. ", "Planning the solution. "):
                emit(
                    {
                        **payload_meta,
                        "choices": [{"index": 0, "delta": {"reasoning_content": piece}, "finish_reason": None}],
                    }
                )
        step = 48
        for start in range(0, len(content), step):
            emit(
                {
                    **payload_meta,
                    "choices": [
                        {"index": 0, "delta": {"content": content[start : start + step]}, "finish_reason": None}
                    ],
                }
            )
        emit({**payload_meta, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": usage})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    # HTTP/1.1 keep-alive needs a length or a close; we stream until close.
    def do_OPTIONS(self) -> None:  # noqa: N802
        self._json(204, {})


class MockServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        suite: Suite,
        host: str = "127.0.0.1",
        port: int = 0,
        mode: str = "ref",
        delay: float = 0.0,
        reasoning: bool = True,
        verbose: bool = False,
    ):
        super().__init__((host, port), _Handler)
        self.suite = suite
        self.mode = mode
        self.delay = delay
        self.reasoning = reasoning
        self.verbose = verbose
        self._bodies = [
            (task, " ".join(task.body.split())[:80]) for task in suite.tasks
        ]

    def pick_task(self, prompt: str):
        flat = " ".join(prompt.split())
        for task, needle in self._bodies:
            if needle and needle in flat:
                return task
        # Repair turns only quote failures; fall back to the last task mentioned.
        return self.suite.tasks[0]

    def answer(self, task, mode: str) -> tuple[str, str]:
        text = task.ref_answer_text()
        if mode == "truncate":
            return text[: max(40, len(text) // 5)], "length"
        if mode == "garbage":
            return "I am sorry, but I cannot help with that request.", "stop"
        return text, "stop"

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}/v1"


class MockHandle:
    def __init__(self, server: MockServer, thread: threading.Thread):
        self.server = server
        self.thread = thread

    @property
    def base_url(self) -> str:
        return self.server.base_url

    def __enter__(self) -> "MockHandle":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def start_mock(
    suite: Suite,
    mode: str = "ref",
    delay: float = 0.0,
    reasoning: bool = True,
    port: int = 0,
    verbose: bool = False,
) -> MockHandle:
    server = MockServer(suite, port=port, mode=mode, delay=delay, reasoning=reasoning, verbose=verbose)
    thread = threading.Thread(target=server.serve_forever, name="modelbench-mock", daemon=True)
    thread.start()
    return MockHandle(server, thread)
