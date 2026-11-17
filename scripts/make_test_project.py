"""Build a small, complete test project from the public MNE sample dataset.

The project has three pseudo-subjects (three consecutive segments of the
sample recording), one task (``audvis``), an empty-room recording and no MRI:
the anatomy is fsaverage scaled to the digitised head (``scaled_template``),
which needs no FreeSurfer installation and therefore also runs on Windows.
No participant data is involved; everything is downloaded from the MNE
dataset servers on first use (about 1.7 GB, cached in ``~/mne_data``).

Usage::

    python scripts/make_test_project.py [TARGET_DIR]

Then run ``python scripts/smoke_test.py TARGET_DIR``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import mne

from meeg_pipeline.project import init_project

SUBJECTS = ("0001", "0002", "0003")
TASK = "audvis"
# (tmin, tmax) in seconds of ``sample_audvis_raw.fif`` for each pseudo-subject.
SEGMENTS = {"0001": (0.0, 90.0), "0002": (90.0, 180.0), "0003": (180.0, 270.0)}


def _replace(text: str, old: str, new: str) -> str:
    """Replace exactly one occurrence so config edits fail loudly."""
    if text.count(old) != 1:
        raise ValueError(f"Expected exactly one occurrence of {old!r} in the config template.")
    return text.replace(old, new)


def _write_config(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    # Sample data: US power line, auditory/visual stimuli on the binary trigger channels.
    text = _replace(text, "notch_freqs: [50]", "notch_freqs: [60]")
    # The sample empty-room file was recorded three days after the task data.
    text = _replace(text, "max_time_diff_hours: 24", "max_time_diff_hours: 100")
    text = _replace(text, "    enabled: true\n    n_components: 0.99", "    enabled: false\n    n_components: 0.99")
    text = _replace(text, "tmin: -0.1\n  tmax: 0.6", "tmin: -0.2\n  tmax: 0.5")
    text = _replace(text, "definitions: {}", "definitions:\n    left_auditory: [1]\n    right_auditory: [2]")
    text = _replace(
        text,
        'mode: "individual_mri"  # "individual_mri" | "scaled_template" | "template"',
        'mode: "scaled_template"  # "individual_mri" | "scaled_template" | "template"',
    )
    text += """
stats:
  tmin: 0.05
  tmax: 0.20
  n_permutations: 200
  cluster_p_threshold: 0.01
  alpha: 0.05
  seed: 0
  n_jobs: 1
  parcellation: "aparc_sub"
  analyses:
    left_vs_right:
      kind: ttest
      terms:
        - {task: audvis, condition: left_auditory, weight: 1}
        - {task: audvis, condition: right_auditory, weight: -1}
"""
    path.write_text(text, encoding="utf-8")


def make_test_project(target: Path) -> Path:
    target = Path(target).resolve()
    if (target / "configs" / "local.yaml").exists():
        raise SystemExit(f"{target} already is a project. Choose a new folder or delete it first.")

    sample = Path(mne.datasets.sample.data_path(verbose=False)) / "MEG" / "sample"
    raw_path = sample / "sample_audvis_raw.fif"
    erm_path = sample / "ernoise_raw.fif"

    init_project(target.name, base_dir=target.parent, modality="meg", anatomy="individual_mri")
    _write_config(target / "configs" / "local.yaml")

    raw_full = mne.io.read_raw_fif(raw_path, preload=False, verbose=False)
    for subject in SUBJECTS:
        tmin, tmax = SEGMENTS[subject]
        out_dir = target / "sourcedata" / f"sub-{subject}" / "meg" / f"task-{TASK}"
        out_dir.mkdir(parents=True, exist_ok=True)
        raw = raw_full.copy().crop(tmin, tmax).load_data()
        raw.save(out_dir / f"sub-{subject}_task-{TASK}_raw.fif", overwrite=True, verbose=False)
        print(f"sub-{subject}: {tmin:.0f}-{tmax:.0f} s of the sample recording")

    erm = mne.io.read_raw_fif(erm_path, preload=True, verbose=False)
    # The session folder must carry the recording date of the file.
    erm_date = erm.info["meas_date"].strftime("%Y%m%d")
    erm_dir = target / "sourcedata" / "emptyroom" / f"ses-{erm_date}"
    erm_dir.mkdir(parents=True, exist_ok=True)
    # Remove the empty placeholder session that init-project creates as an example.
    for placeholder in (target / "sourcedata" / "emptyroom").glob("ses-YYYYMMDD"):
        if not any(placeholder.iterdir()):
            placeholder.rmdir()
    erm.save(erm_dir / "emptyroom_raw.fif", overwrite=True, verbose=False)

    # fsaverage goes straight into the project's SUBJECTS_DIR (writable, no FreeSurfer needed).
    subjects_dir = target / "derivatives" / "freesurfer" / "subjects"
    subjects_dir.mkdir(parents=True, exist_ok=True)
    mne.datasets.fetch_fsaverage(subjects_dir=subjects_dir, verbose=False)

    # Per-subject anatomy overrides (all pseudo-subjects use the scaled template).
    config_path = target / "configs" / "local.yaml"
    text = config_path.read_text(encoding="utf-8")
    subjects_block = "  subjects:\n" + "".join(f'    "{s}":\n      mode: "scaled_template"\n' for s in SUBJECTS)
    text = re.sub(r'(anatomy:\n  mode: "scaled_template"[^\n]*\n)', lambda m: m.group(1) + subjects_block, text, count=1)
    config_path.write_text(text, encoding="utf-8")

    print(f"\nTest project created: {target}")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", default="pipeline-test-project", type=Path)
    args = parser.parse_args(argv)
    make_test_project(args.target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
