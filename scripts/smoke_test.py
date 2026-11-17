"""Run the pipeline end to end on a test project and report what worked.

The script executes the code cells of the project's workflow notebooks one
after another in a single Python process, without Jupyter and without GUI.
Interactive notebooks (coregistration GUI, artifact annotation, ICA) are
skipped; the test project avoids them (scaled template, no ICA).

Usage::

    python scripts/make_test_project.py pipeline-test-project
    python scripts/smoke_test.py pipeline-test-project

Output: a table of steps with PASS/FAIL, and ``smoke_test_report.md`` in the
project folder (send that file back if something fails).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

# (notebook, comment). Order matters; every notebook only touches outputs of earlier ones.
NOTEBOOKS = [
    ("1B_preprocessing/01_raw_bids_import.ipynb", "convert sourcedata to BIDS"),
    ("cli:bad-channels-detect", "automatic bad channels (replaces the interactive notebook 02)"),
    ("cli:write-events", "trigger events (command line)"),
    ("1B_preprocessing/04_preprocessing.ipynb", "filtering"),
    ("1A_anatomy/03_anatomy_setup.ipynb", "scaled template, BEM, source space, labels"),
    ("1A_anatomy/04_coregistration.ipynb", "coregistration status"),
    ("1B_preprocessing/07_epoching.ipynb", "epochs"),
    ("2_sensor_analysis/01_evokeds.ipynb", "evoked responses"),
    ("3_source_modeling/01_forward_solution.ipynb", "forward solution"),
    ("3_source_modeling/02_noise_covariance.ipynb", "noise covariance"),
    ("3_source_modeling/03_inverse_operator.ipynb", "inverse operator"),
    ("3_source_modeling/04_apply_inverse_evokeds.ipynb", "source estimates"),
    ("3_source_modeling/05_morph_evoked_source_estimates_to_fsaverage.ipynb", "morph to fsaverage"),
    ("3_source_modeling/06_extract_label_time_courses_evokeds.ipynb", "label time courses (evoked)"),
    ("3_source_modeling/07_extract_label_time_courses_epochs.ipynb", "label time courses (epochs)"),
    ("6_group_statistics/01_source_cluster_tests.ipynb", "group cluster statistics"),
]


def _prepare_source(code: str) -> str:
    """Make a notebook cell runnable in a plain Python process."""
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith(("%", "!")):  # IPython magics and shell escapes
            continue
        if "set_browser_backend" in stripped:
            continue
        lines.append(line)
    return "\n".join(lines)


FAILED_ROWS: list[str] = []
_FAILURE_PREFIXES = ("fail", "error", "missing")


def _display(obj) -> None:
    """Show a value and remember result tables that contain failed rows.

    Most workflow steps report problems in a ``status`` column instead of raising.
    """
    print(obj.to_string() if hasattr(obj, "to_string") else obj)
    columns = getattr(obj, "columns", None)
    if columns is not None and "status" in columns:
        for _, row in obj.iterrows():
            status = str(row["status"]).lower()
            if status.startswith(_FAILURE_PREFIXES):
                message = str(row["message"]) if "message" in columns else ""
                FAILED_ROWS.append(f"status={row['status']}: {message[:300]}")


def run_notebook(path: Path, project: Path) -> tuple[str, str]:
    """Execute all code cells. Returns (status, detail)."""
    notebook = json.loads(path.read_text(encoding="utf-8"))
    FAILED_ROWS.clear()
    namespace: dict = {"__name__": "__main__", "display": _display}
    os.chdir(project / "notebooks" / path.parent.name)
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] != "code":
            continue
        source = _prepare_source("".join(cell["source"]))
        if not source.strip():
            continue
        try:
            exec(compile(source, f"{path.name}[cell {index}]", "exec"), namespace)
            # Evaluate a trailing bare expression like a notebook would, to catch errors in it.
            last = source.strip().splitlines()[-1]
            if last and not last.startswith((" ", "#", ")", "]", "}")) and "=" not in last.split("(")[0] and not last.startswith(
                ("print", "import", "from", "if ", "for ", "with ", "try", "else", "elif", "def ", "class ", "return", "raise")
            ):
                value = eval(compile(last, f"{path.name}[cell {index} last line]", "eval"), namespace)
                if value is not None:
                    _display(value)
        except Exception:
            return "FAIL", f"cell {index}: " + "".join(traceback.format_exc().splitlines(keepends=True)[-6:])
    if FAILED_ROWS:
        shown = FAILED_ROWS[:3]
        return "FAIL", f"{len(FAILED_ROWS)} result row(s) with a failed status, e.g.:\n" + "\n".join(shown)
    return "PASS", ""


def run_cli(command: str, project: Path) -> tuple[str, str]:
    """Run one ``meegpipe`` command for every subject of the project."""
    import subprocess

    config_path = project / "configs" / "local.yaml"
    subjects = sorted(p.name.removeprefix("sub-") for p in (project / "sourcedata").glob("sub-*") if p.name != "sub-emptyroom")
    for subject in subjects:
        completed = subprocess.run(
            [sys.executable, "-m", "meeg_pipeline", command, "--config", str(config_path), "--subject", subject, "--task", "audvis"],
            capture_output=True,
            text=True,
            cwd=project,
        )
        print(completed.stdout)
        if completed.returncode != 0:
            return "FAIL", f"{command} sub-{subject}: exit code {completed.returncode}\n{completed.stderr[-1500:]}"
    return "PASS", ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path, help="Test project created by make_test_project.py")
    parser.add_argument("--keep-going", action="store_true", help="Continue after a failing notebook.")
    args = parser.parse_args(argv)

    project = args.project.resolve()
    if not (project / "configs" / "local.yaml").exists():
        raise SystemExit(f"{project} is not a project (configs/local.yaml missing).")

    import meeg_pipeline
    import mne

    notebooks_root = project / "notebooks"
    rows: list[tuple[str, str, str, float, str]] = []
    for relative, comment in NOTEBOOKS:
        path = notebooks_root / relative
        if not relative.startswith("cli:") and not path.exists():
            rows.append((relative, comment, "MISSING", 0.0, "notebook not found in the project"))
            continue
        print(f"\n===== {relative} ({comment})", flush=True)
        started = time.time()
        if relative.startswith("cli:"):
            status, detail = run_cli(relative.removeprefix("cli:"), project)
        else:
            status, detail = run_notebook(path, project)
        elapsed = time.time() - started
        rows.append((relative, comment, status, elapsed, detail))
        print(f"----- {status} ({elapsed:.0f} s)", flush=True)
        if status != "PASS":
            print(detail)
            if not args.keep_going:
                break

    lines = [
        "# Smoke test report",
        "",
        f"- platform: {platform.platform()}",
        f"- python: {sys.version.split()[0]}",
        f"- mne: {mne.__version__}",
        f"- meeg_pipeline: {getattr(meeg_pipeline, '__version__', 'unknown')} ({Path(meeg_pipeline.__file__).parent})",
        "",
        "| step | status | seconds |",
        "| --- | --- | --- |",
    ]
    for relative, comment, status, seconds, _ in rows:
        lines.append(f"| {relative} ({comment}) | {status} | {seconds:.0f} |")
    for relative, _, status, _, detail in rows:
        if status != "PASS":
            lines += ["", f"## {relative}: {status}", "", "```text", re.sub(r"\s+$", "", detail), "```"]
    report = project / "smoke_test_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport written to {report}")
    print("\n".join(f"{r[2]:7} {r[0]}" for r in rows))
    return 0 if all(r[2] == "PASS" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
