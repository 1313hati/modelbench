#!/usr/bin/env python3
"""Assertion helpers for task graders.

Every grader is a plain script that receives the solution path as ``argv[1]``
and prints exactly one final line::

    RESULT <passed>/<total>

The runner parses that line; failures printed as ``FAIL <name>: ...`` are fed
back to the model when the repair turn is enabled.  Checks are independent, so a
crash in one does not hide the rest of the suite.
"""

from __future__ import annotations

import os
import sys
import traceback


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.total = 0
        self.failures: list[str] = []

    # -- primitives ------------------------------------------------------ #
    def check(self, name: str, fn) -> None:
        self.total += 1
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - grading must survive anything
            self.failures.append(f"FAIL {name}: {type(exc).__name__}: {exc}")
        else:
            self.passed += 1

    def eq(self, name: str, got, want) -> None:
        def run() -> None:
            if got != want:
                raise AssertionError(f"got {got!r} != want {want!r}")

        self.check(name, run)

    def ne(self, name: str, got, unwanted) -> None:
        def run() -> None:
            if got == unwanted:
                raise AssertionError(f"got {got!r}, which should differ")

        self.check(name, run)

    def true(self, name: str, cond) -> None:
        def run() -> None:
            if not cond:
                raise AssertionError("condition is false")

        self.check(name, run)

    def false(self, name: str, cond) -> None:
        def run() -> None:
            if cond:
                raise AssertionError("condition is true")

        self.check(name, run)

    def raises(self, name: str, exc_type, fn) -> None:
        def run() -> None:
            try:
                fn()
            except exc_type:
                return
            except Exception as exc:  # noqa: BLE001
                raise AssertionError(
                    f"raised {type(exc).__name__}({exc}), want {exc_type.__name__}"
                ) from exc
            raise AssertionError(f"did not raise {exc_type.__name__}")

        self.check(name, run)

    def near(self, name: str, got, want, tol=1e-9) -> None:
        def run() -> None:
            if abs(got - want) > tol:
                raise AssertionError(f"got {got!r} != want {want!r} (tol {tol})")

        self.check(name, run)

    def contains(self, name: str, haystack, needle) -> None:
        def run() -> None:
            if needle not in haystack:
                raise AssertionError(f"{needle!r} not found")

        self.check(name, run)

    # -- output ---------------------------------------------------------- #
    def report(self) -> None:
        for line in self.failures:
            print(line)
        print(f"RESULT {self.passed}/{self.total}")
        sys.exit(0)


def solution_arg() -> str:
    """Path to the solution: a file for single-file tasks, a directory for repos."""
    if len(sys.argv) < 2:
        print("usage: grader.py <solution>", file=sys.stderr)
        print("RESULT 0/1")
        sys.exit(0)
    return sys.argv[1]


def solution_dir() -> str:
    path = solution_arg()
    return path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))


def traceback_text(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
