"""Context windows and answer budgets: one suite, any model size."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from modelbench.client import ChatClient, ChatResult
from modelbench.config import Target
from modelbench.errors import ModelBenchError
from modelbench.runner import Runner


def _client(monkeypatch, payload, context=None):
    target = Target(name="t", base_url="http://127.0.0.1:9/v1", model="m", context=context)
    client = ChatClient(target)
    calls: list[str] = []

    def fake(url, timeout=10.0):
        calls.append(url)
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(client, "_get_json", fake)
    return client, calls


def test_explicit_context_wins_without_a_request(monkeypatch):
    client, calls = _client(monkeypatch, {"n_ctx": 8192}, context=4096)
    assert client.detect_context() == 4096
    assert calls == []


def test_context_from_llama_cpp_props(monkeypatch):
    client, calls = _client(monkeypatch, {"n_ctx": 32768})
    assert client.detect_context() == 32768
    assert calls[0].endswith("/props")


def test_context_from_props_nested_settings(monkeypatch):
    client, _ = _client(monkeypatch, {"default_generation_settings": {"n_ctx": 131072}})
    assert client.detect_context() == 131072


def test_context_falls_back_to_model_metadata(monkeypatch):
    target = Target(name="t", base_url="http://127.0.0.1:9/v1", model="m")
    client = ChatClient(target)

    def fake(url, timeout=10.0):
        if url.endswith("/props"):
            raise OSError("no props here")
        return {"data": [{"id": "m", "context_length": 16384}]}

    monkeypatch.setattr(client, "_get_json", fake)
    assert client.detect_context() == 16384


def test_unknown_context_stays_unknown(monkeypatch):
    target = Target(name="t", base_url="http://127.0.0.1:9/v1", model="m")
    client = ChatClient(target)
    monkeypatch.setattr(client, "_get_json", lambda url, timeout=10.0: {"data": [{"id": "m"}]})
    assert client.detect_context() is None


# --------------------------------------------------------------------------- #
# budgets
# --------------------------------------------------------------------------- #
def _runner(context):
    target = Target(name="t", base_url="http://127.0.0.1:9/v1", model="m", context=context)
    plan = SimpleNamespace(target=target)
    runner = Runner.__new__(Runner)
    runner.context = context
    return runner


def test_budget_is_clamped_to_the_window():
    runner = _runner(4096)
    prompt = "x" * 3000  # ~1000 tokens
    assert runner._cap_for(prompt, 8192) == 4096 - 1000 - 256


def test_budget_shrinks_with_the_window():
    runner = _runner(2048)
    assert runner._cap_for("x" * 1500, 8192) == 2048 - 500 - 256


def test_prompt_that_cannot_fit_is_an_error_not_a_guess():
    runner = _runner(512)
    with pytest.raises(ModelBenchError, match="context window"):
        runner._cap_for("x" * 3000, 8192)


def test_no_context_means_no_clamp():
    runner = _runner(None)
    assert runner._cap_for("x" * 3000, 8192) == 8192


# --------------------------------------------------------------------------- #
# protocol classification
# --------------------------------------------------------------------------- #
def _result(content="", reasoning="", finish="stop"):
    return ChatResult(content=content, reasoning=reasoning, finish_reason=finish)


def _graded(no_result=False):
    return SimpleNamespace(no_result_line=no_result)


def test_protocol_ok():
    assert Runner._protocol(_result("```py\nx=1\n```"), "fence", _graded(), False) == "ok"


def test_protocol_empty_answer_even_with_reasoning():
    assert Runner._protocol(_result("", "thinking hard"), "none", _graded(), False) == "empty_answer"


def test_protocol_unparseable():
    assert Runner._protocol(_result("prose only"), "none", _graded(), False) == "unparseable"


def test_protocol_grader_crash():
    assert Runner._protocol(_result("```py\nx=1\n```"), "fence", _graded(True), False) == "grader_crash"


def test_protocol_truncated_only_without_retry():
    cut = _result("```py\nx=1", finish="length")
    assert Runner._protocol(cut, "fence-unclosed", _graded(), False) == "truncated"
    assert Runner._protocol(cut, "fence-unclosed", _graded(), True) == "ok"
