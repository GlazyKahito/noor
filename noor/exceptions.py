"""NOOR's own exception classes.

Every error NOOR raises on purpose is a NoorError, so the web layer can catch one type
and show a friendly message instead of a stack trace.
"""


class NoorError(Exception):
    """Base class for all expected NOOR errors."""

    status = 400  # HTTP status the web layer should use

    def __init__(self, message, details=None):
        """Store a human-readable message and an optional list of details."""
        super().__init__(message)
        self.message = message
        self.details = details or []


class ValidationError(NoorError):
    """Input that breaks a rule (bad number, unknown option, bad CSV row)."""

    status = 400


class NotFoundError(NoorError):
    """A location, resource, alert or page that does not exist."""

    status = 404


class ConflictError(NoorError):
    """A request that clashes with the current state (duplicate code, closed alert)."""

    status = 409
