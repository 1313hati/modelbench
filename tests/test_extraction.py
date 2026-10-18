from __future__ import annotations

from modelbench.extraction import extract_repo, extract_single, fenced_blocks


def test_last_matching_fence_wins():
    text = """
Here is a draft:
```python
def f():
    return 1
```
And the final version:
```python
def f():
    return 2
```
"""
    code, source = extract_single(text, "py")
    assert source == "fence"
    assert "return 2" in code


def test_requested_language_beats_other_languages():
    text = """
```text
prose that is not code
```
```python
x = 1
```
"""
    code, source = extract_single(text, "py")
    assert source == "fence"
    assert code.strip() == "x = 1"


def test_unclosed_fence_is_salvaged():
    text = "Working on it:\n```python\ndef f():\n    return 3\n"
    code, source = extract_single(text, "py")
    assert source == "fence-unclosed"
    assert "return 3" in code


def test_answer_without_fence_is_graded_raw():
    code, source = extract_single("def f():\n    return 4\n", "py")
    assert source == "raw"
    assert code.startswith("def f")


def test_empty_answer_is_flagged():
    assert extract_single("   ", "py") == ("", "none")


def test_repo_markers_split_files():
    text = """### FILE: pkg/__init__.py
```python
from .core import thing
```
### FILE: pkg/core.py
```python
def thing():
    return 1
```
"""
    files, how = extract_repo(text)
    assert how == "markers"
    assert set(files) == {"pkg/__init__.py", "pkg/core.py"}
    assert "def thing" in files["pkg/core.py"]


def test_repo_paths_cannot_escape_the_workspace():
    text = """### FILE: ../../etc/passwd
```python
root:x:0:0
```
### FILE: pkg/core.py
```python
ok = True
```
"""
    files, _ = extract_repo(text)
    assert list(files) == ["pkg/core.py"]


def test_fenced_blocks_ignores_inline_backticks():
    blocks = fenced_blocks("use `max_tokens` here\n```py\nx = 1\n```\n")
    assert len(blocks) == 1
    assert blocks[0].tag == "py"
