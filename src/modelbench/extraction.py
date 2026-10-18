"""Turning a chat completion into files on disk.

Models answer in fences, sometimes with prose, sometimes with several
``### FILE:`` blocks, sometimes cut off by the token limit.  The rules here are
deliberately simple and deterministic, because extraction mistakes silently
change scores:

* the **last** fenced block in the requested language wins (models often
  restate an earlier draft first);
* an **unclosed** final fence is salvaged — a truncated answer is graded on
  what it did produce instead of scoring zero for formatting;
* repository answers are split on ``### FILE: path`` markers, and each block is
  the first fenced block after its marker;
* every model-supplied path is normalised and rejected if it escapes the
  workspace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .util import safe_rel

LANG_TAGS: dict[str, set[str]] = {
    "py": {"python", "py", "python3"},
    "js": {"javascript", "js", "node", "mjs", "cjs"},
    "ts": {"typescript", "ts"},
    "sql": {"sql", "sqlite", "sqlite3"},
    "json": {"json"},
    "sh": {"bash", "sh", "shell", "zsh"},
    "go": {"go", "golang"},
    "rs": {"rust", "rs"},
    "md": {"markdown", "md"},
    "yaml": {"yaml", "yml"},
    "toml": {"toml"},
    "txt": {"text", "txt"},
}

EXTENSIONS = {
    "py": "py",
    "js": "js",
    "ts": "ts",
    "sql": "sql",
    "json": "json",
    "sh": "sh",
    "go": "go",
    "rs": "rs",
    "md": "md",
    "yaml": "yaml",
    "toml": "toml",
    "txt": "txt",
}

_FENCE_OPEN = re.compile(r"(^|\n)[ \t]*```([A-Za-z0-9_+.\-]*)[ \t]*\r?\n")
_FILE_MARKER = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*)?(?:FILE|File|file)(?:\*\*)?[ \t]*:[ \t]*"
    r"(?:\*\*)?[`'\"]?([^\s`'\"*]+)[`'\"]?(?:\*\*)?[ \t]*$",
    re.M,
)
_HEADING_PATH = re.compile(
    r"^[ \t]*#{1,6}[ \t]+[`'\"]?((?:[\w.\-]+/)*[\w.\-]+\.(?:py|js|ts|sql|json|md|sh|go|rs|yaml|yml|toml|txt))[`'\"]?[ \t]*$",
    re.M,
)


@dataclass
class Block:
    tag: str
    body: str
    closed: bool


def fenced_blocks(text: str) -> list[Block]:
    """All fenced blocks, including an unterminated final one."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[Block] = []
    pos = 0
    while True:
        match = _FENCE_OPEN.search(text, pos)
        if not match:
            break
        tag = (match.group(2) or "").lower()
        start = match.end()
        end = text.find("```", start)
        if end == -1:
            blocks.append(Block(tag, text[start:], False))
            break
        blocks.append(Block(tag, text[start:end], True))
        pos = end + 3
    return blocks


def _clean(body: str) -> str:
    body = body.replace("\r\n", "\n").strip("\n")
    # strip a stray closing fence that survived inside the body
    while body.rstrip().endswith("```"):
        body = body.rstrip()[:-3].rstrip("\n")
    return body.rstrip() + "\n" if body.strip() else ""


def extract_single(text: str, lang: str = "py") -> tuple[str, str]:
    """Return ``(code, source)`` for a single-file task.

    ``source`` is one of ``fence``, ``fence-unclosed``, ``raw`` or ``none`` and
    is recorded in the results so a consumer can tell formatting failures from
    reasoning failures.
    """
    want = LANG_TAGS.get(lang, {lang.lower()})
    blocks = [b for b in fenced_blocks(text) if b.body.strip()]
    if blocks:
        preferred = [b for b in blocks if b.tag in want]
        pool = preferred or blocks
        # Prefer a closed block; among equals, prefer the last (final answer).
        closed = [b for b in pool if b.closed]
        pick = (closed or pool)[-1]
        return _clean(pick.body), ("fence" if pick.closed else "fence-unclosed")
    stripped = (text or "").strip()
    if not stripped:
        return "", "none"
    return stripped + "\n", "raw"


def _first_block(slice_text: str) -> str:
    blocks = [b for b in fenced_blocks(slice_text) if b.body.strip()]
    if blocks:
        return _clean(blocks[0].body)
    return _clean(slice_text)


def extract_repo(text: str, known_paths: set[str] | None = None) -> tuple[dict[str, str], str]:
    """Split a multi-file answer into ``{relative path: content}``.

    Two marker styles are accepted: ``### FILE: path`` (preferred, and what the
    prompt asks for) and, as a fallback, a markdown heading that is nothing but
    a source-file path.  With ``known_paths`` given, markers that do not match a
    file in the task's workspace are dropped, which removes most hallucinated
    paths.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(_FILE_MARKER.finditer(text))
    how = "markers"
    if not matches:
        matches = list(_HEADING_PATH.finditer(text))
        how = "headings" if matches else "none"
    if not matches:
        return {}, "none"

    files: dict[str, str] = {}
    for index, match in enumerate(matches):
        raw_path = match.group(1)
        rel = safe_rel(raw_path)
        if not rel:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = _first_block(text[match.end() : end])
        if not content.strip():
            continue
        if known_paths is not None and rel not in known_paths:
            continue
        files[rel] = content
    return files, (how if files else "none")


def extension_for(lang: str) -> str:
    return EXTENSIONS.get((lang or "").lower(), "txt")


def mentions_file(text: str) -> bool:
    return bool(_FILE_MARKER.search(text or ""))
