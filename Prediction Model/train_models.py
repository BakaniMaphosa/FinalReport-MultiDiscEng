"""Compare two fixed HistGradientBoostingRegressor models and a simple baseline.

Install: python3 -m pip install numpy pandas scikit-learn matplotlib joblib threadpoolctl
Run: python3 "Prediction Model/train_models.py"
Default training buildings: L03_B01, L14_B04, L14_B05 (the requested split).
Default test buildings: L07_B01, L14_B01, L14_B02, L14_B03.
L03 buildings join training; L07 and the other L14 buildings are held out.
Use --test-l14 to test only specified remaining L14 buildings; others are excluded.

Inputs: Input Data/<building>_model_input.csv and Target Set/<building>_targets.csv.
Outputs: results/, charts/, models/ next to this script. No datasets are changed.
Settings/features are fixed in advance: no tuning, validation, or random internal
early-stopping split. Both final models fit all eligible training rows directly.
Calendar features use UTC: no local time-zone mapping is documented in this repo.
Targets already describe their own intervals and are never shifted.
The reference baseline always predicts the mean of eligible TRAINING targets.
It never uses held-out targets to set its constant or any other parameter.
"""

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile

# Avoid a GUI dependency and writes to a global Matplotlib configuration directory.
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "energy_model_matplotlib"))
os.environ.setdefault("OMP_NUM_THREADS", "4")

try:
    import joblib
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import sklearn
    from sklearn.compose import ColumnTransformer
    from sklearn.dummy import DummyRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder
    from threadpoolctl import threadpool_limits
except ImportError as error:
    raise SystemExit(
        f"Missing dependency: {error}\nInstall with:\n"
        "python3 -m pip install numpy pandas 'scikit-learn>=1.2' matplotlib joblib threadpoolctl"
    ) from error


BASE = Path(__file__).resolve().parent
DEFAULT_TRAIN_L14 = ("L14_B04", "L14_B05")
TARGET = "electricity_kwh_per_m2"
NUMERIC_METADATA = [
    "floor_area_m2", "heated_area_m2", "year_opened", "number_of_floors",
    "ventilation_system_count", "ventilation_used_for_heating",
    "ventilation_used_for_cooling", "has_direct_electric_heating",
    "has_district_heating", "has_district_cooling", "has_heat_pump", "has_solar_pv",
]
CATEGORICAL = ["building_use", "climate_zone"]
CALENDAR = [
    "hour_sin", "hour_cos", "weekday_sin", "weekday_cos",
    "annual_sin", "annual_cos", "is_weekend", "calendar_year",
]
WEATHER = [
    "temperature_c", "relative_humidity_pct", "wind_speed_kmh", "wind_direction_deg",
    "direct_solar_radiation_wm2", "diffuse_solar_radiation_wm2",
]
FEATURES = {
    "A": NUMERIC_METADATA + CALENDAR + CATEGORICAL,
    "B": NUMERIC_METADATA + CALENDAR + CATEGORICAL + WEATHER,
}
BASELINE = "baseline_mean"
EVALUATED_MODELS = (BASELINE, "A", "B")
MODEL_LABELS = {
    BASELINE: "Baseline: training-set mean",
    "A": "Model A: metadata + calendar",
    "B": "Model B: metadata + calendar + weather",
}
MODEL_COLORS = {BASELINE: "#666666", "A": "#1f77b4", "B": "#ff7f0e"}
# An explicit predictor allowlist excludes current electricity, the target, any
# extra target-derived columns, timestamps, and building/location identifiers.
SETTINGS = dict(
    loss="squared_error", learning_rate=0.08, max_iter=200, max_leaf_nodes=31,
    min_samples_leaf=30, l2_regularization=1.0, max_bins=255,
    categorical_features=None, early_stopping=False, random_state=42,
)
MISSING = {"", "na", "n/a", "nan", "none", "null", "missing", "unknown"}
WEATHER_ASSUMPTION = (
    "Existing weather is joined by exact interval_start_utc, without shifting. "
    "Weather labelled at prediction time is assumed available then. These are "
    "historical/reanalysis data; publication latency and aggregation timing are "
    "not established. Results are conditional on this availability assumption."
)
ALIGNMENT_REVIEW = (
    "Reviewed Data_cleaning/export_prediction_targets.py: source_targets yields "
    "CSV rows sequentially; export_targets writes each yielded value and checks "
    "order with zip_longest. This run additionally checks target values against "
    "the input's mirrored target column row by row, and any target IDs/timestamps. "
    "Neither file is independently sorted or shuffled."
)


class DataError(ValueError):
    pass


@dataclass
class BuildingData:
    building: str
    features: pd.DataFrame
    target: pd.Series
    tracking: pd.DataFrame
    audit: dict


def fingerprint(path):
    with path.open("rb") as handle:
        checksum = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def read_csv_text(path):
    """Retain empty rows/fields and validate widths before creating a dataframe."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        headers = next(reader, [])
        if not headers or len(headers) != len(set(headers)):
            raise DataError(f"{path}: empty or duplicate column names")
        rows = []
        for number, row in enumerate(reader, 1):
            if len(row) != len(headers):
                raise DataError(f"{path}: data row {number}: CSV field count differs from header")
            rows.append(row)
    if not rows:
        raise DataError(f"{path}: no data rows")
    return pd.DataFrame(rows, columns=headers)


def numeric(series, context):
    text = series.str.strip()
    absent = text.str.casefold().isin(MISSING)
    converted = pd.to_numeric(text.mask(absent), errors="coerce").astype(float)
    bad = converted.isna() & ~absent
    if bad.any():
        raise DataError(f"{context}: unrecognised numeric value at data row {int(np.flatnonzero(bad)[0]) + 1}")
    return converted.replace([np.inf, -np.inf], np.nan)


def timestamps(series, context):
    # utc=True alone would silently accept naive timestamps; require an offset.
    explicit = series.str.strip().str.contains(r"(?:[Zz]|[+-]\d{2}:?\d{2})$", regex=True)
    parsed = pd.to_datetime(series, utc=True, errors="coerce")
    bad = ~explicit | parsed.isna()
    if bad.any():
        raise DataError(f"{context}: missing/invalid/naive timestamp at data row {int(np.flatnonzero(bad)[0]) + 1}")
    return parsed


def build_features(raw, starts):
    """Deterministic unit-preserving transforms; no learned statistics here."""
    features = pd.DataFrame(index=raw.index)
    for name in NUMERIC_METADATA + WEATHER:
        features[name] = numeric(raw[name], name)
    for name in CATEGORICAL:
        text = raw[name].map(lambda value: " ".join(value.split()))
        features[name] = text.mask(text.str.casefold().isin(MISSING), np.nan)
    hour = starts.dt.hour + starts.dt.minute / 60
    weekday = starts.dt.dayofweek
    # A leap year's annual cycle has 366 days; otherwise use 365.
    annual_phase = (starts.dt.dayofyear - 1 + hour / 24) / np.where(starts.dt.is_leap_year, 366, 365)
    for label, phase in (("hour", hour / 24), ("weekday", weekday / 7), ("annual", annual_phase)):
        features[f"{label}_sin"] = np.sin(2 * np.pi * phase)
        features[f"{label}_cos"] = np.cos(2 * np.pi * phase)
    features["is_weekend"] = (weekday >= 5).astype(float)
    features["calendar_year"] = starts.dt.year.astype(float)
    return features


def discover_pairs(base):
    inputs, targets = {}, {}
    for directory, suffix, found in (("Input Data", "model_input", inputs), ("Target Set", "targets", targets)):
        for path in sorted((base / directory).glob("*.csv")):
            match = re.fullmatch(rf"(L\d+_B\d+)_{suffix}\.csv", path.name)
            if not match:
                raise DataError(f"Unexpected CSV filename: {path}")
            found[match.group(1)] = path
    if not inputs or inputs.keys() != targets.keys():
        raise DataError(f"Unmatched input/target building IDs: inputs={sorted(inputs)}, targets={sorted(targets)}")
    if any(building.split("_")[0] not in {"L03", "L07", "L14"} for building in inputs):
        raise DataError("Only L03, L07 and L14 buildings are supported by this experiment")
    return {building: (path, targets[building]) for building, path in inputs.items()}


def load_building(building, source, target_path, generator):
    before = {str(p): fingerprint(p) for p in (source, target_path)}
    raw, target_csv = read_csv_text(source), read_csv_text(target_path)
    required = set(NUMERIC_METADATA + CATEGORICAL + WEATHER + ["building_id", "interval_start_utc", "interval_end_utc"])
    if not required.issubset(raw.columns) or TARGET not in target_csv:
        raise DataError(f"{building}: missing input/target columns: {sorted(required - set(raw.columns))}")
    if len(raw) != len(target_csv):
        raise DataError(f"{building}: row count mismatch: {len(raw)} inputs vs {len(target_csv)} targets")
    if not raw["building_id"].eq(building).all():
        raise DataError(f"{source}: building_id disagrees with filename {building}")
    starts = timestamps(raw["interval_start_utc"], f"{building}/interval_start_utc")
    ends = timestamps(raw["interval_end_utc"], f"{building}/interval_end_utc")
    if not (ends - starts).eq(pd.Timedelta(hours=1)).all():
        raise DataError(f"{building}: intervals must each be exactly one hour")
    keys = []
    for column in ("building_id", "interval_start_utc", "interval_end_utc"):
        if column in target_csv:
            left, right = raw[column], target_csv[column]
            if column.startswith("interval_"):
                left, right = timestamps(left, source), timestamps(right, target_path)
            if not left.eq(right).all():
                raise DataError(f"{building}: target {column} does not align row by row")
            keys.append(column)
    mirrored = TARGET in raw
    if mirrored and not raw[TARGET].eq(target_csv[TARGET]).all():
        raise DataError(f"{building}: target values do not match the input target column row by row")
    if not {"building_id", "interval_start_utc"}.issubset(keys):
        if not mirrored or not generator.is_file():
            raise DataError(f"{building}: cannot establish target alignment without keys or reviewed exporter plus mirrored values")
    target = numeric(target_csv[TARGET], f"{building}/target")
    features = build_features(raw, starts)
    for name in ("floor_area_m2", "heated_area_m2"):
        if (features[name].dropna() <= 0).any():
            raise DataError(f"{building}: supplied {name} must be positive")
    tracking = pd.DataFrame({
        "building_id": building, "location_id": building.split("_")[0],
        "source_data_row": np.arange(1, len(raw) + 1),
        "interval_start_utc": starts, "interval_end_utc": ends,
    })
    audit = dict(
        building_id=building, input_file=str(source), target_file=str(target_path),
        source_sha256=before, input_rows=len(raw), finite_target_rows=int(target.notna().sum()),
        excluded_missing_or_nonfinite_target_rows=int(target.isna().sum()),
        first_interval_start_utc=starts.min().isoformat(), last_interval_start_utc=starts.max().isoformat(),
        duplicate_interval_rows=int(starts.duplicated().sum()),
        target_alignment_keys=keys, mirrored_targets_verified=mirrored,
        predictor_missing_counts={name: int(value) for name, value in features.isna().sum().items()},
        ignored_input_columns=sorted(set(raw.columns) - set(NUMERIC_METADATA + CATEGORICAL + WEATHER)),
    )
    return BuildingData(building, features, target, tracking, audit)


def choose_split(buildings, train_l14, test_l14):
    l14 = {b for b in buildings if b.startswith("L14_")}
    if len(set(train_l14)) != 2 or not set(train_l14).issubset(l14):
        raise DataError(f"Choose exactly two distinct L14 training buildings from {sorted(l14)}")
    selected_test = l14 - set(train_l14) if test_l14 is None else set(test_l14)
    if not selected_test or not selected_test.issubset(l14 - set(train_l14)):
        raise DataError("L14 test buildings must be available, nonempty and disjoint from training")
    train = sorted(b for b in buildings if b.startswith("L03_") or b in train_l14)
    test = sorted(b for b in buildings if b.startswith("L07_") or b in selected_test)
    if not any(b.startswith("L03_") for b in train) or not any(b.startswith("L07_") for b in test):
        raise DataError("This experiment requires L03 training and L07 testing buildings")
    return train, test, sorted(set(buildings) - set(train) - set(test))


def combine(data, names):
    features = pd.concat([data[b].features for b in names], ignore_index=True)
    target = pd.concat([data[b].target for b in names], ignore_index=True)
    tracking = pd.concat([data[b].tracking for b in names], ignore_index=True)
    eligible = target.notna()
    # No weather-based row filtering. Both models share this single mask.
    return features.loc[eligible].reset_index(drop=True), target.loc[eligible].reset_index(drop=True), tracking.loc[eligible].reset_index(drop=True)


def make_pipeline(model):
    categories = Pipeline([
        ("missing", SimpleImputer(strategy="constant", fill_value="__MISSING__", keep_empty_features=True)),
        ("one_hot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    numeric_features = [name for name in FEATURES[model] if name not in CATEGORICAL]
    preprocessing = ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), numeric_features),
        ("categorical", categories, CATEGORICAL),
    ], remainder="drop", sparse_threshold=0)
    # An entirely missing training column gets a fixed zero plus a missingness
    # indicator. This represents absence inside the model, not an observed zero.
    # It also avoids all-NaN binning failures in some sklearn versions.
    return Pipeline([
        ("preprocessing", preprocessing),
        ("regressor", HistGradientBoostingRegressor(**SETTINGS)),
    ])


def evaluate(predictions):
    metrics, reductions = [], []
    for scope, column in (("location", "location_id"), ("building", "building_id")):
        for name, group in predictions.groupby(column, sort=True):
            values = {}
            for model in EVALUATED_MODELS:
                actual, predicted = group["actual_kwh_per_m2"], group[f"predicted_{model}_kwh_per_m2"]
                values[model] = dict(mae_kwh_per_m2=float(mean_absolute_error(actual, predicted)),
                                     rmse_kwh_per_m2=float(np.sqrt(mean_squared_error(actual, predicted))))
                metrics.append(dict(scope=scope, name=name, model=model, n_rows=len(group), **values[model]))
            reductions.append(reduction_row(scope, name, values))
    for model in EVALUATED_MODELS:
        locations = [row for row in metrics if row["scope"] == "location" and row["model"] == model]
        metrics.append(dict(scope="equal_weight_locations", name="L07_and_L14", model=model,
                            n_rows=len(predictions),
                            mae_kwh_per_m2=float(np.mean([row["mae_kwh_per_m2"] for row in locations])),
                            rmse_kwh_per_m2=float(np.mean([row["rmse_kwh_per_m2"] for row in locations]))))
    equal = {row["model"]: row for row in metrics if row["scope"] == "equal_weight_locations"}
    reductions.append(reduction_row("equal_weight_locations", "L07_and_L14", equal))
    metrics = pd.DataFrame(metrics)
    comparisons = []
    for (scope, name), group in metrics.groupby(["scope", "name"], sort=False):
        reference = group[group.model == BASELINE].iloc[0]
        for model in ("A", "B"):
            candidate = group[group.model == model].iloc[0]
            row = dict(scope=scope, name=name, model=model, baseline_model=BASELINE,
                       n_rows=int(candidate.n_rows))
            for metric in ("mae", "rmse"):
                column = f"{metric}_kwh_per_m2"
                baseline_error, model_error = float(reference[column]), float(candidate[column])
                row[f"baseline_{column}"] = baseline_error
                row[f"model_{column}"] = model_error
                row[f"{metric}_reduction_pct"] = percentage_reduction(baseline_error, model_error)
                row[f"{metric}_comparison"] = (
                    "better" if model_error < baseline_error else "worse" if model_error > baseline_error else "equal"
                )
                row[f"{metric}_note"] = (
                    "undefined percentage: baseline error is zero" if baseline_error == 0
                    else "positive = beats baseline; negative = worse than baseline"
                )
            comparisons.append(row)
    return metrics, pd.DataFrame(reductions), pd.DataFrame(comparisons)


def percentage_reduction(reference_error, candidate_error):
    return 100 * (reference_error - candidate_error) / reference_error if reference_error != 0 else np.nan


def reduction_row(scope, name, values):
    row = dict(scope=scope, name=name)
    for metric in ("mae", "rmse"):
        a, b = (values[model][f"{metric}_kwh_per_m2"] for model in ("A", "B"))
        row[f"{metric}_reduction_pct"] = percentage_reduction(a, b)
        row[f"{metric}_note"] = "undefined: Model A error is zero" if a == 0 else "positive = Model B improves; negative = worsens"
    return row


def first_week(frame):
    """First 168 consecutive hourly rows, based only on coverage, not errors."""
    ordered = frame.sort_values(["interval_start_utc", "source_data_row"], kind="stable")
    runs = ordered["interval_start_utc"].diff().ne(pd.Timedelta(hours=1)).cumsum()
    for _, run in ordered.groupby(runs, sort=False):
        if len(run) >= 168:
            return run.iloc[:168]
    raise DataError(f"{frame['building_id'].iloc[0]}: no complete consecutive seven-day period")


def make_charts(predictions, metrics, charts):
    for metric, title in (("mae", "MAE"), ("rmse", "RMSE")):
        locations = metrics[metrics.scope == "location"]
        names = sorted(locations.name.unique())
        fig, ax = plt.subplots(figsize=(9, 5))
        for offset, model in zip((-0.27, 0, 0.27), EVALUATED_MODELS):
            values = [locations[(locations.name == name) & (locations.model == model)][f"{metric}_kwh_per_m2"].iloc[0] for name in names]
            bars = ax.bar(np.arange(len(names)) + offset, values, width=0.27,
                          label=MODEL_LABELS[model], color=MODEL_COLORS[model])
            ax.bar_label(bars, labels=[f"{value:.4g}" for value in values], padding=3, fontsize=9)
        ax.set_xticks(np.arange(len(names)), [f"{name}\n{'Unseen location' if name == 'L07' else 'Unseen buildings; seen location'}" for name in names])
        ax.set_ylabel(f"{title} (kWh/m²)")
        ax.set_title(f"Hourly electricity per gross floor area: test {title} by location")
        ax.legend(fontsize=8)
        ax.margins(y=0.2)
        ax.grid(axis="y", alpha=0.2)
        fig.tight_layout()
        fig.savefig(charts / f"{metric}_by_test_location.png", dpi=160)
        plt.close(fig)
    windows = []
    for building, frame in predictions.groupby("building_id", sort=True):
        week = first_week(frame)
        start = week.interval_start_utc.iloc[0]
        end = start + pd.Timedelta(days=7)
        fig, ax = plt.subplots(figsize=(13, 5))
        ax.plot(week.interval_start_utc, week.actual_kwh_per_m2, label="Actual", color="black", linewidth=1.6)
        for model in EVALUATED_MODELS:
            ax.plot(week.interval_start_utc, week[f"predicted_{model}_kwh_per_m2"],
                    label=MODEL_LABELS[model], color=MODEL_COLORS[model], linewidth=1,
                    linestyle="--" if model == BASELINE else "-", alpha=0.85)
        ax.set_title(f"{building}: actual and predicted hourly electricity per gross floor area\nFirst complete seven-day period: {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC (end exclusive)")
        ax.set_ylabel("Hourly electricity consumption (kWh/m²)")
        ax.set_xlabel("Prediction interval start (UTC)")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M", tz=timezone.utc))
        ax.set_xlim(start, end)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.2)
        fig.tight_layout()
        fig.savefig(charts / f"{building}_first_seven_days.png", dpi=160)
        plt.close(fig)
        windows.append(dict(building_id=building, start_utc=start.isoformat(), end_utc_exclusive=end.isoformat(),
                            rows=len(week), selection="first 168 consecutive hourly rows; independent of prediction errors"))
    return windows


def run(args):
    base, output = args.data_dir.resolve(), args.output_dir.resolve()
    pairs = discover_pairs(base)
    generator = BASE.parent / "Data_cleaning/export_prediction_targets.py"
    data = {building: load_building(building, source, target, generator) for building, (source, target) in pairs.items()}
    print("Target: hourly electricity per gross floor area (kWh/m²); no target shifting.", flush=True)
    print("Calendar time zone: UTC (no documented local time zones).")
    print("Alignment:", ALIGNMENT_REVIEW)
    print("Weather assumption:", WEATHER_ASSUMPTION)
    for building, item in data.items():
        print(f"{building}: input={item.audit['input_rows']:,}; eligible={item.audit['finite_target_rows']:,}; "
              f"missing/nonfinite target={item.audit['excluded_missing_or_nonfinite_target_rows']:,}")
    if args.check_data:
        print("Data checks passed; no preprocessing fitted, no models trained, no outputs written.")
        return
    if args.train_l14 is None:
        raise DataError("Specify the intended two L14 training buildings with --train-l14 ID ID")
    train_names, test_names, excluded = choose_split(data, args.train_l14, args.test_l14)
    train_x, train_y, train_tracking = combine(data, train_names)
    test_x, test_y, tracking = combine(data, test_names)
    if not len(train_y) or not len(test_y):
        raise DataError("Training and test sets must both have finite targets")
    print(f"Training buildings: {train_names}; {len(train_y):,} shared rows")
    print(f"Test buildings: {test_names}; {len(test_y):,} shared rows")
    print(f"Excluded buildings: {excluded}")
    print("L07 is an unseen location; L14 test buildings are unseen buildings at a partly seen location.")
    print("Fixed settings:", json.dumps(SETTINGS, sort_keys=True))
    print("No tuning/validation/model selection; internal early stopping disabled. Fit all training data.")
    print("Reference baseline: constant mean of all eligible training targets; no predictors or test-target fitting.")
    for label in ("A", "B"):
        print(f"Model {label} predictors ({len(FEATURES[label])}): {', '.join(FEATURES[label])}")
    print("Categoricals: training-only constant imputation + one-hot encoding; unknown categories -> all-zero indicators.")
    print("Numeric missing values: training-only median imputation + missingness indicators; entirely missing training columns use 0 + an indicator. No feature scaling.", flush=True)
    models, transformed = {}, {}
    predictions = tracking.copy()
    predictions["actual_kwh_per_m2"] = test_y
    baseline = DummyRegressor(strategy="mean")
    baseline.fit(np.zeros((len(train_y), 1)), train_y)
    baseline_value = float(baseline.constant_.item())
    predictions[f"predicted_{BASELINE}_kwh_per_m2"] = baseline.predict(np.zeros((len(test_y), 1)))
    print(f"Baseline fitted using {len(train_y):,} training rows: {baseline_value:.12g} kWh/m² for every test row.", flush=True)
    with threadpool_limits(limits=args.threads):
        for label in ("A", "B"):
            print(f"Fitting Model {label}...", flush=True)
            model = make_pipeline(label)
            model.fit(train_x[FEATURES[label]], train_y)
            models[label] = model
            transformed[label] = model.named_steps["preprocessing"].get_feature_names_out().tolist()
            predictions[f"predicted_{label}_kwh_per_m2"] = model.predict(test_x[FEATURES[label]])
            print(f"Model {label}: {model.named_steps['regressor'].n_iter_} iterations; {len(transformed[label])} encoded predictors.", flush=True)
    for label in EVALUATED_MODELS:
        if not np.isfinite(predictions[f"predicted_{label}_kwh_per_m2"]).all():
            raise DataError(f"Model {label}: non-finite predictions")
    category_maps = {}
    for label, model in models.items():
        encoder = model.named_steps["preprocessing"].named_transformers_["categorical"].named_steps["one_hot"]
        category_maps[label] = {name: values.tolist() for name, values in zip(CATEGORICAL, encoder.categories_)}
    if category_maps["A"] != category_maps["B"]:
        raise DataError("Models used different category mappings")
    metrics, reductions, baseline_comparisons = evaluate(predictions)
    # Preflight chart coverage before writing outputs.
    for _, frame in predictions.groupby("building_id", sort=True):
        first_week(frame)
    for folder in ("results", "charts", "models"):
        (output / folder).mkdir(parents=True, exist_ok=True)
    results, charts, model_dir = (output / folder for folder in ("results", "charts", "models"))
    predictions.to_csv(results / "test_predictions.csv", index=False)
    metrics.to_csv(results / "metrics.csv", index=False)
    reductions.to_csv(results / "weather_error_reductions.csv", index=False)
    baseline_comparisons.to_csv(results / "baseline_comparisons.csv", index=False)
    for building, frame in predictions.groupby("building_id", sort=True):
        frame.to_csv(results / f"{building}_predictions.csv", index=False)
    windows = make_charts(predictions, metrics, charts)
    pd.DataFrame(windows).to_csv(results / "chart_periods.csv", index=False)
    feature_rows = [dict(model=label, feature=name, representation=representation)
                    for label in ("A", "B")
                    for representation, names in (("input_predictor", FEATURES[label]), ("encoded_predictor", transformed[label]))
                    for name in names]
    pd.DataFrame(feature_rows).to_csv(results / "predictors.csv", index=False)
    split_rows = [dict(split=split, **data[building].audit)
                  for split, names in (("train", train_names), ("test", test_names), ("excluded", excluded))
                  for building in names]
    pd.DataFrame([{k: v for k, v in row.items() if not isinstance(v, (list, dict))} for row in split_rows]).to_csv(results / "split_summary.csv", index=False)
    for label, model in models.items():
        joblib.dump(model, model_dir / f"model_{label}_pipeline.joblib")
    joblib.dump(baseline, model_dir / "baseline_mean.joblib")
    manifest = dict(
        created_utc=datetime.now(timezone.utc).isoformat(), training_script_sha256=fingerprint(Path(__file__)),
        train_buildings=train_names, test_buildings=test_names, excluded_buildings=excluded,
        train_rows=len(train_y), test_rows=len(test_y), calendar_time_zone="UTC",
        target=TARGET, target_unit="kWh/m² per hourly interval", target_shift=0,
        validation="None: settings fixed before test evaluation; early_stopping=False; all training rows fitted",
        model_settings=SETTINGS, input_predictors=FEATURES, encoded_predictors=transformed,
        reference_baseline=dict(
            estimator="sklearn.dummy.DummyRegressor", strategy="mean", value_kwh_per_m2=baseline_value,
            fit_buildings=train_names, fit_rows=len(train_y), predictors=[],
            weighting="Each eligible training row has equal weight; no per-test-building or test-location adjustment",
            predictions_column=f"predicted_{BASELINE}_kwh_per_m2", model_file="baseline_mean.joblib",
            comparison="Same test rows as A/B, by building/location and equal-weight test locations",
        ),
        categorical_vocabularies=category_maps,
        numeric_missing="Training-only median imputation + missingness indicators; entirely missing training columns use fixed 0 + indicator; source metadata unchanged",
        all_missing_training_predictors=[name for name in FEATURES["B"] if train_x[name].isna().all()],
        unknown_test_categories={name: sorted(set(test_x[name].dropna()) - set(train_x[name].dropna())) for name in CATEGORICAL},
        excluded_predictors="All columns outside explicit allowlists, including electricity_kwh, target/derived targets, IDs and raw timestamps",
        weather_availability_assumption=WEATHER_ASSUMPTION, target_alignment_review=ALIGNMENT_REVIEW,
        upstream_exporter=str(generator), upstream_exporter_sha256=fingerprint(generator) if generator.is_file() else None,
        building_audits=split_rows, chart_periods=windows,
        location_interpretation="L07 = unseen location; L14 = unseen buildings within partly seen location; L03 = training",
        equal_weight_average="Arithmetic mean of L07 and L14 location MAEs; separately arithmetic mean of location RMSEs (not pooled RMSE)",
        error_reduction="100 * (A - B) / A; empty when A is zero; negative means B performs worse",
        baseline_error_reduction="100 * (baseline_error - model_error) / baseline_error; empty when baseline_error is zero; negative means worse than baseline",
        interpretation="Predictive improvement does not establish a causal effect of weather",
        versions=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                      scikit_learn=sklearn.__version__, matplotlib=matplotlib.__version__, joblib=joblib.__version__),
    )
    (results / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (model_dir / "feature_schema.json").write_text(json.dumps(dict(input_predictors=FEATURES, encoded_predictors=transformed,
                                                                    calendar_time_zone="UTC", categorical_vocabularies=category_maps,
                                                                    reference_baseline=dict(strategy="training_mean", predictors=[], value_kwh_per_m2=baseline_value),
                                                                    usage="Load pipeline with joblib; use build_features(raw, parsed interval_start_utc) from train_models.py before pipeline.predict."), indent=2) + "\n")
    summary = "\n".join([
        f"Training buildings: {', '.join(train_names)} ({len(train_y):,} rows)",
        f"Test buildings: {', '.join(test_names)} ({len(test_y):,} rows)",
        f"Excluded buildings: {', '.join(excluded) or 'none'}",
        "L07: unseen location. L14: unseen buildings at a partly seen location. L03: training.",
        "Calendar features: UTC. Models use identical rows/settings; no tuning or random early stopping.",
        f"Reference baseline: training-set mean = {baseline_value:.12g} kWh/m², fitted only on {len(train_y):,} training rows.",
        "The baseline uses no predictive features and no held-out targets for fitting.",
        WEATHER_ASSUMPTION, "", metrics.to_string(index=False), "", reductions.to_string(index=False), "",
        "Model comparisons against the training-mean baseline (positive reduction = improvement):",
        baseline_comparisons[["scope", "name", "model", "mae_reduction_pct", "rmse_reduction_pct", "mae_comparison", "rmse_comparison"]].to_string(index=False), "",
        "Units: MAE/RMSE in kWh/m². Equal-weight results average the two location metrics separately.",
        "Error reduction: 100*(A-B)/A; positive improves, negative worsens; blank if A=0.",
        "Baseline error reduction: 100*(baseline-model)/baseline; positive beats baseline, negative is worse; blank if baseline error=0.",
        "Predictive improvement does not establish causation.",
        "Exact input and encoded feature lists: predictors.csv and run_manifest.json.",
    ]) + "\n"
    (results / "run_summary.txt").write_text(summary, encoding="utf-8")
    for item in data.values():
        for path, checksum in item.audit["source_sha256"].items():
            if fingerprint(Path(path)) != checksum:
                raise DataError(f"Source dataset changed during run: {path}")
    print("\n" + summary)
    print(f"Saved metrics/predictions: {results}\nSaved figures: {charts}\nSaved fitted pipelines: {model_dir}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=BASE, help="folder containing Input Data and Target Set")
    parser.add_argument("--output-dir", type=Path, default=BASE, help="parent for results/, charts/, models/")
    parser.add_argument("--train-l14", nargs=2, default=DEFAULT_TRAIN_L14, metavar="BUILDING",
                        help="two L14 buildings to train on alongside L03 (default: L14_B04 L14_B05)")
    parser.add_argument("--test-l14", nargs="+", metavar="BUILDING", help="L14 test buildings (default: all remaining L14s)")
    parser.add_argument("--check-data", action="store_true", help="check files/alignment only; train nothing")
    parser.add_argument("--threads", type=int, default=4, help="maximum numerical-library threads (default: 4)")
    args = parser.parse_args(argv)
    if args.threads < 1:
        parser.error("--threads must be positive")
    try:
        run(args)
    except (DataError, OSError, csv.Error, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
