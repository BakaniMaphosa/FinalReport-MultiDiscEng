"""Chronological validation, three predefined candidates, then one held-out test.

Run from the project root:
  "Prediction Model/.venv/bin/python" -B "Prediction Model/run_validation_experiment.py"

Existing scripts, source data and experiment outputs are read only. Every run
creates a fresh directory under experiments/validation/. Calendar features use
UTC; exact-t weather and existing target/interval conventions remain unchanged.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys

import train_models as original
import run_followup_experiments as shared

np, pd, plt = original.np, original.pd, original.plt
BASE = original.BASE
DEVELOPMENT = shared.TRAIN_WITH_L03
TEST = shared.TEST
METHODS, METRICS = shared.METHODS, shared.METRICS
SELECTION_RULE = (
    "Minimise (equal-weight validation-building RMSE of A + equal-weight "
    "validation-building RMSE of B) / 2. Choose one shared configuration. "
    "Exact numerical ties: fewer max_leaf_nodes, then larger min_samples_leaf. "
    "Only the three predefined candidates; no test performance is consulted."
)
SPLIT_RULE = (
    "Within EACH development building sort unique UTC interval-start timestamps; "
    "fit on the first floor(0.8 * unique_count), validate on the remainder. "
    "Keep all rows at a timestamp together and preserve original row order. "
    "This is future-period validation within known buildings, with per-building "
    "cutoffs, not unseen-building validation or a common global time cutoff."
)


def now():
    return datetime.now(timezone.utc).isoformat()


def candidate_settings():
    return {
        "candidate_1": dict(original.SETTINGS),
        "candidate_2": dict(original.SETTINGS, max_leaf_nodes=15, min_samples_leaf=60),
        "candidate_3": dict(original.SETTINGS, max_leaf_nodes=7, min_samples_leaf=120),
    }


def project_snapshot(exclude=None):
    """Hash substantive files, including ALL prior experiments and raw sources."""
    paths = []
    for root in (BASE.parent / "Data", BASE.parent / "Data_cleaning", BASE):
        paths.extend(root.rglob("*"))
    paths.extend(BASE.parent.iterdir())
    result = {}
    for path in paths:
        if not path.is_file() or path.name == ".DS_Store":
            continue
        if any(part in {".venv", "__pycache__", ".git"} for part in path.parts):
            continue
        if exclude is not None and (path == exclude or exclude in path.parents):
            continue
        result[str(path.resolve())] = original.fingerprint(path)
    return result


def chronological_split(item):
    starts = item.tracking.interval_start_utc
    unique = pd.DatetimeIndex(starts.unique()).sort_values()
    count = len(unique)
    # Integer arithmetic makes the documented floor rule exact.
    n_fit = 4 * count // 5
    if n_fit < 1 or n_fit >= count:
        raise original.DataError(f"{item.building}: need at least two unique timestamps")
    cutoff = unique[n_fit]
    masks = {"fit": starts < cutoff, "validation": starts >= cutoff}
    pieces = {}
    membership = item.tracking.copy()
    membership["role"] = np.where(masks["fit"], "fit", "validation")
    membership["finite_target"] = item.target.notna().to_numpy()
    for role, mask in masks.items():
        pieces[role] = original.BuildingData(
            item.building, item.features.loc[mask].reset_index(drop=True),
            item.target.loc[mask].reset_index(drop=True),
            item.tracking.loc[mask].reset_index(drop=True), item.audit,
        )
        if not pieces[role].target.notna().any():
            raise original.DataError(f"{item.building}: no finite targets in {role}")
    fit_times = set(starts[masks["fit"]])
    validation_times = set(starts[masks["validation"]])
    if fit_times & validation_times or max(fit_times) >= min(validation_times):
        raise original.DataError(f"{item.building}: chronological split overlaps")
    fit_ids = set(pieces["fit"].tracking.source_data_row)
    val_ids = set(pieces["validation"].tracking.source_data_row)
    if fit_ids & val_ids or fit_ids | val_ids != set(item.tracking.source_data_row):
        raise original.DataError(f"{item.building}: split row membership is incomplete or overlapping")
    boundary = dict(building_id=item.building, total_rows=len(starts), unique_timestamps=count,
                    fit_unique_timestamps=n_fit, validation_unique_timestamps=count - n_fit,
                    validation_start_utc=cutoff.isoformat(),
                    within_building_timestamp_overlap=0, within_building_row_overlap=0)
    for role, piece in pieces.items():
        boundary.update({f"{role}_rows": len(piece.target),
                         f"{role}_eligible_rows": int(piece.target.notna().sum()),
                         f"{role}_first_utc": piece.tracking.interval_start_utc.min().isoformat(),
                         f"{role}_last_utc": piece.tracking.interval_start_utc.max().isoformat()})
    return pieces["fit"], pieces["validation"], boundary, membership


def evaluate_validation(predictions):
    if set(predictions.building_id) != set(DEVELOPMENT):
        raise original.DataError("Validation must contain exactly the three development buildings")
    rows = []
    for building, group in predictions.groupby("building_id", sort=True):
        for method in METHODS:
            rows.append(dict(scope="building", name=building, model=method,
                             n_rows=len(group), aggregation="building_rows",
                             **shared.metric_values(group.actual_kwh_per_m2,
                                                    group[f"predicted_{method}_kwh_per_m2"])))
    for method in METHODS:
        buildings = [r for r in rows if r["model"] == method]
        average = dict(scope="equal_weight_buildings", name="development_buildings", model=method,
                       n_rows=len(predictions), aggregation="equal_weight_mean_of_building_metrics",
                       mean_observed_target_kwh_per_m2=np.nan)
        for metric in METRICS:
            values = np.asarray([r[metric] for r in buildings])
            average[metric] = float(values.mean()) if np.isfinite(values).all() else np.nan
        average["nrmse_undefined_reason"] = "; ".join(
            f'{r["name"]}: {r["nrmse_undefined_reason"]}' for r in buildings if r["nrmse_undefined_reason"])
        rows.append(average)
    return pd.DataFrame(rows)


def select_configuration(metrics, candidates):
    scores = []
    for name, settings in candidates.items():
        group = metrics[(metrics.candidate == name) & (metrics.scope == "equal_weight_buildings")]
        errors = {}
        for model in ("A", "B"):
            values = group.loc[group.model == model, "rmse_kwh_per_m2"]
            if len(values) != 1 or not np.isfinite(values.iloc[0]):
                raise original.DataError("Selection needs one finite validation macro RMSE per candidate/model")
            errors[model] = float(values.iloc[0])
        scores.append(dict(candidate=name, A_validation_macro_rmse=errors["A"],
                           B_validation_macro_rmse=errors["B"],
                           selection_score=(errors["A"] + errors["B"]) / 2,
                           max_leaf_nodes=settings["max_leaf_nodes"],
                           min_samples_leaf=settings["min_samples_leaf"]))
    if set(metrics.candidate) != set(candidates):
        raise original.DataError("Validation candidate set differs from preregistration")
    winner = min(scores, key=lambda r: (r["selection_score"], r["max_leaf_nodes"], -r["min_samples_leaf"]))
    frame = pd.DataFrame(scores)
    frame["selected"] = frame.candidate.eq(winner["candidate"])
    return winner["candidate"], frame


def fit_baselines(features, targets, tracking):
    if set(tracking.building_id) != set(DEVELOPMENT):
        raise original.DataError("A test building entered baseline fitting")
    mean = original.DummyRegressor(strategy="mean").fit(np.zeros((len(targets), 1)), targets)
    keys = shared.calendar_keys(features, tracking)
    calendar = shared.CalendarUseBaseline().fit(keys, targets)
    np.testing.assert_allclose(mean.constant_.item(), targets.mean())
    # Reconstruct means AND counts independently from allowed fitting rows.
    frame = keys.assign(target=targets.to_numpy())
    for level in calendar.state()["lookup_tables"]:
        expected = frame.groupby(level["keys"]).target.agg(["mean", "count"])
        if sum(row["count"] for row in level["groups"]) != len(targets):
            raise original.DataError("Calendar group counts do not cover fitting rows")
        for row in level["groups"]:
            lookup = expected.loc[tuple(row[c] for c in level["keys"])]
            np.testing.assert_allclose(row["mean"], lookup["mean"])
            if row["count"] != lookup["count"]:
                raise original.DataError("Calendar group count differs from fitting rows")
    return mean, calendar


def fit_models(features, targets, tracking, settings, directory, threads):
    if set(tracking.building_id) != set(DEVELOPMENT):
        raise original.DataError("A test building entered model fitting")
    directory.mkdir(parents=True, exist_ok=False)
    models, audit = {}, {}
    with original.threadpool_limits(limits=threads):
        for label in ("A", "B"):
            pipeline = original.make_pipeline(label)
            pipeline.set_params(**{f"regressor__{k}": v for k, v in settings.items()})
            pipeline.fit(features[original.FEATURES[label]], targets)
            expected = original.HistGradientBoostingRegressor(**settings).get_params()
            if pipeline.named_steps["regressor"].get_params() != expected:
                raise original.DataError("Fitted settings differ from declared candidate")
            audit[label] = shared.preprocessing_audit(pipeline, label, features, DEVELOPMENT)
            original.joblib.dump(pipeline, directory / f"model_{label}_pipeline.joblib")
            models[label] = pipeline
    shared.write_json(directory / "fitted_preprocessing_audit.json", audit)
    pd.DataFrame([dict(model=label, representation=kind, feature=feature)
                  for label in ("A", "B")
                  for kind, names in (("input", original.FEATURES[label]),
                                      ("encoded", audit[label]["encoded_features"]))
                  for feature in names]).to_csv(directory / "predictors.csv", index=False)
    return models


def save_baselines(baselines, directory):
    directory.mkdir(parents=True, exist_ok=True)
    mean, calendar = baselines
    original.joblib.dump(mean, directory / "baseline_mean.joblib")
    shared.write_json(directory / "calendar_use_baseline.json",
                      dict(calendar.state(), fit_buildings=list(DEVELOPMENT)))


def predict_methods(models, baselines, features, targets, tracking, model_dir, baseline_dir, threads):
    predictions = tracking.copy()
    predictions["actual_kwh_per_m2"] = targets.to_numpy()
    mean, calendar = baselines
    predicted_mean = mean.predict(np.zeros((len(targets), 1)))
    predicted_calendar, fallback = calendar.predict(shared.calendar_keys(features, tracking))
    predictions["predicted_baseline_mean_kwh_per_m2"] = predicted_mean
    predictions["predicted_baseline_calendar_use_kwh_per_m2"] = predicted_calendar
    predictions["calendar_baseline_fallback"] = fallback
    restored = shared.CalendarUseBaseline.from_state(json.loads((baseline_dir / "calendar_use_baseline.json").read_text()))
    restored_prediction, restored_fallback = restored.predict(shared.calendar_keys(features, tracking))
    np.testing.assert_allclose(restored_prediction, predicted_calendar)
    np.testing.assert_array_equal(restored_fallback, fallback)
    np.testing.assert_allclose(original.joblib.load(baseline_dir / "baseline_mean.joblib").predict(
        np.zeros((len(targets), 1))), predicted_mean)
    with original.threadpool_limits(limits=threads):
        for label, pipeline in models.items():
            values = pipeline.predict(features[original.FEATURES[label]])
            reloaded = original.joblib.load(model_dir / f"model_{label}_pipeline.joblib")
            np.testing.assert_allclose(reloaded.predict(features[original.FEATURES[label]]), values,
                                       rtol=1e-12, atol=1e-13)
            predictions[f"predicted_{label}_kwh_per_m2"] = values
    for method in METHODS:
        if not np.isfinite(predictions[f"predicted_{method}_kwh_per_m2"]).all():
            raise original.DataError(f"Non-finite predictions: {method}")
    return predictions


def save_evaluation(predictions, directory, validation):
    directory.mkdir(parents=True, exist_ok=False)
    evaluator = evaluate_validation if validation else shared.evaluate
    stem = "validation" if validation else "test"
    metrics = evaluator(predictions)
    predictions.to_csv(directory / f"{stem}_predictions.csv", index=False)
    metrics.to_csv(directory / "metrics.csv", index=False)
    shared.compare_metrics(metrics, "A", ("B",)).to_csv(directory / "weather_error_reductions.csv", index=False)
    pd.concat([shared.compare_metrics(metrics, b, ("A", "B")) for b in METHODS[:2]], ignore_index=True).to_csv(
        directory / "baseline_comparisons.csv", index=False)
    # Verify metrics from reread, persisted predictions, including undefined reasons.
    reread = pd.read_csv(directory / f"{stem}_predictions.csv")
    expected = evaluator(reread).set_index(["scope", "name", "model"]).sort_index()
    saved = pd.read_csv(directory / "metrics.csv", keep_default_na=False).set_index(
        ["scope", "name", "model"]).sort_index()
    pd.testing.assert_index_equal(expected.index, saved.index)
    for column in (*METRICS, "mean_observed_target_kwh_per_m2", "n_rows"):
        np.testing.assert_allclose(pd.to_numeric(saved[column], errors="coerce"), expected[column],
                                   rtol=1e-10, atol=1e-12, equal_nan=True)
    if expected.nrmse_undefined_reason.tolist() != saved.nrmse_undefined_reason.tolist():
        raise original.DataError("Saved nRMSE reasons disagree with saved predictions")
    # Check all saved comparison columns, including undefined-reference reasons.
    for filename, expected_comparison in (
        ("weather_error_reductions.csv", shared.compare_metrics(expected.reset_index(), "A", ("B",))),
        ("baseline_comparisons.csv", pd.concat([
            shared.compare_metrics(expected.reset_index(), b, ("A", "B")) for b in METHODS[:2]], ignore_index=True)),
    ):
        stored = pd.read_csv(directory / filename, keep_default_na=False)
        key = ["scope", "name", "reference_model", "model"]
        stored, expected_comparison = stored.set_index(key).sort_index(), expected_comparison.set_index(key).sort_index()
        pd.testing.assert_index_equal(stored.index, expected_comparison.index)
        for column in expected_comparison:
            if pd.api.types.is_numeric_dtype(expected_comparison[column]):
                np.testing.assert_allclose(pd.to_numeric(stored[column], errors="coerce"), expected_comparison[column],
                                           rtol=1e-9, atol=1e-10, equal_nan=True)
            elif stored[column].tolist() != expected_comparison[column].tolist():
                raise original.DataError("Saved comparison reasons disagree")
    return metrics


def make_charts(scores, validation_metrics, test_metrics, directory):
    directory.mkdir(exist_ok=False)
    fig, ax = plt.subplots(figsize=(11, 6))
    x = np.arange(len(scores))
    for offset, method in ((-0.18, "A"), (0.18, "B")):
        bars = ax.bar(x + offset, scores[f"{method}_validation_macro_rmse"], width=0.36,
                      label=shared.LABELS[method], color=shared.COLORS[method])
        ax.bar_label(bars, fmt="%.4g", padding=3, fontsize=8)
    ax.plot(x, scores.selection_score, "ko--", label="Shared selection score: mean of A/B RMSE")
    for method in METHODS[:2]:
        value = validation_metrics[(validation_metrics.candidate == "candidate_1") &
                                   (validation_metrics.scope == "equal_weight_buildings") &
                                   (validation_metrics.model == method)].rmse_kwh_per_m2.iloc[0]
        ax.axhline(value, color=shared.COLORS[method], linestyle=":", label=shared.LABELS[method])
    ax.set_xticks(x, [f"{r.candidate}{' (selected)' if r.selected else ''}\n"
                     f"leaves={r.max_leaf_nodes}, min leaf={r.min_samples_leaf}" for r in scores.itertuples()])
    ax.set_ylabel("Equal-weight mean of validation-building RMSEs (kWh/m²)")
    ax.set_title("Chronological validation within known buildings\nThree predefined candidates; lower is better")
    ax.legend(fontsize=8, ncol=2)
    ax.margins(y=0.28)
    fig.tight_layout()
    fig.savefig(directory / "validation_candidate_comparison.png", dpi=160)
    plt.close(fig)
    for metric, label in zip(METRICS[:2], ("MAE", "RMSE")):
        fig, ax = plt.subplots(figsize=(11, 6))
        locations = test_metrics[test_metrics.scope == "location"]
        for offset, method in zip((-0.3, -0.1, 0.1, 0.3), METHODS):
            values = [locations[(locations.name == location) & (locations.model == method)][metric].iloc[0]
                      for location in ("L07", "L14")]
            bars = ax.bar(np.arange(2) + offset, values, width=0.2,
                          color=shared.COLORS[method], label=shared.LABELS[method])
            ax.bar_label(bars, fmt="%.4g", padding=3, fontsize=8)
        ax.set_xticks([0, 1], ["L07: unseen location", "L14: unseen buildings; known location"])
        ax.set_ylabel(f"{label} (kWh/m²)")
        ax.set_title(f"Validation-guided refit: {label} by held-out test location\nPreviously inspected tests; lower is better")
        ax.legend(fontsize=8, ncol=2)
        ax.margins(y=0.25)
        fig.tight_layout()
        fig.savefig(directory / f"final_{label.lower()}_by_test_location.png", dpi=160)
        plt.close(fig)


def write_methodology(run, boundaries, scores, selected, validation_metrics, test_metrics, command):
    best_validation = validation_metrics[(validation_metrics.candidate == selected) &
                                         (validation_metrics.scope == "equal_weight_buildings")]
    text = [
        "# Chronological validation and shared parameter selection\n",
        "This is a validation-guided follow-up. The four test buildings were already inspected in earlier fixed-setting and sensitivity experiments; they are not a newly untouched final test. Original files/results remain preserved.\n",
        "## Design and isolation\n", SPLIT_RULE + "\n",
        "Development: L03_B01, L14_B04, L14_B05. Test: L07_B01, L14_B01/B02/B03. "
        "Cross-building time ranges can overlap: only the within-building future boundary is enforced. "
        "Validation measures later periods of known buildings. Held-out testing measures transfer: "
        "L07 is an unseen location; L14 contains unseen buildings within a known location.\n",
        shared.markdown_table(boundaries), "\n## Preregistered comparison\n", SELECTION_RULE + "\n",
        "candidate_1 uses all original settings. candidate_2 changes only max_leaf_nodes=15 and "
        "min_samples_leaf=60; candidate_3 changes only max_leaf_nodes=7 and min_samples_leaf=120. "
        "Both models retain 200 iterations, learning rate 0.08, L2=1, max_bins=255, seed 42 and "
        "early_stopping=False. candidate_plan.json was written before fitting or scoring. "
        "selected_settings.json was written before any test-building data was loaded. No search expansion occurred.\n",
        shared.markdown_table(scores), f"\nSelected shared configuration: **{selected}**.\n",
        "## Features, preprocessing, baselines and alignment\n",
        "Existing train_models.py builds the exact original 22 metadata/calendar predictors for A and "
        "the same plus six weather predictors for B. Raw and encoded names are saved in predictors.csv "
        "and fitted_preprocessing_audit.json at every fitting stage. Electricity, target-derived columns, "
        "IDs and raw timestamps are excluded by the existing allowlist; no target shift or source rescaling occurs.\n",
        "Calendar features use UTC because no documented local mapping is available. Original exact-t "
        "weather is used without changing staged values. Reanalysis weather's per-variable interval semantics "
        "and publication latency are not documented: availability at prediction time t for [t,t+1 hour) "
        "remains an assumption, so these are conditional predictive comparisons.\n",
        "For validation, medians, missingness indicators and one-hot vocabularies are fitted on earliest-80% "
        "rows only. Unknown categories use the original ignore policy. Both baselines fit those same rows: "
        "global row-weighted target mean, and building_use×weekday×hour means falling back to "
        "building_use×hour, weekday×hour, then global mean. Means/counts and preprocessing are independently "
        "checked against allowed rows. Baselines are fitted once and shared across all candidates.\n",
        "Inputs/targets are paired by building and checked by the existing loader. Current target-only "
        "files preserve exporter order and must exactly match mirrored input targets row by row. "
        "Masks are applied jointly to features/targets/tracking without independently sorting files. "
        "Only non-finite targets are ineligible; weather missingness does not change comparison rows.\n",
        "## Validation results\n",
        "MAE/RMSE use kWh/m². nRMSE (%) = 100 × RMSE / observed mean target, undefined with a reason "
        "for non-positive/invalid means. Validation averages give equal weight to the three buildings' "
        "metrics, not their row counts. The nRMSE average is a mean of percentages, not a pooled normalisation.\n",
        shared.markdown_table(best_validation[["model", *METRICS]]),
        "\nAll candidates' building-level metrics and aligned predictions are retained in validation/.\n",
        "## Full-development refit and previously inspected test results\n",
        "After selection, both pipelines and both baselines were refitted on the full three-building "
        "development pool. The locked setting was evaluated once on the four tests. Test results did not "
        "change the candidate, training pool, features, L03 units or weather timing. Repeated numerical "
        "verification uses the same saved predictions and is not another selection step.\n",
        shared.markdown_table(test_metrics[["scope", "name", "model", *METRICS]]),
        "\nTest location metrics pool that location's rows. The final equal-location summary averages "
        "L07/L14 metrics separately; it is neither pooled RMSE nor pooled nRMSE. Baseline and B-versus-A "
        "percentage reductions are 100×(reference error−model error)/reference error; zero/undefined "
        "references leave an empty percentage and reason. Positive means improvement.\n",
        "## Interpretation and reproducibility\n",
        "Validation performance does not guarantee improved transfer to other buildings. Limited training "
        "building diversity, unresolved L03 scale, UTC-only calendar assumptions, weather availability and "
        "previous test inspection remain limitations. Predictive weather differences are not causal evidence. "
        "No correction is inferred merely from a distribution or model error.\n",
        "Split boundaries and row membership, candidate plan, settings, all predictions/metrics, stage "
        "events, fitted preprocessing/baselines and source hashes are saved. Saved estimators were reloaded "
        "to reproduce predictions; metrics and comparison percentages were recomputed from saved CSVs. "
        "Existing project files were hashed before and after. The pre-update progress report is archived "
        "here so a later authorised report update retains its historical hash.\n",
        "Reproduce from the project root (creates a new timestamped directory):\n\n```bash\n" + command + "\n```\n",
        "Install pinned dependencies with `\"Prediction Model/.venv/bin/python\" -m pip install -r "
        "\"" + str(run.relative_to(BASE.parent) / "requirements_versions.txt") + "\"`. "
        "Exact versions, full pip freeze and the command are retained alongside the manifest.\n",
    ]
    (run / "methodology_and_results.md").write_text("\n".join(text), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    if args.threads < 1:
        parser.error("--threads must be positive")
    old_manifest = json.loads((BASE / "results/run_manifest.json").read_text())
    if original.SETTINGS != old_manifest["model_settings"] or original.FEATURES != old_manifest["input_predictors"]:
        raise original.DataError("Original features/settings changed")
    if original.fingerprint(BASE / "train_models.py") != old_manifest["training_script_sha256"]:
        raise original.DataError("Original training script changed")
    source_hashes = {}
    for audit in old_manifest["building_audits"]:
        source_hashes.update(audit["source_sha256"])
    shared.verify_hashes(source_hashes)
    preserved = project_snapshot()
    pairs = original.discover_pairs(BASE)
    if set(pairs) != set(DEVELOPMENT) | set(TEST) or set(DEVELOPMENT) & set(TEST):
        raise original.DataError("Expected the seven disjoint development/test buildings")
    candidates = candidate_settings()
    run = shared.new_run_directory(BASE / "experiments/validation")
    events = []
    def event(name):
        events.append(dict(event=name, utc=now()))
        print(f"[{events[-1]['utc']}] {name}", flush=True)
    plan = dict(recorded_utc=now(), candidates=candidates, selection_rule=SELECTION_RULE,
                split_rule=SPLIT_RULE, development_buildings=list(DEVELOPMENT), test_buildings=list(TEST),
                predictors=original.FEATURES, weather="original exact-t", target_shift_hours=0,
                validation_aggregation="equal weight per development building", test_data_loaded=False)
    shared.write_json(run / "candidate_plan.json", plan)
    plan_hash = original.fingerprint(run / "candidate_plan.json")
    shared.write_json(run / "preservation_hashes.json", preserved)
    shutil.copyfile(BASE.parent / "progress_so_far.md", run / "progress_report_before_validation_update.md")
    command = shlex.join([sys.executable, "-B", str(Path(__file__).resolve()), "--threads", str(args.threads)])
    (run / "command.txt").write_text("PYTHONDONTWRITEBYTECODE=1 " + command + "\n", encoding="utf-8")
    versions = {p: importlib.metadata.version(p) for p in
                ("numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "joblib", "threadpoolctl")}
    versions["python"] = platform.python_version()
    shared.write_json(run / "dependency_versions.json", versions)
    (run / "requirements_versions.txt").write_text("\n".join(f"{p}=={v}" for p, v in versions.items() if p != "python") + "\n")
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], check=True, capture_output=True, text=True)
    (run / "environment_freeze.txt").write_text(freeze.stdout)
    event("candidate_plan_recorded_before_fitting_or_scoring")
    generator = BASE.parent / "Data_cleaning/export_prediction_targets.py"
    # Only development CSVs are loaded before selection. Test files are hashed,
    # but their data and prior prediction results never enter the selector.
    development = {b: original.load_building(b, *pairs[b], generator) for b in DEVELOPMENT}
    fitting, validation, boundaries, memberships = {}, {}, [], []
    for building, item in development.items():
        fitting[building], validation[building], boundary, membership = chronological_split(item)
        boundaries.append(boundary)
        memberships.append(membership)
    boundaries = pd.DataFrame(boundaries)
    boundaries.to_csv(run / "split_boundaries.csv", index=False)
    pd.concat(memberships, ignore_index=True).to_csv(run / "development_row_membership.csv", index=False)
    print(SPLIT_RULE, flush=True)
    print(boundaries.to_string(index=False), flush=True)
    for label, features in original.FEATURES.items():
        print(f"Model {label} predictors ({len(features)}): {', '.join(features)}", flush=True)
    fit_x, fit_y, fit_tracking = original.combine(fitting, DEVELOPMENT)
    val_x, val_y, val_tracking = original.combine(validation, DEVELOPMENT)
    print(f"Fit: {len(fit_y):,}; validation: {len(val_y):,}; original exact-t weather retained.", flush=True)
    print(original.WEATHER_ASSUMPTION, flush=True)
    validation_root = run / "validation"
    validation_root.mkdir()
    fit_tracking.to_csv(validation_root / "fitting_rows.csv", index=False)
    val_tracking.to_csv(validation_root / "validation_rows.csv", index=False)
    baselines = fit_baselines(fit_x, fit_y, fit_tracking)
    save_baselines(baselines, validation_root / "baselines")
    all_metrics = []
    baseline_predictions = None
    for name, settings in candidates.items():
        directory = validation_root / name
        event(f"fit_and_validate_{name}")
        models = fit_models(fit_x, fit_y, fit_tracking, settings, directory / "models", args.threads)
        predictions = predict_methods(models, baselines, val_x, val_y, val_tracking,
                                      directory / "models", validation_root / "baselines", args.threads)
        current_baselines = predictions[[f"predicted_{b}_kwh_per_m2" for b in METHODS[:2]]]
        if baseline_predictions is None:
            baseline_predictions = current_baselines.copy()
        else:
            pd.testing.assert_frame_equal(current_baselines, baseline_predictions)
        metrics = save_evaluation(predictions, directory / "results", validation=True)
        metrics.insert(0, "candidate", name)
        all_metrics.append(metrics)
        print(metrics[metrics.scope == "equal_weight_buildings"].to_string(index=False), flush=True)
    validation_metrics = pd.concat(all_metrics, ignore_index=True)
    validation_metrics.to_csv(validation_root / "all_candidate_metrics.csv", index=False)
    selected, scores = select_configuration(validation_metrics, candidates)
    scores.to_csv(run / "selection_scores.csv", index=False)
    shared.write_json(run / "selected_settings.json", dict(
        selected_utc=now(), candidate=selected, settings=candidates[selected], selection_rule=SELECTION_RULE,
        scores=scores.to_dict("records"), test_data_loaded=False, candidate_plan_sha256=plan_hash))
    event("shared_settings_selected_and_saved_before_loading_test_data")
    print(scores.to_string(index=False), flush=True)
    full_x, full_y, full_tracking = original.combine(development, DEVELOPMENT)
    final = run / "final"
    final_models = fit_models(full_x, full_y, full_tracking, candidates[selected], final / "models", args.threads)
    full_baselines = fit_baselines(full_x, full_y, full_tracking)
    save_baselines(full_baselines, final / "models")
    event("selected_models_and_baselines_refitted_on_all_development_rows")
    test = {b: original.load_building(b, *pairs[b], generator) for b in TEST}
    test_x, test_y, test_tracking = original.combine(test, TEST)
    event("test_building_data_loaded_after_selection_and_refit")
    prior_predictions = pd.read_csv(BASE / "results/test_predictions.csv")
    shared.check_shared_rows(test_tracking, test_y, prior_predictions)
    predictions = predict_methods(final_models, full_baselines, test_x, test_y, test_tracking,
                                  final / "models", final / "models", args.threads)
    test_metrics = save_evaluation(predictions, final / "results", validation=False)
    shared.verify_saved_metrics(final)
    for building in TEST:
        predictions[predictions.building_id == building].to_csv(final / "results" / f"{building}_predictions.csv", index=False)
    print(f"Full development refit: {len(full_y):,}; held-out test: {len(test_y):,}.", flush=True)
    print(test_metrics.to_string(index=False), flush=True)
    print(pd.read_csv(final / "results/baseline_comparisons.csv").query(
        "scope == 'equal_weight_locations'").to_string(index=False), flush=True)
    make_charts(scores, validation_metrics, test_metrics, run / "charts")
    write_methodology(run, boundaries, scores, selected, validation_metrics, test_metrics,
                      "PYTHONDONTWRITEBYTECODE=1 " + command)
    audits = [item.audit for item in [*development.values(), *test.values()]]
    shared.write_json(run / "alignment_audits.json", audits)
    for item in audits:
        source_hashes.update(item["source_sha256"])
    if original.fingerprint(run / "candidate_plan.json") != plan_hash:
        raise original.DataError("Candidate plan changed after registration")
    shared.verify_hashes(preserved)
    if project_snapshot(exclude=run) != preserved:
        raise original.DataError("Pre-existing project file set changed")
    event("saved_estimators_predictions_metrics_splits_and_preservation_verified")
    shared.write_json(run / "stage_events.json", events)
    shared.write_json(run / "verification_summary.json", dict(
        within_building_timestamp_and_row_overlap=0, split_union_covers_all_development_rows=True,
        input_target_alignment_verified=True, fitting_rows=len(fit_y), validation_rows=len(val_y),
        full_development_rows=len(full_y), test_rows=len(test_y),
        validation_metric_rows=len(validation_metrics), final_test_metric_rows=len(test_metrics),
        training_only_preprocessing_and_baseline_statistics_verified=True,
        saved_estimators_reproduce_predictions=True, saved_predictions_reproduce_metrics_and_comparisons=True,
        same_validation_rows_all_candidates_and_methods=True, same_original_test_rows_all_methods=True,
        test_loaded_only_after_selection_and_full_refit=True, preregistration_unchanged=True,
        previous_project_files_unchanged=True, preserved_file_count=len(preserved), chart_count=3))
    shared.write_json(run / "run_manifest.json", dict(
        status="validation_guided_followup_on_previously_inspected_tests", completed_utc=now(),
        command=command, versions=versions, development_buildings=list(DEVELOPMENT), test_buildings=list(TEST),
        split_rule=SPLIT_RULE, boundaries=boundaries.to_dict("records"), candidates=candidates,
        candidate_plan_sha256=plan_hash, selection_rule=SELECTION_RULE, selected_candidate=selected,
        selected_settings=candidates[selected], predictors=original.FEATURES, source_hashes=source_hashes,
        preservation_hashes_file="preservation_hashes.json", stage_events=events,
        calendar_timezone="UTC", weather_alignment="exact interval_start_utc (original exact-t)",
        weather_availability_limitation=original.WEATHER_ASSUMPTION, target_shift_hours=0,
        fit_rows=len(fit_y), validation_rows=len(val_y), development_rows=len(full_y), test_rows=len(test_y),
        validation_aggregation="arithmetic mean of three building metrics separately",
        test_aggregation="per building, pooled per location, arithmetic mean of two location metrics",
        final_calendar_fallback_usage=dict(Counter(predictions.calendar_baseline_fallback)),
        preservation_note="All prior files unchanged at completion; pre-update progress report archived here for subsequent authorised documentation update"))
    print(f"\nSelected {selected}. Saved new validation experiment: {run}\nAll previous files preserved.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (original.DataError, OSError, AssertionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
