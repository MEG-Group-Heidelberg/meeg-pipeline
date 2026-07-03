from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


@dataclass(frozen=True)
class ProjectPaths:
    bids_root: Path
    sourcedata_root: Path
    derivatives_root: Path
    mri_raw_root: Path
    mri_root: Path


@dataclass(frozen=True)
class RuntimeConfig:
    n_jobs: int = 1
    thread_limits: bool = True


@dataclass(frozen=True)
class BIDSConfig:
    datatype: str = "meg"
    task: str | None = None
    session: str | None = None
    run: str | None = None




@dataclass(frozen=True)
class ChannelAnalysisConfig:
    meg: bool = True
    eeg: bool = False
    eog: bool = False
    ecg: bool = False
    stim: bool = False
    misc: bool = False


@dataclass(frozen=True)
class ChannelReferenceConfig:
    eeg: str | None = None


@dataclass(frozen=True)
class ChannelMontageConfig:
    kind: str | None = None
    dig: bool = True


@dataclass(frozen=True)
class ChannelConfig:
    analysis: ChannelAnalysisConfig = field(default_factory=ChannelAnalysisConfig)
    reference: ChannelReferenceConfig = field(default_factory=ChannelReferenceConfig)
    montage: ChannelMontageConfig = field(default_factory=ChannelMontageConfig)


@dataclass(frozen=True)
class EventExtractionConfig:
    method: str = "binary_channels"
    stim_channels: tuple[str, ...] = (
        "STI 001",
        "STI 002",
        "STI 003",
        "STI 004",
        "STI 005",
        "STI 006",
    )
    min_duration: float = 0.0
    shortest_event: int = 1
    min_gap: int = 7000
    adjust_timeline_by_msec: float = 0.0
    tolerance_samples: int = 1
    mute_bad_annotations: bool = True


@dataclass(frozen=True)
class EventsConfig:
    extraction: EventExtractionConfig


@dataclass(frozen=True)
class FilteringConfig:
    notch_freqs: tuple[float, ...] = (50.0,)
    l_freq: float | None = 1.0
    h_freq: float | None = 40.0
    method: str = "fir"


@dataclass(frozen=True)
class PreprocessingConfig:
    filtering: FilteringConfig


@dataclass(frozen=True)
class ICAConfig:
    enabled: bool = True
    n_components: int | float | None = 0.99
    method: str = "fastica"
    random_state: int = 97
    max_iter: int | str = "auto"
    decim: int | None = None
    fit_resample_sfreq: float | None = None


@dataclass(frozen=True)
class CleaningConfig:
    ica: ICAConfig


@dataclass(frozen=True)
class EpochsConfig:
    input: Literal["auto", "cleaned", "filtered"] = "auto"
    tmin: float = -1.0
    tmax: float = 1.0
    baseline: tuple[float | None, float | None] | None = None
    bad_interpolation: str | None = "epochs"


@dataclass(frozen=True)
class AutorejectConfig:
    enabled: bool = False
    use: str | None = None
    consensus_percs: tuple[float, ...] | None = None
    n_interpolates: tuple[int, ...] | None = None
    subset: int | float | None = None
    tmin: float | None = None
    tmax: float | None = None
    crop_to_epochs: bool = True


@dataclass(frozen=True)
class SourcedataConfig:
    sessions: Literal["ignore", "include", "auto"] = "ignore"


@dataclass(frozen=True)
class EmptyRoomMatchingConfig:
    strategy: Literal[
        "auto",
        "meas_date_nearest",
        "session_exact",
        "session_date_nearest",
    ] = "meas_date_nearest"
    max_time_diff_hours: float | None = None
    allow_fallback: bool = True
    fallback_strategy: Literal[
        "meas_date_nearest",
        "session_exact",
        "session_date_nearest",
    ] | None = "session_date_nearest"


@dataclass(frozen=True)
class EmptyRoomConfig:
    enabled: bool = False
    subject: str = "emptyroom"
    task: str = "noise"
    sourcedata_root: Path | None = None
    sessions: Literal["from_folders"] = "from_folders"
    session_pattern: str = "ses-*"
    file_patterns: tuple[str, ...] = ("*.fif", "*.fif.gz")
    matching: EmptyRoomMatchingConfig = EmptyRoomMatchingConfig()


@dataclass(frozen=True)
class FreeSurferConfig:
    home: Path | None = None
    subjects_dir: Path | None = None


@dataclass(frozen=True)
class AnatomyConversionConfig:
    converter: Literal["dcm2niix"] = "dcm2niix"
    t1_source_pattern: str = "{subject}/T1"
    t2_source_pattern: str = "{subject}/T2"
    make_mgz: bool = True


@dataclass(frozen=True)
class AnatomyReconConfig:
    use_t1: bool = True
    use_t2: bool = False


@dataclass(frozen=True)
class AnatomyWatershedConfig:
    volume: str = "T1"


@dataclass(frozen=True)
class AnatomyBEMConfig:
    method: Literal["watershed", "flash"] = "watershed"
    conductivity: tuple[float, ...] = (0.3,)
    ico: int = 4


@dataclass(frozen=True)
class AnatomySourceSpaceConfig:
    spacing: str = "ico5"
    surface: str = "white"
    add_dist: bool | str = False


@dataclass(frozen=True)
class AnatomyVolumeSourceSpaceConfig:
    enabled: bool = False
    spacing: float = 5.0


@dataclass(frozen=True)
class AnatomyLabelsConfig:
    morph_from: str = "fsaverage"
    parcellations: tuple[str, ...] = ("aparc_sub",)


@dataclass(frozen=True)
class AnatomyCoregistrationConfig:
    # Controls the canonical output path for MEG<->MRI transforms.
    # - recording: include subject/session/task/run entities
    # - session: include subject/session only
    # - subject: include subject only
    transform_scope: Literal["recording", "session", "subject"] = "recording"

    # If the canonical transform is missing, source-modeling helpers may search
    # compatible legacy transforms, e.g. a task-chords transform for task-nochords.
    allow_compatible_fallback: bool = True


@dataclass(frozen=True)
class AnatomyConfig:
    mode: Literal["individual_mri", "fsaverage"] = "individual_mri"
    t1_patterns: tuple[str, ...] = (
        "{subject}/anat/T1.mgz",
        "{subject}/anat/*T1w*.nii*",
    )
    t2_patterns: tuple[str, ...] = (
        "{subject}/anat/T2.mgz",
        "{subject}/anat/*T2w*.nii*",
    )
    conversion: AnatomyConversionConfig = AnatomyConversionConfig()
    recon: AnatomyReconConfig = AnatomyReconConfig()
    watershed: AnatomyWatershedConfig = AnatomyWatershedConfig()
    bem: AnatomyBEMConfig = AnatomyBEMConfig()
    source_space: AnatomySourceSpaceConfig = AnatomySourceSpaceConfig()
    volume_source_space: AnatomyVolumeSourceSpaceConfig = AnatomyVolumeSourceSpaceConfig()
    labels: AnatomyLabelsConfig = AnatomyLabelsConfig()
    coregistration: AnatomyCoregistrationConfig = AnatomyCoregistrationConfig()

    @property
    def t1_pattern(self) -> str:
        """Backward-compatible first T1 pattern."""
        return self.t1_patterns[0]

    @property
    def t2_pattern(self) -> str:
        """Backward-compatible first T2 pattern."""
        return self.t2_patterns[0]


@dataclass(frozen=True)
class SourceInverseConfig:
    method: Literal["MNE", "dSPM", "sLORETA", "eLORETA"] = "dSPM"
    snr: float = 3.0
    lambda2: float | None = None
    pick_ori: str | None = None


@dataclass(frozen=True)
class SourceLabelsConfig:
    parcellation: str = "aparc_sub"
    extract_mode: str = "mean_flip"
    target_labels: tuple[str, ...] | None = None


@dataclass(frozen=True)
class SourceNoiseCovConfig:
    mode: str = "erm"


@dataclass(frozen=True)
class SourceApplyInverseConfig:
    apply_to: Literal["evoked", "epochs"] = "evoked"
    # Resolved from source.inverse by default. Kept here so step-specific
    # overrides and older code paths can keep using config.source.apply_inverse.*.
    method: Literal["MNE", "dSPM", "sLORETA", "eLORETA"] = "dSPM"
    snr: float = 3.0
    lambda2: float | None = None
    pick_conditions: tuple[str, ...] | Literal["all"] = "all"
    save_stcs: bool = True
    stc_format: Literal["h5"] = "h5"


@dataclass(frozen=True)
class SourceLabelTimeCoursesEpochsConfig:
    enabled: bool = True
    # Resolved from source.inverse and source.labels by default. Step-specific
    # overrides remain possible by setting these keys under
    # source.label_time_courses_epochs.
    method: Literal["MNE", "dSPM", "sLORETA", "eLORETA"] = "dSPM"
    snr: float = 3.0
    lambda2: float | None = None
    parcellation: str | None = None
    extract_mode: str | None = None
    target_labels: tuple[str, ...] | None = None
    decim: int | None = 5
    tmin: float | None = None
    tmax: float | None = None
    dtype: Literal["float32", "float64"] = "float32"
    save_format: Literal["npy"] = "npy"


@dataclass(frozen=True)
class SourceMorphConfig:
    enabled: bool = True
    subject_to: str = "fsaverage"
    spacing: str | None = None
    smooth: int | None = None
    method: Literal["MNE", "dSPM", "sLORETA", "eLORETA"] | None = None
    pick_conditions: tuple[str, ...] | Literal["all"] = "all"
    stc_format: Literal["h5"] = "h5"


@dataclass(frozen=True)
class SourceConfig:
    spacing: str = "ico5"
    inverse: SourceInverseConfig = SourceInverseConfig()
    labels: SourceLabelsConfig = SourceLabelsConfig()
    noise_cov: SourceNoiseCovConfig = SourceNoiseCovConfig()
    apply_inverse: SourceApplyInverseConfig = SourceApplyInverseConfig()
    morph: SourceMorphConfig = SourceMorphConfig()
    label_time_courses_epochs: SourceLabelTimeCoursesEpochsConfig = SourceLabelTimeCoursesEpochsConfig()

    # Backward-compatible aliases for older notebooks/helpers. Prefer the
    # nested blocks above in new config files and new code.
    @property
    def noise_cov_mode(self) -> str:
        return self.noise_cov.mode

    @property
    def inverse_method(self) -> str:
        return self.inverse.method

    @property
    def parcellation(self) -> str:
        return self.labels.parcellation

    @property
    def extract_mode(self) -> str:
        return self.labels.extract_mode

    @property
    def target_labels(self) -> tuple[str, ...] | None:
        return self.labels.target_labels


@dataclass(frozen=True)
class ConditionsConfig:
    """Project-specific named condition definitions.

    This is intentionally optional. Most projects can work directly with
    trigger/event labels in event_name or trial_type. Projects that need derived
    selections can define named pandas metadata queries here, for example:

        first_deviant: "deviant == 1"

    Downstream steps can then refer to ``first_deviant`` while the generic
    library still works for simple trigger-based workflows.
    """

    definitions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectivityWindowConfig:
    tmin: float
    tmax: float


@dataclass(frozen=True)
class ConnectivityBandConfig:
    fmin: float
    fmax: float


@dataclass(frozen=True)
class ConnectivityConfig:
    enabled: bool = True
    input: Literal["label_time_course_epochs"] = "label_time_course_epochs"
    space: Literal["label"] = "label"
    parcellation: str | None = None
    methods: tuple[str, ...] = ("imcoh", "wpli")
    mode: str = "multitaper"
    windows: dict[str, ConnectivityWindowConfig] = None  # type: ignore[assignment]
    bands: dict[str, ConnectivityBandConfig] = None  # type: ignore[assignment]
    faverage: bool = True
    conditions: tuple[str, ...] | Literal["all"] = "all"
    label_patterns: tuple[str, ...] | None = None
    block_size: int = 1000
    n_jobs: int | None = None
    save_format: Literal["npz"] = "npz"

    def __post_init__(self) -> None:
        if self.windows is None:
            object.__setattr__(
                self,
                "windows",
                {"note_early": ConnectivityWindowConfig(tmin=0.0, tmax=0.25)},
            )
        if self.bands is None:
            object.__setattr__(
                self,
                "bands",
                {
                    "beta": ConnectivityBandConfig(fmin=13.0, fmax=30.0),
                    "low_gamma": ConnectivityBandConfig(fmin=30.0, fmax=70.0),
                },
            )


@dataclass(frozen=True)
class PipelineConfig:
    project_name: str
    paths: ProjectPaths
    runtime: RuntimeConfig
    bids: BIDSConfig
    channels: ChannelConfig
    sourcedata: SourcedataConfig
    empty_room: EmptyRoomConfig
    freesurfer: FreeSurferConfig
    anatomy: AnatomyConfig
    events: EventsConfig
    preprocessing: PreprocessingConfig
    cleaning: CleaningConfig
    epochs: EpochsConfig
    autoreject: AutorejectConfig
    source: SourceConfig
    conditions: ConditionsConfig = ConditionsConfig()
    connectivity: ConnectivityConfig = ConnectivityConfig()


def _resolve_path(path: str | Path, *, base_dir: Path) -> Path:
    path = Path(path).expanduser()

    if not path.is_absolute():
        path = base_dir / path

    return path.resolve()


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None

    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None

    return int(value)


def _optional_int_or_float(value: Any) -> int | float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        raise ValueError(
            "Expected int, float, or null, got boolean value "
            f"{value!r}."
        )

    if isinstance(value, int):
        return int(value)

    if isinstance(value, float):
        return float(value)

    text = str(value)
    if "." in text:
        return float(text)

    return int(text)


def _optional_float_tuple(value: Any) -> tuple[float, ...] | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return (float(value),)

    return tuple(float(item) for item in value)


def _optional_int_tuple(value: Any) -> tuple[int, ...] | None:
    if value is None:
        return None

    if isinstance(value, int):
        return (int(value),)

    return tuple(int(item) for item in value)


def _optional_str_tuple(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None

    if isinstance(value, str):
        return (value,)

    return tuple(str(item) for item in value)


def _str_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    """Return a string tuple from a scalar/list config value."""
    if value is None:
        return default

    if isinstance(value, str):
        return (value,)

    return tuple(str(item) for item in value)


def _anatomy_patterns(
    raw: dict[str, Any],
    *,
    plural_key: str,
    singular_key: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    """Read anatomy image patterns with singular-key backward compatibility."""
    if plural_key in raw:
        return _str_tuple(raw.get(plural_key), default)

    if singular_key in raw:
        return _str_tuple(raw.get(singular_key), default)

    return default


def _optional_baseline(
    value: Any,
) -> tuple[float | None, float | None] | None:
    if value is None:
        return None

    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(
            "epochs.baseline must be null or a two-element list/tuple, "
            f"got {value!r}."
        )

    start, end = value

    return (
        None if start is None else float(start),
        None if end is None else float(end),
    )


def _ica_n_components(value: Any) -> int | float | None:
    if value is None:
        return None

    if isinstance(value, int):
        return int(value)

    return float(value)


def load_config(config_path: str | Path) -> PipelineConfig:
    config_path = Path(config_path).expanduser().resolve()

    if not config_path.exists():
        raise FileNotFoundError(f"Config file does not exist: {config_path}")

    # Assumption:
    # If config is at <project>/configs/local.yaml,
    # then <project> is config_path.parent.parent.
    project_root = config_path.parent.parent

    with config_path.open("r", encoding="utf-8") as f:
        raw_loaded = yaml.safe_load(f)

    raw: dict[str, Any] = raw_loaded if raw_loaded is not None else {}

    paths_raw = raw["paths"]

    paths = ProjectPaths(
        bids_root=_resolve_path(paths_raw["bids_root"], base_dir=project_root),
        sourcedata_root=_resolve_path(
            paths_raw.get("sourcedata_root", "./sourcedata"),
            base_dir=project_root,
        ),
        derivatives_root=_resolve_path(
            paths_raw["derivatives_root"],
            base_dir=project_root,
        ),
        mri_raw_root=_resolve_path(
            paths_raw.get("mri_raw_root", "./sourcedata/mri_raw"),
            base_dir=project_root,
        ),
        mri_root=_resolve_path(
            paths_raw.get("mri_root", "./sourcedata/mri"),
            base_dir=project_root,
        ),
    )

    freesurfer_raw = raw.get("freesurfer", {})
    freesurfer_home_raw = freesurfer_raw.get("home", None)
    freesurfer_subjects_dir_raw = freesurfer_raw.get(
        "subjects_dir",
        paths_raw.get("subjects_dir", "./derivatives/freesurfer/subjects"),
    )
    freesurfer = FreeSurferConfig(
        home=None
        if freesurfer_home_raw is None
        else _resolve_path(freesurfer_home_raw, base_dir=project_root),
        subjects_dir=None
        if freesurfer_subjects_dir_raw is None
        else _resolve_path(freesurfer_subjects_dir_raw, base_dir=project_root),
    )

    anatomy_raw = raw.get("anatomy", {})
    anatomy_conversion_raw = anatomy_raw.get("conversion", {})
    anatomy_recon_raw = anatomy_raw.get("recon", {})
    anatomy_watershed_raw = anatomy_raw.get("watershed", {})
    anatomy_bem_raw = anatomy_raw.get("bem", {})
    anatomy_source_space_raw = anatomy_raw.get("source_space", {})
    anatomy_volume_source_space_raw = anatomy_raw.get("volume_source_space", {})
    anatomy_labels_raw = anatomy_raw.get("labels", {})
    anatomy_coregistration_raw = anatomy_raw.get("coregistration", {})

    anatomy_mode = str(anatomy_raw.get("mode", "individual_mri"))
    if anatomy_mode not in {"individual_mri", "fsaverage"}:
        raise ValueError(
            "anatomy.mode must be one of 'individual_mri' or 'fsaverage', "
            f"got {anatomy_mode!r}."
        )

    bem_method = anatomy_bem_raw.get("method", "watershed")
    if bem_method not in {"watershed", "flash"}:
        raise ValueError(
            "anatomy.bem.method must be one of 'watershed' or 'flash', "
            f"got {bem_method!r}."
        )

    anatomy_converter = anatomy_conversion_raw.get("converter", "dcm2niix")
    if anatomy_converter not in {"dcm2niix"}:
        raise ValueError(
            "anatomy.conversion.converter must currently be 'dcm2niix', "
            f"got {anatomy_converter!r}."
        )

    coregistration_transform_scope = anatomy_coregistration_raw.get(
        "transform_scope",
        "recording",
    )
    if coregistration_transform_scope not in {"recording", "session", "subject"}:
        raise ValueError(
            "anatomy.coregistration.transform_scope must be one of "
            "'recording', 'session', or 'subject', "
            f"got {coregistration_transform_scope!r}."
        )

    anatomy = AnatomyConfig(
        mode=anatomy_mode,
        t1_patterns=_anatomy_patterns(
            anatomy_raw,
            plural_key="t1_patterns",
            singular_key="t1_pattern",
            default=("{subject}/anat/T1.mgz", "{subject}/anat/*T1w*.nii*"),
        ),
        t2_patterns=_anatomy_patterns(
            anatomy_raw,
            plural_key="t2_patterns",
            singular_key="t2_pattern",
            default=("{subject}/anat/T2.mgz", "{subject}/anat/*T2w*.nii*"),
        ),
        conversion=AnatomyConversionConfig(
            converter=anatomy_converter,
            t1_source_pattern=anatomy_conversion_raw.get(
                "t1_source_pattern",
                "{subject}/T1",
            ),
            t2_source_pattern=anatomy_conversion_raw.get(
                "t2_source_pattern",
                "{subject}/T2",
            ),
            make_mgz=bool(anatomy_conversion_raw.get("make_mgz", True)),
        ),
        recon=AnatomyReconConfig(
            use_t1=bool(anatomy_recon_raw.get("use_t1", True)),
            use_t2=bool(anatomy_recon_raw.get("use_t2", False)),
        ),
        watershed=AnatomyWatershedConfig(
            volume=str(anatomy_watershed_raw.get("volume", "T1")),
        ),
        bem=AnatomyBEMConfig(
            method=bem_method,
            conductivity=tuple(
                float(value)
                for value in anatomy_bem_raw.get("conductivity", [0.3])
            ),
            ico=int(anatomy_bem_raw.get("ico", 4)),
        ),
        source_space=AnatomySourceSpaceConfig(
            spacing=str(anatomy_source_space_raw.get("spacing", "ico5")),
            surface=str(anatomy_source_space_raw.get("surface", "white")),
            add_dist=anatomy_source_space_raw.get("add_dist", False),
        ),
        volume_source_space=AnatomyVolumeSourceSpaceConfig(
            enabled=bool(anatomy_volume_source_space_raw.get("enabled", False)),
            spacing=float(anatomy_volume_source_space_raw.get("spacing", 5.0)),
        ),
        labels=AnatomyLabelsConfig(
            morph_from=str(anatomy_labels_raw.get("morph_from", "fsaverage")),
            parcellations=tuple(
                str(value)
                for value in anatomy_labels_raw.get("parcellations", ["aparc_sub"])
            ),
        ),
        coregistration=AnatomyCoregistrationConfig(
            transform_scope=str(coregistration_transform_scope),
            allow_compatible_fallback=bool(
                anatomy_coregistration_raw.get("allow_compatible_fallback", True)
            ),
        ),
    )

    runtime_raw = raw.get("runtime", {})
    runtime = RuntimeConfig(
        n_jobs=int(runtime_raw.get("n_jobs", 1)),
        thread_limits=bool(runtime_raw.get("thread_limits", True)),
    )

    bids_raw = raw.get("bids", {})
    bids_datatype = str(bids_raw.get("datatype", "meg"))
    if bids_datatype not in {"meg", "eeg"}:
        raise ValueError(
            "bids.datatype must be one of 'meg' or 'eeg', "
            f"got {bids_datatype!r}."
        )

    bids = BIDSConfig(
        datatype=bids_datatype,
        task=bids_raw.get("task"),
        session=bids_raw.get("session"),
        run=bids_raw.get("run"),
    )

    channels_raw = raw.get("channels", {}) or {}
    analysis_raw = channels_raw.get("analysis", {}) or {}
    reference_raw = channels_raw.get("reference", {}) or {}
    montage_raw = channels_raw.get("montage", {}) or {}

    channels = ChannelConfig(
        analysis=ChannelAnalysisConfig(
            meg=bool(analysis_raw.get("meg", True)),
            eeg=bool(analysis_raw.get("eeg", False)),
            eog=bool(analysis_raw.get("eog", False)),
            ecg=bool(analysis_raw.get("ecg", False)),
            stim=bool(analysis_raw.get("stim", False)),
            misc=bool(analysis_raw.get("misc", False)),
        ),
        reference=ChannelReferenceConfig(
            eeg=reference_raw.get("eeg", None),
        ),
        montage=ChannelMontageConfig(
            kind=montage_raw.get("kind", None),
            dig=bool(montage_raw.get("dig", True)),
        ),
    )

    sourcedata_raw = raw.get("sourcedata", {})
    sourcedata_sessions = sourcedata_raw.get("sessions", "ignore")

    if sourcedata_sessions not in {"ignore", "include", "auto"}:
        raise ValueError(
            "sourcedata.sessions must be one of 'ignore', 'include', "
            f"or 'auto', got {sourcedata_sessions!r}."
        )

    sourcedata = SourcedataConfig(sessions=sourcedata_sessions)

    empty_room_raw = raw.get("empty_room", {})
    empty_room_matching_raw = empty_room_raw.get("matching", {})

    empty_room_strategy = empty_room_matching_raw.get(
        "strategy",
        "meas_date_nearest",
    )
    if empty_room_strategy not in {
        "auto",
        "meas_date_nearest",
        "session_exact",
        "session_date_nearest",
    }:
        raise ValueError(
            "empty_room.matching.strategy must be one of 'auto', "
            "'meas_date_nearest', 'session_exact', or "
            f"'session_date_nearest', got {empty_room_strategy!r}."
        )

    empty_room_fallback_strategy = empty_room_matching_raw.get(
        "fallback_strategy",
        "session_date_nearest",
    )
    if empty_room_fallback_strategy is not None and empty_room_fallback_strategy not in {
        "meas_date_nearest",
        "session_exact",
        "session_date_nearest",
    }:
        raise ValueError(
            "empty_room.matching.fallback_strategy must be null or one of "
            "'meas_date_nearest', 'session_exact', or "
            f"'session_date_nearest', got {empty_room_fallback_strategy!r}."
        )

    empty_room_sessions = empty_room_raw.get("sessions", "from_folders")
    if empty_room_sessions not in {"from_folders"}:
        raise ValueError(
            "empty_room.sessions currently must be 'from_folders', "
            f"got {empty_room_sessions!r}."
        )

    empty_room_sourcedata_root_raw = empty_room_raw.get(
        "sourcedata_root",
        "./sourcedata/emptyroom",
    )
    empty_room = EmptyRoomConfig(
        enabled=bool(empty_room_raw.get("enabled", False)),
        subject=str(empty_room_raw.get("subject", "emptyroom")).removeprefix("sub-"),
        task=str(empty_room_raw.get("task", "noise")),
        sourcedata_root=_resolve_path(
            empty_room_sourcedata_root_raw,
            base_dir=project_root,
        ),
        sessions=empty_room_sessions,
        session_pattern=str(empty_room_raw.get("session_pattern", "ses-*")),
        file_patterns=_str_tuple(
            empty_room_raw.get("file_patterns", ["*.fif", "*.fif.gz"]),
            ("*.fif", "*.fif.gz"),
        ),
        matching=EmptyRoomMatchingConfig(
            strategy=empty_room_strategy,
            max_time_diff_hours=_optional_float(
                empty_room_matching_raw.get("max_time_diff_hours", None)
            ),
            allow_fallback=bool(
                empty_room_matching_raw.get("allow_fallback", True)
            ),
            fallback_strategy=empty_room_fallback_strategy,
        ),
    )

    events_raw = raw.get("events", {})
    extraction_raw = events_raw.get("extraction", {})

    event_extraction = EventExtractionConfig(
        method=extraction_raw.get("method", "binary_channels"),
        stim_channels=tuple(
            extraction_raw.get(
                "stim_channels",
                [
                    "STI 001",
                    "STI 002",
                    "STI 003",
                    "STI 004",
                    "STI 005",
                    "STI 006",
                ],
            )
        ),
        min_duration=float(extraction_raw.get("min_duration", 0.0)),
        shortest_event=int(extraction_raw.get("shortest_event", 1)),
        min_gap=int(extraction_raw.get("min_gap", 7000)),
        adjust_timeline_by_msec=float(
            extraction_raw.get("adjust_timeline_by_msec", 0.0)
        ),
        tolerance_samples=int(extraction_raw.get("tolerance_samples", 1)),
        mute_bad_annotations=bool(extraction_raw.get("mute_bad_annotations", True)),
    )

    events = EventsConfig(extraction=event_extraction)

    preprocessing_raw = raw.get("preprocessing", {})
    filtering_raw = preprocessing_raw.get("filtering", {})

    notch_freqs_raw = filtering_raw.get("notch_freqs", [50.0])

    if notch_freqs_raw is None:
        notch_freqs = ()
    else:
        notch_freqs = tuple(float(freq) for freq in notch_freqs_raw)

    filtering = FilteringConfig(
        notch_freqs=notch_freqs,
        l_freq=_optional_float(filtering_raw.get("l_freq", 1.0)),
        h_freq=_optional_float(filtering_raw.get("h_freq", 40.0)),
        method=filtering_raw.get("method", "fir"),
    )

    preprocessing = PreprocessingConfig(filtering=filtering)

    cleaning_raw = raw.get("cleaning", {})
    ica_raw = cleaning_raw.get("ica", {})

    cleaning = CleaningConfig(
        ica=ICAConfig(
            enabled=bool(ica_raw.get("enabled", True)),
            n_components=_ica_n_components(ica_raw.get("n_components", 0.99)),
            method=ica_raw.get("method", "fastica"),
            random_state=int(ica_raw.get("random_state", 97)),
            max_iter=ica_raw.get("max_iter", "auto"),
            decim=_optional_int(ica_raw.get("decim", None)),
            fit_resample_sfreq=_optional_float(
                ica_raw.get("fit_resample_sfreq", None)
            ),
        )
    )

    epochs_raw = raw.get("epochs", {})
    epochs_input = str(epochs_raw.get("input", "auto"))
    if epochs_input not in {"auto", "cleaned", "filtered"}:
        raise ValueError(
            "epochs.input must be one of 'auto', 'cleaned', or 'filtered', "
            f"got {epochs_input!r}."
        )

    epochs = EpochsConfig(
        input=epochs_input,
        tmin=float(epochs_raw.get("tmin", -1.0)),
        tmax=float(epochs_raw.get("tmax", 1.0)),
        baseline=_optional_baseline(epochs_raw.get("baseline", None)),
        bad_interpolation=epochs_raw.get("bad_interpolation", "epochs"),
    )

    autoreject_raw = raw.get("autoreject", {})
    autoreject = AutorejectConfig(
        enabled=bool(autoreject_raw.get("enabled", False)),
        use=autoreject_raw.get("use"),
        consensus_percs=_optional_float_tuple(
            autoreject_raw.get("consensus_percs", None)
        ),
        n_interpolates=_optional_int_tuple(
            autoreject_raw.get("n_interpolates", None)
        ),
        subset=_optional_int_or_float(autoreject_raw.get("subset", None)),
        tmin=_optional_float(autoreject_raw.get("tmin", None)),
        tmax=_optional_float(autoreject_raw.get("tmax", None)),
        crop_to_epochs=bool(autoreject_raw.get("crop_to_epochs", True)),
    )


    conditions_raw = raw.get("conditions", {})
    if conditions_raw is None:
        condition_definitions_raw: dict[str, Any] = {}
    elif not isinstance(conditions_raw, dict):
        raise ValueError("conditions must be a mapping or null.")
    elif "definitions" in conditions_raw:
        definitions_value = conditions_raw.get("definitions") or {}
        if not isinstance(definitions_value, dict):
            raise ValueError("conditions.definitions must be a mapping.")
        condition_definitions_raw = definitions_value
    else:
        # Backward-compatible shorthand:
        # conditions:
        #   my_condition: "metadata_query"
        # Ignore reserved non-definition keys.
        reserved = {"mode"}
        condition_definitions_raw = {
            str(key): value
            for key, value in conditions_raw.items()
            if str(key) not in reserved
        }

    condition_definitions: dict[str, Any] = {}
    for name, definition in condition_definitions_raw.items():
        if isinstance(definition, str):
            condition_definitions[str(name)] = definition
        elif isinstance(definition, (list, tuple, set)):
            condition_definitions[str(name)] = [int(value) for value in definition]
        elif definition is None:
            raise ValueError(f"Condition definition {name!r} must not be null.")
        else:
            raise TypeError(
                "Condition definitions must be pandas query strings or lists "
                f"of integer event IDs, got {type(definition)!r} for {name!r}."
            )

    conditions = ConditionsConfig(definitions=condition_definitions)

    connectivity_raw = raw.get("connectivity", {})

    connectivity_input = str(connectivity_raw.get("input", "label_time_course_epochs"))
    if connectivity_input != "label_time_course_epochs":
        raise ValueError(
            "connectivity.input currently must be 'label_time_course_epochs', "
            f"got {connectivity_input!r}."
        )

    connectivity_space = str(connectivity_raw.get("space", "label"))
    if connectivity_space != "label":
        raise ValueError(
            "connectivity.space currently must be 'label', "
            f"got {connectivity_space!r}."
        )

    connectivity_windows_raw = connectivity_raw.get(
        "windows",
        {"note_early": {"tmin": 0.0, "tmax": 0.25}},
    )
    connectivity_windows: dict[str, ConnectivityWindowConfig] = {}
    for name, window_raw in connectivity_windows_raw.items():
        connectivity_windows[str(name)] = ConnectivityWindowConfig(
            tmin=float(window_raw["tmin"]),
            tmax=float(window_raw["tmax"]),
        )
        if connectivity_windows[str(name)].tmax <= connectivity_windows[str(name)].tmin:
            raise ValueError(f"connectivity.windows.{name}.tmax must be larger than tmin.")

    connectivity_bands_raw = connectivity_raw.get(
        "bands",
        {
            "beta": {"fmin": 13.0, "fmax": 30.0},
            "low_gamma": {"fmin": 30.0, "fmax": 70.0},
        },
    )
    connectivity_bands: dict[str, ConnectivityBandConfig] = {}
    for name, band_raw in connectivity_bands_raw.items():
        connectivity_bands[str(name)] = ConnectivityBandConfig(
            fmin=float(band_raw["fmin"]),
            fmax=float(band_raw["fmax"]),
        )
        if connectivity_bands[str(name)].fmax <= connectivity_bands[str(name)].fmin:
            raise ValueError(f"connectivity.bands.{name}.fmax must be larger than fmin.")

    connectivity_conditions_raw = connectivity_raw.get("conditions", "all")
    if connectivity_conditions_raw == "all":
        connectivity_conditions: tuple[str, ...] | Literal["all"] = "all"
    else:
        connectivity_conditions = _str_tuple(connectivity_conditions_raw, ())

    connectivity_n_jobs_raw = connectivity_raw.get("n_jobs", None)
    connectivity_n_jobs = (
        None if connectivity_n_jobs_raw is None else int(connectivity_n_jobs_raw)
    )

    connectivity_save_format = str(connectivity_raw.get("save_format", "npz"))
    if connectivity_save_format != "npz":
        raise ValueError(
            "connectivity.save_format currently must be 'npz', "
            f"got {connectivity_save_format!r}."
        )

    connectivity = ConnectivityConfig(
        enabled=bool(connectivity_raw.get("enabled", True)),
        input=connectivity_input,
        space=connectivity_space,
        parcellation=connectivity_raw.get("parcellation", None),
        methods=_str_tuple(connectivity_raw.get("methods", ["imcoh", "wpli"]), ("imcoh", "wpli")),
        mode=str(connectivity_raw.get("mode", "multitaper")),
        windows=connectivity_windows,
        bands=connectivity_bands,
        faverage=bool(connectivity_raw.get("faverage", True)),
        conditions=connectivity_conditions,
        label_patterns=_optional_str_tuple(connectivity_raw.get("label_patterns", None)),
        block_size=int(connectivity_raw.get("block_size", 1000)),
        n_jobs=connectivity_n_jobs,
        save_format=connectivity_save_format,
    )

    source_raw = raw.get("source", {})
    source_inverse_raw = source_raw.get("inverse", {})
    source_labels_raw = source_raw.get("labels", {})
    source_noise_cov_raw = source_raw.get("noise_cov", {})
    apply_inverse_raw = source_raw.get("apply_inverse", {})

    valid_inverse_methods = {"MNE", "dSPM", "sLORETA", "eLORETA"}

    inverse_method = str(
        source_inverse_raw.get(
            "method",
            source_raw.get("inverse_method", "dSPM"),
        )
    )
    if inverse_method not in valid_inverse_methods:
        raise ValueError(
            "source.inverse.method must be one of 'MNE', 'dSPM', "
            f"'sLORETA', or 'eLORETA', got {inverse_method!r}."
        )

    inverse_snr = float(
        source_inverse_raw.get(
            "snr",
            source_raw.get("snr", 3.0),
        )
    )
    inverse_lambda2 = _optional_float(
        source_inverse_raw.get(
            "lambda2",
            source_raw.get("lambda2", None),
        )
    )
    inverse_pick_ori_raw = source_inverse_raw.get(
        "pick_ori",
        source_raw.get("pick_ori", None),
    )
    inverse_pick_ori = None if inverse_pick_ori_raw is None else str(inverse_pick_ori_raw)

    labels_parcellation = str(
        source_labels_raw.get(
            "parcellation",
            source_raw.get("parcellation", "aparc_sub"),
        )
    )
    labels_extract_mode = str(
        source_labels_raw.get(
            "extract_mode",
            source_raw.get("extract_mode", "mean_flip"),
        )
    )
    labels_target_labels = _optional_str_tuple(
        source_labels_raw.get(
            "target_labels",
            source_raw.get("target_labels", None),
        )
    )

    noise_cov_mode = str(
        source_noise_cov_raw.get(
            "mode",
            source_raw.get("noise_cov_mode", "erm"),
        )
    )

    apply_to = str(apply_inverse_raw.get("apply_to", "evoked"))
    if apply_to not in {"evoked", "epochs"}:
        raise ValueError(
            "source.apply_inverse.apply_to must be one of 'evoked' or 'epochs', "
            f"got {apply_to!r}."
        )

    apply_inverse_method = str(apply_inverse_raw.get("method", inverse_method))
    if apply_inverse_method not in valid_inverse_methods:
        raise ValueError(
            "source.apply_inverse.method must be one of 'MNE', 'dSPM', "
            f"'sLORETA', or 'eLORETA', got {apply_inverse_method!r}."
        )

    apply_inverse_snr = float(apply_inverse_raw.get("snr", inverse_snr))
    apply_inverse_lambda2 = _optional_float(
        apply_inverse_raw.get("lambda2", inverse_lambda2)
    )

    pick_conditions_raw = apply_inverse_raw.get("pick_conditions", "all")
    if pick_conditions_raw == "all":
        pick_conditions: tuple[str, ...] | Literal["all"] = "all"
    else:
        pick_conditions = _str_tuple(pick_conditions_raw, ())

    stc_format = str(apply_inverse_raw.get("stc_format", "h5"))
    if stc_format != "h5":
        raise ValueError(
            "source.apply_inverse.stc_format currently must be 'h5', "
            f"got {stc_format!r}."
        )

    morph_raw = source_raw.get("morph", {})

    morph_method_raw = morph_raw.get("method", None)
    morph_method = None if morph_method_raw is None else str(morph_method_raw)
    if morph_method is not None and morph_method not in valid_inverse_methods:
        raise ValueError(
            "source.morph.method must be null or one of 'MNE', 'dSPM', "
            f"'sLORETA', or 'eLORETA', got {morph_method!r}."
        )

    morph_pick_conditions_raw = morph_raw.get("pick_conditions", "all")
    if morph_pick_conditions_raw == "all":
        morph_pick_conditions: tuple[str, ...] | Literal["all"] = "all"
    else:
        morph_pick_conditions = _str_tuple(morph_pick_conditions_raw, ())

    morph_stc_format = str(morph_raw.get("stc_format", "h5"))
    if morph_stc_format != "h5":
        raise ValueError(
            "source.morph.stc_format currently must be 'h5', "
            f"got {morph_stc_format!r}."
        )

    label_time_courses_epochs_raw = source_raw.get("label_time_courses_epochs", {})

    ltc_epochs_method = str(
        label_time_courses_epochs_raw.get(
            "method",
            apply_inverse_method,
        )
    )
    if ltc_epochs_method not in valid_inverse_methods:
        raise ValueError(
            "source.label_time_courses_epochs.method must be one of 'MNE', "
            f"'dSPM', 'sLORETA', or 'eLORETA', got {ltc_epochs_method!r}."
        )

    ltc_epochs_decim = _optional_int(label_time_courses_epochs_raw.get("decim", 5))
    if ltc_epochs_decim is not None and ltc_epochs_decim < 1:
        raise ValueError("source.label_time_courses_epochs.decim must be >= 1 or null.")

    ltc_epochs_dtype = str(label_time_courses_epochs_raw.get("dtype", "float32"))
    if ltc_epochs_dtype not in {"float32", "float64"}:
        raise ValueError(
            "source.label_time_courses_epochs.dtype must be 'float32' or 'float64', "
            f"got {ltc_epochs_dtype!r}."
        )

    ltc_epochs_save_format = str(label_time_courses_epochs_raw.get("save_format", "npy"))
    if ltc_epochs_save_format != "npy":
        raise ValueError(
            "source.label_time_courses_epochs.save_format currently must be 'npy', "
            f"got {ltc_epochs_save_format!r}."
        )

    source = SourceConfig(
        spacing=source_raw.get("spacing", "ico5"),
        inverse=SourceInverseConfig(
            method=inverse_method,
            snr=inverse_snr,
            lambda2=inverse_lambda2,
            pick_ori=inverse_pick_ori,
        ),
        labels=SourceLabelsConfig(
            parcellation=labels_parcellation,
            extract_mode=labels_extract_mode,
            target_labels=labels_target_labels,
        ),
        noise_cov=SourceNoiseCovConfig(mode=noise_cov_mode),
        apply_inverse=SourceApplyInverseConfig(
            apply_to=apply_to,
            method=apply_inverse_method,
            snr=apply_inverse_snr,
            lambda2=apply_inverse_lambda2,
            pick_conditions=pick_conditions,
            save_stcs=bool(apply_inverse_raw.get("save_stcs", True)),
            stc_format=stc_format,
        ),
        morph=SourceMorphConfig(
            enabled=bool(morph_raw.get("enabled", True)),
            subject_to=str(morph_raw.get("subject_to", "fsaverage")),
            spacing=morph_raw.get("spacing", None),
            smooth=_optional_int(morph_raw.get("smooth", None)),
            method=morph_method,
            pick_conditions=morph_pick_conditions,
            stc_format=morph_stc_format,
        ),
        label_time_courses_epochs=SourceLabelTimeCoursesEpochsConfig(
            enabled=bool(label_time_courses_epochs_raw.get("enabled", True)),
            method=ltc_epochs_method,
            snr=float(label_time_courses_epochs_raw.get("snr", apply_inverse_snr)),
            lambda2=_optional_float(label_time_courses_epochs_raw.get("lambda2", apply_inverse_lambda2)),
            parcellation=label_time_courses_epochs_raw.get("parcellation", None),
            extract_mode=label_time_courses_epochs_raw.get("extract_mode", None),
            target_labels=_optional_str_tuple(label_time_courses_epochs_raw.get("target_labels", None)),
            decim=ltc_epochs_decim,
            tmin=_optional_float(label_time_courses_epochs_raw.get("tmin", None)),
            tmax=_optional_float(label_time_courses_epochs_raw.get("tmax", None)),
            dtype=ltc_epochs_dtype,
            save_format=ltc_epochs_save_format,
        ),
    )

    return PipelineConfig(
        project_name=raw["project"]["name"],
        paths=paths,
        runtime=runtime,
        bids=bids,
        channels=channels,
        sourcedata=sourcedata,
        empty_room=empty_room,
        freesurfer=freesurfer,
        anatomy=anatomy,
        events=events,
        preprocessing=preprocessing,
        cleaning=cleaning,
        epochs=epochs,
        autoreject=autoreject,
        source=source,
        conditions=conditions,
        connectivity=connectivity,
    )
