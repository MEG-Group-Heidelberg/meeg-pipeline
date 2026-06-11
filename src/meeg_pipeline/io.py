from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WriteDecision:
    path: Path
    should_write: bool
    status: str
    message: str = ""


def decide_write(path: Path, *, overwrite: bool = False) -> WriteDecision:
    """Return whether a file should be written.

    Missing inputs and existing outputs are normal pipeline states. This helper
    never raises for an existing output; it returns a status instead.
    """
    if path.exists() and not overwrite:
        return WriteDecision(
            path=path,
            should_write=False,
            status="skipped_existing",
            message="Target already exists.",
        )

    return WriteDecision(
        path=path,
        should_write=True,
        status="overwrite" if path.exists() and overwrite else "write",
    )


def ensure_output_does_not_exist(path: Path, *, overwrite: bool = False) -> None:
    """Backward-compatible no-op wrapper.

    New code should use decide_write(...). This function intentionally no longer
    raises FileExistsError because existing outputs should not interrupt batch
    processing.
    """
    return None
