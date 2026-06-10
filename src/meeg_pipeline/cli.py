from __future__ import annotations

import argparse

from meeg_pipeline import __version__
from meeg_pipeline.bids import (
    compare_subjects_with_participants,
    has_dataset_description,
    has_participants_tsv,
    list_bids_entities,
    make_bids_path,
    read_participants,
)
from meeg_pipeline.config import load_config


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

    subparsers = parser.add_subparsers(dest="command")

    config_parser = subparsers.add_parser(
        "config-info",
        help="Show basic information from a project config file.",
    )
    config_parser.add_argument(
        "--config",
        required=True,
        help="Path to a project config YAML file.",
    )

    bids_parser = subparsers.add_parser(
        "bids-info",
        help="Show basic information about the configured BIDS dataset.",
    )
    bids_parser.add_argument(
        "--config",
        required=True,
        help="Path to a project config YAML file.",
    )

    bids_path_parser = subparsers.add_parser(
        "bids-path",
        help="Show the BIDSPath constructed for a recording.",
    )
    bids_path_parser.add_argument(
        "--config",
        required=True,
        help="Path to a project config YAML file.",
    )
    bids_path_parser.add_argument("--subject", required=True)
    bids_path_parser.add_argument("--task", default=None)
    bids_path_parser.add_argument("--session", default=None)
    bids_path_parser.add_argument("--run", default=None)
    bids_path_parser.add_argument("--extension", default=None)

    args = parser.parse_args()

    if args.command == "config-info":
        config = load_config(args.config)

        print(f"Project: {config.project_name}")
        print(f"BIDS root: {config.paths.bids_root}")
        print(f"Derivatives root: {config.paths.derivatives_root}")
        print(f"Datatype: {config.bids.datatype}")
        print(f"Task: {config.bids.task}")
        print(f"Session: {config.bids.session}")
        print(f"Run: {config.bids.run}")

    elif args.command == "bids-info":
        config = load_config(args.config)

        print(f"BIDS root: {config.paths.bids_root}")
        print(
            "dataset_description.json:",
            "found" if has_dataset_description(config.paths.bids_root) else "missing",
        )
        print(
            "participants.tsv:",
            "found" if has_participants_tsv(config.paths.bids_root) else "missing",
        )
        print(f"Participants: {read_participants(config.paths.bids_root)}")
        print(f"Subjects: {list_bids_entities(config, 'subject')}")
        print(f"Sessions: {list_bids_entities(config, 'session')}")
        print(f"Tasks: {list_bids_entities(config, 'task')}")
        print(f"Runs: {list_bids_entities(config, 'run')}")

        missing_in_participants, missing_subject_folders = (
            compare_subjects_with_participants(config)
        )

        print(f"Subjects missing in participants.tsv: {missing_in_participants}")
        print(f"Participants without subject folder: {missing_subject_folders}")

    elif args.command == "bids-path":
        config = load_config(args.config)

        bids_path = make_bids_path(
            config,
            subject=args.subject,
            task=args.task,
            session=args.session,
            run=args.run,
            extension=args.extension,
        )

        print(f"BIDSPath: {bids_path}")
        print(f"Root: {bids_path.root}")
        print(f"Subject: {bids_path.subject}")
        print(f"Session: {bids_path.session}")
        print(f"Task: {bids_path.task}")
        print(f"Run: {bids_path.run}")
        print(f"Datatype: {bids_path.datatype}")
        print(f"Suffix: {bids_path.suffix}")
        print(f"Basename: {bids_path.basename}")
        print(f"Directory: {bids_path.directory}")
        print(f"Full path: {bids_path.fpath}")
        print(f"Path exists: {bids_path.fpath.exists()}")

    else:
        parser.print_help()