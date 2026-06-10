from __future__ import annotations

from pathlib import Path


def ensure_output_does_not_exist(path: Path, *, overwrite: bool = False) -> None:
    """Raise an error if an output path already exists and overwrite is False."""
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {path}\n"
            "Delete the file first or rerun with overwrite=True."
        )