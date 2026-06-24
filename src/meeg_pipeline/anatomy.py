from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import mne
import pandas as pd
from mne import bem as mne_bem

ExistingOutputPolicy = Literal["skip", "overwrite"]
PatternLike = str | Sequence[str]

DEFAULT_T1_PATTERNS: tuple[str, ...] = (
    "{subject}/anat/T1.mgz",
    "{subject}/anat/*T1w*.nii*",
)
DEFAULT_T2_PATTERNS: tuple[str, ...] = (
    "{subject}/anat/T2.mgz",
    "{subject}/anat/*T2w*.nii*",
)


@dataclass(frozen=True)
class AnatomyCommandResult:
    """Status object for external anatomy commands."""

    subject: str
    step: str
    status: str
    path: str = ""
    returncode: int | None = None
    message: str = ""
    command: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnatomyFileResult:
    """Status object for anatomy files created inside the project."""

    subject: str
    step: str
    path: str
    status: str
    message: str = ""


def _path_or_none(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    return Path(path).expanduser().resolve()


def _stringify_command(command: Sequence[str | Path]) -> tuple[str, ...]:
    return tuple(str(item) for item in command)


def _subject_label(subject: str) -> str:
    """Return a FreeSurfer/MNE subject name without changing valid labels."""
    subject = str(subject)
    return subject.removeprefix("sub-") if subject.startswith("sub-") else subject


def _subject_variants(subject: str) -> list[str]:
    """Return possible subject folder labels with and without ``sub-``."""
    stripped = _subject_label(subject)
    prefixed = f"sub-{stripped}"
    variants = [str(subject), stripped, prefixed]
    result: list[str] = []
    for variant in variants:
        if variant not in result:
            result.append(variant)
    return result


def subject_dir(subjects_dir: str | Path, subject: str) -> Path:
    """Return the FreeSurfer subject directory for one subject."""
    return Path(subjects_dir).expanduser().resolve() / _subject_label(subject)


def _as_patterns(patterns: PatternLike) -> tuple[str, ...]:
    """Normalize one or more glob patterns while preserving strings."""
    if isinstance(patterns, str):
        return (patterns,)
    return tuple(str(pattern) for pattern in patterns)


def _glob_one(root: Path, patterns: PatternLike, subject: str) -> Path | None:
    """Find one path matching one of the patterns that contain ``{subject}``."""
    for pattern in _as_patterns(patterns):
        for subject_variant in _subject_variants(subject):
            resolved_pattern = pattern.format(subject=subject_variant)
            matches = sorted(root.glob(resolved_pattern))
            if matches:
                return matches[0].expanduser().resolve()
    return None


def find_anatomical_image(
    mri_root: str | Path,
    subject: str,
    *,
    patterns: PatternLike,
) -> Path | None:
    """Find a T1/T2 image for one subject using configurable glob patterns."""
    root = Path(mri_root).expanduser().resolve()
    if not root.exists():
        return None
    return _glob_one(root, patterns, subject)


def find_anatomical_images(
    mri_root: str | Path,
    subject: str,
    *,
    t1_patterns: PatternLike = DEFAULT_T1_PATTERNS,
    t2_patterns: PatternLike = DEFAULT_T2_PATTERNS,
) -> tuple[Path | None, Path | None]:
    """Find T1 and T2 images for one subject.

    Multiple patterns are tried in order. This allows subject-specific mixes of
    already prepared ``T1.mgz`` files and converted BIDS-like ``*T1w*.nii*``
    files inside the same project.
    """
    return (
        find_anatomical_image(mri_root, subject, patterns=t1_patterns),
        find_anatomical_image(mri_root, subject, patterns=t2_patterns),
    )


def _discover_subject_dirs(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {path.name for path in root.iterdir() if path.is_dir()}


def discover_mri_subjects(
    mri_root: str | Path,
    *,
    t1_patterns: PatternLike = DEFAULT_T1_PATTERNS,
    t2_patterns: PatternLike = DEFAULT_T2_PATTERNS,
    include_t2_only: bool = True,
) -> list[str]:
    """Discover subjects with converted anatomical images."""
    root = Path(mri_root).expanduser().resolve()
    subjects = _discover_subject_dirs(root)
    discovered: list[str] = []
    for subject in sorted(subjects):
        t1, t2 = find_anatomical_images(
            root,
            subject,
            t1_patterns=t1_patterns,
            t2_patterns=t2_patterns,
        )
        if t1 is not None or (include_t2_only and t2 is not None):
            discovered.append(subject)
    return discovered


def discover_raw_mri_subjects(mri_raw_root: str | Path) -> list[str]:
    """Discover subjects with raw MRI folders."""
    return sorted(_discover_subject_dirs(Path(mri_raw_root).expanduser().resolve()))


def resolve_subjects(
    subjects: str | Sequence[str],
    *,
    mri_root: str | Path | None = None,
    mri_raw_root: str | Path | None = None,
    subjects_dir: str | Path | None = None,
    t1_patterns: PatternLike = DEFAULT_T1_PATTERNS,
    t2_patterns: PatternLike = DEFAULT_T2_PATTERNS,
) -> list[str]:
    """Resolve notebook-style subject selections.

    With ``subjects="all"``, subjects are discovered from all supplied roots and
    combined. This supports mixed projects where some subjects already have a
    prepared ``T1.mgz`` under ``mri_root`` while other subjects only have raw
    DICOM folders under ``mri_raw_root``.
    """
    if subjects != "all":
        if isinstance(subjects, str):
            return [_subject_label(subjects)]
        return [_subject_label(subject) for subject in subjects]

    found: set[str] = set()

    if mri_root is not None:
        found.update(
            discover_mri_subjects(
                mri_root,
                t1_patterns=t1_patterns,
                t2_patterns=t2_patterns,
                include_t2_only=True,
            )
        )

    if mri_raw_root is not None:
        found.update(discover_raw_mri_subjects(mri_raw_root))

    if subjects_dir is not None:
        root = Path(subjects_dir).expanduser().resolve()
        if root.exists():
            found.update(
                path.name
                for path in root.iterdir()
                if path.is_dir() and path.name != "fsaverage"
            )

    return sorted(_subject_label(subject) for subject in found)


def make_freesurfer_env(
    *,
    subjects_dir: str | Path,
    freesurfer_home: str | Path | None = None,
    mne_path: str | Path | None = None,
) -> dict[str, str]:
    """Create an environment for FreeSurfer/MNE command-line tools."""
    subjects_dir = Path(subjects_dir).expanduser().resolve()
    freesurfer_home = _path_or_none(
        freesurfer_home or os.environ.get("FREESURFER_HOME") or "/Applications/freesurfer"
    )
    mne_path = _path_or_none(mne_path)

    env = os.environ.copy()
    env["SUBJECTS_DIR"] = str(subjects_dir)
    env.setdefault("COPYFILE_DISABLE", "1")
    env.setdefault("TMPDIR", "/tmp")

    path_parts: list[str] = []

    if freesurfer_home is not None:
        env["FREESURFER_HOME"] = str(freesurfer_home)
        path_parts.append(str(freesurfer_home / "bin"))

        misc_bin = freesurfer_home / "lib" / "misc" / "bin"
        misc_lib = freesurfer_home / "lib" / "misc" / "lib"
        gcc_lib = freesurfer_home / "lib" / "gcc" / "lib"

        if misc_bin.exists():
            path_parts.append(str(misc_bin))
        if misc_lib.exists():
            env["MISC_LIB"] = str(misc_lib)
            env["LD_LIBRARY_PATH"] = str(misc_lib)
            env["DYLD_LIBRARY_PATH"] = str(misc_lib)
        if gcc_lib.exists():
            env["DYLD_LIBRARY_PATH"] = str(gcc_lib)

    if mne_path is not None:
        path_parts.append(str(mne_path / "bin"))

    existing_path = env.get("PATH", "")
    env["PATH"] = os.pathsep.join([*path_parts, existing_path])

    return env



def freesurfer_derivatives_dir(subjects_dir: str | Path) -> Path:
    """Return the FreeSurfer derivatives root for a configured subjects_dir.

    If ``subjects_dir`` points to ``derivatives/freesurfer/subjects``, this
    returns ``derivatives/freesurfer``. Otherwise, the parent of subjects_dir is
    used.
    """
    subjects_dir = Path(subjects_dir).expanduser().resolve()
    if subjects_dir.name == "subjects":
        return subjects_dir.parent
    return subjects_dir.parent


def freesurfer_provenance_path(subjects_dir: str | Path) -> Path:
    """Return the project-level FreeSurfer provenance JSON path."""
    return freesurfer_derivatives_dir(subjects_dir) / "freesurfer_provenance.json"


def _capture_command_output(
    command: Sequence[str | Path],
    *,
    env: dict[str, str] | None = None,
) -> tuple[int | None, str]:
    """Run a small version command and return return code plus output."""
    try:
        completed = subprocess.run(
            _stringify_command(command),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None, ""

    return completed.returncode, completed.stdout.strip()


def freesurfer_version_info(
    *,
    subjects_dir: str | Path,
    freesurfer_home: str | Path | None = None,
) -> dict[str, Any]:
    """Collect FreeSurfer/MNE environment information for documentation."""
    subjects_dir = Path(subjects_dir).expanduser().resolve()
    env = make_freesurfer_env(
        subjects_dir=subjects_dir,
        freesurfer_home=freesurfer_home,
    )

    recon_all = shutil.which("recon-all", path=env.get("PATH")) or "recon-all"
    freeview = shutil.which("freeview", path=env.get("PATH")) or "freeview"
    mri_convert = shutil.which("mri_convert", path=env.get("PATH")) or "mri_convert"

    recon_code, recon_version = _capture_command_output(
        [recon_all, "--version"],
        env=env,
    )
    freeview_code, freeview_version = _capture_command_output(
        [freeview, "--version"],
        env=env,
    )
    mri_convert_code, mri_convert_version = _capture_command_output(
        [mri_convert, "--version"],
        env=env,
    )

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "freesurfer_home": env.get("FREESURFER_HOME", ""),
        "subjects_dir": str(subjects_dir),
        "commands": {
            "recon_all": str(recon_all),
            "freeview": str(freeview),
            "mri_convert": str(mri_convert),
        },
        "versions": {
            "recon_all": recon_version,
            "freeview": freeview_version,
            "mri_convert": mri_convert_version,
            "mne": mne.__version__,
            "python": sys.version.replace("\n", " "),
        },
        "returncodes": {
            "recon_all_version": recon_code,
            "freeview_version": freeview_code,
            "mri_convert_version": mri_convert_code,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
    }


def write_freesurfer_provenance(
    *,
    subjects_dir: str | Path,
    freesurfer_home: str | Path | None = None,
    path: str | Path | None = None,
    on_existing: ExistingOutputPolicy = "overwrite",
) -> AnatomyFileResult:
    """Write project-level FreeSurfer software provenance.

    This documents the FreeSurfer installation used by the anatomy notebooks. It
    is intentionally project-level rather than subject-level; FreeSurfer itself
    also writes detailed per-subject logs inside each subject's ``scripts``
    directory during ``recon-all``.
    """
    subjects_dir = Path(subjects_dir).expanduser().resolve()
    output_path = (
        freesurfer_provenance_path(subjects_dir)
        if path is None
        else Path(path).expanduser().resolve()
    )

    if output_path.exists() and on_existing == "skip":
        return AnatomyFileResult(
            subject="project",
            step="freesurfer_provenance",
            path=str(output_path),
            status="skipped_existing",
            message="FreeSurfer provenance file already exists.",
        )

    info = freesurfer_version_info(
        subjects_dir=subjects_dir,
        freesurfer_home=freesurfer_home,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(info, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return AnatomyFileResult(
        subject="project",
        step="freesurfer_provenance",
        path=str(output_path),
        status="written",
        message=info["versions"].get("recon_all", ""),
    )

def run_streamed_subprocess(
    command: Sequence[str | Path],
    *,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
    dry_run: bool = False,
) -> int:
    """Run a command and stream combined stdout/stderr to the notebook."""
    command = _stringify_command(command)
    print("Running:", " ".join(command))

    if dry_run:
        print("Dry run only; command was not executed.")
        return 0

    process = subprocess.Popen(
        command,
        env=env,
        cwd=None if cwd is None else str(Path(cwd).expanduser().resolve()),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)

    return process.wait()


def _is_nifti(path: Path) -> bool:
    return path.name.endswith(".nii") or path.name.endswith(".nii.gz")


def _is_mgz(path: Path) -> bool:
    return path.suffix in {".mgz", ".mgh"}


def _source_path_for_modality(
    mri_raw_root: str | Path,
    subject: str,
    *,
    pattern: str,
) -> Path | None:
    root = Path(mri_raw_root).expanduser().resolve()
    if not root.exists():
        return None
    return _glob_one(root, pattern, subject)


def _converted_anat_dir(mri_root: str | Path, subject: str) -> Path:
    return Path(mri_root).expanduser().resolve() / _subject_label(subject) / "anat"


def converted_nifti_path(mri_root: str | Path, subject: str, modality: Literal["T1w", "T2w"]) -> Path:
    subject = _subject_label(subject)
    return _converted_anat_dir(mri_root, subject) / f"{subject}_{modality}.nii.gz"


def converted_mgz_path(mri_root: str | Path, subject: str, modality: Literal["T1", "T2"]) -> Path:
    subject = _subject_label(subject)
    return _converted_anat_dir(mri_root, subject) / f"{modality}.mgz"


def _find_dcm2niix_output(output_dir: Path, output_stem: str) -> Path | None:
    candidates = sorted(output_dir.glob(f"{output_stem}*.nii.gz"))
    if candidates:
        return candidates[0]
    candidates = sorted(output_dir.glob(f"{output_stem}*.nii"))
    if candidates:
        return candidates[0]
    return None


def convert_raw_mri_modality(
    subject: str,
    *,
    mri_raw_root: str | Path,
    mri_root: str | Path,
    source_pattern: str,
    modality: Literal["T1", "T2"],
    freesurfer_home: str | Path | None = None,
    make_mgz: bool = True,
    on_existing: ExistingOutputPolicy = "skip",
    dry_run: bool = False,
) -> list[AnatomyCommandResult | AnatomyFileResult]:
    """Convert one raw MRI modality to standardized NIfTI and optional MGZ."""
    subject = _subject_label(subject)
    results: list[AnatomyCommandResult | AnatomyFileResult] = []
    source = _source_path_for_modality(mri_raw_root, subject, pattern=source_pattern)
    modality_bids = "T1w" if modality == "T1" else "T2w"
    nifti_path = converted_nifti_path(mri_root, subject, modality_bids)
    mgz_path = converted_mgz_path(mri_root, subject, modality)

    if source is None:
        status = "missing_t1_source" if modality == "T1" else "missing_optional_t2_source"
        return [
            AnatomyFileResult(
                subject=subject,
                step=f"convert_{modality.lower()}",
                path=str(Path(mri_raw_root).expanduser().resolve()),
                status=status,
                message=f"No raw {modality} source matched pattern {source_pattern!r}.",
            )
        ]

    nifti_path.parent.mkdir(parents=True, exist_ok=True)

    if nifti_path.exists() and on_existing == "skip":
        results.append(
            AnatomyFileResult(
                subject=subject,
                step=f"convert_{modality.lower()}_nifti",
                path=str(nifti_path),
                status="skipped_existing",
                message="Converted NIfTI already exists.",
            )
        )
    elif source.is_dir():
        output_stem = f"{subject}_{modality_bids}"
        dcm2niix = shutil.which("dcm2niix")
        if dcm2niix is None and not dry_run:
            return [
                AnatomyCommandResult(
                    subject=subject,
                    step=f"convert_{modality.lower()}_nifti",
                    status="missing_converter",
                    path=str(nifti_path),
                    returncode=None,
                    message=(
                        "dcm2niix is required for DICOM-to-NIfTI conversion but "
                        "was not found on PATH. Install it, for example with "
                        "'brew install dcm2niix', or provide an already converted "
                        f"{modality} input under mri_root."
                    ),
                    command=("dcm2niix",),
                )
            ]
        command = [
            dcm2niix or "dcm2niix",
            "-z",
            "y",
            "-f",
            output_stem,
            "-o",
            nifti_path.parent,
            source,
        ]
        returncode = run_streamed_subprocess(command, dry_run=dry_run)
        generated = _find_dcm2niix_output(nifti_path.parent, output_stem)
        if returncode != 0:
            return [
                AnatomyCommandResult(
                    subject=subject,
                    step=f"convert_{modality.lower()}_nifti",
                    status="failed",
                    path=str(nifti_path),
                    returncode=returncode,
                    message=f"dcm2niix failed for {source}.",
                    command=_stringify_command(command),
                )
            ]
        if generated is not None and generated != nifti_path and not dry_run:
            if nifti_path.exists():
                nifti_path.unlink()
            generated.rename(nifti_path)
        results.append(
            AnatomyCommandResult(
                subject=subject,
                step=f"convert_{modality.lower()}_nifti",
                status="written",
                path=str(nifti_path),
                returncode=returncode,
                command=_stringify_command(command),
            )
        )
    elif _is_nifti(source):
        if not dry_run:
            shutil.copy2(source, nifti_path)
        results.append(
            AnatomyFileResult(
                subject=subject,
                step=f"convert_{modality.lower()}_nifti",
                path=str(nifti_path),
                status="written",
                message=f"Copied from {source}.",
            )
        )
    elif _is_mgz(source):
        env = make_freesurfer_env(
            subjects_dir=Path(mri_root).expanduser().resolve(),
            freesurfer_home=freesurfer_home,
        )
        mri_convert = shutil.which("mri_convert", path=env.get("PATH")) or "mri_convert"
        command = [mri_convert, source, nifti_path]
        returncode = run_streamed_subprocess(command, env=env, dry_run=dry_run)
        results.append(
            AnatomyCommandResult(
                subject=subject,
                step=f"convert_{modality.lower()}_nifti",
                status="written" if returncode == 0 else "failed",
                path=str(nifti_path),
                returncode=returncode,
                command=_stringify_command(command),
            )
        )
        if returncode != 0:
            return results
    else:
        return [
            AnatomyFileResult(
                subject=subject,
                step=f"convert_{modality.lower()}_nifti",
                path=str(source),
                status="unsupported_source",
                message="Source must be a DICOM directory, NIfTI file, or MGZ/MGH file.",
            )
        ]

    if make_mgz:
        if mgz_path.exists() and on_existing == "skip":
            results.append(
                AnatomyFileResult(
                    subject=subject,
                    step=f"convert_{modality.lower()}_mgz",
                    path=str(mgz_path),
                    status="skipped_existing",
                    message="Converted MGZ already exists.",
                )
            )
        else:
            env = make_freesurfer_env(
                subjects_dir=Path(mri_root).expanduser().resolve(),
                freesurfer_home=freesurfer_home,
            )
            mri_convert = shutil.which("mri_convert", path=env.get("PATH")) or "mri_convert"
            command = [mri_convert, nifti_path, mgz_path]
            returncode = run_streamed_subprocess(command, env=env, dry_run=dry_run)
            results.append(
                AnatomyCommandResult(
                    subject=subject,
                    step=f"convert_{modality.lower()}_mgz",
                    status="written" if returncode == 0 else "failed",
                    path=str(mgz_path),
                    returncode=returncode,
                    command=_stringify_command(command),
                )
            )

    return results


def _skip_existing_anatomical_input_result(
    subject: str,
    *,
    modality: Literal["T1", "T2"],
    path: Path,
) -> AnatomyFileResult:
    """Return a result row for an already prepared anatomical input."""
    return AnatomyFileResult(
        subject=_subject_label(subject),
        step=f"prepare_{modality.lower()}_input",
        path=str(path),
        status="skipped_existing",
        message=f"Standardized {modality} input already exists.",
    )


def prepare_anatomical_inputs_for_subject(
    subject: str,
    *,
    mri_raw_root: str | Path,
    mri_root: str | Path,
    t1_source_pattern: str = "{subject}/T1",
    t2_source_pattern: str = "{subject}/T2",
    t1_patterns: PatternLike = DEFAULT_T1_PATTERNS,
    t2_patterns: PatternLike = DEFAULT_T2_PATTERNS,
    freesurfer_home: str | Path | None = None,
    make_mgz: bool = True,
    on_existing: ExistingOutputPolicy = "skip",
    dry_run: bool = False,
) -> list[AnatomyCommandResult | AnatomyFileResult]:
    """Prepare standardized T1/T2 inputs for one subject.

    The function first checks whether a standardized anatomical input already
    exists under ``mri_root``. If so, conversion is skipped for that modality.
    Otherwise it attempts to create the input from raw MRI data under
    ``mri_raw_root``. T1 is required for the standard recon-all workflow; T2 is
    optional and may be missing for some subjects.
    """
    subject = _subject_label(subject)
    results: list[AnatomyCommandResult | AnatomyFileResult] = []

    existing_t1 = find_anatomical_image(
        mri_root,
        subject,
        patterns=t1_patterns,
    )
    if existing_t1 is not None and on_existing == "skip":
        results.append(
            _skip_existing_anatomical_input_result(
                subject,
                modality="T1",
                path=existing_t1,
            )
        )
    else:
        results.extend(
            convert_raw_mri_modality(
                subject,
                mri_raw_root=mri_raw_root,
                mri_root=mri_root,
                source_pattern=t1_source_pattern,
                modality="T1",
                freesurfer_home=freesurfer_home,
                make_mgz=make_mgz,
                on_existing=on_existing,
                dry_run=dry_run,
            )
        )

    existing_t2 = find_anatomical_image(
        mri_root,
        subject,
        patterns=t2_patterns,
    )
    if existing_t2 is not None and on_existing == "skip":
        results.append(
            _skip_existing_anatomical_input_result(
                subject,
                modality="T2",
                path=existing_t2,
            )
        )
    else:
        results.extend(
            convert_raw_mri_modality(
                subject,
                mri_raw_root=mri_raw_root,
                mri_root=mri_root,
                source_pattern=t2_source_pattern,
                modality="T2",
                freesurfer_home=freesurfer_home,
                make_mgz=make_mgz,
                on_existing=on_existing,
                dry_run=dry_run,
            )
        )

    return results


def prepare_anatomical_inputs_for_subjects(
    subjects: Iterable[str],
    *,
    mri_raw_root: str | Path,
    mri_root: str | Path,
    t1_source_pattern: str = "{subject}/T1",
    t2_source_pattern: str = "{subject}/T2",
    t1_patterns: PatternLike = DEFAULT_T1_PATTERNS,
    t2_patterns: PatternLike = DEFAULT_T2_PATTERNS,
    freesurfer_home: str | Path | None = None,
    make_mgz: bool = True,
    on_existing: ExistingOutputPolicy = "skip",
    dry_run: bool = False,
) -> list[AnatomyCommandResult | AnatomyFileResult]:
    """Prepare standardized T1/T2 inputs for multiple subjects."""
    results: list[AnatomyCommandResult | AnatomyFileResult] = []
    for subject in subjects:
        results.extend(
            prepare_anatomical_inputs_for_subject(
                subject,
                mri_raw_root=mri_raw_root,
                mri_root=mri_root,
                t1_source_pattern=t1_source_pattern,
                t2_source_pattern=t2_source_pattern,
                t1_patterns=t1_patterns,
                t2_patterns=t2_patterns,
                freesurfer_home=freesurfer_home,
                make_mgz=make_mgz,
                on_existing=on_existing,
                dry_run=dry_run,
            )
        )
    return results


def mri_conversion_status_to_dataframe(
    subjects: Iterable[str],
    *,
    mri_raw_root: str | Path,
    mri_root: str | Path,
    t1_source_pattern: str = "{subject}/T1",
    t2_source_pattern: str = "{subject}/T2",
    t1_patterns: PatternLike = DEFAULT_T1_PATTERNS,
    t2_patterns: PatternLike = DEFAULT_T2_PATTERNS,
) -> pd.DataFrame:
    """Summarize raw and standardized MRI inputs.

    A subject can already have standardized inputs under ``mri_root`` even when
    no raw DICOM folder exists. In that case ``01_convert_mri`` can skip that
    subject while ``02_recon`` can still use the existing T1/T2 input.
    """
    rows = []
    for subject in subjects:
        subject = _subject_label(subject)
        t1_source = _source_path_for_modality(mri_raw_root, subject, pattern=t1_source_pattern)
        t2_source = _source_path_for_modality(mri_raw_root, subject, pattern=t2_source_pattern)
        existing_t1 = find_anatomical_image(mri_root, subject, patterns=t1_patterns)
        existing_t2 = find_anatomical_image(mri_root, subject, patterns=t2_patterns)
        t1_nifti = converted_nifti_path(mri_root, subject, "T1w")
        t2_nifti = converted_nifti_path(mri_root, subject, "T2w")
        t1_mgz = converted_mgz_path(mri_root, subject, "T1")
        t2_mgz = converted_mgz_path(mri_root, subject, "T2")
        rows.append(
            {
                "subject": subject,
                "t1_ready": existing_t1 is not None,
                "t1_ready_path": "" if existing_t1 is None else str(existing_t1),
                "t2_ready": existing_t2 is not None,
                "t2_ready_path": "" if existing_t2 is None else str(existing_t2),
                "t1_source_exists": t1_source is not None,
                "t1_source_path": "" if t1_source is None else str(t1_source),
                "t2_source_exists": t2_source is not None,
                "t2_source_path": "" if t2_source is None else str(t2_source),
                "t1_nifti_exists": t1_nifti.exists(),
                "t1_nifti_path": str(t1_nifti),
                "t2_nifti_exists": t2_nifti.exists(),
                "t2_nifti_path": str(t2_nifti),
                "t1_mgz_exists": t1_mgz.exists(),
                "t1_mgz_path": str(t1_mgz),
                "t2_mgz_exists": t2_mgz.exists(),
                "t2_mgz_path": str(t2_mgz),
            }
        )
    return pd.DataFrame(rows)


def default_t1_path(mri_root: str | Path, subject: str) -> Path:
    """Return the standardized T1 NIfTI path used by the anatomy notebooks."""
    return converted_nifti_path(mri_root, subject, "T1w")


def run_recon_all(
    subject: str,
    *,
    mri_root: str | Path,
    subjects_dir: str | Path,
    t1_path: str | Path | None = None,
    t2_path: str | Path | None = None,
    t1_patterns: PatternLike = DEFAULT_T1_PATTERNS,
    t2_patterns: PatternLike = DEFAULT_T2_PATTERNS,
    use_t2: bool = False,
    freesurfer_home: str | Path | None = None,
    on_existing: ExistingOutputPolicy = "skip",
    dry_run: bool = False,
) -> AnatomyCommandResult:
    """Run FreeSurfer ``recon-all`` for one subject.

    T1 is required. T2 is optional and only used when ``use_t2=True`` and a T2
    image exists. T2-only subjects are reported as unsupported for this standard
    recon-all workflow.
    """
    subject = _subject_label(subject)
    subjects_dir = Path(subjects_dir).expanduser().resolve()
    subject_path = subject_dir(subjects_dir, subject)

    if t1_path is None or t2_path is None:
        discovered_t1, discovered_t2 = find_anatomical_images(
            mri_root,
            subject,
            t1_patterns=t1_patterns,
            t2_patterns=t2_patterns,
        )
        if t1_path is None:
            t1_path = discovered_t1
        if t2_path is None:
            t2_path = discovered_t2

    t1_path = None if t1_path is None else Path(t1_path).expanduser().resolve()
    t2_path = None if t2_path is None else Path(t2_path).expanduser().resolve()

    if subject_path.exists() and on_existing == "skip":
        return AnatomyCommandResult(
            subject=subject,
            step="recon_all",
            status="skipped_existing",
            path=str(subject_path),
            message=f"FreeSurfer subject already exists: {subject_path}",
        )

    if t1_path is None or not t1_path.exists():
        status = "unsupported_t2_only" if t2_path is not None and t2_path.exists() else "missing_t1"
        return AnatomyCommandResult(
            subject=subject,
            step="recon_all",
            status=status,
            path="" if t1_path is None else str(t1_path),
            message="T1 image is required for the standard recon-all workflow.",
        )

    subjects_dir.mkdir(parents=True, exist_ok=True)
    env = make_freesurfer_env(
        subjects_dir=subjects_dir,
        freesurfer_home=freesurfer_home,
    )

    recon = shutil.which("recon-all", path=env.get("PATH")) or "recon-all"
    command: list[str | Path]
    command = [recon, "-sd", subjects_dir, "-s", subject]

    orig_mgz = subject_path / "mri" / "orig.mgz"
    if not (subject_path.exists() and orig_mgz.exists()):
        command.extend(["-i", t1_path])

    if use_t2:
        if t2_path is not None and t2_path.exists():
            command.extend(["-T2", t2_path, "-T2pial"])
        else:
            print(
                f"T2 was requested for {subject}, but no T2 image was found. "
                "Running T1-only recon-all."
            )

    command.append("-all")

    returncode = run_streamed_subprocess(command, env=env, dry_run=dry_run)

    if returncode != 0:
        return AnatomyCommandResult(
            subject=subject,
            step="recon_all",
            status="failed",
            path=str(subject_path),
            returncode=returncode,
            message=f"recon-all failed with code {returncode}.",
            command=_stringify_command(command),
        )

    return AnatomyCommandResult(
        subject=subject,
        step="recon_all",
        status="written",
        path=str(subject_path),
        returncode=returncode,
        command=_stringify_command(command),
    )


def run_recon_all_for_subjects(
    subjects: Iterable[str],
    *,
    mri_root: str | Path,
    subjects_dir: str | Path,
    t1_patterns: PatternLike = DEFAULT_T1_PATTERNS,
    t2_patterns: PatternLike = DEFAULT_T2_PATTERNS,
    use_t2: bool = False,
    freesurfer_home: str | Path | None = None,
    on_existing: ExistingOutputPolicy = "skip",
    dry_run: bool = False,
) -> list[AnatomyCommandResult]:
    """Run ``recon-all`` for multiple subjects."""
    return [
        run_recon_all(
            subject,
            mri_root=mri_root,
            subjects_dir=subjects_dir,
            t1_patterns=t1_patterns,
            t2_patterns=t2_patterns,
            use_t2=use_t2,
            freesurfer_home=freesurfer_home,
            on_existing=on_existing,
            dry_run=dry_run,
        )
        for subject in subjects
    ]


def apply_watershed_bem(
    subject: str,
    *,
    subjects_dir: str | Path,
    freesurfer_home: str | Path | None = None,
    volume: str = "T1",
    overwrite: bool = True,
    verbose: bool | str | int | None = True,
) -> AnatomyFileResult:
    """Create watershed BEM surfaces for one FreeSurfer subject."""
    subject = _subject_label(subject)
    subjects_dir = Path(subjects_dir).expanduser().resolve()
    env = make_freesurfer_env(
        subjects_dir=subjects_dir,
        freesurfer_home=freesurfer_home,
    )

    old_env = os.environ.copy()
    os.environ.update(env)
    try:
        mne_bem.make_watershed_bem(
            subject=subject,
            subjects_dir=subjects_dir,
            volume=volume,
            overwrite=overwrite,
            verbose=verbose,
        )
    finally:
        os.environ.clear()
        os.environ.update(old_env)

    path = subjects_dir / subject / "bem"
    return AnatomyFileResult(
        subject=subject,
        step="watershed_bem",
        path=str(path),
        status="written",
    )


def make_dense_scalp_surfaces(
    subject: str,
    *,
    subjects_dir: str | Path,
    force: bool = True,
    overwrite: bool = True,
    verbose: bool | str | int | None = True,
) -> AnatomyFileResult:
    """Create dense scalp surfaces that help coregistration/QC."""
    subject = _subject_label(subject)
    subjects_dir = Path(subjects_dir).expanduser().resolve()

    mne_bem.make_scalp_surfaces(
        subject=subject,
        subjects_dir=subjects_dir,
        force=force,
        overwrite=overwrite,
        verbose=verbose,
    )

    path = subjects_dir / subject / "bem"
    return AnatomyFileResult(
        subject=subject,
        step="dense_scalp_surfaces",
        path=str(path),
        status="written",
    )


def bem_model_path(
    subjects_dir: str | Path,
    subject: str,
    *,
    ico: int = 4,
    conductivity: Sequence[float] = (0.3,),
) -> Path:
    """Return path for a BEM model file."""
    subject = _subject_label(subject)
    n_layers = len(tuple(conductivity))
    return Path(subjects_dir).expanduser().resolve() / subject / "bem" / f"{subject}-{ico}-{n_layers}layer-bem.fif"


def bem_solution_path(
    subjects_dir: str | Path,
    subject: str,
    *,
    ico: int = 4,
    conductivity: Sequence[float] = (0.3,),
) -> Path:
    """Return path for a BEM solution file."""
    subject = _subject_label(subject)
    n_layers = len(tuple(conductivity))
    return Path(subjects_dir).expanduser().resolve() / subject / "bem" / f"{subject}-{ico}-{n_layers}layer-bem-sol.fif"


def make_bem_model_and_solution(
    subject: str,
    *,
    subjects_dir: str | Path,
    ico: int = 4,
    conductivity: Sequence[float] = (0.3,),
    on_existing: ExistingOutputPolicy = "skip",
    verbose: bool | str | int | None = True,
) -> AnatomyFileResult:
    """Create and save BEM model plus BEM solution."""
    subject = _subject_label(subject)
    subjects_dir = Path(subjects_dir).expanduser().resolve()
    model_path = bem_model_path(subjects_dir, subject, ico=ico, conductivity=conductivity)
    solution_path = bem_solution_path(subjects_dir, subject, ico=ico, conductivity=conductivity)

    if solution_path.exists() and on_existing == "skip":
        return AnatomyFileResult(
            subject=subject,
            step="bem_solution",
            path=str(solution_path),
            status="skipped_existing",
            message="BEM solution already exists.",
        )

    model_path.parent.mkdir(parents=True, exist_ok=True)
    model = mne.make_bem_model(
        subject=subject,
        ico=ico,
        conductivity=tuple(float(value) for value in conductivity),
        subjects_dir=subjects_dir,
        verbose=verbose,
    )
    mne.write_bem_surfaces(model_path, model, overwrite=on_existing == "overwrite")

    solution = mne.make_bem_solution(model, verbose=verbose)
    mne.write_bem_solution(solution_path, solution, overwrite=on_existing == "overwrite")

    return AnatomyFileResult(
        subject=subject,
        step="bem_solution",
        path=str(solution_path),
        status="written",
    )


def source_space_path(
    subjects_dir: str | Path,
    subject: str,
    *,
    spacing: str = "ico5",
) -> Path:
    """Return path for a surface source space file."""
    subject = _subject_label(subject)
    return Path(subjects_dir).expanduser().resolve() / subject / "bem" / f"{subject}-{spacing}-src.fif"


def volume_source_space_path(
    subjects_dir: str | Path,
    subject: str,
    *,
    pos: float = 5.0,
) -> Path:
    """Return path for a volume source space file."""
    subject = _subject_label(subject)
    pos_label = str(pos).replace(".", "p")
    return Path(subjects_dir).expanduser().resolve() / subject / "bem" / f"{subject}-{pos_label}mm-vol-src.fif"


def setup_surface_source_space(
    subject: str,
    *,
    subjects_dir: str | Path,
    spacing: str = "ico5",
    surface: str = "white",
    add_dist: bool | str = False,
    n_jobs: int = 1,
    on_existing: ExistingOutputPolicy = "skip",
    verbose: bool | str | int | None = True,
) -> AnatomyFileResult:
    """Create and save a cortical surface source space."""
    subject = _subject_label(subject)
    path = source_space_path(subjects_dir, subject, spacing=spacing)

    if path.exists() and on_existing == "skip":
        return AnatomyFileResult(
            subject=subject,
            step="surface_source_space",
            path=str(path),
            status="skipped_existing",
            message="Source space already exists.",
        )

    src = mne.setup_source_space(
        subject=subject,
        spacing=spacing,
        surface=surface,
        subjects_dir=subjects_dir,
        add_dist=add_dist,
        n_jobs=n_jobs,
        verbose=verbose,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    mne.write_source_spaces(path, src, overwrite=on_existing == "overwrite")

    return AnatomyFileResult(
        subject=subject,
        step="surface_source_space",
        path=str(path),
        status="written",
    )


def compute_source_space_distances(
    subject: str,
    *,
    subjects_dir: str | Path,
    spacing: str = "ico5",
    n_jobs: int = 1,
    on_existing: ExistingOutputPolicy = "overwrite",
    verbose: bool | str | int | None = True,
) -> AnatomyFileResult:
    """Add source-space distances and save the source space again."""
    subject = _subject_label(subject)
    path = source_space_path(subjects_dir, subject, spacing=spacing)

    if not path.exists():
        return AnatomyFileResult(
            subject=subject,
            step="source_space_distances",
            path=str(path),
            status="missing_input",
            message="Surface source space does not exist.",
        )

    src = mne.read_source_spaces(path, verbose=verbose)
    src = mne.add_source_space_distances(src, n_jobs=n_jobs, verbose=verbose)
    mne.write_source_spaces(path, src, overwrite=on_existing == "overwrite")

    return AnatomyFileResult(
        subject=subject,
        step="source_space_distances",
        path=str(path),
        status="written",
    )


def setup_volume_source_space(
    subject: str,
    *,
    subjects_dir: str | Path,
    bem_path: str | Path,
    pos: float = 5.0,
    on_existing: ExistingOutputPolicy = "skip",
    verbose: bool | str | int | None = True,
) -> AnatomyFileResult:
    """Create and save an optional volume source space."""
    subject = _subject_label(subject)
    path = volume_source_space_path(subjects_dir, subject, pos=pos)

    if path.exists() and on_existing == "skip":
        return AnatomyFileResult(
            subject=subject,
            step="volume_source_space",
            path=str(path),
            status="skipped_existing",
            message="Volume source space already exists.",
        )

    src = mne.setup_volume_source_space(
        subject=subject,
        pos=pos,
        bem=bem_path,
        subjects_dir=subjects_dir,
        verbose=verbose,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    mne.write_source_spaces(path, src, overwrite=on_existing == "overwrite")

    return AnatomyFileResult(
        subject=subject,
        step="volume_source_space",
        path=str(path),
        status="written",
    )


def fetch_fsaverage_parcellations(
    *,
    subjects_dir: str | Path,
    fetch_hcp_mmp: bool = True,
    fetch_aparc_sub: bool = True,
) -> None:
    """Fetch optional fsaverage parcellations used by the notebooks."""
    subjects_dir = Path(subjects_dir).expanduser().resolve()

    if fetch_hcp_mmp:
        mne.datasets.fetch_hcp_mmp_parcellation(subjects_dir=subjects_dir, verbose=True)

    if fetch_aparc_sub:
        mne.datasets.fetch_aparc_sub_parcellation(subjects_dir=subjects_dir, verbose=True)


def morph_labels_from_fsaverage(
    subject: str,
    *,
    subjects_dir: str | Path,
    parcellations: Sequence[str] = ("aparc_sub", "HCPMMP1_combined", "HCPMMP1"),
    overwrite: bool = False,
) -> list[AnatomyFileResult]:
    """Morph fsaverage annotation labels to one individual subject."""
    subject = _subject_label(subject)
    subjects_dir = Path(subjects_dir).expanduser().resolve()
    results: list[AnatomyFileResult] = []

    for parc in parcellations:
        output_path = subjects_dir / subject / "label" / f"lh.{parc}.annot"

        if output_path.exists() and not overwrite:
            results.append(
                AnatomyFileResult(
                    subject=subject,
                    step=f"morph_labels_{parc}",
                    path=str(output_path),
                    status="skipped_existing",
                    message="Annotation already exists.",
                )
            )
            continue

        labels = mne.read_labels_from_annot(
            subject="fsaverage",
            parc=parc,
            hemi="both",
            subjects_dir=subjects_dir,
        )
        morphed_labels = mne.morph_labels(
            labels,
            subject_to=subject,
            subject_from="fsaverage",
            subjects_dir=subjects_dir,
            surf_name="pial",
        )
        mne.write_labels_to_annot(
            morphed_labels,
            subject=subject,
            parc=parc,
            subjects_dir=subjects_dir,
            overwrite=True,
        )
        results.append(
            AnatomyFileResult(
                subject=subject,
                step=f"morph_labels_{parc}",
                path=str(output_path),
                status="written",
            )
        )

    return results


def anatomy_status_to_dataframe(
    subjects: Iterable[str],
    *,
    subjects_dir: str | Path,
    mri_root: str | Path | None = None,
    t1_patterns: PatternLike = DEFAULT_T1_PATTERNS,
    t2_patterns: PatternLike = DEFAULT_T2_PATTERNS,
    spacing: str = "ico5",
    bem_ico: int = 4,
    bem_conductivity: Sequence[float] = (0.3,),
) -> pd.DataFrame:
    """Summarize expected anatomy-preparation files for subjects."""
    rows = []
    subjects_dir = Path(subjects_dir).expanduser().resolve()

    for subject in subjects:
        subject = _subject_label(subject)
        fs_subject_dir = subject_dir(subjects_dir, subject)
        t1_path, t2_path = (None, None)
        if mri_root is not None:
            t1_path, t2_path = find_anatomical_images(
                mri_root,
                subject,
                t1_patterns=t1_patterns,
                t2_patterns=t2_patterns,
            )
        bem_sol = bem_solution_path(
            subjects_dir,
            subject,
            ico=bem_ico,
            conductivity=bem_conductivity,
        )
        src = source_space_path(subjects_dir, subject, spacing=spacing)

        rows.append(
            {
                "subject": subject,
                "t1_exists": t1_path is not None and t1_path.exists(),
                "t1_path": "" if t1_path is None else str(t1_path),
                "t2_exists": t2_path is not None and t2_path.exists(),
                "t2_path": "" if t2_path is None else str(t2_path),
                "recon_exists": fs_subject_dir.exists(),
                "bem_dir_exists": (fs_subject_dir / "bem").exists(),
                "inner_skull_exists": (fs_subject_dir / "bem" / "inner_skull.surf").exists(),
                "bem_solution_exists": bem_sol.exists(),
                "bem_solution_path": str(bem_sol),
                "source_space_exists": src.exists(),
                "source_space_path": str(src),
            }
        )

    return pd.DataFrame(rows)


def results_to_dataframe(
    results: Iterable[AnatomyCommandResult | AnatomyFileResult],
) -> pd.DataFrame:
    """Convert anatomy result objects to a notebook-friendly table."""
    rows = []
    for result in results:
        row: dict[str, Any] = {
            "subject": result.subject,
            "step": result.step,
            "status": result.status,
            "path": result.path,
            "message": result.message,
        }
        if isinstance(result, AnatomyCommandResult):
            row["returncode"] = result.returncode
            row["command"] = " ".join(result.command)
        rows.append(row)
    return pd.DataFrame(rows)



def coregistration_trans_path(
    config: Any,
    *,
    subject: str,
    session: str | None = None,
    task: str | None = None,
    run: str | None = None,
    desc: str = "coreg",
) -> Path:
    """Return the expected derivative path for a coregistration transform.

    The transform is stored as a pipeline derivative because it is a manual
    analysis decision derived from the raw recording's digitization and the
    subject's FreeSurfer anatomy.
    """
    subject = _subject_label(subject)
    parts = [f"sub-{subject}"]
    if session is not None:
        parts.append(f"ses-{session}")
    if task is not None:
        parts.append(f"task-{task}")
    if run is not None:
        parts.append(f"run-{run}")

    filename = "_".join(parts + [f"desc-{desc}_trans.fif"])

    if session is None:
        directory = (
            config.paths.derivatives_root
            / f"sub-{subject}"
            / config.bids.datatype
            / "coregistration"
        )
    else:
        directory = (
            config.paths.derivatives_root
            / f"sub-{subject}"
            / f"ses-{session}"
            / config.bids.datatype
            / "coregistration"
        )

    return directory / filename


def coregistration_status_to_dataframe(
    config: Any,
    recordings: Iterable[dict[str, str | None]],
    *,
    trans_desc: str = "coreg",
) -> pd.DataFrame:
    """Summarize raw-BIDS, FreeSurfer, and trans-file status for coregistration."""
    from meeg_pipeline.bids import make_bids_path
    from meeg_pipeline.paths import bids_path_to_path

    rows = []
    subjects_dir = Path(config.freesurfer.subjects_dir).expanduser().resolve()

    for recording in recordings:
        subject = _subject_label(str(recording["subject"]))
        session = recording.get("session")
        task = recording.get("task")
        run = recording.get("run")

        raw_bids_path = make_bids_path(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
            extension=".fif",
        )
        raw_path = bids_path_to_path(raw_bids_path)
        fs_dir = subject_dir(subjects_dir, subject)
        trans_path = coregistration_trans_path(
            config,
            subject=subject,
            session=session,
            task=task,
            run=run,
            desc=trans_desc,
        )

        rows.append(
            {
                "subject": subject,
                "session": session,
                "task": task,
                "run": run,
                "raw_exists": raw_path.exists(),
                "raw_path": str(raw_path),
                "freesurfer_subject_exists": fs_dir.exists(),
                "freesurfer_subject_dir": str(fs_dir),
                "trans_exists": trans_path.exists(),
                "trans_path": str(trans_path),
            }
        )

    return pd.DataFrame(rows)


def first_recording_per_subject(
    recordings: Iterable[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    """Return the first recording for each subject, preserving input order."""
    selected: list[dict[str, str | None]] = []
    seen: set[str] = set()

    for recording in recordings:
        subject = _subject_label(str(recording["subject"]))
        if subject in seen:
            continue
        selected.append(recording)
        seen.add(subject)

    return selected


def launch_coregistration_gui(
    config: Any,
    *,
    subject: str,
    session: str | None = None,
    task: str | None = None,
    run: str | None = None,
    inst_path: str | Path | None = None,
    trans_desc: str = "coreg",
    block_with_input: bool = True,
) -> AnatomyFileResult:
    """Launch the MNE coregistration GUI for one recording.

    The user should save the transform manually to the printed ``trans_path``.
    The function reports whether the expected transform exists after the GUI is
    closed and the user confirms in the notebook.
    """
    from meeg_pipeline.bids import make_bids_path
    from meeg_pipeline.paths import bids_path_to_path

    subject = _subject_label(subject)
    subjects_dir = Path(config.freesurfer.subjects_dir).expanduser().resolve()

    if inst_path is None:
        inst_path = bids_path_to_path(
            make_bids_path(
                config,
                subject=subject,
                session=session,
                task=task,
                run=run,
                extension=".fif",
            )
        )
    else:
        inst_path = Path(inst_path).expanduser().resolve()

    trans_path = coregistration_trans_path(
        config,
        subject=subject,
        session=session,
        task=task,
        run=run,
        desc=trans_desc,
    )
    trans_path.parent.mkdir(parents=True, exist_ok=True)

    if not subjects_dir.exists():
        return AnatomyFileResult(
            subject=subject,
            step="coregistration",
            path=str(trans_path),
            status="missing_subjects_dir",
            message=f"FreeSurfer SUBJECTS_DIR does not exist: {subjects_dir}",
        )

    if not subject_dir(subjects_dir, subject).exists():
        return AnatomyFileResult(
            subject=subject,
            step="coregistration",
            path=str(trans_path),
            status="missing_freesurfer_subject",
            message=f"FreeSurfer subject does not exist: {subject_dir(subjects_dir, subject)}",
        )

    if inst_path is not None and not Path(inst_path).exists():
        return AnatomyFileResult(
            subject=subject,
            step="coregistration",
            path=str(trans_path),
            status="missing_inst",
            message=f"Raw BIDS inst file does not exist: {inst_path}",
        )

    print(f"Launching MNE coregistration GUI for subject {subject}.")
    print(f"SUBJECTS_DIR: {subjects_dir}")
    print(f"Inst file: {inst_path}")
    print("Save the transform from the GUI to:")
    print(trans_path)

    mne.gui.coregistration(
        subject=subject,
        subjects_dir=str(subjects_dir),
        inst=None if inst_path is None else str(inst_path),
    )

    if block_with_input:
        input("After saving the trans file and closing the GUI, press Enter to continue...")

    status = "saved" if trans_path.exists() else "not_saved"
    message = "Transform file exists." if trans_path.exists() else "Expected transform file does not exist yet."

    return AnatomyFileResult(
        subject=subject,
        step="coregistration",
        path=str(trans_path),
        status=status,
        message=message,
    )
