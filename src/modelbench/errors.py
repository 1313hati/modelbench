"""Exception types used across the package."""

from __future__ import annotations


class ModelBenchError(Exception):
    """Base class for expected, user-facing failures (printed without traceback)."""


class ConfigError(ModelBenchError):
    """The configuration file is missing, malformed or incomplete."""


class TargetUnavailable(ModelBenchError):
    """The endpoint could not be reached, or refused every retry."""


class TaskError(ModelBenchError):
    """A task pack is malformed (missing tests, bad meta, unsafe path, ...)."""


class GradeError(ModelBenchError):
    """The grader could not be executed."""


class SuiteError(ModelBenchError):
    """A suite manifest or task set is invalid."""
