"""modelbench — a reproducible coding benchmark for OpenAI-compatible models.

The package is deliberately dependency-free: everything runs on the Python
standard library so that a benchmark result can be reproduced on a bare
machine years from now.
"""

from __future__ import annotations

__version__ = "3.0.0"

#: Version of the record format written to ``results.jsonl``.
#: 3 adds stream pacing (``itl_p50_s``/``itl_p95_s``), the end-to-end rate and
#: the prompt-cache ratio to each attempt. Older records stay readable: every
#: aggregate treats a missing field as "not measured", not as zero.
RECORD_VERSION = 3

__all__ = ["__version__", "RECORD_VERSION"]
