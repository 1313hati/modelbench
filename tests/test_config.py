from __future__ import annotations

import pytest

from modelbench.config import Config, Generation, expand_env, find_config
from modelbench.errors import ConfigError


def test_minimal_config():
    config = Config.from_dict({"targets": {"local": {"base_url": "http://127.0.0.1:8080/v1", "model": "local"}}})
    target = config.target(None)
    assert target.name == "local"
    assert target.url == "http://127.0.0.1:8080/v1/chat/completions"
    assert target.generation.temperature == 1.0


def test_sampling_keys_on_the_target_win_over_defaults():
    config = Config.from_dict(
        {
            "defaults": {"temperature": 1.0, "top_p": 0.95},
            "targets": {"local": {"base_url": "http://x/v1", "model": "m", "top_k": 20, "temperature": 0.2}},
        }
    )
    target = config.target("local")
    assert target.generation.top_k == 20
    assert target.generation.temperature == 0.2
    body = target.request_body([{"role": "user", "content": "hi"}], max_tokens=64)
    assert body["top_k"] == 20
    assert body["max_tokens"] == 64


def test_nested_generation_table_is_supported():
    config = Config.from_dict(
        {"targets": {"local": {"base_url": "http://x/v1", "model": "m", "generation": {"min_p": 0.05, "seed": 7}}}}
    )
    generation = config.target("local").generation
    assert generation.min_p == 0.05
    assert generation.seed == 7


def test_env_expansion_and_fallback(monkeypatch):
    monkeypatch.setenv("MB_TEST_HOST", "example.test")
    assert expand_env("http://${MB_TEST_HOST}/v1") == "http://example.test/v1"
    assert expand_env("${MB_MISSING:-fallback}") == "fallback"
    with pytest.raises(ConfigError):
        expand_env("${MB_MISSING}")


def test_env_is_expanded_before_targets_are_built(monkeypatch):
    monkeypatch.setenv("MB_PORT", "9999")
    config = Config.from_dict({"targets": {"local": {"base_url": "http://127.0.0.1:${MB_PORT}/v1", "model": "m"}}})
    assert config.target("local").port == 9999


def test_unknown_and_ambiguous_targets_raise():
    config = Config.from_dict(
        {
            "targets": {
                "a": {"base_url": "http://a/v1", "model": "a"},
                "b": {"base_url": "http://b/v1", "model": "b"},
            }
        }
    )
    with pytest.raises(ConfigError):
        config.target(None)
    with pytest.raises(ConfigError):
        config.target("nope")
    assert config.target("b").name == "b"


def test_config_is_found_through_the_environment(tmp_path, monkeypatch):
    path = tmp_path / "custom.toml"
    path.write_text('[targets.local]\nbase_url = "http://x/v1"\nmodel = "m"\n', encoding="utf-8")
    monkeypatch.setenv("MODELBENCH_CONFIG", str(path))
    assert find_config(None) == path
    assert Config.load(None).target(None).name == "local"


def test_invalid_toml_reports_the_file(tmp_path):
    path = tmp_path / "broken.toml"
    path.write_text("not toml = = =", encoding="utf-8")
    with pytest.raises(ConfigError) as excinfo:
        Config.load(path)
    assert "invalid TOML" in str(excinfo.value)


def test_generation_merged_ignores_none():
    generation = Generation(temperature=0.5).merged(temperature=None, seed=3)
    assert generation.temperature == 0.5
    assert generation.seed == 3
