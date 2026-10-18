"""Suites and tasks: discovery, validation, solution materialisation.

Layout of a suite::

    suites/core-v2/
      suite.toml            # id, name, version, description (optional)
      prompt.md             # optional prompt wrapper override
      tasks/
        t01_weighted_jobs/
          task.md           # the prompt shown to the model
          meta.json         # category, kind, lang, limits, checks
          tests/            # hidden grader script(s)
          ref/              # reference solution, must score 100%
          files/            # repo tasks only: the starting repository

A task directory containing ``task.md`` + ``tests/`` is enough; ``meta.json`` is
optional and gets conservative defaults.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import extraction
from .errors import SuiteError, TaskError
from .util import sha256_dir

PACKAGED_SUITES = Path(__file__).resolve().parent / "suites"


def payload_files(root: Path) -> list[Path]:
    """Files of a task directory that are part of the task.

    Byte-code caches, editor droppings and dotfiles are excluded.  This matters
    more than it looks: ``pip`` byte-compiles every ``.py`` it installs,
    including reference solutions, so an installed package has a
    ``ref/__pycache__`` that a source checkout does not.  Counting those files
    would make ``kind=file`` tasks look ambiguous and could pick a ``.pyc`` as
    the reference answer.
    """
    if not root.is_dir():
        return []
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
            continue
        if path.suffix in {".pyc", ".pyo"} or path.name.endswith("~"):
            continue
        files.append(path)
    return files

KIND_ALIASES = {
    "file": "file",
    "single": "file",
    "js": "file",
    "sql": "file",
    "review": "file",
    "repo": "repo",
    "repository": "repo",
}

RUNNERS = {
    ".py": "python",
    ".js": "node",
    ".mjs": "node",
    ".cjs": "node",
    ".sh": "bash",
}

TEXT_SUFFIXES = {".py", ".js", ".ts", ".sql", ".json", ".md", ".sh", ".go", ".rs", ".txt", ".yaml", ".yml", ".toml"}


def _read_meta(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TaskError(f"{path}: invalid JSON: {exc}") from None
    if not isinstance(meta, dict):
        raise TaskError(f"{path}: expected a JSON object")
    return meta


def _find_test(root: Path) -> Path | None:
    candidates: list[Path] = []
    for directory in (root / "tests", root):
        if not directory.is_dir():
            continue
        for name in ("test_*", "check_*", "grade_*"):
            candidates.extend(sorted(p for p in directory.glob(name) if p.is_file()))
    if not candidates:
        return None
    # Prefer a language-appropriate script, then the alphabetically first.
    for path in candidates:
        if path.suffix in RUNNERS:
            return path
    return candidates[0]


@dataclass
class Task:
    id: str
    root: Path
    body: str
    meta: dict[str, Any] = field(default_factory=dict)

    # -- identity -------------------------------------------------------- #
    @property
    def category(self) -> str:
        return str(self.meta.get("category") or "misc")

    @property
    def kind(self) -> str:
        raw = str(self.meta.get("kind") or "file").lower()
        return KIND_ALIASES.get(raw, "repo" if (self.root / "files").is_dir() else "file")

    @property
    def lang(self) -> str:
        if self.meta.get("lang"):
            return str(self.meta["lang"]).lower()
        test = self.test_path
        return test.suffix.lstrip(".") if test else "py"

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or self.id)

    @property
    def max_tokens(self) -> int:
        return int(self.meta.get("max_tokens") or 8192)

    @property
    def timeout(self) -> float:
        return float(self.meta.get("timeout") or 180)

    @property
    def checks(self) -> int:
        return int(self.meta.get("checks") or 0)

    @property
    def retry_cap(self) -> int | None:
        value = self.meta.get("retry_cap")
        return int(value) if value else None

    @property
    def extension(self) -> str:
        return extraction.extension_for(self.lang)

    # -- files ----------------------------------------------------------- #
    @property
    def tests_dir(self) -> Path:
        return self.root / "tests"

    @property
    def test_path(self) -> Path | None:
        explicit = self.meta.get("test")
        if explicit:
            candidate = (self.root / str(explicit)).resolve()
            return candidate if candidate.is_file() else None
        return _find_test(self.root)

    @property
    def runner(self) -> str:
        if self.meta.get("runner"):
            return str(self.meta["runner"]).lower()
        test = self.test_path
        return RUNNERS.get(test.suffix.lower(), "python") if test else "python"

    @property
    def files_dir(self) -> Path:
        return self.root / "files"

    @property
    def ref_dir(self) -> Path:
        return self.root / "ref"

    def workspace_paths(self) -> set[str]:
        if not self.files_dir.is_dir():
            return set()
        return {
            p.relative_to(self.files_dir).as_posix()
            for p in self.files_dir.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }

    # -- validation ------------------------------------------------------ #
    def problems(self) -> list[str]:
        issues: list[str] = []
        if not self.body.strip():
            issues.append(f"{self.id}: task.md is empty")
        if self.test_path is None:
            issues.append(f"{self.id}: no test/check script found")
        if not self.ref_dir.is_dir() or not payload_files(self.ref_dir):
            issues.append(f"{self.id}: ref/ is missing or empty")
        if self.kind == "repo" and not self.files_dir.is_dir():
            issues.append(f"{self.id}: kind=repo but files/ is missing")
        if self.checks <= 0:
            issues.append(f"{self.id}: meta.checks missing (used when a grader crashes)")
        if self.kind == "file":
            ref_files = payload_files(self.ref_dir)
            if len(ref_files) > 1:
                issues.append(f"{self.id}: kind=file but ref/ has {len(ref_files)} files")
        return issues

    # -- solutions ------------------------------------------------------- #
    def prepare_ref(self, dest: Path) -> Path:
        """Materialise the reference solution; returns the path to grade."""
        if self.kind == "repo":
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(self.files_dir, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            for src in payload_files(self.ref_dir):
                target = dest / src.relative_to(self.ref_dir)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
            return dest
        ref_files = payload_files(self.ref_dir)
        if not ref_files:
            raise TaskError(f"{self.id}: ref/ has no files")
        preferred = [p for p in ref_files if p.suffix.lower().lstrip(".") in {self.lang, self.extension}]
        return (preferred or ref_files)[0]

    def write_solution(self, text: str, dest_dir: Path) -> tuple[Path, str, int]:
        """Write an extracted answer to disk.

        Returns ``(path, extraction_source, files_written)``.  For repo tasks the
        path is the workspace root; for file tasks it is the single solution
        file.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        if self.kind == "repo":
            workspace = dest_dir / self.id
            if workspace.exists():
                shutil.rmtree(workspace)
            shutil.copytree(
                self.files_dir, workspace, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
            )
            files, how = extraction.extract_repo(text)
            written = 0
            for rel, content in files.items():
                if not rel or "/" not in rel and "." not in rel:
                    continue
                if Path(rel).suffix.lower() not in TEXT_SUFFIXES:
                    continue
                target = (workspace / rel).resolve()
                try:
                    target.relative_to(workspace.resolve())
                except ValueError:
                    continue  # path escape attempt
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                written += 1
            return workspace, how, written

        code, how = extraction.extract_single(text, self.lang)
        path = dest_dir / f"{self.id}.solution.{self.extension}"
        path.write_text(code, encoding="utf-8")
        return path, how, 1 if code.strip() else 0

    def ref_answer_text(self) -> str:
        """Reference solution rendered the way a model is asked to answer."""
        if self.kind == "repo":
            parts = []
            for path in payload_files(self.ref_dir):
                rel = path.relative_to(self.ref_dir).as_posix()
                body = path.read_text(encoding="utf-8", errors="replace")
                parts.append(f"### FILE: {rel}\n```{path.suffix.lstrip('.')}\n{body.rstrip()}\n```\n")
            return "\n".join(parts)
        files = payload_files(self.ref_dir)
        if not files:
            return ""
        body = files[0].read_text(encoding="utf-8", errors="replace")
        return f"```{self.lang}\n{body.rstrip()}\n```\n"


@dataclass
class Suite:
    root: Path
    id: str
    name: str
    version: str
    description: str
    tasks: list[Task]
    prompt_text: str | None = None

    # -- loading --------------------------------------------------------- #
    @classmethod
    def load(cls, root: str | Path) -> "Suite":
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            raise SuiteError(f"suite directory not found: {root}")
        manifest: dict[str, Any] = {}
        manifest_path = root / "suite.toml"
        if manifest_path.is_file():
            import tomllib

            try:
                manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as exc:
                raise SuiteError(f"{manifest_path}: invalid TOML: {exc}") from None
        tasks_root = root / "tasks" if (root / "tasks").is_dir() else root
        tasks: list[Task] = []
        for candidate in sorted(tasks_root.iterdir()):
            if not candidate.is_dir():
                continue
            body_file = candidate / "task.md"
            if not body_file.is_file():
                continue
            meta = _read_meta(candidate / "meta.json")
            if meta.get("id") and meta["id"] != candidate.name:
                raise TaskError(
                    f"{candidate}: meta.id={meta['id']!r} does not match directory name {candidate.name!r}"
                )
            tasks.append(Task(id=candidate.name, root=candidate, body=body_file.read_text(encoding="utf-8"), meta=meta))
        if not tasks:
            raise SuiteError(f"{root}: no tasks found (expected tasks/*/task.md)")

        prompt_path = root / "prompt.md"
        prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else None
        return cls(
            root=root,
            id=str(manifest.get("id") or root.name),
            name=str(manifest.get("name") or root.name),
            version=str(manifest.get("version") or "1"),
            description=str(manifest.get("description") or ""),
            tasks=tasks,
            prompt_text=prompt_text,
        )

    # -- queries --------------------------------------------------------- #
    def task(self, task_id: str) -> Task:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise TaskError(f"{self.id}: unknown task {task_id!r}")

    def select(self, only: Iterable[str] | None = None, exclude: Iterable[str] | None = None) -> list[Task]:
        chosen = list(self.tasks)
        only = list(only or [])
        if only:
            missing = sorted(set(only) - {t.id for t in chosen})
            if missing:
                raise TaskError(f"{self.id}: unknown task(s): {', '.join(missing)}")
            chosen = [t for t in chosen if t.id in set(only)]
        exclude = set(exclude or [])
        chosen = [t for t in chosen if t.id not in exclude]
        if not chosen:
            raise TaskError("no tasks selected")
        return chosen

    @property
    def categories(self) -> list[str]:
        return sorted({t.category for t in self.tasks})

    @property
    def total_checks(self) -> int:
        return sum(t.checks for t in self.tasks if t.checks)

    def digest(self) -> str:
        return sha256_dir(self.root)

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "root": str(self.root),
            "tasks": len(self.tasks),
            "categories": self.categories,
            "checks": self.total_checks,
            "digest": self.digest(),
        }

    def problems(self) -> list[str]:
        issues: list[str] = []
        seen: set[str] = set()
        for task in self.tasks:
            if task.id in seen:
                issues.append(f"duplicate task id {task.id}")
            seen.add(task.id)
            issues.extend(task.problems())
        return issues


def available_suites(extra_paths: Iterable[Path] = ()) -> list[Suite]:
    """Every suite reachable from the package plus configured paths."""
    found: dict[str, Suite] = {}
    roots: list[Path] = [PACKAGED_SUITES, *[Path(p) for p in extra_paths]]
    for root in roots:
        if not root.is_dir():
            continue
        candidates = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
        # A path may itself be one suite.
        if (root / "task.md").is_file() or (root / "suite.toml").is_file():
            candidates = [root]
        for candidate in candidates:
            if not (candidate / "tasks").is_dir() and not any(candidate.glob("*/task.md")):
                continue
            try:
                suite = Suite.load(candidate)
            except (SuiteError, TaskError):
                continue
            found.setdefault(suite.id, suite)
    return list(found.values())


def resolve_suite(spec: str | None, extra_paths: Iterable[Path] = (), default: str | None = None) -> Suite:
    """Resolve ``--suite`` to a :class:`Suite`.

    ``spec`` may be a directory, a suite id, or ``None`` (config default, then
    ``core-v2``, then whatever is available).
    """
    if spec:
        candidate = Path(spec).expanduser()
        if candidate.is_dir():
            return Suite.load(candidate)
        for suite in available_suites(extra_paths):
            if suite.id == spec or suite.name == spec:
                return suite
        raise SuiteError(f"suite {spec!r} not found (pass a directory or a suite id)")

    wanted = default or "core-v2"
    suites = available_suites(extra_paths)
    for suite in suites:
        if suite.id == wanted:
            return suite
    if suites:
        return suites[0]
    raise SuiteError("no suites found; the installation is incomplete")
