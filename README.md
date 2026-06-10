# meeg-pipeline

A modular, BIDS-compatible M/EEG analysis pipeline built on top of
[MNE-Python](https://mne.tools/stable/index.html) and
[MNE-BIDS](https://mne.tools/mne-bids/stable/index.html).

The goal of this project is to provide a transparent and extensible pipeline
for MEG and EEG data analysis. The pipeline is intended to be developed step by
step, with a strong focus on understanding each processing stage.

## Design principles

- BIDS-compatible project structure
- Separation between reusable pipeline code and project-specific data/configs
- Transparent Python implementation
- Configurable processing steps
- Event handling based on metadata-rich event tables
- Local and HPC-compatible execution
- Built on MNE-Python and MNE-BIDS

## Repository structure

```text
meeg-pipeline/
  README.md
  pyproject.toml
  src/
    meeg_pipeline/
      __init__.py