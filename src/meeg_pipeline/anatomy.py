from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mne
import pandas as pd
from mne import bem as mne_bem

ExistingOutputPolicy = Literal["skip", "overwrite"]


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
    """Status object for MNE anatomy files created inside SUBJECTS_DIR."""

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


def subject_dir(subjects_dir: str | Path, subject: str) -> Path:
    """Return the FreeSurfer subject directory for one subject."""
    return Path(subjects_dir).expanduser().resolve() / _subject_label(subject)


def _format_anatomy_pattern(pattern: str, subject: str) -> str:
    """Format an anatomy glob pattern for a subject.

    Patterns can use ``{subject}`` for the plain subject label, for example
    ``1409``, and ``{bids_subject}`` for the BIDS-style label, for example
    ``sub-1409``.
    """
    subject = _subject_label(subject)
    return pattern.format(subject=subject, bids_subject=f"sub-{subject}")


def _first_existing_glob(root: Path, pattern: str) -> Path | None:
    matches = sorted(root.glob(pattern))
    return matches[0] if matches else None


def find_anatomical_images(
    mri_root: str | Path,
    subject: str,
    *,
    t1_pattern: str = "{subject}/anat/*T1w*.nii*",
    t2_pattern: str = "{subject}/anat/*T2w*.nii*",
) -> dict[str, Path | None]:
    """Find T1/T2 images for one subject using configurable glob patterns.

    The returned dictionary contains ``"t1"`` and ``"t2"`` keys. Missing files
    are represented as ``None``. ``subject`` can be passed with or without the
    ``sub-`` prefix.
    """
    mri_root = Path(mri_root).expanduser().resolve()
    subject = _subject_label(subject)

    return {
        "t1": _first_existing_glob(
            mri_root,
            _format_anatomy_pattern(t1_pattern, subject),
        ),
        "t2": _first_existing_glob(
            mri_root,
            _format_anatomy_pattern(t2_pattern, subject),
        ),
    }


def default_t1_path(mri_root: str | Path, subject: str) -> Path:
    """Return the legacy default T1 path used by older anatomy notebooks.

    The legacy folder structure is ``<mri_root>/<subject>/mri/T1.mgz``. New
    projects should prefer ``find_anatomical_images`` with configurable
    ``t1_pattern`` and ``t2_pattern``.
    """
    subject = _subject_label(subject)
    return Path(mri_root).expanduser().resolve() / subject / "mri" / "T1.mgz"


def discover_mri_subjects(
    mri_root: str | Path,
    *,
    t1_pattern: str = "{subject}/anat/*T1w*.nii*",
    t2_pattern: str = "{subject}/anat/*T2w*.nii*",
) -> list[str]:
    """Discover subjects with T1 or T2 images under ``mri_root``.

    This discovery is intentionally permissive: subjects with only a T2 image
    are reported in status tables, even though ``recon-all`` normally still
    requires a T1 image.
    """
    mri_root = Path(mri_root).expanduser().resolve()

    if not mri_root.exists():
        return []

    subjects: set[str] = set()
    for candidate in sorted(path for path in mri_root.iterdir() if path.is_dir()):
        subject = _subject_label(candidate.name)
        images = find_anatomical_images(
            mri_root,
            subject,
            t1_pattern=t1_pattern,
            t2_pattern=t2_pattern,
        )
        if images["t1"] is not None or images["t2"] is not None:
            subjects.add(subject)

    return sorted(subjects)

def resolve_subjects(
    subjects: str | Sequence[str],
    *,
    mri_root: str | Path | None = None,
    subjects_dir: str | Path | None = None,
    t1_pattern: str = "{subject}/anat/*T1w*.nii*",
    t2_pattern: str = "{subject}/anat/*T2w*.nii*",
) -> list[str]:
    """Resolve notebook-style subject selections.

    ``subjects='all'`` discovers subjects from ``mri_root`` first, then from
    ``subjects_dir`` if no MRI root was supplied.
    """
    if subjects != "all":
        if isinstance(subjects, str):
            return [_subject_label(subjects)]
        return [_subject_label(subject) for subject in subjects]

    if mri_root is not None:
        return discover_mri_subjects(
            mri_root,
            t1_pattern=t1_pattern,
            t2_pattern=t2_pattern,
        )

    if subjects_dir is not None:
        subjects_dir = Path(subjects_dir).expanduser().resolve()
        if subjects_dir.exists():
            return sorted(path.name for path in subjects_dir.iterdir() if path.is_dir())

    return []

def make_freesurfer_env(
    *,
    subjects_dir: str | Path,
    freesurfer_home: str | Path | None = None,
    mne_path: str | Path | None = None,
) -> dict[str, str]:
    """Create an environment for FreeSurfer/MNE command-line tools.

    The function avoids shell-specific ``source SetUpFreeSurfer.sh`` calls and
    instead sets the key environment variables directly. This works well for
    subprocess-based notebook workflows on macOS and Linux.
    """
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


def run_recon_all(
    subject: str,
    *,
    mri_root: str | Path,
    subjects_dir: str | Path,
    t1_path: str | Path | None = None,
    t2_path: str | Path | None = None,
    t1_pattern: str = "{subject}/anat/*T1w*.nii*",
    t2_pattern: str = "{subject}/anat/*T2w*.nii*",
    use_t1: bool = True,
    use_t2: bool = False,
    freesurfer_home: str | Path | None = None,
    on_existing: ExistingOutputPolicy = "skip",
    dry_run: bool = False,
) -> AnatomyCommandResult:
    """Run FreeSurfer ``recon-all`` for one subject.

    T1 is required for this workflow. If ``use_t2=True`` and a T2 image is
    available, the command adds ``-T2 <path> -T2pial``. If no T2 image is found,
    recon-all falls back to T1-only and reports this in the result message.
    """
    subject = _subject_label(subject)
    subjects_dir = Path(subjects_dir).expanduser().resolve()
    subject_path = subject_dir(subjects_dir, subject)

    images = find_anatomical_images(
        mri_root,
        subject,
        t1_pattern=t1_pattern,
        t2_pattern=t2_pattern,
    )
    t1 = Path(t1_path).expanduser().resolve() if t1_path else images["t1"]
    t2 = Path(t2_path).expanduser().resolve() if t2_path else images["t2"]

    if subject_path.exists() and on_existing == "skip":
        return AnatomyCommandResult(
            subject=subject,
            step="recon_all",
            status="skipped_existing",
            path=str(subject_path),
            message=f"FreeSurfer subject already exists: {subject_path}",
        )

    if use_t1 and (t1 is None or not t1.exists()):
        return AnatomyCommandResult(
            subject=subject,
            step="recon_all",
            status="missing_input",
            path="" if t1 is None else str(t1),
            message=(
                "T1 image does not exist. recon-all currently requires a T1 "
                "image; T2-only recon is not supported by this workflow."
            ),
        )

    subjects_dir.mkdir(parents=True, exist_ok=True)
    env = make_freesurfer_env(
        subjects_dir=subjects_dir,
        freesurfer_home=freesurfer_home,
    )

    recon = shutil.which("recon-all", path=env.get("PATH")) or "recon-all"
    orig_mgz = subject_path / "mri" / "orig.mgz"

    command: list[str | Path] = [recon, "-sd", subjects_dir, "-s", subject]

    if not (subject_path.exists() and orig_mgz.exists()):
        command.extend(["-i", t1])

    t2_message = ""
    if use_t2:
        if t2 is not None and t2.exists():
            command.extend(["-T2", t2, "-T2pial"])
            t2_message = f" T2 pial refinement enabled using {t2}."
        else:
            t2_message = " T2 requested but not found; running T1-only recon-all."

    command.append("-all")

    returncode = run_streamed_subprocess(command, env=env, dry_run=dry_run)

    if returncode != 0:
        return AnatomyCommandResult(
            subject=subject,
            step="recon_all",
            status="failed",
            path=str(subject_path),
            returncode=returncode,
            message=f"recon-all failed with return code {returncode}.{t2_message}",
            command=_stringify_command(command),
        )

    return AnatomyCommandResult(
        subject=subject,
        step="recon_all",
        status="written" if not dry_run else "dry_run",
        path=str(subject_path),
        returncode=returncode,
        message=f"recon-all finished for {subject}.{t2_message}",
        command=_stringify_command(command),
    )

def run_recon_all_for_subjects(
    subjects: Iterable[str],
    *,
    mri_root: str | Path,
    subjects_dir: str | Path,
    t1_pattern: str = "{subject}/anat/*T1w*.nii*",
    t2_pattern: str = "{subject}/anat/*T2w*.nii*",
    use_t1: bool = True,
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
            t1_pattern=t1_pattern,
            t2_pattern=t2_pattern,
            use_t1=use_t1,
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
    t1_pattern: str = "{subject}/anat/*T1w*.nii*",
    t2_pattern: str = "{subject}/anat/*T2w*.nii*",
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
        images = (
            find_anatomical_images(
                mri_root,
                subject,
                t1_pattern=t1_pattern,
                t2_pattern=t2_pattern,
            )
            if mri_root is not None
            else {"t1": None, "t2": None}
        )
        t1_path = images["t1"]
        t2_path = images["t2"]
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
                "t1_exists": None if t1_path is None else t1_path.exists(),
                "t1_path": "" if t1_path is None else str(t1_path),
                "t2_exists": None if t2_path is None else t2_path.exists(),
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
        row = {
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
