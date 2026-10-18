"""Prompt templates.

The wrapper is part of the benchmark: it asks for a *complete file* rather than a
diff, discourages restating the problem, and caps the reasoning budget so that a
model which would ramble until the token limit is measured on its ability to
answer, not on its ability to loop.  Suites may override the wrapper with their
own ``prompt.md`` (``{body}`` is replaced with the task text, ``{files}`` with
the repository listing).
"""

from __future__ import annotations

from pathlib import Path

SINGLE_WRAPPER = """Solve the coding task below. Correctness on hidden tests is what matters.

Work efficiently: do not restate the problem. Spend at most about 1200 words on
internal reasoning, then emit the complete final answer. If you are still
unsure, stop analysing and write the code before the token limit.

Return format:
- The complete file in a single fenced code block.
- No tests and no explanations inside the code block.
- Standard library only unless the task says otherwise.

"""

REPO_WRAPPER = """Solve the coding task below. Correctness on hidden tests is what matters.

Work efficiently: do not restate the problem. Spend at most about 1200 words on
internal reasoning, then emit the complete final answer. If you are still
unsure, stop analysing and write the code before the token limit.

Return format:
- Return ONLY the files you changed, each introduced by a line
  `### FILE: relative/path.ext` followed immediately by one fenced block with the
  COMPLETE file content.
- Do not return unchanged files. Do not return a diff or a patch.
- No tests and no explanations inside the code blocks.

"""

REPAIR_PROMPT = """Your solution failed some of the hidden tests.

{failures}

Fix the code. Return the complete corrected file(s) in the exact same format as
before. Do not explain, do not apologise, do not return a diff.

"""


def repo_section(root: Path) -> str:
    """Render a repository as ``### FILE:`` blocks for the prompt."""
    root = Path(root)
    if not root.is_dir():
        return ""
    parts = ["\n## Repository files\n"]
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lang = path.suffix.lstrip(".") or "text"
        parts.append(f"\n### FILE: {rel.as_posix()}\n```{lang}\n{content.rstrip()}\n```\n")
    return "".join(parts)


def build_prompt(task, wrapper: str | None = None, repo_files: str | None = None) -> str:
    """Assemble the first user message for *task*."""
    if wrapper:
        text = wrapper.replace("{body}", task.body)
        text = text.replace("{files}", repo_files or "")
        return text
    base = REPO_WRAPPER if task.kind == "repo" else SINGLE_WRAPPER
    prompt = base + task.body
    if task.kind == "repo":
        prompt += repo_files if repo_files is not None else repo_section(task.files_dir)
    return prompt


def build_repair_prompt(failures: str) -> str:
    return REPAIR_PROMPT.format(failures=failures.strip() or "(no failure details available)")
