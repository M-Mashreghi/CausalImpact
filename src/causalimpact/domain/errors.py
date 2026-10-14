"""Domain-level exceptions."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for domain rule violations."""


class IllegalTransitionError(DomainError):
    """A lifecycle transition that the state machine does not allow."""


class DesignNotReadyError(DomainError):
    """A design was used for analysis, or promoted, without satisfying readiness rules."""
