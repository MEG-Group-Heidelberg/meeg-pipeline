from __future__ import annotations

from meeg_pipeline.config import load_config
from meeg_pipeline.project import init_project


def test_init_project_eeg_fsaverage_standard_montage(tmp_path):
    result = init_project(
        "eeg_fsaverage_demo",
        base_dir=tmp_path,
        modality="eeg",
        anatomy="fsaverage",
        montage="standard_1020",
    )

    project_root = tmp_path / "eeg_fsaverage_demo"
    config = load_config(project_root / "configs" / "local.yaml")

    assert result.status == "initialized"
    assert config.bids.datatype == "eeg"
    assert config.channels.analysis.meg is False
    assert config.channels.analysis.eeg is True
    assert config.channels.montage.kind == "standard_1020"
    assert config.channels.montage.dig is False
    assert config.anatomy.mode == "fsaverage"
    assert config.anatomy.bem.conductivity == (0.3, 0.006, 0.3)
    assert config.source.noise_cov.mode == "baseline"
    assert (project_root / "sourcedata" / "sub-0001" / "eeg").is_dir()
    assert not (project_root / "sourcedata" / "sub-0001" / "meg").exists()


def test_init_project_meg_defaults_keep_individual_mri(tmp_path):
    init_project("meg_demo", base_dir=tmp_path)

    project_root = tmp_path / "meg_demo"
    config = load_config(project_root / "configs" / "local.yaml")

    assert config.bids.datatype == "meg"
    assert config.channels.analysis.meg is True
    assert config.channels.analysis.eeg is False
    assert config.channels.montage.kind is None
    assert config.channels.montage.dig is True
    assert config.anatomy.mode == "individual_mri"
    assert config.anatomy.bem.conductivity == (0.3,)
    assert config.source.noise_cov.mode == "erm"
    assert (project_root / "sourcedata" / "sub-0001" / "meg").is_dir()
    assert (project_root / "sourcedata" / "emptyroom" / "ses-YYYYMMDD").is_dir()
