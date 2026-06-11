from __future__ import annotations

import argparse

from meeg_pipeline import __version__
from meeg_pipeline.bids import (
    compare_subjects_with_participants,
    has_dataset_description,
    has_participants_tsv,
    list_bids_entities,
    make_bids_path,
    make_events_path,
    read_participants,
    read_raw_bids_recording_if_exists,
)
from meeg_pipeline.sourcedata import discover_source_recordings, make_target_bids_path
from meeg_pipeline.conversion import convert_source_recordings_to_bids
from meeg_pipeline.channels import print_channel_summary, summarize_channels
from meeg_pipeline.events import (
    BinaryChannelEventConfig,
    binary_event_config_from_pipeline_config,
    find_binary_channel_events,
    print_event_summary,
    summarize_events,
    write_bids_events_for_recording,
)
from meeg_pipeline.project import init_project
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

    sourcedata_parser = subparsers.add_parser(
        "sourcedata-info",
        help="Show source recordings found in the standardized sourcedata structure.",
    )
    sourcedata_parser.add_argument(
        "--config",
        required=True,
        help="Path to a project config YAML file.",
    )

    convert_parser = subparsers.add_parser(
        "convert-to-bids",
        help="Convert source FIF files from sourcedata/ to raw BIDS.",
    )
    convert_parser.add_argument(
        "--config",
        required=True,
        help="Path to a project config YAML file.",
    )
    convert_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing BIDS files. Default: do not overwrite.",
    )

    raw_info_parser = subparsers.add_parser(
        "raw-info",
        help="Read a raw BIDS recording and show basic information.",
    )
    raw_info_parser.add_argument(
        "--config",
        required=True,
        help="Path to a project config YAML file.",
    )
    raw_info_parser.add_argument("--subject", required=True)
    raw_info_parser.add_argument("--task", default=None)
    raw_info_parser.add_argument("--session", default=None)
    raw_info_parser.add_argument("--run", default=None)
    raw_info_parser.add_argument(
        "--preload",
        action="store_true",
        help="Preload the raw data into memory.",
    )

    channels_info_parser = subparsers.add_parser(
        "channels-info",
        help="Read a raw BIDS recording and show channel information.",
    )
    channels_info_parser.add_argument(
        "--config",
        required=True,
        help="Path to a project config YAML file.",
    )
    channels_info_parser.add_argument("--subject", required=True)
    channels_info_parser.add_argument("--task", default=None)
    channels_info_parser.add_argument("--session", default=None)
    channels_info_parser.add_argument("--run", default=None)

    events_info_parser = subparsers.add_parser(
        "events-info",
        help="Extract binary-coded events and show basic information.",
    )
    events_info_parser.add_argument(
        "--config",
        required=True,
        help="Path to a project config YAML file.",
    )
    events_info_parser.add_argument("--subject", required=True)
    events_info_parser.add_argument("--task", default=None)
    events_info_parser.add_argument("--session", default=None)
    events_info_parser.add_argument("--run", default=None)
    events_info_parser.add_argument(
        "--stim-channels",
        nargs="+",
        default=None,
        help="Override stimulus channels used for binary event coding.",
    )
    events_info_parser.add_argument("--min-duration", type=float, default=None)
    events_info_parser.add_argument("--shortest-event", type=int, default=None)
    events_info_parser.add_argument("--min-gap", type=int, default=None)
    events_info_parser.add_argument(
        "--adjust-timeline-by-msec",
        type=float,
        default=None,
    )
    events_info_parser.add_argument("--tolerance-samples", type=int, default=None)
    events_info_parser.add_argument(
        "--mute-bad-annotations",
        dest="mute_bad_annotations",
        action="store_true",
        default=None,
        help="Override config: zero stim channels during BAD annotations.",
    )
    events_info_parser.add_argument(
        "--no-mute-bad-annotations",
        dest="mute_bad_annotations",
        action="store_false",
        default=None,
        help="Override config: do not zero stim channels during BAD annotations.",
    )

    write_events_parser = subparsers.add_parser(
        "write-events",
        help="Extract events and write a BIDS-compatible events.tsv file.",
    )
    write_events_parser.add_argument(
        "--config",
        required=True,
        help="Path to a project config YAML file.",
    )
    write_events_parser.add_argument("--subject", required=True)
    write_events_parser.add_argument("--task", default=None)
    write_events_parser.add_argument("--session", default=None)
    write_events_parser.add_argument("--run", default=None)
    write_events_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing events.tsv file.",
    )

    init_project_parser = subparsers.add_parser(
        "init-project",
        help="Create a new meeg-pipeline project scaffold.",
    )

    init_project_parser.add_argument(
        "project_name",
        help="Name of the project folder to create.",
    )

    init_project_parser.add_argument(
        "--base-dir",
        default=".",
        help="Directory in which the project folder should be created.",
    )

    init_project_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing template files.",
    )

    args = parser.parse_args()

    if args.command == "config-info":
        config = load_config(args.config)

        print(f"Project: {config.project_name}")
        print(f"BIDS root: {config.paths.bids_root}")
        print(f"Sourcedata root: {config.paths.sourcedata_root}")
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

    elif args.command == "sourcedata-info":
        config = load_config(args.config)
        recordings = discover_source_recordings(config)

        print(f"Found {len(recordings)} source recording(s).")

        for recording in recordings:
            target_bids_path = make_target_bids_path(config, recording)

            print()
            print(f"Source: {recording.source_path}")
            print(f"Subject: {recording.subject}")
            print(f"Session: {recording.session}")
            print(f"Task: {recording.task}")
            print(f"Run: {recording.run}")
            print(f"Target: {target_bids_path.fpath}")
            print(f"Target exists: {target_bids_path.fpath.exists()}")

    elif args.command == "convert-to-bids":
        config = load_config(args.config)
        recordings = discover_source_recordings(config)

        print(f"Found {len(recordings)} source recording(s).")

        results = convert_source_recordings_to_bids(
            config,
            recordings,
            on_existing="overwrite" if args.overwrite else "skip",
        )

        for result in results:
            print()
            print(f"Status: {result.status}")
            print(f"Source: {result.source_path}")
            print(f"Target: {result.target_path}")
            if result.message:
                print(f"Message: {result.message}")

    elif args.command == "raw-info":
        config = load_config(args.config)

        raw_result = read_raw_bids_recording_if_exists(
            config,
            subject=args.subject,
            task=args.task,
            session=args.session,
            run=args.run,
            preload=args.preload,
        )

        if raw_result.raw is None:
            print(f"Status: {raw_result.status}")
            print(f"Message: {raw_result.message}")
            print(f"Path: {raw_result.path}")
            return

        raw = raw_result.raw
        duration = raw.times[-1] if len(raw.times) > 0 else 0.0

        print(raw)
        print(f"Channels: {len(raw.ch_names)}")
        print(f"Sampling frequency: {raw.info['sfreq']} Hz")
        print(f"Duration: {duration:.2f} s")
        print(f"Bad channels: {raw.info['bads']}")
        print(f"Annotations: {len(raw.annotations)}")

    elif args.command == "channels-info":
        config = load_config(args.config)

        raw_result = read_raw_bids_recording_if_exists(
            config,
            subject=args.subject,
            task=args.task,
            session=args.session,
            run=args.run,
            preload=False,
        )

        if raw_result.raw is None:
            print(f"Status: {raw_result.status}")
            print(f"Message: {raw_result.message}")
            print(f"Path: {raw_result.path}")
            return

        summary = summarize_channels(raw_result.raw)
        print_channel_summary(summary)

    elif args.command == "events-info":
        config = load_config(args.config)

        raw_result = read_raw_bids_recording_if_exists(
            config,
            subject=args.subject,
            task=args.task,
            session=args.session,
            run=args.run,
            preload=False,
        )

        if raw_result.raw is None:
            print(f"Status: {raw_result.status}")
            print(f"Message: {raw_result.message}")
            print(f"Path: {raw_result.path}")
            return

        raw = raw_result.raw

        event_config = binary_event_config_from_pipeline_config(config)

        event_config = BinaryChannelEventConfig(
            stim_channels=tuple(args.stim_channels) if args.stim_channels else event_config.stim_channels,
            min_duration=(
                args.min_duration
                if args.min_duration is not None
                else event_config.min_duration
            ),
            shortest_event=(
                args.shortest_event
                if args.shortest_event is not None
                else event_config.shortest_event
            ),
            min_gap=args.min_gap if args.min_gap is not None else event_config.min_gap,
            adjust_timeline_by_msec=(
                args.adjust_timeline_by_msec
                if args.adjust_timeline_by_msec is not None
                else event_config.adjust_timeline_by_msec
            ),
            tolerance_samples=(
                args.tolerance_samples
                if args.tolerance_samples is not None
                else event_config.tolerance_samples
            ),
            mute_bad_annotations=(
                event_config.mute_bad_annotations
                if args.mute_bad_annotations is None
                else args.mute_bad_annotations
            ),
        )

        events = find_binary_channel_events(raw, event_config)
        summary = summarize_events(events)
        print_event_summary(summary)

    elif args.command == "write-events":
        config = load_config(args.config)

        result = write_bids_events_for_recording(
            config,
            subject=args.subject,
            task=args.task,
            session=args.session,
            run=args.run,
            on_existing="overwrite" if args.overwrite else "skip",
        )

        print(f"Status: {result.status}")
        if result.message:
            print(f"Message: {result.message}")
        if result.n_events is not None:
            print(f"Events: {result.n_events}")
        if result.unique_ids is not None:
            print(f"Unique IDs: {result.unique_ids}")
        print(f"Output: {result.output_path}")
    
    elif args.command == "init-project":
        result = init_project(
            args.project_name,
            base_dir=args.base_dir,
            overwrite=args.overwrite,
        )

        print(f"Project root: {result.project_root}")
        print(f"Status: {result.status}")
        print(f"Created paths: {len(result.created_paths)}")
        print(f"Skipped existing paths: {len(result.skipped_paths)}")

        if result.created_paths:
            print("\nCreated:")
            for path in result.created_paths:
                print(f"  {path}")

        if result.skipped_paths:
            print("\nSkipped existing:")
            for path in result.skipped_paths:
                print(f"  {path}")

        return

    else:
        parser.print_help()