"""Configuration loading.

A configuration file describes *targets*: an OpenAI-compatible base URL, a
model name, and how to talk to it.  Everything else has a sane default, so the
smallest useful file is::

    [targets.local]
    base_url = "http://127.0.0.1:8080/v1"
    model = "local"

The file is TOML (stdlib ``tomllib``).  Values may reference environment
variables with ``${VAR}`` or ``${VAR:-fallback}`` so that API keys never have to
be written into the file.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

try:  # Python >= 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - guarded by requires-python
    raise SystemExit("modelbench requires Python 3.11+ (tomllib)") from None

from .errors import ConfigError

ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")

CONFIG_ENV = "MODELBENCH_CONFIG"
CONFIG_NAMES = ("modelbench.toml", "modelbench.local.toml")
USER_CONFIG = Path("~/.config/modelbench/modelbench.toml")


# --------------------------------------------------------------------------- #
# value coercion with useful error messages
# --------------------------------------------------------------------------- #
def _coerce(value: Any, kind: type, where: str) -> Any:
    if value is None:
        return None
    try:
        if kind is bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                low = value.strip().lower()
                if low in {"true", "yes", "on", "1"}:
                    return True
                if low in {"false", "no", "off", "0"}:
                    return False
            raise ValueError
        if kind is int:
            if isinstance(value, bool):
                raise ValueError
            return int(value)
        if kind is float:
            if isinstance(value, bool):
                raise ValueError
            return float(value)
        if kind is str:
            return str(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{where}: expected {kind.__name__}, got {value!r}") from None
    return value


def _int(table: dict, key: str, where: str, default: int | None = None) -> int | None:
    if key not in table or table[key] is None:
        return default
    return _coerce(table[key], int, f"{where}.{key}")


def _float(table: dict, key: str, where: str, default: float | None = None) -> float | None:
    if key not in table or table[key] is None:
        return default
    return _coerce(table[key], float, f"{where}.{key}")


def _bool(table: dict, key: str, where: str, default: bool | None = None) -> bool | None:
    if key not in table or table[key] is None:
        return default
    return _coerce(table[key], bool, f"{where}.{key}")


def _str(table: dict, key: str, where: str, default: str | None = None) -> str | None:
    if key not in table or table[key] is None:
        return default
    return _coerce(table[key], str, f"{where}.{key}")


def expand_env(value: str, where: str = "value") -> str:
    """Expand ``${VAR}`` / ``${VAR:-default}`` in a string."""

    def repl(match: re.Match[str]) -> str:
        name, fallback = match.group(1), match.group(2)
        if name in os.environ:
            return os.environ[name]
        if fallback is not None:
            return fallback
        raise ConfigError(f"{where}: environment variable {name} is not set")

    return ENV_PATTERN.sub(repl, value)


def expand_tree(node: Any, where: str = "config") -> Any:
    if isinstance(node, str):
        return expand_env(node, where)
    if isinstance(node, list):
        return [expand_tree(item, f"{where}[]") for item in node]
    if isinstance(node, dict):
        return {key: expand_tree(val, f"{where}.{key}") for key, val in node.items()}
    return node


# --------------------------------------------------------------------------- #
# generation settings
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Generation:
    """Sampling parameters plus hard token limits.

    ``None`` means "do not send this field", which matters because strict
    providers (OpenAI, Azure) reject unknown sampling keys such as ``top_k``.
    """

    temperature: float | None = 1.0
    top_p: float | None = 0.95
    top_k: int | None = None
    min_p: float | None = None
    # Pinned by default: the same model on the same endpoint can swing several
    # points between runs unless the sampler is seeded. Sample n uses
    # ``seed + n - 1``, so independent samples stay independent while the whole
    # run stays reproducible.
    seed: int | None = 42
    max_tokens: int = 8192
    retry_cap: int = 16384

    @classmethod
    def from_table(cls, table: dict, where: str, base: "Generation | None" = None) -> "Generation":
        base = base or cls()
        return cls(
            temperature=_float(table, "temperature", where, base.temperature),
            top_p=_float(table, "top_p", where, base.top_p),
            top_k=_int(table, "top_k", where, base.top_k),
            min_p=_float(table, "min_p", where, base.min_p),
            seed=_int(table, "seed", where, base.seed),
            max_tokens=_int(table, "max_tokens", where, base.max_tokens),
            retry_cap=_int(table, "retry_cap", where, base.retry_cap),
        )

    def merged(self, **overrides: Any) -> "Generation":
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean)

    def sampling_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {}
        for key in ("temperature", "top_p", "top_k", "min_p", "seed"):
            value = getattr(self, key)
            if value is not None:
                body[key] = value
        return body

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "min_p": self.min_p,
            "seed": self.seed,
            "max_tokens": self.max_tokens,
            "retry_cap": self.retry_cap,
        }


# --------------------------------------------------------------------------- #
# target
# --------------------------------------------------------------------------- #
@dataclass
class Target:
    """One model endpoint."""

    name: str
    base_url: str
    model: str
    api_key: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    stream: bool = True
    send_usage: bool = True
    timeout_s: float = 1800.0
    connect_timeout_s: float = 10.0
    max_retries: int = 2
    generation: Generation = field(default_factory=Generation)
    extra_body: dict[str, Any] = field(default_factory=dict)
    token_field: str = "max_tokens"
    start_cmd: str | None = None
    stop_cmd: str | None = None
    ready_timeout_s: float = 900.0
    health_path: str = "/health"
    # USD per 1M tokens. Optional, because a local server costs nothing at the
    # margin; when set, every report says what the run cost and what one
    # fully-solved task cost, which is half of "should I use this model".
    price_input: float | None = None
    price_output: float | None = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.base_url:
            raise ConfigError(f"target {self.name!r}: base_url is empty")
        if not self.model:
            raise ConfigError(f"target {self.name!r}: model is empty")

    # -- URLs ------------------------------------------------------------- #
    @property
    def url(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{self.base_url}/models"

    @property
    def health_url(self) -> str:
        root = self.base_url
        if root.endswith("/v1"):
            root = root[: -len("/v1")]
        return f"{root}{self.health_path}"

    @property
    def port(self) -> int | None:
        match = re.search(r":(\d+)(?:/|$)", self.base_url)
        return int(match.group(1)) if match else None

    # -- request building ------------------------------------------------- #
    def request_body(
        self, messages: list[dict], max_tokens: int | None = None, seed: int | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": self.stream,
        }
        if self.stream and self.send_usage:
            body["stream_options"] = {"include_usage": True}
        cap = max_tokens if max_tokens is not None else self.generation.max_tokens
        if cap:
            body[self.token_field] = int(cap)
        body.update(self.generation.sampling_body())
        if seed is not None:
            # Per-sample seed from the runner; overrides the configured base.
            body["seed"] = int(seed)
        body.update(self.extra_body)
        return body

    def headers_for_request(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream, application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.headers)
        return headers

    def describe(self) -> dict[str, Any]:
        """Redacted snapshot safe to store in a run manifest."""
        return {
            "name": self.name,
            "base_url": self.base_url,
            "model": self.model,
            "stream": self.stream,
            "timeout_s": self.timeout_s,
            "generation": self.generation.to_dict(),
            "extra_body": self.extra_body,
            "has_api_key": bool(self.api_key),
            "managed_server": bool(self.start_cmd),
            "pricing": {
                "input_per_mtok": self.price_input,
                "output_per_mtok": self.price_output,
            },
        }


def _target_from_table(name: str, table: dict, defaults: Generation, base: Path) -> Target:
    where = f"targets.{name}"
    if not isinstance(table, dict):
        raise ConfigError(f"{where}: expected a table")
    base_url = _str(table, "base_url", where)
    if not base_url:
        raise ConfigError(f"{where}: base_url is required")
    model = _str(table, "model", where)
    if not model:
        raise ConfigError(f"{where}: model is required (the id sent in the request body)")

    api_key = _str(table, "api_key", where)
    api_key_env = _str(table, "api_key_env", where)
    if api_key_env and not api_key:
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ConfigError(
                f"{where}: api_key_env={api_key_env!r} is set but the variable is empty; "
                f"export it or remove api_key_env"
            )

    sampling_table = table.get("generation", table.get("sampling", {})) or {}
    if not isinstance(sampling_table, dict):
        raise ConfigError(f"{where}.generation: expected a table")
    generation = Generation.from_table(sampling_table, f"{where}.generation", defaults)
    # Sampling keys may also be written directly on the target, which is what
    # most people try first; those win over the nested table.
    flat = {
        key: table[key]
        for key in ("temperature", "top_p", "top_k", "min_p", "seed", "max_tokens", "retry_cap")
        if key in table and table[key] is not None
    }
    if flat:
        generation = Generation.from_table(flat, where, generation)

    headers = table.get("headers", {}) or {}
    if not isinstance(headers, dict):
        raise ConfigError(f"{where}.headers: expected a table of strings")
    extra_body = table.get("extra_body", {}) or {}
    if not isinstance(extra_body, dict):
        raise ConfigError(f"{where}.extra_body: expected a table")

    return Target(
        name=name,
        base_url=base_url,
        model=model,
        api_key=api_key,
        headers={str(k): str(v) for k, v in headers.items()},
        stream=bool(_bool(table, "stream", where, True)),
        send_usage=bool(_bool(table, "send_usage", where, True)),
        timeout_s=float(_float(table, "timeout_s", where, 1800.0)),
        connect_timeout_s=float(_float(table, "connect_timeout_s", where, 10.0)),
        max_retries=int(_int(table, "max_retries", where, 2)),
        generation=generation,
        extra_body=extra_body,
        token_field=_str(table, "token_field", where, "max_tokens") or "max_tokens",
        start_cmd=_str(table, "start_cmd", where),
        stop_cmd=_str(table, "stop_cmd", where),
        ready_timeout_s=float(_float(table, "ready_timeout_s", where, 900.0)),
        health_path=_str(table, "health_path", where, "/health") or "/health",
        price_input=_float(table, "price_input", where),
        price_output=_float(table, "price_output", where),
    )


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    path: Path | None = None
    defaults: Generation = field(default_factory=Generation)
    samples: int = 2
    repair: bool = True
    suite: str | None = None
    suite_paths: list[Path] = field(default_factory=list)
    targets: dict[str, Target] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    # -- loading ---------------------------------------------------------- #
    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        candidate = find_config(path)
        if candidate is None:
            raise ConfigError(
                "no modelbench.toml found. Copy modelbench.example.toml to "
                "modelbench.toml (or pass --config PATH)."
            )
        try:
            raw = tomllib.loads(Path(candidate).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ConfigError(f"config file not found: {candidate}") from None
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{candidate}: invalid TOML: {exc}") from None
        return cls.from_dict(raw, Path(candidate))

    @classmethod
    def from_dict(cls, raw: dict, path: Path | None = None) -> "Config":
        raw = expand_tree(raw, str(path or "config"))
        base_dir = (path or Path.cwd()).parent if path else Path.cwd()

        project = raw.get("project", {}) or {}
        defaults_table = raw.get("defaults", {}) or {}
        if not isinstance(defaults_table, dict):
            raise ConfigError("defaults: expected a table")
        defaults = Generation.from_table(defaults_table, "defaults")
        samples = int(_int(defaults_table, "samples", "defaults", 2) or 2)
        if samples < 1:
            raise ConfigError("defaults.samples must be >= 1")
        repair = bool(_bool(defaults_table, "repair", "defaults", True))

        targets_table = raw.get("targets", {}) or {}
        if not isinstance(targets_table, dict):
            raise ConfigError("targets: expected a table of tables")
        targets = {
            name: _target_from_table(name, table, defaults, base_dir)
            for name, table in targets_table.items()
        }

        suite_paths = []
        for entry in project.get("suite_paths", []) or []:
            candidate = Path(expand_env(str(entry), "project.suite_paths"))
            if not candidate.is_absolute():
                candidate = base_dir / candidate
            suite_paths.append(candidate.resolve())

        config = cls(
            path=path,
            defaults=defaults,
            samples=samples,
            repair=repair,
            suite=project.get("suite"),
            suite_paths=suite_paths,
            targets=targets,
        )
        if not targets:
            config.warnings.append("config defines no [targets.*] tables")
        return config

    # -- access ----------------------------------------------------------- #
    def target(self, name: str | None) -> Target:
        if name:
            if name not in self.targets:
                known = ", ".join(sorted(self.targets)) or "none"
                raise ConfigError(f"unknown target {name!r} (known: {known})")
            return self.targets[name]
        if len(self.targets) == 1:
            return next(iter(self.targets.values()))
        if not self.targets:
            raise ConfigError("config defines no targets; add a [targets.NAME] table")
        known = ", ".join(sorted(self.targets))
        raise ConfigError(f"multiple targets defined, choose one with --target: {known}")


def find_config(path: str | Path | None = None) -> Path | None:
    """Resolution order: explicit path, $MODELBENCH_CONFIG, cwd, ~/.config."""
    if path:
        candidate = Path(path).expanduser()
        return candidate if candidate.is_file() else None
    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        candidate = Path(env_path).expanduser()
        return candidate if candidate.is_file() else None
    for name in CONFIG_NAMES:
        candidate = Path.cwd() / name
        if candidate.is_file():
            return candidate
    user = USER_CONFIG.expanduser()
    return user if user.is_file() else None


def target_from_cli(
    name: str,
    base_url: str,
    model: str,
    api_key_env: str | None = None,
    generation: Generation | None = None,
) -> Target:
    """Build a target from command-line flags (no config file needed)."""
    api_key = os.environ.get(api_key_env) if api_key_env else None
    return Target(
        name=name,
        base_url=base_url,
        model=model,
        api_key=api_key,
        generation=generation or Generation(),
    )
