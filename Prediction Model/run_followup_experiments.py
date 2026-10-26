"""Run exploratory timing/L03 diagnostics without writing to the original run.

From the project root:
  "Prediction Model/.venv/bin/python" "Prediction Model/run_followup_experiments.py"

Each invocation creates a new UTC-stamped directory under experiments/timing_L03/.
It reads the active staged inputs/targets, original manifest and original chart
windows. It reuses train_models.py's fixed features, pipeline and settings.
No upstream tables are regenerated, no source units changed, no targets shifted.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import shlex
import subprocess
import sys

import train_models as original

sys.path.insert(0, str(original.BASE.parent / "Data_cleaning"))
import join_weather_data as weather_joiner

np, pd, plt = original.np, original.pd, original.plt
BASE = original.BASE
TRAIN_WITH_L03 = ("L03_B01", "L14_B04", "L14_B05")
TRAIN_WITHOUT_L03 = ("L14_B04", "L14_B05")
TEST = ("L07_B01", "L14_B01", "L14_B02", "L14_B03")
METHODS = ("baseline_mean", "baseline_calendar_use", "A", "B")
LABELS = {
    "baseline_mean": "Global training mean",
    "baseline_calendar_use": "Building-use/calendar baseline",
    "A": "Model A: no weather", "B": "Model B: with weather",
}
COLORS = {"baseline_mean": "#666666", "baseline_calendar_use": "#9467bd",
          "A": "#1f77b4", "B": "#ff7f0e"}
METRICS = ("mae_kwh_per_m2", "rmse_kwh_per_m2", "nrmse_pct")
EVIDENCE = [
    dict(source="ADRENALIN_data_description.pdf", pages="5", finding="Timestamps are ISO 8601 UTC; the generic moment-in-time description does not define the hourly interval labelling or availability of each selected weather quantity."),
    dict(source="ADRENALIN_data_description.pdf", pages="8", finding="Weather comes from CERRA, ERA5-Land and ERA5; coordinates and station identities are anonymised. Per-variable product mapping, interval/averaging semantics and publication latency are not specified."),
    dict(source="ADRENALIN_data_description.pdf", pages="16, 19-20", finding="Dataset harmonisation/resampling and gaps, possible unit mislabelling and different accumulation/measurement strategies are documented. There is no authoritative L03-specific divide-by-1000 instruction."),
    dict(source="Data_cleaning/build_consumption_tables.py", pages=None, finding="L03/L14 source timestamps are treated as interval ends by project convention; values are used directly. L07 uses already processed counter differences and their existing interval bounds."),
    dict(source="Data_cleaning/convert_cumulative_to_hourly.py", pages=None, finding="L07 counter differences are assigned to the preceding/current counter timestamps; invalid intervals/gaps remain exclusions."),
    dict(source="Data_cleaning/join_weather_data.py", pages=None, finding="Original weather uses exact interval_start_utc equality; no availability metadata or publication-latency check is implemented."),
    dict(source="Data_cleaning/export_prediction_targets.py", pages=None, finding="Targets are exported sequentially in their input row order and verified row by row; no target shift is performed."),
    dict(source="Data/BuildingsByLocation/L03/L03_B01/L03_B01-topology.txt", pages=None, finding="Selected L03 EM02 is electricity use; EM01 is the separate virtual aggregate described in the building-info note. These must not be conflated."),
]
TIMING_LIMITATION = (
    "Intended prediction at t is consumption over [t,t+1h). Current electricity "
    "interval conventions are retained, without shifting targets. The dataset "
    "documents historical reanalysis weather but not its per-variable interval "
    "semantics or availability at t. Current alignment is an assumed conditional "
    "comparison, not established operational information at t. Exact t-1h weather "
    "reduces contemporaneous dependence but does not establish publication latency."
)


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_json(path, value):
    # All outputs are new files inside a freshly created run directory.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(json_safe(value), handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def preserved_files(base=BASE):
    paths = [base / "train_models.py", base.parent / "progress_so_far.md"]
    for name in ("results", "charts", "models"):
        paths.extend(p for p in (base / name).rglob("*") if p.is_file())
    return {str(p.resolve()): original.fingerprint(p) for p in paths if p.is_file()}


def verify_hashes(hashes):
    for name, checksum in hashes.items():
        path = Path(name)
        if not path.is_file() or original.fingerprint(path) != checksum:
            raise original.DataError(f"Required/preserved file differs from recorded hash: {path}")


def new_run_directory(output_root):
    root = Path(output_root).expanduser().resolve()
    protected = [BASE / name for name in ("results", "charts", "models", "Input Data", "Target Set")]
    protected.append(BASE.parent / "Data")
    if any(root == p.resolve() or p.resolve() in root.parents for p in protected):
        raise original.DataError("Follow-up output root cannot be inside original outputs or source-data directories")
    run = root / datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%S_%fZ")
    run.mkdir(parents=True, exist_ok=False)
    return run


def calendar_keys(features, tracking):
    times = pd.to_datetime(tracking["interval_start_utc"], utc=True)
    return pd.DataFrame({
        "building_use": features["building_use"].fillna("__MISSING__").to_numpy(),
        "weekday": times.dt.dayofweek.to_numpy(), "hour": times.dt.hour.to_numpy(),
    })


class CalendarUseBaseline:
    """Training-row-weighted lookup means with an explicit four-level fallback."""

    levels = (("building_use", "weekday", "hour"), ("building_use", "hour"), ("weekday", "hour"))

    def fit(self, keys, targets):
        frame = keys.reset_index(drop=True).copy()
        if len(frame) != len(targets) or not len(frame):
            raise original.DataError("Calendar baseline needs aligned nonempty training rows")
        frame["target"] = np.asarray(targets, dtype=float)
        if not np.isfinite(frame.target).all():
            raise original.DataError("Calendar baseline requires finite training targets")
        self.global_mean = float(frame.target.mean())
        self.training_rows = len(frame)
        self.tables, self.group_records = [], []
        for columns in self.levels:
            grouped = frame.groupby(list(columns), sort=True)["target"].agg(["mean", "count"]).reset_index()
            table = {tuple(row[c] for c in columns): float(row["mean"]) for _, row in grouped.iterrows()}
            self.tables.append(table)
            self.group_records.append(dict(keys=list(columns), groups=grouped.to_dict("records")))
        return self

    def predict(self, keys):
        predictions, fallbacks = [], []
        for row in keys.to_dict("records"):
            for columns, table in zip(self.levels, self.tables):
                value = table.get(tuple(row[c] for c in columns))
                if value is not None:
                    predictions.append(value)
                    fallbacks.append("x".join(columns))
                    break
            else:
                predictions.append(self.global_mean)
                fallbacks.append("global_training_mean")
        return np.asarray(predictions), np.asarray(fallbacks)

    def state(self):
        return dict(training_rows=self.training_rows, global_mean=self.global_mean,
                    calendar_timezone="UTC", weighting="equal per training row within each group",
                    fallback_order=[list(c) for c in self.levels] + [["global_training_mean"]],
                    lookup_tables=self.group_records)

    @classmethod
    def from_state(cls, state):
        result = cls()
        result.global_mean = float(state["global_mean"])
        result.training_rows = int(state["training_rows"])
        result.group_records = state["lookup_tables"]
        result.tables = [{tuple(row[c] for c in level["keys"]): float(row["mean"])
                          for row in level["groups"]} for level in result.group_records]
        if [tuple(level["keys"]) for level in result.group_records] != list(cls.levels):
            raise original.DataError("Saved calendar baseline has an unexpected fallback definition")
        return result


def exact_weather_at(starts, location, weather, lag_hours):
    """Timestamp reindex of the location's full weather series; never row shift."""
    requested = pd.DatetimeIndex(starts) - pd.Timedelta(hours=lag_hours)
    values, matched = {}, np.zeros(len(requested), dtype=int)
    for column in original.WEATHER:
        series = weather[location][column]
        if not series.index.is_unique:
            raise original.DataError(f"Duplicate weather timestamps: {location}/{column}")
        matched += requested.isin(series.index).astype(int)
        values[column] = series.reindex(requested).to_numpy()
    return pd.DataFrame(values), requested, matched


def load_weather(data, root):
    weather, hashes, descriptions = {}, {}, []
    for location in sorted({b.split("_")[0] for b in data}):
        weather[location] = {}
        for quantity, column in weather_joiner.WEATHER_COLUMNS.items():
            path = root / location / f"{location}_WS" / f"adrenalin.1h.{location}.WS01.{quantity}.csv"
            hashes[str(path.resolve())] = original.fingerprint(path)
            source = weather_joiner.read_weather(path, quantity)
            raw = pd.Series(source.values, dtype=object)
            raw.index = pd.to_datetime(raw.index, utc=True)
            numeric = original.numeric(raw.fillna(""), str(path))
            weather[location][column] = numeric
            descriptions.append(dict(location=location, column=column, file=str(path.resolve()),
                                     headers=source.headers, unit=source.stated_unit,
                                     rows=len(numeric), sha256=hashes[str(path.resolve())]))
    return weather, hashes, descriptions


def weather_variants(data, weather):
    variants, audits = {}, []
    for label, lag in (("current_weather", 0), ("lagged_weather_1h", 1)):
        variant = {}
        for building, item in data.items():
            location = building.split("_")[0]
            mapped, requested, matched = exact_weather_at(item.tracking.interval_start_utc, location, weather, lag)
            features = item.features.copy()
            if lag == 0:
                if not np.allclose(features[original.WEATHER], mapped, equal_nan=True, rtol=1e-12, atol=1e-12):
                    raise original.DataError(f"{building}: staged weather does not match original exact-t location weather; nothing was replaced")
                # Keep the active staged current-weather values exactly as they are.
            else:
                features.loc[:, original.WEATHER] = mapped.to_numpy()
            tracking = item.tracking.copy()
            tracking["weather_requested_utc"] = requested
            tracking["weather_timestamp_matches"] = matched
            tracking["weather_finite_fields"] = np.isfinite(mapped).sum(axis=1).to_numpy()
            variant[building] = original.BuildingData(building, features, item.target.copy(), tracking, item.audit)
            for column in original.WEATHER:
                series = weather[location][column]
                audits.append(dict(weather_timing=label, building_id=building, location_id=location,
                                   column=column, requested_rows=len(requested), lag_hours=lag,
                                   exact_timestamp_matches=int(requested.isin(series.index).sum()),
                                   missing_values=int(mapped[column].isna().sum())))
        variants[label] = variant
    return variants, pd.DataFrame(audits)


def target_distributions(data):
    rows = []
    for building, item in sorted(data.items()):
        target = item.target.dropna()
        row = dict(building_id=building, count=len(target), mean=target.mean(), median=target.median(),
                   minimum=target.min(), maximum=target.max(), unit="kWh/m² per hourly interval",
                   original_role="train" if building in TRAIN_WITH_L03 else "test",
                   diagnostic_role="train" if building in TRAIN_WITHOUT_L03 else "excluded" if building == "L03_B01" else "test")
        for percentile in (1, 5, 25, 75, 95, 99):
            row[f"p{percentile:02d}"] = target.quantile(percentile / 100)
        rows.append(row)
    return pd.DataFrame(rows)


def normalised_rmse(rmse, observed_mean):
    if not np.isfinite(observed_mean):
        return np.nan, "observed target mean is invalid"
    if observed_mean <= 0:
        return np.nan, "observed target mean is non-positive"
    return 100 * rmse / observed_mean, ""


def metric_values(actual, predicted):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if actual.shape != predicted.shape or not len(actual) or not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise original.DataError("Metric inputs must be nonempty, aligned and finite")
    error = predicted - actual
    mean = float(actual.mean())
    rmse = float(np.sqrt(np.mean(np.square(error))))
    nrmse, reason = normalised_rmse(rmse, mean)
    return dict(mae_kwh_per_m2=float(np.mean(np.abs(error))), rmse_kwh_per_m2=rmse,
                nrmse_pct=nrmse,
                nrmse_undefined_reason=reason, mean_observed_target_kwh_per_m2=mean)


def evaluate(predictions):
    rows = []
    for scope, column in (("building", "building_id"), ("location", "location_id")):
        for name, group in predictions.groupby(column, sort=True):
            for method in METHODS:
                rows.append(dict(scope=scope, name=name, model=method, n_rows=len(group),
                                 aggregation="pooled_location_rows" if scope == "location" else "building_rows",
                                 **metric_values(group.actual_kwh_per_m2, group[f"predicted_{method}_kwh_per_m2"])))
    for method in METHODS:
        locations = [r for r in rows if r["scope"] == "location" and r["model"] == method]
        if {r["name"] for r in locations} != {"L07", "L14"}:
            raise original.DataError("Expected L07 and L14 test locations")
        row = dict(scope="equal_weight_locations", name="L07_and_L14", model=method,
                   n_rows=len(predictions), aggregation="equal_weight_mean_of_location_metrics",
                   mean_observed_target_kwh_per_m2=np.nan)
        for metric in METRICS:
            values = np.asarray([r[metric] for r in locations])
            row[metric] = float(values.mean()) if np.isfinite(values).all() else np.nan
        row["nrmse_undefined_reason"] = "; ".join(f'{r["name"]}: {r["nrmse_undefined_reason"]}' for r in locations if r["nrmse_undefined_reason"])
        rows.append(row)
    return pd.DataFrame(rows)


def compare_metrics(metrics, reference, candidates):
    rows = []
    for (scope, name), group in metrics.groupby(["scope", "name"], sort=False):
        ref = group[group.model == reference].iloc[0]
        for candidate in candidates:
            value = group[group.model == candidate].iloc[0]
            row = dict(scope=scope, name=name, reference_model=reference, model=candidate, n_rows=int(value.n_rows))
            for metric in METRICS:
                a, b = float(ref[metric]), float(value[metric])
                valid = np.isfinite(a) and np.isfinite(b) and a > 0
                row[f"reference_{metric}"] = a
                row[f"model_{metric}"] = b
                row[f"{metric}_reduction_pct"] = 100 * (a - b) / a if valid else np.nan
                row[f"{metric}_undefined_reason"] = "" if valid else "reference error is zero/non-positive or a metric is undefined"
            rows.append(row)
    return pd.DataFrame(rows)


def preprocessing_audit(pipeline, label, train_x, train_ids):
    """Independently check each fitted statistic against allowed training rows."""
    numeric_names = [c for c in original.FEATURES[label] if c not in original.CATEGORICAL]
    preprocessing = pipeline.named_steps["preprocessing"]
    imputer = preprocessing.named_transformers_["numeric"]
    expected = train_x[numeric_names].median().fillna(0).to_numpy()
    np.testing.assert_allclose(imputer.statistics_, expected)
    encoder = preprocessing.named_transformers_["categorical"].named_steps["one_hot"]
    vocabularies = {}
    for name, categories in zip(original.CATEGORICAL, encoder.categories_):
        if set(categories) != set(train_x[name].fillna("__MISSING__")):
            raise original.DataError(f"Non-training category vocabulary in Model {label}")
        vocabularies[name] = categories.tolist()
    return dict(fit_buildings=list(train_ids), fit_rows=len(train_x), numeric_features=numeric_names,
                fitted_medians=dict(zip(numeric_names, imputer.statistics_.tolist())),
                categorical_vocabularies=vocabularies,
                encoded_features=preprocessing.get_feature_names_out().tolist(),
                numerical_statistics_match_training_only=True, categorical_vocabulary_matches_training_only=True)


def check_shared_rows(tracking, target, original_predictions):
    if len(tracking) != len(original_predictions):
        raise original.DataError("Follow-up evaluation rows differ from the preserved original")
    for name in ("building_id", "location_id", "source_data_row"):
        if tracking[name].tolist() != original_predictions[name].tolist():
            raise original.DataError(f"Original evaluation alignment differs: {name}")
    for name in ("interval_start_utc", "interval_end_utc"):
        if not pd.to_datetime(original_predictions[name], utc=True).equals(tracking[name]):
            raise original.DataError(f"Original evaluation timestamps differ: {name}")
    np.testing.assert_allclose(target, original_predictions.actual_kwh_per_m2, rtol=1e-13, atol=1e-15)


def saved_week(frame, window):
    start, end = pd.Timestamp(window.start_utc), pd.Timestamp(window.end_utc_exclusive)
    week = frame[(frame.interval_start_utc >= start) & (frame.interval_start_utc < end)]
    week = week.sort_values("interval_start_utc", kind="stable")
    expected = pd.date_range(start, end, freq="h", inclusive="left")
    if len(week) != int(window.rows) or not pd.DatetimeIndex(week.interval_start_utc).equals(expected):
        raise original.DataError(f"Original saved chart window is not fully covered for {window.building_id}")
    return week


def make_charts(predictions, metrics, windows, destination, experiment):
    for metric, label, unit in ((METRICS[0], "MAE", "kWh/m²"), (METRICS[1], "RMSE", "kWh/m²"),
                                (METRICS[2], "Mean-normalised RMSE", "% of location observed mean")):
        locations = metrics[metrics.scope == "location"]
        fig, ax = plt.subplots(figsize=(10, 5.5))
        for offset, method in zip((-0.3, -0.1, 0.1, 0.3), METHODS):
            values = [locations[(locations.name == location) & (locations.model == method)][metric].iloc[0]
                      for location in ("L07", "L14")]
            bars = ax.bar(np.arange(2) + offset, values, width=0.2, color=COLORS[method], label=LABELS[method])
            ax.bar_label(bars, labels=[f"{v:.4g}" if np.isfinite(v) else "undefined" for v in values], padding=3, fontsize=8)
        ax.set_xticks([0, 1], ["L07: unseen location", "L14: unseen buildings; seen location"])
        ax.set_ylabel(f"{label} ({unit})")
        ax.set_title(f"Exploratory {experiment}\n{label} by test location; lower is better")
        ax.legend(fontsize=8, ncol=2, loc="upper center")
        ax.margins(y=0.25)
        ax.grid(axis="y", alpha=0.2)
        fig.tight_layout()
        fig.savefig(destination / f"{metric}_by_test_location.png", dpi=160)
        plt.close(fig)
    for window in windows.itertuples(index=False):
        week = saved_week(predictions[predictions.building_id == window.building_id], window)
        fig, ax = plt.subplots(figsize=(14, 5.5))
        ax.plot(week.interval_start_utc, week.actual_kwh_per_m2, color="black", linewidth=1.5, label="Actual")
        for method in METHODS:
            ax.plot(week.interval_start_utc, week[f"predicted_{method}_kwh_per_m2"], color=COLORS[method],
                    linestyle="--" if method.startswith("baseline") else "-", linewidth=1, alpha=0.85, label=LABELS[method])
        ax.set_title(f"Exploratory {experiment}: {window.building_id}\nOriginal fixed window: {window.start_utc} to {window.end_utc_exclusive} (end exclusive)")
        ax.set_xlabel("Prediction interval start (UTC)")
        ax.set_ylabel("Hourly electricity per gross floor area (kWh/m²)")
        ax.xaxis.set_major_formatter(original.mdates.DateFormatter("%d %b\n%H:%M", tz=timezone.utc))
        ax.set_xlim(pd.Timestamp(window.start_utc), pd.Timestamp(window.end_utc_exclusive))
        ax.legend(fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.19))
        ax.grid(alpha=0.2)
        fig.tight_layout()
        fig.savefig(destination / f"{window.building_id}_original_seven_day_window.png", dpi=160)
        plt.close(fig)


def verify_saved_metrics(directory):
    predictions = pd.read_csv(directory / "results/test_predictions.csv")
    calculated = evaluate(predictions)
    saved = pd.read_csv(directory / "results/metrics.csv", keep_default_na=False)
    key = ["scope", "name", "model"]
    calculated = calculated.set_index(key).sort_index()
    saved = saved.set_index(key).sort_index()
    if not calculated.index.equals(saved.index):
        raise original.DataError("Saved metric method/group set differs from saved predictions")
    for column in METRICS + ("mean_observed_target_kwh_per_m2",):
        actual = pd.to_numeric(saved[column], errors="coerce").to_numpy()
        np.testing.assert_allclose(actual, calculated[column], rtol=1e-10, atol=1e-12, equal_nan=True)
    if saved.nrmse_undefined_reason.tolist() != calculated.nrmse_undefined_reason.tolist():
        raise original.DataError("Saved nRMSE undefined reasons disagree with predictions")
    for name, reference, candidates in (("weather_error_reductions.csv", "A", ("B",)),
                                         ("baseline_comparisons.csv", None, ("A", "B"))):
        expected = (pd.concat([compare_metrics(calculated.reset_index(), baseline, candidates)
                               for baseline in METHODS[:2]], ignore_index=True)
                    if reference is None else compare_metrics(calculated.reset_index(), reference, candidates))
        stored = pd.read_csv(directory / "results" / name, keep_default_na=False)
        comparison_key = ["scope", "name", "reference_model", "model"]
        expected = expected.set_index(comparison_key).sort_index()
        stored = stored.set_index(comparison_key).sort_index()
        if not expected.index.equals(stored.index):
            raise original.DataError("Saved comparison rows differ from saved metrics")
        for column in expected.select_dtypes(include="number").columns:
            np.testing.assert_allclose(pd.to_numeric(stored[column], errors="coerce"), expected[column],
                                       rtol=1e-9, atol=1e-10, equal_nan=True)
    return dict(saved_metrics_match_predictions=True, saved_comparisons_match_metrics=True,
                metric_rows=len(saved), prediction_rows=len(predictions))


def run_experiment(data, train_ids, name, timing, directory, windows, prior_predictions, threads, source_hashes):
    if set(train_ids) & set(TEST):
        raise original.DataError("Held-out building entered the fitting set")
    for folder in ("results", "models", "charts"):
        (directory / folder).mkdir(parents=True, exist_ok=False)
    train_x, train_y, train_tracking = original.combine(data, train_ids)
    test_x, test_y, tracking = original.combine(data, TEST)
    if set(train_tracking.building_id) != set(train_ids) or set(tracking.building_id) != set(TEST):
        raise original.DataError("Unexpected training or test membership")
    check_shared_rows(tracking, test_y, prior_predictions)
    predictions = tracking.copy()
    predictions["actual_kwh_per_m2"] = test_y
    global_baseline = original.DummyRegressor(strategy="mean").fit(np.zeros((len(train_y), 1)), train_y)
    predictions[f"predicted_{METHODS[0]}_kwh_per_m2"] = global_baseline.predict(np.zeros((len(test_y), 1)))
    train_keys, test_keys = calendar_keys(train_x, train_tracking), calendar_keys(test_x, tracking)
    calendar_baseline = CalendarUseBaseline().fit(train_keys, train_y)
    calendar_predicted, fallback = calendar_baseline.predict(test_keys)
    predictions[f"predicted_{METHODS[1]}_kwh_per_m2"] = calendar_predicted
    predictions["calendar_baseline_fallback"] = fallback
    np.testing.assert_allclose(calendar_baseline.global_mean, global_baseline.constant_.item())
    # Group means are independently reconstructed from training targets only.
    for columns, table in zip(calendar_baseline.levels, calendar_baseline.tables):
        independent = train_keys.copy()
        independent["target"] = train_y.to_numpy()
        means = independent.groupby(list(columns)).target.mean()
        for key, mean in means.items():
            if not np.isclose(table[key], mean):
                raise original.DataError("Calendar baseline group mean differs from training-only mean")
    models, fitted = {}, {}
    print(f"[{name}] {len(train_y):,} training / {len(test_y):,} shared test rows", flush=True)
    with original.threadpool_limits(limits=threads):
        for label in ("A", "B"):
            model = original.make_pipeline(label)
            model.fit(train_x[original.FEATURES[label]], train_y)
            predictions[f"predicted_{label}_kwh_per_m2"] = model.predict(test_x[original.FEATURES[label]])
            fitted[label] = preprocessing_audit(model, label, train_x, train_ids)
            if model.named_steps["regressor"].get_params() != original.HistGradientBoostingRegressor(**original.SETTINGS).get_params():
                raise original.DataError("Model settings changed")
            models[label] = model
    for method in METHODS:
        if not np.isfinite(predictions[f"predicted_{method}_kwh_per_m2"]).all():
            raise original.DataError(f"Nonfinite predictions from {method}")
    reproduction = {}
    if tuple(train_ids) == TRAIN_WITH_L03 and timing == "current_weather":
        for method in ("baseline_mean", "A", "B"):
            column = f"predicted_{method}_kwh_per_m2"
            np.testing.assert_allclose(predictions[column], prior_predictions[column], rtol=1e-11, atol=1e-12)
            reproduction[method] = float(np.abs(predictions[column] - prior_predictions[column]).max())
    metrics = evaluate(predictions)
    weather_changes = compare_metrics(metrics, "A", ("B",))
    baseline_changes = pd.concat([compare_metrics(metrics, b, ("A", "B")) for b in METHODS[:2]], ignore_index=True)
    results, model_dir = directory / "results", directory / "models"
    predictions.to_csv(results / "test_predictions.csv", index=False)
    metrics.to_csv(results / "metrics.csv", index=False)
    weather_changes.to_csv(results / "weather_error_reductions.csv", index=False)
    baseline_changes.to_csv(results / "baseline_comparisons.csv", index=False)
    windows.to_csv(results / "chart_periods.csv", index=False)
    membership = pd.DataFrame([dict(building_id=b, role="train" if b in train_ids else "test" if b in TEST else "excluded",
                                    rows=data[b].audit["input_rows"]) for b in sorted(data)])
    membership.to_csv(results / "split_membership.csv", index=False)
    pd.DataFrame([dict(model=label, representation=kind, feature=feature) for label in ("A", "B")
                  for kind, names in (("input", original.FEATURES[label]), ("encoded", fitted[label]["encoded_features"]))
                  for feature in names]).to_csv(results / "predictors.csv", index=False)
    for label, pipeline in models.items():
        path = model_dir / f"model_{label}_pipeline.joblib"
        original.joblib.dump(pipeline, path)
        with original.threadpool_limits(limits=threads):
            reloaded = original.joblib.load(path).predict(test_x[original.FEATURES[label]])
        np.testing.assert_allclose(reloaded, predictions[f"predicted_{label}_kwh_per_m2"], rtol=1e-12, atol=1e-13)
    original.joblib.dump(global_baseline, model_dir / "baseline_mean.joblib")
    write_json(model_dir / "calendar_use_baseline.json", dict(calendar_baseline.state(), fit_buildings=list(train_ids)))
    saved_calendar = CalendarUseBaseline.from_state(json.loads((model_dir / "calendar_use_baseline.json").read_text()))
    restored_predictions, restored_fallbacks = saved_calendar.predict(test_keys)
    np.testing.assert_allclose(restored_predictions, calendar_predicted)
    if not np.array_equal(restored_fallbacks, fallback):
        raise original.DataError("Reloaded calendar baseline chose different fallbacks")
    np.testing.assert_allclose(original.joblib.load(model_dir / "baseline_mean.joblib").predict(
        np.zeros((len(test_y), 1))), predictions[f"predicted_{METHODS[0]}_kwh_per_m2"])
    write_json(model_dir / "fitted_preprocessing_audit.json", fitted)
    make_charts(predictions, metrics, windows, directory / "charts", name)
    verified = verify_saved_metrics(directory)
    verify_hashes(source_hashes)
    information = dict(experiment=name, status="exploratory_followup_after_original_test_inspection",
                       train_buildings=list(train_ids), test_buildings=list(TEST), training_rows=len(train_y), test_rows=len(test_y),
                       weather_timing=timing, weather_lag_hours=1 if timing == "lagged_weather_1h" else 0,
                       target_shift_hours=0, calendar_timezone="UTC", settings=original.SETTINGS,
                       predictors=original.FEATURES, fitted_preprocessing=fitted,
                       global_baseline_value=global_baseline.constant_.item(),
                       calendar_baseline_fallback_order=calendar_baseline.state()["fallback_order"],
                       test_fallback_usage=dict(Counter(fallback)), source_hashes=source_hashes,
                       timing_assumption=TIMING_LIMITATION,
                       nrmse_definition="100 * RMSE / pooled mean observed target within each building/location; undefined if mean <= 0 or invalid",
                       equal_weight_average="Arithmetic mean of L07 and L14 metrics separately, including nRMSE; not pooled RMSE/nRMSE",
                       original_prediction_max_absolute_difference=reproduction,
                       verification=dict(**verified, training_only_preprocessing_verified=True,
                                         training_only_baseline_means_verified=True,
                                         all_methods_use_original_evaluation_rows=True, reloaded_model_predictions_verified=True))
    write_json(results / "run_manifest.json", information)
    (results / "run_summary.txt").write_text(
        f"EXPLORATORY: {name}\n{TIMING_LIMITATION}\nTraining: {list(train_ids)}\nTest: {list(TEST)}\n"
        "Equal-weight metrics are averages of location metrics, not pooled metrics.\n\n"
        + metrics.to_string(index=False) + "\n\nWeather reductions (positive improves):\n"
        + weather_changes.to_string(index=False) + "\n\nBaseline comparisons (positive improves):\n"
        + baseline_changes.to_string(index=False) + "\n", encoding="utf-8")
    metrics = metrics.assign(experiment=name, training_configuration="with_L03" if "L03_B01" in train_ids else "without_L03", weather_timing=timing)
    print(metrics[metrics.scope == "equal_weight_locations"][["model", *METRICS]].to_string(index=False), flush=True)
    return metrics


def factor_comparison(all_metrics, factor):
    if factor == "L03":
        key, reference, candidate = "training_configuration", "with_L03", "without_L03"
        shared = ["weather_timing", "scope", "name", "model"]
    else:
        key, reference, candidate = "weather_timing", "current_weather", "lagged_weather_1h"
        shared = ["training_configuration", "scope", "name", "model"]
    left = all_metrics[all_metrics[key] == reference]
    right = all_metrics[all_metrics[key] == candidate]
    joined = left.merge(right, on=shared, suffixes=("_reference", "_candidate"), validate="one_to_one")
    rows = []
    for record in joined.to_dict("records"):
        row = {k: record[k] for k in shared}
        row.update(reference=reference, candidate=candidate)
        for metric in METRICS:
            a, b = record[f"{metric}_reference"], record[f"{metric}_candidate"]
            row[f"{metric}_{reference}"] = a
            row[f"{metric}_{candidate}"] = b
            row[f"{metric}_change_candidate_minus_reference"] = b - a
            row[f"{metric}_reduction_pct"] = 100 * (a - b) / a if np.isfinite(a) and np.isfinite(b) and a > 0 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def make_influence_chart(comparison, destination):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True)
    buildings = list(TEST)
    for row_index, timing in enumerate(("current_weather", "lagged_weather_1h")):
        for column_index, model in enumerate(("A", "B")):
            ax = axes[row_index, column_index]
            selected = comparison[(comparison.weather_timing == timing) & (comparison.model == model)].set_index("name")
            for offset, label, color in ((-0.19, "with_L03", "#8c564b"), (0.19, "without_L03", "#2ca02c")):
                values = [selected.loc[b, f"rmse_kwh_per_m2_{label}"] for b in buildings]
                ax.bar(np.arange(len(buildings)) + offset, values, width=0.38, label=label.replace("_", " "), color=color)
            ax.set_title(f"Model {model}: {timing.replace('_', ' ')}")
            ax.set_xticks(np.arange(len(buildings)), buildings, rotation=20)
            ax.set_ylabel("RMSE (kWh/m²)")
            ax.legend(fontsize=8)
            ax.grid(axis="y", alpha=0.2)
    fig.suptitle("Exploratory L03-exclusion diagnostic: same held-out rows, fixed model settings")
    fig.tight_layout()
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def markdown_table(frame):
    def cell(value):
        if isinstance(value, (float, np.floating)):
            return f"{value:.6g}" if np.isfinite(value) else "undefined"
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(map(str, frame.columns)) + " |",
             "| " + " | ".join("---" for _ in frame.columns) + " |"]
    lines.extend("| " + " | ".join(cell(v) for v in row) + " |" for row in frame.itertuples(index=False, name=None))
    return "\n".join(lines)


def methodology_report(batch, metrics, distributions, command):
    macro = metrics[metrics.scope == "equal_weight_locations"]
    sections = [
        "# Exploratory timing and L03 follow-up: methodology and findings\n",
        "The original experiment, original train_models.py, progress report, datasets, models, metrics, predictions and charts are preserved. These follow-ups are exploratory because the original test outcomes have already been inspected. They are not an untouched final-test estimate.\n",
        "## Prediction timing and documentation evidence\n",
        "At time t, the intended target is electricity over [t,t+1 hour), divided by gross floor area. For L03/L14 the existing source-end-timestamp convention is retained; for L07 the counter difference already has its two interval bounds. Targets are neither moved nor re-differenced. Metadata enrichment and target export preserve the interval rows.\n",
        "The dataset PDF says timestamps are UTC moments (p. 5), identifies CERRA/ERA5-Land/ERA5 reanalysis weather and anonymisation (p. 8), and describes harmonisation/resampling and measurement limitations (pp. 16, 19–20). It does not define the selected weather variables' instantaneous/averaged/accumulated interval semantics, per-file product mapping or publication latency. Weather at t therefore cannot be confirmed to have been available for a prediction made at t. It could contain contemporaneous or retrospective information; the available evidence does not resolve which selected variables do. We retain the original alignment only as an explicitly assumed reference.\n",
        "The one-hour sensitivity uses a timestamp lookup of location weather at exactly t−1 hour, not a row shift. It uses the full original location weather series, including weather records at times when electricity rows are absent; missing timestamp matches remain missing. Lagging reduces reliance on contemporaneous weather but does not establish provider publication latency. All active staged current-weather values were checked against the original exact-t weather sources, without replacing staged data.\n",
        "Evidence references and source hashes are in documentation_evidence.json and batch_manifest.json. No authoritative instruction was found to divide L03 by 1,000, so its stated kWh and derived kWh/m² units remain unchanged. L03 uses electricity submeter EM02, not the separate virtual aggregate EM01. Distribution differences and diagnostic improvements cannot prove a unit error.\n",
        "## Fixed design and fitting\n",
        "The 2×2 design crosses training on L03_B01/L14_B04/L14_B05 (80,665 rows) versus L14_B04/L14_B05 only (71,929 rows), with current versus exact one-hour-lagged weather. Each case uses the same 118,887 test rows from L07_B01 and L14_B01/B02/B03. These are fixed holdouts, not leave-one-site-out cross-validation: L07 is an unseen location, while L14 holdouts are unseen buildings at a partly seen location. Leave-one-site-out would exclude every building at a site and repeat that procedure across site folds; that procedure is not performed here. L03 is a training building or diagnostic exclusion. Training on only two or three buildings limits transfer despite the hourly row count.\n",
        "Both HistGradientBoostingRegressor models retain the original settings (200 iterations, learning rate 0.08, 31 leaves, minimum leaf size 30, L2=1, max_bins=255, seed 42, early stopping disabled). Model A retains its 22 metadata/calendar predictors; B retains the same plus six weather measurements. No feature selection, tuning, new ML algorithm or source-data cleaning was introduced. UTC calendar construction is unchanged. Electricity, the target, other target-derived columns and building/location IDs are excluded from predictors.\n",
        "Imputers, encoders and both baselines are refitted using only the relevant training rows. Fitted numerical medians and category vocabularies are independently checked against training data. Unknown held-out categories are handled by the original one-hot encoder. Weather missingness does not change evaluation eligibility.\n",
        "## Baselines and metrics\n",
        "The global baseline predicts the row-weighted mean training target. The new calendar/building-use baseline first uses the training mean for building_use × weekday × hour, falling back in order to building_use × hour, weekday × hour across training buildings, and the global training mean. All grouping uses UTC, the same convention as the models. Each lookup has saved means and group counts; fallback usage is recorded. Held-out targets are used only for descriptive distributions and evaluation metrics, never to fit or adjust predictions.\n",
        "MAE and RMSE are in kWh/m². Mean-normalised RMSE is nRMSE (%) = 100 × RMSE / mean(observed target), computed separately for each test building and pooled location. A non-positive or invalid observed mean yields an undefined value and reason. The equal-weight summary averages L07 and L14 metrics separately, including their nRMSE percentages. It is neither a pooled RMSE nor a pooled nRMSE, and has no pooled normalisation denominator. Percentage error reduction is 100 × (reference error − candidate error) / reference error, undefined for zero/invalid references.\n",
        "## Original findings and exploratory follow-up findings\n",
        "The preserved original equal-weight location result was MAE/RMSE 0.293805/0.294841 for the global mean baseline, 0.598728/1.054113 for A and 0.605341/1.083748 for B. Both models failed badly on L14_B03 and neither beat that reference overall. Adding weather worsened overall MAE by 1.10% and RMSE by 2.81%. The with-L03/current-weather case is verified to reproduce original A/B/global-baseline predictions, while adding the new baseline and nRMSE.\n",
        "Equal-weight means of location metrics for all follow-up cases:\n",
        markdown_table(macro[["training_configuration", "weather_timing", "model", *METRICS]]),
        "\nWeather contribution (Model B versus A), reported separately by training configuration and timing:\n",
    ]
    weather_rows = []
    for (configuration, timing), group in metrics.groupby(["training_configuration", "weather_timing"], sort=False):
        comparison = compare_metrics(group.drop(columns=["experiment", "training_configuration", "weather_timing"]), "A", ("B",))
        for row in comparison.to_dict("records"):
            weather_rows.append(dict(training_configuration=configuration, weather_timing=timing, **row))
    weather = pd.DataFrame(weather_rows)
    weather.to_csv(batch / "weather_effect_all_experiments.csv", index=False)
    sections.append(markdown_table(weather[weather.scope == "equal_weight_locations"][["training_configuration", "weather_timing", *[f"{m}_reduction_pct" for m in METRICS]]]))
    sections.append("\nPositive percentages improve on A; negative percentages worsen it. Building/location details and comparisons against both baselines are saved separately in every experiment.\n")
    for row in weather[weather.scope == "equal_weight_locations"].to_dict("records"):
        mae, rmse = row[f"{METRICS[0]}_reduction_pct"], row[f"{METRICS[1]}_reduction_pct"]
        sections.append(f"- **{row['training_configuration']}, {row['weather_timing']}:** B {'reduces' if mae >= 0 else 'increases'} average location MAE by {abs(mae):.2f}% and {'reduces' if rmse >= 0 else 'increases'} average location RMSE by {abs(rmse):.2f}%.\n")
    sections.extend([
        "\nRemoving L03 is compared at each fixed weather timing in l03_influence_by_building.csv and l03_influence_rmse.png; changing weather timing at each fixed training configuration is in weather_timing_comparison.csv. Those factors are not bundled into a single before/after claim. Target distributions follow. All units are retained.\n",
        markdown_table(distributions[["building_id", "count", "mean", "median", "p01", "p05", "p25", "p75", "p95", "p99", "maximum"]]),
        "\n## Interpretation, limitations and reproducibility\n",
        "These results test conditional predictive transfer. Any apparent improvement is exploratory, does not prove L03 has incorrect units, does not establish a causal weather effect, and does not establish production-ready forecasting. Weather timing/publication evidence and the L03-specific unit question remain unresolved. The original test set has been inspected; later model selection needs training-only validation and a genuinely separate final evaluation.\n",
        "The four experiments share original saved seven-day chart windows; none was selected for prediction quality. All methods share original test IDs, timestamps and row order. Saved predictions are reread to verify metrics, both-baseline comparisons and weather reductions. Saved A/B pipelines are reloaded to verify predictions; original outputs and all read sources are hashed before/after.\n",
        "The runner creates a fresh UTC-stamped run folder every invocation and refuses output roots inside original outputs or source datasets. It does not call original.run(), regenerate upstream tables, copy replacement staged data or write into original results/charts/models.\n",
        "Reproduce with the recorded command (a new output directory is created):\n\n```bash\n" + command + "\n```\n",
        "Exact Python/library versions are in dependency_versions.json, requirements_versions.txt and environment_freeze.txt. Original code/settings, source hashes and preservation checks are in batch_manifest.json.\n",
    ])
    (batch / "methodology_and_findings.md").write_text("\n".join(sections), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-root", type=Path, default=BASE / "experiments/timing_L03")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    if args.threads < 1:
        parser.error("--threads must be positive")
    preserved = preserved_files()
    old = json.loads((BASE / "results/run_manifest.json").read_text())
    if original.SETTINGS != old["model_settings"] or original.FEATURES != old["input_predictors"]:
        raise original.DataError("Original settings/features changed; fixed follow-up comparison cannot be established")
    if original.fingerprint(BASE / "train_models.py") != old["training_script_sha256"]:
        raise original.DataError("Original training code differs from its saved manifest")
    hashes = {}
    for audit in old["building_audits"]:
        hashes.update(audit["source_sha256"])
    verify_hashes(hashes)
    pairs = original.discover_pairs(BASE)
    if set(pairs) != set(TRAIN_WITH_L03) | set(TEST):
        raise original.DataError("Expected exactly the seven original staged buildings")
    generator = BASE.parent / "Data_cleaning/export_prediction_targets.py"
    data = {b: original.load_building(b, *paths, generator) for b, paths in pairs.items()}
    weather, weather_hashes, weather_sources = load_weather(data, BASE.parent / "Data/BuildingsByLocation")
    hashes.update(weather_hashes)
    documents = [BASE.parent / "ADRENALIN_data_description.pdf", BASE / "train_models.py", Path(__file__).resolve()]
    documents.extend((BASE.parent / "Data_cleaning").glob("*.py"))
    documents.extend((BASE.parent / "Data_cleaning").glob("*.json"))
    documents.extend((BASE.parent / "Data/BuildingsByLocation").glob("L*/*/*-building_info.txt"))
    documents.extend((BASE.parent / "Data/BuildingsByLocation").glob("L*/*/*-topology.txt"))
    documents.extend((BASE.parent / "Data/BuildingsByLocation").glob("L*/*/1h/*.csv"))
    for path in documents:
        hashes[str(path.resolve())] = original.fingerprint(path)
    variants, weather_audit = weather_variants(data, weather)
    windows = pd.read_csv(BASE / "results/chart_periods.csv")
    if set(windows.building_id) != set(TEST) or windows.building_id.duplicated().any():
        raise original.DataError("Original chart windows must cover each held-out building exactly once")
    prior_predictions = pd.read_csv(BASE / "results/test_predictions.csv")
    verify_hashes(preserved)
    verify_hashes(hashes)
    batch = new_run_directory(args.output_root)
    command = shlex.join([sys.executable, "-B", str(Path(__file__).resolve()), "--output-root", str(args.output_root.resolve()), "--threads", str(args.threads)])
    (batch / "command.txt").write_text(command + "\n", encoding="utf-8")
    versions = {package: importlib.metadata.version(package) for package in
                ("numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "joblib", "threadpoolctl")}
    versions["python"] = platform.python_version()
    write_json(batch / "dependency_versions.json", versions)
    (batch / "requirements_versions.txt").write_text("\n".join(f"{k}=={v}" for k, v in versions.items() if k != "python") + "\n", encoding="utf-8")
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, check=True)
    (batch / "environment_freeze.txt").write_text(freeze.stdout, encoding="utf-8")
    write_json(batch / "documentation_evidence.json", dict(evidence=EVIDENCE, timing_limitation=TIMING_LIMITATION,
                                                          review_method="Local PDF read with macOS PDFKit; preparation code, metadata and saved outputs inspected before implementation"))
    write_json(batch / "original_preservation_hashes.json", preserved)
    distributions = target_distributions(data)
    distributions.to_csv(batch / "target_distributions.csv", index=False)
    weather_audit.to_csv(batch / "weather_join_audit.csv", index=False)
    print(TIMING_LIMITATION, flush=True)
    print("All follow-ups are exploratory. No hyperparameter tuning or source rescaling.", flush=True)
    print(distributions[["building_id", "count", "mean", "median", "p95", "maximum"]].to_string(index=False), flush=True)
    experiments = []
    for configuration, train_ids in (("with_L03", TRAIN_WITH_L03), ("without_L03", TRAIN_WITHOUT_L03)):
        for timing, variant in variants.items():
            name = f"{configuration}__{timing}"
            result = run_experiment(variant, train_ids, name, timing, batch / name, windows,
                                    prior_predictions, args.threads, hashes)
            experiments.append(result)
    all_metrics = pd.concat(experiments, ignore_index=True)
    all_metrics.to_csv(batch / "all_experiment_metrics.csv", index=False)
    l03_comparison = factor_comparison(all_metrics, "L03")
    l03_comparison[l03_comparison.scope == "building"].to_csv(batch / "l03_influence_by_building.csv", index=False)
    l03_comparison.to_csv(batch / "l03_influence_all_groups.csv", index=False)
    timing_comparison = factor_comparison(all_metrics, "timing")
    timing_comparison.to_csv(batch / "weather_timing_comparison.csv", index=False)
    # Non-weather methods must be invariant to the weather-timing-only factor.
    for metric in METRICS:
        unaffected = timing_comparison[timing_comparison.model != "B"]
        np.testing.assert_allclose(unaffected[f"{metric}_current_weather"], unaffected[f"{metric}_lagged_weather_1h"],
                                   rtol=1e-12, atol=1e-13, equal_nan=True)
    make_influence_chart(l03_comparison[l03_comparison.scope == "building"], batch / "l03_influence_rmse.png")
    methodology_report(batch, all_metrics, distributions, command)
    verify_hashes(preserved)
    verify_hashes(hashes)
    # Also compare the original directory file sets, detecting unexpected additions.
    if preserved_files() != preserved:
        raise original.DataError("Original experiment file set changed")
    write_json(batch / "batch_manifest.json", dict(
        status="exploratory", command=command, versions=versions, settings=original.SETTINGS,
        features=original.FEATURES, source_hashes=hashes, weather_sources=weather_sources,
        preserved_original_hashes=preserved, original_run_manifest=str(BASE / "results/run_manifest.json"),
        experiment_names=all_metrics.experiment.unique().tolist(), evaluation_rows=len(prior_predictions),
        original_outputs_unchanged=True, original_source_datasets_unchanged=True,
        nonweather_methods_invariant_to_weather_timing=True, all_evaluation_rows_identical=True,
        original_chart_windows_reused=windows.to_dict("records"), timing_limitation=TIMING_LIMITATION,
        target_units="stated kWh retained; target kWh/m²; no rescaling or additional shifting",
        interpretation="exploratory predictive diagnostics, not untouched tests, causal evidence or production-ready forecasts"))
    print(f"\nCompleted four exploratory experiments. Original outputs and staged sources unchanged.\nSaved: {batch}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (original.DataError, OSError, AssertionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
