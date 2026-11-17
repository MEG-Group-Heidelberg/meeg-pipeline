from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mne
import numpy as np
import pandas as pd
from mne.stats import combine_adjacency
from scipy import stats as scipy_stats
from scipy.sparse.csgraph import connected_components

from meeg_pipeline.config import PipelineConfig, StatsAnalysisConfig
from meeg_pipeline.paths import sanitize_bids_label
from meeg_pipeline.source_modeling import make_morphed_evoked_source_estimate_path
from meeg_pipeline.workflow import ExistingOutputPolicy


def _morphed_condition(condition: str) -> str:
    """Condition label as it appears in morphed STC file names.

    Source estimates are named after the sanitised evoked label, and the
    morph step sanitises that label once more. The label sanitiser is not
    idempotent (``left_auditory`` -> ``leftAuditory`` -> ``leftauditory``), so
    the same two passes are needed to find the files on case-sensitive systems.
    """
    return sanitize_bids_label(sanitize_bids_label(condition))


@dataclass(frozen=True)
class SubjectEffects:
    """Subject-level effect maps of one analysis.

    ``data`` has shape (n_subjects, n_times, n_vertices) for ``ttest`` and
    ``regression`` and (n_subjects, n_terms, n_times, n_vertices) for ``anova``.
    """

    data: np.ndarray
    subjects: list[str]
    skipped: dict[str, str]
    vertices: list[np.ndarray]
    tmin: float
    tstep: float
    moderator: np.ndarray | None = None


@dataclass(frozen=True)
class ClusterTestResult:
    analysis: str
    kind: str
    statistic: np.ndarray
    clusters: list[np.ndarray]
    cluster_stats: np.ndarray
    cluster_p_values: np.ndarray
    null_distribution: np.ndarray
    threshold: float
    n_permutations: int
    subjects: list[str]
    vertices: list[np.ndarray]
    tmin: float
    tstep: float


@dataclass(frozen=True)
class ClusterAnalysisResult:
    analysis: str
    status: str
    directory: str
    n_subjects: int = 0
    n_clusters: int = 0
    n_significant: int = 0
    message: str = ""


def make_stats_directory(config: PipelineConfig, analysis: str) -> Path:
    """Directory for the outputs of one group-level analysis."""
    return (
        config.paths.derivatives_root
        / "group"
        / "stats"
        / sanitize_bids_label(analysis)
    )


def _window(config: PipelineConfig, analysis: StatsAnalysisConfig) -> tuple[float, float]:
    tmin = config.stats.tmin if analysis.tmin is None else analysis.tmin
    tmax = config.stats.tmax if analysis.tmax is None else analysis.tmax
    if tmax <= tmin:
        raise ValueError("The statistics window needs tmax larger than tmin.")
    return tmin, tmax


def stats_subjects(config: PipelineConfig) -> list[str]:
    """Subjects that may enter group statistics, from raw BIDS and the config."""
    if config.stats.subjects == "all":
        subjects = sorted(
            path.name.removeprefix("sub-")
            for path in config.paths.bids_root.glob("sub-*")
            if path.name != "sub-emptyroom"
        )
    else:
        subjects = [str(subject).removeprefix("sub-") for subject in config.stats.subjects]

    excluded = {str(subject).removeprefix("sub-") for subject in config.stats.exclude_subjects}
    return [subject for subject in subjects if subject not in excluded]


def load_moderators(config: PipelineConfig) -> pd.DataFrame:
    """Read the per-subject scores table (column ``subject`` plus scores)."""
    if config.stats.scores_path is None:
        raise ValueError("stats.scores_path is not set in the config.")

    scores = pd.read_csv(config.stats.scores_path, sep="\t", dtype={"subject": str})
    scores["subject"] = scores["subject"].str.removeprefix("sub-")
    return scores.set_index("subject")


def _read_cropped_stc(
    config: PipelineConfig,
    *,
    subject: str,
    task: str | None,
    condition: str,
    tmin: float,
    tmax: float,
) -> mne.SourceEstimate:
    path = make_morphed_evoked_source_estimate_path(
        config,
        subject=subject,
        task=task,
        condition=_morphed_condition(condition),
    )
    if not path.exists():
        raise FileNotFoundError(path)

    return mne.read_source_estimate(path).crop(tmin, tmax)


def load_subject_effects(
    config: PipelineConfig,
    analysis: StatsAnalysisConfig,
    *,
    subjects: list[str] | None = None,
) -> SubjectEffects:
    """Load morphed source estimates and combine the terms per subject."""
    tmin, tmax = _window(config, analysis)
    candidates = stats_subjects(config) if subjects is None else list(subjects)

    moderator_table = load_moderators(config) if analysis.moderator else None

    effects: list[np.ndarray] = []
    used: list[str] = []
    skipped: dict[str, str] = {}
    template: mne.SourceEstimate | None = None
    moderator: list[float] = []

    for subject in candidates:
        if moderator_table is not None:
            if subject not in moderator_table.index:
                skipped[subject] = "no row in scores table"
                continue
            value = moderator_table.loc[subject, analysis.moderator]
            if not np.isfinite(value):
                skipped[subject] = f"missing moderator {analysis.moderator}"
                continue

        try:
            stcs = [
                _read_cropped_stc(
                    config,
                    subject=subject,
                    task=term.task,
                    condition=term.condition,
                    tmin=tmin,
                    tmax=tmax,
                )
                for term in analysis.terms
            ]
        except FileNotFoundError as error:
            skipped[subject] = f"missing source estimate: {Path(str(error)).name}"
            continue

        if template is None:
            template = stcs[0]
        if any(stc.data.shape != template.data.shape for stc in stcs):
            skipped[subject] = "time or vertex axis differs from the first subject"
            continue

        data = np.stack([stc.data.T for stc in stcs]).astype(np.float32)
        if analysis.kind == "anova":
            effects.append(data)
        else:
            weights = np.array([term.weight for term in analysis.terms], dtype=np.float32)
            effects.append(np.tensordot(weights, data, axes=1))

        used.append(subject)
        if moderator_table is not None:
            moderator.append(float(value))

    if template is None or len(used) < 3:
        raise ValueError(
            f"Need at least 3 subjects with complete data, found {len(used)}. "
            f"Skipped: {skipped}"
        )

    return SubjectEffects(
        data=np.stack(effects),
        subjects=used,
        skipped=skipped,
        vertices=[np.asarray(v) for v in template.vertices],
        tmin=float(template.tmin),
        tstep=float(template.tstep),
        moderator=np.asarray(moderator) if moderator_table is not None else None,
    )


def fsaverage_source_adjacency(
    config: PipelineConfig,
    vertices: list[np.ndarray],
    *,
    subject: str = "fsaverage",
    spacing: str = "ico5",
):
    """Spatial adjacency of the fsaverage source space the estimates live in."""
    src = mne.setup_source_space(
        subject,
        spacing=spacing,
        subjects_dir=config.freesurfer.subjects_dir,
        add_dist=False,
        verbose="error",
    )
    for hemi, source in zip(vertices, src):
        if not np.array_equal(source["vertno"], hemi):
            raise ValueError(
                "Source estimate vertices do not match the fsaverage "
                f"{spacing} source space."
            )
    return mne.spatial_src_adjacency(src, verbose="error")


def _t_statistic_one_sample(data: np.ndarray) -> np.ndarray:
    n = data.shape[0]
    std = data.std(axis=0, ddof=1)
    return data.mean(axis=0) / np.maximum(std / np.sqrt(n), 1e-30)


def _t_statistic_regression(data: np.ndarray, moderator: np.ndarray) -> np.ndarray:
    n = data.shape[0]
    centered = data - data.mean(axis=0, keepdims=True)
    numerator = moderator @ centered
    denominator = np.sqrt(
        float(moderator @ moderator) * np.maximum((centered**2).sum(axis=0), 1e-30)
    )
    r = np.clip(numerator / denominator, -0.999999, 0.999999)
    return (r * np.sqrt((n - 2) / (1 - r**2))).astype(np.float32)


def _f_statistic_repeated_measures(data: np.ndarray) -> np.ndarray:
    """One-way repeated-measures ANOVA F for data (n_subjects, n_terms, n_tests)."""
    n, k, _ = data.shape
    grand = data.mean(axis=(0, 1))
    subject_mean = data.mean(axis=1)
    term_mean = data.mean(axis=0)
    ss_terms = n * ((term_mean - grand) ** 2).sum(axis=0)
    ss_subjects = k * ((subject_mean - grand) ** 2).sum(axis=0)
    ss_total = ((data - grand) ** 2).sum(axis=(0, 1))
    ss_error = ss_total - ss_terms - ss_subjects
    return ((ss_terms / (k - 1)) / np.maximum(ss_error / ((n - 1) * (k - 1)), 1e-30)).astype(
        np.float32
    )


def _find_clusters(
    statistic: np.ndarray,
    threshold: float,
    *,
    tail: int,
    adjacency,
) -> tuple[list[np.ndarray], np.ndarray]:
    """Connected groups of supra-threshold tests and their summed statistic.

    ``adjacency`` is a CSR matrix over the flattened tests. Positive and
    negative groups are separated for two-sided tests. MNE's own search masks
    the full adjacency on every call, which is too slow for thousands of
    permutations on the fsaverage source space.
    """
    clusters: list[np.ndarray] = []
    sums: list[float] = []
    for sign in (1, -1) if tail == 0 else (1,):
        indices = np.flatnonzero(sign * statistic > threshold)
        if indices.size == 0:
            continue
        subgraph = adjacency[indices][:, indices]
        _, labels = connected_components(subgraph, directed=False)
        order = np.argsort(labels, kind="stable")
        splits = np.flatnonzero(np.diff(labels[order])) + 1
        for group in np.split(indices[order], splits):
            clusters.append(group)
            sums.append(float(statistic[group].sum()))
    return clusters, np.asarray(sums, dtype=float)


def _max_cluster_statistic(
    statistic: np.ndarray,
    threshold: float,
    tail: int,
    adjacency,
) -> float:
    _, cluster_stats = _find_clusters(
        statistic,
        threshold,
        tail=tail,
        adjacency=adjacency,
    )
    if len(cluster_stats) == 0:
        return 0.0
    if tail == 0:
        return float(np.max(np.abs(cluster_stats)))
    return float(np.max(cluster_stats))


def _null_chunk(
    kind: str,
    data: np.ndarray,
    moderator: np.ndarray | None,
    draws: np.ndarray,
    threshold: float,
    tail: int,
    adjacency,
) -> np.ndarray:
    values = np.empty(len(draws))
    for index, draw in enumerate(draws):
        if kind == "ttest":
            statistic = _t_statistic_one_sample(data * draw[:, None])
        elif kind == "regression":
            statistic = _t_statistic_regression(data, moderator[draw])
        else:
            permuted = np.take_along_axis(data, draw[:, :, None], axis=1)
            statistic = _f_statistic_repeated_measures(permuted)
        values[index] = _max_cluster_statistic(statistic, threshold, tail, adjacency)
    return values


def _permutation_draws(
    kind: str,
    n_subjects: int,
    n_terms: int,
    n_permutations: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if kind == "ttest":
        return rng.choice(np.array([-1.0, 1.0], dtype=np.float32), size=(n_permutations, n_subjects))
    if kind == "regression":
        return np.stack([rng.permutation(n_subjects) for _ in range(n_permutations)])
    return np.stack(
        [
            np.stack([rng.permutation(n_terms) for _ in range(n_subjects)])
            for _ in range(n_permutations)
        ]
    )


def run_cluster_test(
    config: PipelineConfig,
    name: str,
    analysis: StatsAnalysisConfig,
    effects: SubjectEffects,
    *,
    n_permutations: int | None = None,
    n_jobs: int | None = None,
    verbose: bool = True,
) -> ClusterTestResult:
    """Spatio-temporal cluster permutation test on subject-level effects.

    ``ttest`` flips the sign of whole subjects, ``regression`` permutes the
    moderator across subjects, and ``anova`` permutes the term labels within
    each subject. The cluster statistic is the sum of the statistic inside a
    cluster; p-values come from the distribution of the maximum cluster
    statistic.
    """
    stats_config = config.stats
    n_permutations = stats_config.n_permutations if n_permutations is None else n_permutations
    n_jobs = stats_config.n_jobs if n_jobs is None else n_jobs
    n_jobs = 1 if n_jobs is None else n_jobs

    data = effects.data
    n_subjects = data.shape[0]
    n_terms = data.shape[1] if analysis.kind == "anova" else 1
    n_times, n_vertices = data.shape[-2:]

    flat = data.reshape(*data.shape[: data.ndim - 2], n_times * n_vertices)

    adjacency = combine_adjacency(
        n_times,
        fsaverage_source_adjacency(config, effects.vertices),
    ).tocsr()

    p = stats_config.cluster_p_threshold
    moderator = None
    if analysis.kind == "ttest":
        threshold = float(scipy_stats.t.isf(p / 2, n_subjects - 1))
        tail = 0
        statistic = _t_statistic_one_sample(flat)
    elif analysis.kind == "regression":
        threshold = float(scipy_stats.t.isf(p / 2, n_subjects - 2))
        tail = 0
        moderator = effects.moderator - effects.moderator.mean()
        statistic = _t_statistic_regression(flat, moderator)
    else:
        threshold = float(scipy_stats.f.isf(p, n_terms - 1, (n_subjects - 1) * (n_terms - 1)))
        tail = 1
        statistic = _f_statistic_repeated_measures(flat)

    clusters, cluster_stats = _find_clusters(
        statistic,
        threshold,
        tail=tail,
        adjacency=adjacency,
    )

    if verbose:
        print(
            f"{name}: N={n_subjects}, window {effects.tmin:.3f}-"
            f"{effects.tmin + effects.tstep * (n_times - 1):.3f} s, "
            f"{len(clusters)} clusters above threshold {threshold:.3f}, "
            f"{n_permutations} permutations"
        )

    draws = _permutation_draws(
        analysis.kind, n_subjects, n_terms, n_permutations, stats_config.seed
    )

    if n_jobs == 1:
        null = _null_chunk(analysis.kind, flat, moderator, draws, threshold, tail, adjacency)
    else:
        from joblib import Parallel, delayed

        chunks = np.array_split(draws, max(n_jobs * 4, 1))
        parts = Parallel(n_jobs=n_jobs)(
            delayed(_null_chunk)(
                analysis.kind, flat, moderator, chunk, threshold, tail, adjacency
            )
            for chunk in chunks
            if len(chunk)
        )
        null = np.concatenate(parts)

    observed = np.abs(cluster_stats) if tail == 0 else cluster_stats
    null_with_observed = np.concatenate([null, [observed.max()] if len(observed) else []])
    p_values = np.array([(null_with_observed >= value).mean() for value in observed])

    return ClusterTestResult(
        analysis=name,
        kind=analysis.kind,
        statistic=statistic.reshape(n_times, n_vertices),
        clusters=[np.asarray(cluster) for cluster in clusters],
        cluster_stats=cluster_stats,
        cluster_p_values=p_values,
        null_distribution=null,
        threshold=threshold,
        n_permutations=n_permutations,
        subjects=effects.subjects,
        vertices=effects.vertices,
        tmin=effects.tmin,
        tstep=effects.tstep,
    )


def _vertex_labels(config: PipelineConfig, vertices: list[np.ndarray]) -> np.ndarray:
    """Annotation label name for every vertex of the fsaverage source space."""
    labels = mne.read_labels_from_annot(
        "fsaverage",
        parc=config.stats.parcellation,
        subjects_dir=config.freesurfer.subjects_dir,
        verbose="error",
    )
    names = np.full(sum(len(v) for v in vertices), "unknown", dtype=object)
    offset = 0
    for hemi_index, hemi_vertices in enumerate(vertices):
        position = {int(v): i for i, v in enumerate(hemi_vertices)}
        hemi = "lh" if hemi_index == 0 else "rh"
        for label in labels:
            if label.hemi != hemi:
                continue
            for vertex in label.vertices:
                index = position.get(int(vertex))
                if index is not None:
                    names[offset + index] = label.name
        offset += len(hemi_vertices)
    return names


def cluster_results_to_dataframe(
    config: PipelineConfig,
    result: ClusterTestResult,
) -> pd.DataFrame:
    """One row per cluster, sorted by p-value and size, with anatomical labels."""
    n_times, n_vertices = result.statistic.shape
    n_left = len(result.vertices[0])
    label_names = _vertex_labels(config, result.vertices)

    rows: list[dict[str, Any]] = []
    for cluster, stat_sum, p_value in zip(
        result.clusters, result.cluster_stats, result.cluster_p_values
    ):
        time_index, vertex_index = np.unravel_index(cluster, (n_times, n_vertices))
        values = result.statistic[time_index, vertex_index]
        peak = int(np.argmax(np.abs(values)))
        peak_vertex = int(vertex_index[peak])
        label_counts = pd.Series(label_names[np.unique(vertex_index)]).value_counts()
        hemi = "lh" if peak_vertex < n_left else "rh"
        vertno = (
            result.vertices[0][peak_vertex]
            if hemi == "lh"
            else result.vertices[1][peak_vertex - n_left]
        )
        rows.append(
            {
                "analysis": result.analysis,
                "p_value": float(p_value),
                "significant": bool(p_value < config.stats.alpha),
                "stat_sum": float(stat_sum),
                "stat_peak": float(values[peak]),
                "n_vertices": int(len(np.unique(vertex_index))),
                "n_times": int(len(np.unique(time_index))),
                "tmin_s": float(result.tmin + result.tstep * time_index.min()),
                "tmax_s": float(result.tmin + result.tstep * time_index.max()),
                "peak_time_s": float(result.tmin + result.tstep * time_index[peak]),
                "peak_hemi": hemi,
                "peak_vertex": int(vertno),
                "peak_label": str(label_names[peak_vertex]),
                "labels": "; ".join(f"{name} ({count})" for name, count in label_counts.head(5).items()),
            }
        )

    columns = [
        "analysis", "p_value", "significant", "stat_sum", "stat_peak", "n_vertices",
        "n_times", "tmin_s", "tmax_s", "peak_time_s", "peak_hemi", "peak_vertex",
        "peak_label", "labels",
    ]
    table = pd.DataFrame(rows, columns=columns)
    if table.empty:
        return table
    return table.sort_values(["p_value", "n_vertices"], ascending=[True, False]).reset_index(drop=True)


def write_cluster_results(
    config: PipelineConfig,
    name: str,
    analysis: StatsAnalysisConfig,
    result: ClusterTestResult,
    table: pd.DataFrame,
    effects: SubjectEffects,
) -> Path:
    """Write cluster table, statistic maps, and a provenance sidecar."""
    directory = make_stats_directory(config, name)
    directory.mkdir(parents=True, exist_ok=True)

    table.to_csv(directory / f"desc-{sanitize_bids_label(name)}_clusters.tsv", sep="\t", index=False)

    np.savez_compressed(
        directory / f"desc-{sanitize_bids_label(name)}_statistic.npz",
        statistic=result.statistic.astype(np.float32),
        clusters=np.array([c.astype(np.int64) for c in result.clusters], dtype=object),
        cluster_stats=result.cluster_stats,
        cluster_p_values=result.cluster_p_values,
        null_distribution=result.null_distribution,
        vertices_lh=result.vertices[0],
        vertices_rh=result.vertices[1],
        tmin=result.tmin,
        tstep=result.tstep,
        subjects=np.array(result.subjects),
    )

    sidecar = {
        "analysis": name,
        "kind": analysis.kind,
        "terms": [
            {"task": term.task, "condition": term.condition, "weight": term.weight}
            for term in analysis.terms
        ],
        "moderator": analysis.moderator,
        "window_s": list(_window(config, analysis)),
        "n_permutations": result.n_permutations,
        "cluster_p_threshold": config.stats.cluster_p_threshold,
        "cluster_forming_threshold": result.threshold,
        "alpha": config.stats.alpha,
        "seed": config.stats.seed,
        "subjects": result.subjects,
        "skipped": effects.skipped,
        "mne_version": mne.__version__,
    }
    (directory / f"desc-{sanitize_bids_label(name)}_stats.json").write_text(
        json.dumps(sidecar, indent=2) + "\n", encoding="utf-8"
    )
    return directory


def run_cluster_analysis(
    config: PipelineConfig,
    name: str,
    *,
    n_permutations: int | None = None,
    subjects: list[str] | None = None,
    n_jobs: int | None = None,
    on_existing: ExistingOutputPolicy = "skip",
    verbose: bool = True,
) -> ClusterAnalysisResult:
    """Load, test, and write one analysis defined under ``stats.analyses``."""
    if name not in config.stats.analyses:
        raise KeyError(
            f"Unknown analysis {name!r}. Defined: {sorted(config.stats.analyses)}"
        )
    analysis = config.stats.analyses[name]
    directory = make_stats_directory(config, name)
    table_path = directory / f"desc-{sanitize_bids_label(name)}_clusters.tsv"

    if table_path.exists() and on_existing == "skip":
        return ClusterAnalysisResult(
            analysis=name,
            status="exists",
            directory=str(directory),
            message="Cluster table already exists.",
        )

    try:
        effects = load_subject_effects(config, analysis, subjects=subjects)
    except ValueError as error:
        return ClusterAnalysisResult(
            analysis=name,
            status="missing_input",
            directory=str(directory),
            message=str(error),
        )

    result = run_cluster_test(
        config, name, analysis, effects, n_permutations=n_permutations, n_jobs=n_jobs, verbose=verbose
    )
    table = cluster_results_to_dataframe(config, result)
    write_cluster_results(config, name, analysis, result, table, effects)

    return ClusterAnalysisResult(
        analysis=name,
        status="written",
        directory=str(directory),
        n_subjects=len(effects.subjects),
        n_clusters=len(table),
        n_significant=int(table["significant"].sum()) if len(table) else 0,
    )


def stats_input_status_to_dataframe(config: PipelineConfig) -> pd.DataFrame:
    """Which subjects have all morphed source estimates for each analysis."""
    rows: list[dict[str, Any]] = []
    moderators = load_moderators(config) if config.stats.scores_path is not None else None
    for name, analysis in config.stats.analyses.items():
        for subject in stats_subjects(config):
            missing = [
                f"{term.task}/{term.condition}"
                for term in analysis.terms
                if not make_morphed_evoked_source_estimate_path(
                    config, subject=subject, task=term.task, condition=_morphed_condition(term.condition)
                ).exists()
            ]
            if analysis.moderator and (
                moderators is None
                or subject not in moderators.index
                or not np.isfinite(moderators.loc[subject, analysis.moderator])
            ):
                missing.append(f"moderator {analysis.moderator}")
            rows.append(
                {
                    "analysis": name,
                    "subject": subject,
                    "status": "ready" if not missing else "missing_input",
                    "missing": ", ".join(missing),
                }
            )
    return pd.DataFrame(rows, columns=["analysis", "subject", "status", "missing"])
