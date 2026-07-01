from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import mne
import numpy as np
import pytest

from meeg_pipeline.channels import (
    analysis_pick_kwargs_from_config,
    channel_selection_summary,
    get_analysis_channel_types,
    pick_analysis_channels,
)
from meeg_pipeline.config import load_config
from meeg_pipeline.source_modeling import source_forward_config_to_dataframe


def _write_config(tmp_path: Path, *, extra_yaml: str = "") -> Path:
    """Write a minimal project config that exercises load_config defaults."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "local.yaml"
    config_path.write_text(
        "\n".join(
            [
                "project:",
                "  name: test-meeg-config",
                "paths:",
                "  bids_root: ./rawdata",
                "  sourcedata_root: ./sourcedata",
                "  derivatives_root: ./derivatives/meeg-pipeline",
                dedent(extra_yaml).strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _mixed_raw() -> mne.io.RawArray:
    info = mne.create_info(
        ["MEG0111", "MEG0112", "EEG001", "EEG002", "EOG001", "STI001"],
        sfreq=100.0,
        ch_types=["mag", "grad", "eeg", "eeg", "eog", "stim"],
    )
    return mne.io.RawArray(np.zeros((6, 100)), info, verbose=False)


def test_default_analysis_channel_config_is_meg_only(tmp_path: Path) -> None:
    cfg = load_config(_write_config(tmp_path))

    assert get_analysis_channel_types(cfg) == ("meg",)
    assert analysis_pick_kwargs_from_config(cfg) == {
        "meg": True,
        "eeg": False,
        "eog": False,
        "ecg": False,
        "stim": False,
        "misc": False,
    }

    raw = _mixed_raw()
    picks = pick_analysis_channels(raw, cfg)
    assert [raw.ch_names[pick] for pick in picks] == ["MEG0111", "MEG0112"]

    summary = channel_selection_summary(raw, cfg)
    assert summary.status == "ok"
    assert summary.requested_channel_types == ("meg",)
    assert summary.selected_channel_types == {"meg": 2}


def test_eeg_only_config_selects_eeg_and_reports_one_layer_bem_guard(
    tmp_path: Path,
) -> None:
    cfg = load_config(
        _write_config(
            tmp_path,
            extra_yaml="""
            bids:
              datatype: eeg
            channels:
              analysis:
                meg: false
                eeg: true
            """,
        )
    )

    raw = _mixed_raw()
    picks = pick_analysis_channels(raw, cfg)
    assert [raw.ch_names[pick] for pick in picks] == ["EEG001", "EEG002"]

    overview = source_forward_config_to_dataframe(cfg)
    assert bool(overview.loc[0, "fwd_meg"]) is False
    assert bool(overview.loc[0, "fwd_eeg"]) is True
    assert overview.loc[0, "fwd_desc"] == "eeg"
    assert overview.loc[0, "status"] == "unsupported_configuration"
    assert "three-layer BEM" in overview.loc[0, "message"]


def test_meeg_config_uses_meg_and_eeg_with_three_layer_bem(tmp_path: Path) -> None:
    cfg = load_config(
        _write_config(
            tmp_path,
            extra_yaml="""
            bids:
              datatype: meg
            channels:
              analysis:
                meg: true
                eeg: true
            anatomy:
              bem:
                conductivity: [0.3, 0.006, 0.3]
            source:
              noise_cov:
                mode: epochs_baseline
            """,
        )
    )

    raw = _mixed_raw()
    picks = pick_analysis_channels(raw, cfg)
    assert [raw.ch_names[pick] for pick in picks] == [
        "MEG0111",
        "MEG0112",
        "EEG001",
        "EEG002",
    ]

    overview = source_forward_config_to_dataframe(cfg)
    assert bool(overview.loc[0, "fwd_meg"]) is True
    assert bool(overview.loc[0, "fwd_eeg"]) is True
    assert overview.loc[0, "fwd_desc"] == "meeg"
    assert overview.loc[0, "bem_n_layers"] == 3
    assert overview.loc[0, "noise_cov_mode"] == "epochs_baseline"
    assert overview.loc[0, "status"] == "ok"


def test_invalid_bids_datatype_is_rejected(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        extra_yaml="""
        bids:
          datatype: ieeg
        """,
    )

    with pytest.raises(ValueError, match="bids.datatype"):
        load_config(config_path)
