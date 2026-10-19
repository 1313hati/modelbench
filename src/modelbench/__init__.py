"""modelbench — a reproducible coding benchmark for OpenAI-compatible models.

The package is deliberately dependency-free: everything runs on the Python
standard library so that a benchmark result can be reproduced on a bare
machine years from now.
"""

from __future__ import annotations

__version__ = "2.1.0"

#: Version of the record format written to ``results.jsonl``.
RECORD_VERSION = 2

__all__ = ["__version__", "RECORD_VERSION"]
