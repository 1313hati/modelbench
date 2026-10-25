"""The client's derived numbers, and the stream they come from.

Half of these are arithmetic on a :class:`ChatResult` and need no network at
all; the other half run against the packaged mock server so that "the intervals
are captured from real SSE chunks" is a fact and not an assumption.
"""

from __future__ import annotations

import pytest

from modelbench.client import ChatResult, ChatClient
from modelbench.config import Target
from modelbench.mockserver import start_mock
from modelbench.tasks import Suite


# --------------------------------------------------------------------------- #
# arithmetic
# --------------------------------------------------------------------------- #
def test_itl_percentiles_come_from_the_intervals():
    result = ChatResult(content="x", intervals=[0.010, 0.020, 0.030, 0.040, 0.100])
    assert result.itl_p50_s == 0.03
    assert result.itl_p95_s == 0.10


def test_itl_is_unknown_without_intervals():
    result = ChatResult(content="x")
    assert result.itl_p50_s is None
    assert result.itl_p95_s is None


def test_wall_rate_includes_the_pause_before_the_first_token():
    result = ChatResult(content="x", total_s=10.0, ttft_s=2.0, usage={"completion_tokens": 400})
    assert result.tok_per_s == pytest.approx(50.0)  # 400 tokens in the 8s after TTFT
    assert result.tok_per_s_wall == pytest.approx(40.0)  # 400 tokens in 10s flat


def test_wall_rate_is_unknown_without_a_clock():
    result = ChatResult(content="x", usage={"completion_tokens": 400})
    assert result.tok_per_s_wall is None
    assert result.tok_per_s is None


def test_cache_ratio_is_none_when_the_server_says_nothing():
    result = ChatResult(content="x", usage={"prompt_tokens": 1000})
    assert result.cache_ratio is None


def test_a_reported_zero_cache_is_not_none():
    flat = {"prompt_tokens": 1000, "prompt_tokens_details": {"cached_tokens": 0}}
    assert ChatResult(content="x", usage=flat).cache_ratio == 0.0


def test_cache_ratio_uses_the_prompt_as_the_denominator():
    usage = {"prompt_tokens": 1000, "prompt_tokens_details": {"cached_tokens": 250}}
    assert ChatResult(content="x", usage=usage).cache_ratio == pytest.approx(0.25)


def test_cache_ratio_survives_a_server_that_over_reports():
    # A few servers report more cached tokens than the prompt they measured;
    # a ratio above 1.0 is nonsense in a report, so clamp rather than publish it.
    usage = {"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": 500}}
    assert ChatResult(content="x", usage=usage).cache_ratio == 1.0


def test_cache_ratio_accepts_anthropic_style_usage():
    usage = {"input_tokens": 200, "input_tokens_details": {"cached_tokens": 50}}
    assert ChatResult(content="x", usage=usage).cache_ratio == pytest.approx(0.25)


# --------------------------------------------------------------------------- #
# the real stream
# --------------------------------------------------------------------------- #
@pytest.fixture()
def tiny_suite(tmp_path):
    (tmp_path / "t_add").mkdir()
    (tmp_path / "t_add" / "task.md").write_text("Write `add(a, b)`.", encoding="utf-8")
    (tmp_path / "t_add" / "meta.json").write_text(
        '{"id": "t_add", "category": "test", "kind": "file", "lang": "py", "max_tokens": 256}',
        encoding="utf-8",
    )
    (tmp_path / "t_add" / "ref").mkdir()
    (tmp_path / "t_add" / "ref" / "solution.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    return Suite.load(tmp_path)


def test_streaming_result_captures_chunk_pacing(tiny_suite):
    with start_mock(tiny_suite, delay=0.01) as mock:
        client = ChatClient(Target(name="mock", base_url=mock.base_url, model="mock-model", context=8192))
        result = client.chat([{"role": "user", "content": "Write add(a, b)."}], max_tokens=256)

    assert result.streamed is True
    assert result.chunks >= 1
    assert result.intervals, "streaming must record the gap between chunks"
    assert result.itl_p50_s is not None and result.itl_p50_s > 0
    assert result.ttft_s is not None


def test_streaming_result_keeps_wall_and_decode_rates_distinct(tiny_suite):
    with start_mock(tiny_suite, delay=0.01) as mock:
        client = ChatClient(Target(name="mock", base_url=mock.base_url, model="mock-model", context=8192))
        result = client.chat([{"role": "user", "content": "Write add(a, b)."}], max_tokens=256)

    assert result.tok_per_s is not None and result.tok_per_s > 0
    assert result.tok_per_s_wall is not None and result.tok_per_s_wall > 0
    # The wall rate pays for TTFT, so it can never beat the decode rate.
    assert result.tok_per_s_wall <= result.tok_per_s


def test_a_stream_with_usage_reports_a_cache_ratio(tiny_suite):
    with start_mock(tiny_suite, delay=0.0) as mock:
        client = ChatClient(Target(name="mock", base_url=mock.base_url, model="mock-model", context=8192))
        result = client.chat([{"role": "user", "content": "Write add(a, b)."}], max_tokens=256)

    assert result.usage.get("prompt_tokens")
    assert result.cache_ratio == 0.0  # the mock looked, and found nothing cached


def test_non_streaming_reports_no_intervals(tiny_suite):
    with start_mock(tiny_suite, delay=0.0) as mock:
        client = ChatClient(
            Target(name="mock", base_url=mock.base_url, model="mock-model", stream=False, context=8192)
        )
        result = client.chat([{"role": "user", "content": "Write add(a, b)."}], max_tokens=256)

    assert result.streamed is False
    assert result.intervals == []
    assert result.itl_p50_s is None
    assert result.content.strip()
