from __future__ import annotations

import argparse

from meeg_pipeline import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="meegpipe",
        description="Command-line interface for the meeg-pipeline package.",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"meeg-pipeline {__version__}",
    )

    parser.parse_args()