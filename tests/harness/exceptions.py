"""Custom exceptions for the agent harness."""

from __future__ import annotations


class HarnessConfigError(Exception):
    """Raised when required config files (agents.yaml, tasks.yaml) cannot be read.

    Parameters
    ----------
    filename:
        The name or path of the missing / unreadable config file.
    """

    def __init__(self, filename: str) -> None:
        self.filename = filename
        super().__init__(f"Required config file cannot be read: {filename}")


class ReplayExhaustedError(Exception):
    """Raised when replay runs out of canned responses.

    Parameters
    ----------
    call_type:
        Either ``"LLM"`` or ``"tool"`` indicating which replay sequence
        was exhausted.
    index:
        The zero-based index at which exhaustion occurred (i.e. the number
        of calls already served before the sequence ran out).
    """

    def __init__(self, call_type: str, index: int) -> None:
        self.call_type = call_type
        self.index = index
        super().__init__(
            f"Replay exhausted for {call_type} calls at index {index}"
        )


class ManifestDriftError(Exception):
    """Raised in strict mode when replay manifest differs from current config.

    Parameters
    ----------
    differing_fields:
        A list of field names that differ between the stored and current
        manifests.
    """

    def __init__(self, differing_fields: list[str]) -> None:
        self.differing_fields = differing_fields
        fields_str = ", ".join(differing_fields)
        super().__init__(
            f"Manifest drift detected in strict mode. "
            f"Differing fields: {fields_str}"
        )
