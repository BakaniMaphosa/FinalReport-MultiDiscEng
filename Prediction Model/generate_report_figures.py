"""Draw six report figures from the completed validation experiment; never fit.

From the project root:
  "Prediction Model/.venv/bin/python" -B "Prediction Model/generate_report_figures.py"

Default destination: Prediction Model/charts/. Existing output filenames are
never overwritten; pass --output-dir with a fresh folder for another rendering.
PNG (320 DPI), editable SVG, captions, plotted data and provenance are saved.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shlex
import sys
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "energy_model_matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
RUN = BASE / "experiments/validation/run_20261025T091525_455049Z"
DEVELOPMENT = ("L03_B01", "L14_B04", "L14_B05")
TEST = ("L07_B01", "L14_B01", "L14_B02", "L14_B03")
METHODS = ("A", "B", "baseline_mean", "baseline_calendar_use")
COLORS = {"A": "#0072B2", "B": "#D55E00", "baseline_mean": "#666666", "baseline_calendar_use": "#8C6BB1"}
LABELS = {"A": "Model A: no weather", "B": "Model B: with weather",
          "baseline_mean": "Global-mean baseline", "baseline_calendar_use": "Calendar/building-use baseline"}
ROLES = {"fit": "#5B8DB8", "validation": "#E6AD4F", "test": "#5E9F83"}
STEMS = ("figure_1_workflow", "figure_2_data_split", "figure_3_validation_rmse",
         "figure_4_test_rmse", "figure_5_actual_vs_predicted", "figure_6_weather_contribution")
EXTRAS = ("captions.md", "figure_manifest.json", "figure_2_plot_data.csv", "figure_3_plot_data.csv",
          "figure_4_plot_data.csv", "figure_5_plot_data.csv", "figure_6_plot_data.csv")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path):
    return pd.read_csv(path, keep_default_na=False)


def existing_files():
    """Include datasets, code and remaining experiment artifacts in preservation."""
    paths = []
    for folder in (BASE.parent / "Data", BASE.parent / "Data_cleaning", BASE):
        paths.extend(folder.rglob("*"))
    return {str(p.resolve()): sha256(p) for p in paths if p.is_file() and
            not any(part in {".venv", "__pycache__"} for part in p.parts) and p.name != ".DS_Store"}


def verify_rmse(frame, expected, method, context):
    actual = frame.actual_kwh_per_m2.to_numpy(dtype=float)
    predicted = frame[f"predicted_{method}_kwh_per_m2"].to_numpy(dtype=float)
    require(np.isfinite(actual).all() and np.isfinite(predicted).all(), f"Nonfinite {context} values")
    value = float(np.sqrt(np.mean((predicted - actual) ** 2)))
    np.testing.assert_allclose(value, expected, rtol=1e-11, atol=1e-12, err_msg=context)
    return value


def load_plot_data():
    manifest = json.loads((RUN / "run_manifest.json").read_text())
    selected = json.loads((RUN / "selected_settings.json").read_text())
    plan = json.loads((RUN / "candidate_plan.json").read_text())
    require(manifest["selected_candidate"] == selected["candidate"], "Selected candidate disagrees with manifest")
    require(selected["settings"] == plan["candidates"][selected["candidate"]], "Selected settings disagree with candidate plan")
    require(manifest["weather_alignment"] == "exact interval_start_utc (original exact-t)", "Unexpected weather timing")
    for name, expected in manifest["source_hashes"].items():
        require(sha256(name) == expected, f"Experiment source changed: {name}")
    predictions = read_csv(RUN / "final/results/test_predictions.csv")
    for column in ("interval_start_utc", "interval_end_utc"):
        predictions[column] = pd.to_datetime(predictions[column], utc=True)
    require(set(predictions.building_id) == set(TEST), "Unexpected test buildings")
    require(len(predictions) == manifest["test_rows"], "Test row count changed")
    require(not predictions.duplicated(["building_id", "source_data_row"]).any(), "Duplicate test source rows")
    metrics = read_csv(RUN / "final/results/metrics.csv")
    building_metrics = metrics[metrics.scope == "building"]
    require(len(building_metrics) == 16, "Expected four methods for each of four test buildings")
    rmse_rows = []
    for building in TEST:
        frame = predictions[predictions.building_id == building]
        for method in METHODS:
            saved = building_metrics[(building_metrics.name == building) & (building_metrics.model == method)]
            require(len(saved) == 1, f"Missing/duplicate metric: {building}/{method}")
            value = verify_rmse(frame, float(saved.rmse_kwh_per_m2.iloc[0]), method, f"{building}/{method}")
            rmse_rows.append(dict(building_id=building, method=method, test_rows=len(frame), rmse_kwh_per_m2=value))
    test_rmse = pd.DataFrame(rmse_rows)
    boundaries = read_csv(RUN / "split_boundaries.csv")
    require(set(boundaries.building_id) == set(DEVELOPMENT), "Development split differs")
    timeline, inputs = [], {}
    for building in (*DEVELOPMENT, *TEST):
        path = BASE / "Input Data" / f"{building}_model_input.csv"
        raw = pd.read_csv(path, dtype=str, keep_default_na=False)
        target = pd.read_csv(BASE / "Target Set" / f"{building}_targets.csv", dtype=str, keep_default_na=False)
        require(raw.building_id.eq(building).all(), f"Input building identity differs: {building}")
        require(raw.electricity_kwh_per_m2.equals(target.electricity_kwh_per_m2), f"Input/target order mismatch: {building}")
        starts = pd.to_datetime(raw.interval_start_utc, utc=True)
        ends = pd.to_datetime(raw.interval_end_utc, utc=True)
        require((ends - starts).eq(pd.Timedelta(hours=1)).all(), f"Non-hourly interval: {building}")
        inputs[building] = (raw, starts, ends)
        if building in DEVELOPMENT:
            boundary = boundaries[boundaries.building_id == building].iloc[0]
            unique = pd.DatetimeIndex(starts.unique()).sort_values()
            n_fit = 4 * len(unique) // 5
            cutoff = unique[n_fit]
            require(cutoff == pd.Timestamp(boundary.validation_start_utc), f"Cutoff changed: {building}")
            for role, mask in (("fit", starts < cutoff), ("validation", starts >= cutoff)):
                require(int(mask.sum()) == int(boundary[f"{role}_rows"]), f"Split count changed: {building}/{role}")
                timeline.append(dict(building_id=building, role=role, start_utc=starts[mask].min(),
                                     end_utc_exclusive=ends[mask].max(), rows=int(mask.sum()),
                                     unique_timestamps=int(starts[mask].nunique()), cutoff_utc=cutoff))
        else:
            frame = predictions[predictions.building_id == building]
            index = frame.source_data_row.to_numpy(dtype=int) - 1
            for column, source in (("interval_start_utc", starts), ("interval_end_utc", ends)):
                np.testing.assert_array_equal(frame[column], source.iloc[index])
            np.testing.assert_allclose(frame.actual_kwh_per_m2, pd.to_numeric(raw.electricity_kwh_per_m2.iloc[index]),
                                       rtol=1e-12, atol=1e-14)
            timeline.append(dict(building_id=building, role="test", start_utc=starts.min(),
                                 end_utc_exclusive=ends.max(), rows=len(frame),
                                 unique_timestamps=starts.nunique(), cutoff_utc=pd.NaT))
    scores = read_csv(RUN / "selection_scores.csv")
    validation_metrics = read_csv(RUN / "validation/all_candidate_metrics.csv")
    candidate_rows, row_reference = [], None
    for name, settings in plan["candidates"].items():
        frame = read_csv(RUN / "validation" / name / "results/validation_predictions.csv")
        key = frame[["building_id", "source_data_row", "interval_start_utc", "interval_end_utc", "actual_kwh_per_m2"]]
        if row_reference is None:
            row_reference = key
        else:
            pd.testing.assert_frame_equal(key, row_reference)
        require(set(frame.building_id) == set(DEVELOPMENT), "Validation has test building rows")
        for building, group in frame.groupby("building_id", sort=False):
            raw, starts, _ = inputs[building]
            index = group.source_data_row.to_numpy(dtype=int) - 1
            cutoff = pd.Timestamp(boundaries[boundaries.building_id == building].validation_start_utc.iloc[0])
            require((starts.iloc[index] >= cutoff).all(), "Fitting row entered validation predictions")
            np.testing.assert_allclose(group.actual_kwh_per_m2, pd.to_numeric(raw.electricity_kwh_per_m2.iloc[index]),
                                       rtol=1e-12, atol=1e-14)
        for method in ("A", "B"):
            errors = []
            for building, group in frame.groupby("building_id", sort=False):
                saved = validation_metrics[(validation_metrics.candidate == name) & (validation_metrics.scope == "building") &
                                           (validation_metrics.name == building) & (validation_metrics.model == method)]
                require(len(saved) == 1, "Missing building validation metric")
                errors.append(verify_rmse(group, float(saved.rmse_kwh_per_m2.iloc[0]), method, f"{name}/{building}/{method}"))
            macro = float(np.mean(errors))
            np.testing.assert_allclose(macro, scores.loc[scores.candidate == name, f"{method}_validation_macro_rmse"].iloc[0], rtol=1e-11)
            candidate_rows.append(dict(candidate=name, model=method, validation_rmse_kwh_per_m2=macro,
                                       max_leaf_nodes=settings["max_leaf_nodes"], min_samples_leaf=settings["min_samples_leaf"]))
    validation_rmse = pd.DataFrame(candidate_rows)
    ranking = [(float(group.validation_rmse_kwh_per_m2.mean()), int(group.max_leaf_nodes.iloc[0]),
                -int(group.min_samples_leaf.iloc[0]), name) for name, group in validation_rmse.groupby("candidate")]
    require(min(ranking)[-1] == selected["candidate"], "Shared validation winner differs")
    windows = read_csv(BASE / "results/chart_periods.csv")
    require(set(windows.building_id) == set(TEST) and len(windows) == 4, "Expected original four chart windows")
    week_frames = []
    for window in windows.itertuples(index=False):
        start, end = pd.Timestamp(window.start_utc), pd.Timestamp(window.end_utc_exclusive)
        frame = predictions[(predictions.building_id == window.building_id) &
                            (predictions.interval_start_utc >= start) & (predictions.interval_start_utc < end)].copy()
        require(len(frame) == int(window.rows) == 168, f"Incomplete week: {window.building_id}")
        require(pd.DatetimeIndex(frame.interval_start_utc).equals(pd.date_range(start, end, freq="h", inclusive="left")),
                f"Nonconsecutive/unsorted original chart window: {window.building_id}")
        week_frames.append(frame[["building_id", "source_data_row", "interval_start_utc", "interval_end_utc",
                                  "actual_kwh_per_m2", "predicted_A_kwh_per_m2", "predicted_B_kwh_per_m2"]])
    weeks = pd.concat(week_frames, ignore_index=True)
    effects = test_rmse.pivot(index="building_id", columns="method", values="rmse_kwh_per_m2").reindex(TEST)
    effects = effects[["A", "B"]].rename(columns={"A": "rmse_A_kwh_per_m2", "B": "rmse_B_kwh_per_m2"})
    effects["delta_rmse_kwh_per_m2"] = effects.rmse_A_kwh_per_m2 - effects.rmse_B_kwh_per_m2
    return manifest, selected, pd.DataFrame(timeline), validation_rmse, test_rmse, windows, weeks, effects.reset_index()


def style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12,
        "axes.labelsize": 10, "legend.fontsize": 9, "xtick.labelsize": 9, "ytick.labelsize": 9,
        "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
        "grid.color": "#D8DDE2", "grid.linewidth": 0.6, "axes.edgecolor": "#66717C",
        "figure.facecolor": "white", "savefig.facecolor": "white", "svg.fonttype": "none",
        "svg.hashsalt": "electricity-report-figures", "pdf.fonttype": 42,
    })


def save_figure(fig, output, stem):
    for suffix in ("png", "svg"):
        with (output / f"{stem}.{suffix}").open("xb") as handle:
            fig.savefig(handle, format=suffix, dpi=320, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def workflow(output):
    fig, ax = plt.subplots(figsize=(14.5, 4.4))
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.13, top=0.87)
    ax.set(xlim=(0, 16.1), ylim=(0, 4.5))
    ax.axis("off")
    def box(x, y, width, height, text, face="#F4F6F8", edge="#657585", size=10):
        ax.add_patch(FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0.06,rounding_size=0.09",
                                   linewidth=0.9, facecolor=face, edgecolor=edge, zorder=2))
        ax.text(x + width / 2, y + height / 2, text, ha="center", va="center", fontsize=size, zorder=3, linespacing=1.4)
    def arrow(start, end, connection="arc3,rad=0"):
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=12, color="#4B5662",
                                    linewidth=1.15, connectionstyle=connection, zorder=1))
    # Test observations leave the building split and bypass both fitting stages.
    ax.add_patch(FancyBboxPatch((8.78, 1.48), 4.6, 2.65, boxstyle="round,pad=0.09,rounding_size=0.1",
                               facecolor="#EEF4F9", edgecolor="#9BB4CA", linewidth=0.8, linestyle="--"))
    ax.text(11.08, 3.91, "MODEL DEVELOPMENT ONLY", ha="center", fontsize=10, weight="bold", color="#385A78")
    ax.text(11.08, 1.70, "Known-building future-period validation", ha="center", fontsize=9, color="#385A78")
    for y, label in ((3.45, "Electricity\nconsumption"), (2.35, "Weather"), (1.25, "Building\nmetadata")):
        box(0.08, y, 1.50, 0.72, label, size=9.5)
        arrow((1.65, y + 0.36), (2.04, 2.87))
    nodes = [
        (2.1, 1.65, "Data\npreparation\nUTC alignment"),
        (4.25, 1.75, "Features + target\nA: 22; B: 28\nkWh / gross m²"),
        (6.5, 1.85, "Building split\n3 development\n4 held-out"),
        (8.98, 2.0, "Model validation\n80% fit / 20% validate\n3 fixed candidates"),
        (11.45, 1.65, "Model refitting\nAll 80,665 dev. rows\nA, B + baselines"),
        (13.87, 2.04, "Final evaluation\n118,887 test rows\nMAE · RMSE · nRMSE"),
    ]
    for x, width, text in nodes:
        box(x, 2.18, width, 1.32, text, face="#E9F3ED" if x > 13 else "#FFFFFF", size=9.1)
    for (x, width, _), (next_x, _, _) in zip(nodes, nodes[1:]):
        arrow((x + width + 0.05, 2.84), (next_x - 0.07, 2.84))
    ax.text(11.22, 3.58, "Selected settings", ha="center", fontsize=8)
    box(8.98, 0.25, 4.12, 0.73, "Held out: L07_B01, L14_B01/B02/B03\nExcluded from fitting and parameter selection", face="#E9F3ED", size=9)
    arrow((7.42, 2.10), (8.93, 0.61), "angle,angleA=-90,angleB=180,rad=0")
    arrow((13.16, 0.61), (14.88, 2.10), "angle,angleA=0,angleB=-90,rad=0")
    ax.text(11.1, 1.28, "Development: L03_B01, L14_B04, L14_B05", ha="center", fontsize=8.7)
    fig.suptitle("Experimental workflow: chronological validation followed by held-out evaluation", y=0.99, fontsize=13)
    fig.text(0.5, 0.03, "Previously inspected test buildings; exact-t reanalysis weather availability remains an assumption.", ha="center", fontsize=9, color="#4B5662")
    save_figure(fig, output, STEMS[0])


def data_split(timeline, output):
    fig, ax = plt.subplots(figsize=(11.8, 5.5))
    fig.subplots_adjust(left=0.22, right=0.77, bottom=0.19, top=0.86)
    positions = {building: i for i, building in enumerate((*DEVELOPMENT, *TEST))}
    for row in timeline.itertuples(index=False):
        start, end = mdates.date2num(row.start_utc), mdates.date2num(row.end_utc_exclusive)
        ax.barh(positions[row.building_id], end - start, left=start, height=0.57,
                color=ROLES[row.role], edgecolor="white", linewidth=0.6)
    for building, group in timeline.groupby("building_id", sort=False):
        counts = {r.role: int(r.rows) for r in group.itertuples()}
        label = (f"Fit {counts['fit']:,}  |  Val {counts['validation']:,}" if "fit" in counts else f"Test {counts['test']:,}")
        ax.text(1.02, positions[building], label, transform=ax.get_yaxis_transform(), va="center", fontsize=9)
        if "fit" in counts:
            cutoff = group[group.role == "validation"].start_utc.iloc[0]
            ax.plot([cutoff, cutoff], [positions[building] - 0.35, positions[building] + 0.35], color="#614415", linewidth=0.8)
    ax.set_yticks(list(positions.values()), list(positions))
    ax.invert_yaxis()
    ax.axhline(2.5, color="#8C969F", linewidth=0.8, linestyle="--")
    ax.text(-0.34, 1, "DEVELOPMENT", transform=ax.get_yaxis_transform(), rotation=90, va="center", fontsize=10, weight="bold", color="#385A78")
    ax.text(-0.34, 4.5, "HELD-OUT TEST", transform=ax.get_yaxis_transform(), rotation=90, va="center", fontsize=10, weight="bold", color="#38604B")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y", tz=timezone.utc))
    ax.set_xlim(pd.Timestamp("2017-10-01", tz="UTC"), pd.Timestamp("2023-03-01", tz="UTC"))
    ax.set_xlabel("Observation interval (UTC calendar time)")
    ax.grid(axis="x", alpha=0.65)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=10)
    fig.suptitle("Dataset partition by building and observation time", y=0.98, fontsize=13)
    fig.legend(handles=[Patch(facecolor=ROLES[r], label=label) for r, label in
                        (("fit", "Fitting: earliest 80%"), ("validation", "Validation: latest 20%"), ("test", "Held-out test"))],
               loc="upper center", bbox_to_anchor=(0.5, 0.935), ncol=3, frameon=False)
    fig.text(0.5, 0.045, "80/20 uses unique timestamps within each development building (rounded down for fitting).\n"
             "Bars show coverage spans, including gaps; widths reflect elapsed time, not row counts.\n"
             "Held-out buildings do not enter development; all development rows are used again for the final refit.",
             ha="center", va="center", fontsize=8.8, color="#4B5662", linespacing=1.45)
    save_figure(fig, output, STEMS[1])


def validation_comparison(frame, selected, output):
    fig, ax = plt.subplots(figsize=(9.3, 5.2))
    fig.subplots_adjust(bottom=0.24, top=0.86, left=0.12, right=0.97)
    candidates = list(frame.candidate.drop_duplicates())
    x = np.arange(len(candidates))
    for model, offset in (("A", -0.19), ("B", 0.19)):
        values = frame[frame.model == model].set_index("candidate").loc[candidates].validation_rmse_kwh_per_m2
        bars = ax.bar(x + offset, values, width=0.35, color=COLORS[model], label=LABELS[model])
        ax.bar_label(bars, labels=[f"{value:.6f}" for value in values], padding=5, fontsize=9)
        best = int(np.argmin(values.to_numpy()))
        bars[best].set_edgecolor("#171D23")
        bars[best].set_linewidth(1.5)
        ax.text(x[best] + offset, values.iloc[best] * 0.55, "Best", color="white", fontsize=9, weight="bold", ha="center")
    labels = []
    for name in candidates:
        row = frame[frame.candidate == name].iloc[0]
        labels.append(f"Configuration {name.rsplit('_', 1)[-1]}\n{int(row.max_leaf_nodes)} leaves; min leaf {int(row.min_samples_leaf)}")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Validation RMSE (kWh/m²)")
    ax.set_ylim(0, frame.validation_rmse_kwh_per_m2.max() * 1.20)
    ax.grid(axis="y", alpha=0.65)
    ax.set_title("Validation RMSE for the three predefined configurations", pad=16)
    ax.legend(frameon=False, loc="upper left")
    fig.text(0.5, 0.055, f"Equal-weight mean of the three validation-building RMSEs. Shared selection: {selected['candidate'].replace('_', ' ')}.\n"
             "Black outlines identify each model's lowest validation RMSE; the selection rule averages A and B.", ha="center", fontsize=9, color="#4B5662")
    save_figure(fig, output, STEMS[2])


def test_comparison(frame, output):
    fig, ax = plt.subplots(figsize=(10.7, 5.6))
    fig.subplots_adjust(bottom=0.17, top=0.79, left=0.10, right=0.98)
    x = np.arange(len(TEST))
    for offset, method in zip((-0.30, -0.10, 0.10, 0.30), METHODS):
        values = frame[frame.method == method].set_index("building_id").loc[list(TEST)].rmse_kwh_per_m2
        bars = ax.bar(x + offset, values, width=0.18, color=COLORS[method], label=LABELS[method])
        ax.bar_label(bars, labels=[f"{value:.4f}" for value in values], rotation=90, padding=5, fontsize=8.5)
    ax.set_xticks(x, TEST)
    ax.set_ylabel("Test RMSE (kWh/m²)")
    ax.set_ylim(0, frame.rmse_kwh_per_m2.max() * 1.20)
    ax.grid(axis="y", alpha=0.65)
    fig.suptitle("Final models and baselines: error by held-out building", y=0.98, fontsize=13)
    fig.legend(*ax.get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(0.5, 0.93), ncol=2, frameon=False)
    fig.text(0.5, 0.045, "Candidate 2 refitted on all development rows. L07: unseen location; L14: unseen buildings at a known location.\n"
             "All four methods use identical test observations; these test buildings were inspected in earlier experiments.", ha="center", fontsize=8.8, color="#4B5662")
    save_figure(fig, output, STEMS[3])


def actual_vs_predicted(weeks, windows, output):
    fig, axes = plt.subplots(2, 2, figsize=(12.6, 8.8))
    fig.subplots_adjust(top=0.86, bottom=0.22, left=0.08, right=0.98, hspace=0.53, wspace=0.22)
    for index, (ax, building) in enumerate(zip(axes.flat, TEST)):
        frame = weeks[weeks.building_id == building]
        window = windows[windows.building_id == building].iloc[0]
        start, end = pd.Timestamp(window.start_utc), pd.Timestamp(window.end_utc_exclusive)
        for column, label, color, linestyle, width in (
            ("actual_kwh_per_m2", "Actual", "#20252A", "-", 1.6),
            ("predicted_A_kwh_per_m2", LABELS["A"], COLORS["A"], "--", 1.05),
            ("predicted_B_kwh_per_m2", LABELS["B"], COLORS["B"], ":", 1.25),
        ):
            ax.plot(frame.interval_start_utc, frame[column], label=label, color=color, linestyle=linestyle, linewidth=width)
        ax.axhline(0, color="#7D8791", linewidth=0.5)
        ax.set_xlim(start, end)
        ticks = [start + pd.Timedelta(days=days) for days in (0, 2, 4, 6)]
        ax.set_xticks(ticks)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M", tz=timezone.utc))
        ax.set_title(f"({chr(97 + index)}) {building}  |  {start:%d %b %Y}–{end:%d %b %Y}", loc="left", fontsize=10.5)
        ax.set_xlabel("Prediction interval start (UTC)", fontsize=9)
        ax.set_ylabel("Hourly electricity (kWh/m²)", fontsize=9)
        ax.grid(alpha=0.6)
        if building == "L14_B03":
            # Show the large error on the main axis while allowing actual demand
            # peaks to remain readable; this inset is explicitly actual-only.
            inset = ax.inset_axes([0.14, 0.10, 0.77, 0.21])
            inset.plot(frame.interval_start_utc, frame.actual_kwh_per_m2, color="#20252A", linewidth=0.8)
            inset.set_xlim(start, end)
            inset.tick_params(labelsize=7, axis="y", pad=1)
            inset.set_xticks([])
            inset.set_title("Actual-only detail (same kWh/m² units)", fontsize=7.5, pad=3)
            inset.grid(axis="y", alpha=0.45)
            inset.patch.set_alpha(0.98)
    fig.suptitle("Actual and predicted hourly electricity per gross floor area", y=0.99, fontsize=13)
    fig.legend(*axes.flat[0].get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(0.5, 0.95), ncol=3, frameon=False)
    fig.text(0.5, 0.045, "Original first complete seven-day windows; 168 hourly observations per building; end dates are exclusive.\n"
             "Panels use independent vertical scales. L14_B03 includes an actual-only inset because predictions are much larger.\n"
             "Negative model predictions are retained without clipping. Models and targets are not retrained or shifted.",
             ha="center", fontsize=9, color="#4B5662", linespacing=1.5)
    save_figure(fig, output, STEMS[4])


def weather_contribution(effects, output):
    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    fig.subplots_adjust(left=0.12, right=0.97, bottom=0.22, top=0.84)
    values = effects.delta_rmse_kwh_per_m2
    colors = ["#009E73" if value > 0 else "#BC3C3D" if value < 0 else "#777777" for value in values]
    bars = ax.bar(np.arange(len(TEST)), values, width=0.58, color=colors)
    for bar, value in zip(bars, values):
        ax.annotate(f"{value:+.6f}", (bar.get_x() + bar.get_width() / 2, value),
                    xytext=(0, 6 if value >= 0 else -6), textcoords="offset points", ha="center",
                    va="bottom" if value >= 0 else "top", fontsize=10)
    ax.axhline(0, color="#171D23", linewidth=1.2)
    ax.set_xticks(np.arange(len(TEST)), TEST)
    ax.set_ylabel("ΔRMSE = RMSE(A) − RMSE(B) (kWh/m²)")
    extent = max(abs(values.min()), abs(values.max())) * 1.45
    ax.set_ylim(-extent, extent)
    ax.grid(axis="y", alpha=0.65)
    fig.suptitle("Weather contribution to held-out prediction accuracy", y=0.995, fontsize=13)
    fig.legend(handles=[Patch(facecolor="#009E73", label="Positive: lower error with weather"),
                        Patch(facecolor="#BC3C3D", label="Negative: higher error with weather")],
               loc="upper center", bbox_to_anchor=(0.5, 0.95), ncol=2, frameon=False, fontsize=8.8)
    fig.text(0.5, 0.065, "Identical candidate-2 settings and test rows; the RMSE values are the same as in Figure 4.\n"
             "This is a predictive comparison conditional on assumed exact-t weather availability, not evidence of causation.",
             ha="center", fontsize=9, color="#4B5662")
    save_figure(fig, output, STEMS[5])


def captions(selected):
    return [
        "Experimental workflow for predicting hourly electricity consumption per gross floor area. "
        "L03_B01/L14_B04/L14_B05 supply per-building chronological validation and full-development refitting; "
        "L07_B01/L14_B01/B02/B03 bypass model development and enter only held-out evaluation. "
        "The tests were previously inspected and exact-t reanalysis weather availability is assumed.",
        "Chronological coverage and partition membership for all seven buildings. Within each development building, "
        "the earliest floor(80% of unique interval-start timestamps) fit the methods and the remaining timestamps validate them. "
        "Held-out buildings are excluded from development. Bar widths show elapsed time over coverage spans, including gaps, "
        "rather than observation counts; cutoffs differ by building and all development rows are subsequently used for refitting.",
        "Validation RMSE for the three predefined HistGradientBoostingRegressor configurations, averaged equally across "
        "the three validation buildings. Black outlines identify the lowest value for each model. Configuration 2 "
        "(15 leaf nodes; minimum leaf size 60) is best for both and is selected by the predefined mean of A/B macro RMSEs. "
        "All other settings, features and fitting/validation rows are fixed across candidates.",
        "Held-out test RMSE for Models A/B and the global-mean and calendar/building-use baselines after refitting "
        "on all 80,665 development rows. Values are recomputed from identical held-out observations for each building. "
        "L07 is an unseen location, whereas L14 holdouts are unseen buildings within a represented location. "
        "These previously inspected tests are a validation-guided follow-up, not an untouched final test.",
        "Actual and candidate-2 predicted hourly electricity consumption per gross floor area over the original first "
        "complete seven-day window for each held-out building (168 hourly observations; UTC). All three series in a panel "
        "share identical timestamps. Panels use independent vertical scales; L14_B03 has an explicitly actual-only inset "
        "to reveal demand variation obscured by its much larger prediction errors. Negative forecasts are retained without "
        "clipping. Windows are fixed from the original experiment and were not selected for prediction quality.",
        "Weather-related change in test RMSE, ΔRMSE = RMSE(A) − RMSE(B), using exactly the building-level values "
        "in Figure 4. Positive values indicate lower error with weather; negative values indicate deterioration. "
        "Both models use the same validation-selected settings and test observations. Differences are conditional "
        "predictive evidence under the exact-t weather assumption and do not establish a causal weather effect.",
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, default=BASE / "charts")
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser().resolve()
    protected = [BASE / name for name in ("experiments", "results", "models", "Input Data", "Target Set")]
    protected += [BASE.parent / "Data", BASE.parent / "Data_cleaning"]
    require(not any(output == p.resolve() or p.resolve() in output.parents for p in protected),
            "Choose a figure folder outside datasets and preserved experiment/model/result directories")
    names = [f"{stem}.{ext}" for stem in STEMS for ext in ("png", "svg")] + list(EXTRAS)
    conflicts = [name for name in names if (output / name).exists()]
    require(not conflicts, f"Refusing to overwrite existing figure artifacts: {conflicts}. Use --output-dir with a fresh folder.")
    preserved = existing_files()
    sources = [RUN / name for name in ("run_manifest.json", "selected_settings.json", "candidate_plan.json",
               "selection_scores.csv", "split_boundaries.csv", "validation/all_candidate_metrics.csv",
               "final/results/test_predictions.csv", "final/results/metrics.csv")]
    sources += [RUN / "validation" / f"candidate_{i}" / "results/validation_predictions.csv" for i in (1, 2, 3)]
    sources += [BASE / "results/chart_periods.csv", Path(__file__).resolve()]
    source_hashes = {str(p.resolve()): sha256(p) for p in sources}
    manifest, selected, timeline, validation, test, windows, weeks, effects = load_plot_data()
    output.mkdir(parents=True, exist_ok=True)
    style()
    for function, arguments in ((workflow, ()), (data_split, (timeline,)),
                                 (validation_comparison, (validation, selected)), (test_comparison, (test,)),
                                 (actual_vs_predicted, (weeks, windows)), (weather_contribution, (effects,))):
        function(*arguments, output)
        print(f"Created {function.__name__}: PNG (320 DPI) + SVG", flush=True)
    for number, frame in ((2, timeline), (3, validation), (4, test), (5, weeks), (6, effects)):
        frame.to_csv(output / f"figure_{number}_plot_data.csv", index=False, mode="x")
    command = "PYTHONDONTWRITEBYTECODE=1 " + shlex.join([sys.executable, "-B", str(Path(__file__).resolve()), "--output-dir", str(output)])
    caption_text = ["# Academic report figure captions\n", f"Source experiment: `{RUN.relative_to(BASE.parent)}`. "
                    f"Selected setting: `{selected['candidate']}`. No fitting, target shifting, clipping or source changes.\n"]
    for number, (stem, caption) in enumerate(zip(STEMS, captions(selected)), 1):
        caption_text += [f"## Figure {number}\n", f"![Figure {number}]({stem}.png)\n", caption + "\n",
                         f"Files: `{stem}.png` (320 DPI); `{stem}.svg` (editable vector text).\n"]
    caption_text += ["## Reproduction\n", "Requires numpy, pandas and matplotlib (exact versions in figure_manifest.json).\n",
                     "```bash\n\"Prediction Model/.venv/bin/python\" -m pip install numpy pandas matplotlib\n" + command + "\n```\n",
                     "Existing filenames are protected. After this generation, use `--output-dir` with a fresh folder to render again. "
                     "The original six chart images in the main charts folder were removed by the user before this task; "
                     "this report set replaces that folder's contents. Existing experiment-specific charts remain unchanged.\n"]
    with (output / "captions.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(caption_text))
    for name, expected in preserved.items():
        require(Path(name).is_file() and sha256(name) == expected, f"Pre-existing file changed: {name}")
    pngs = []
    for stem in STEMS:
        image = plt.imread(output / f"{stem}.png")
        require(image.shape[0] > 1000 and image.shape[1] > 2000, f"Insufficient pixel dimensions: {stem}")
        pngs.append(dict(file=f"{stem}.png", width_pixels=image.shape[1], height_pixels=image.shape[0], dpi=320))
    record = dict(created_utc=datetime.now(timezone.utc).isoformat(), source_experiment=str(RUN),
                  selected_candidate=selected, command=command, no_retraining=True,
                  colors=COLORS, partition_colors=ROLES,
                  versions=dict(python=platform.python_version(), **{p: importlib.metadata.version(p) for p in ("numpy", "pandas", "matplotlib")}),
                  source_sha256=source_hashes, staged_input_target_hashes=manifest["source_hashes"],
                  original_chart_windows=windows.to_dict("records"), PNGs=pngs,
                  output_sha256={name: sha256(output / name) for name in names if name != "figure_manifest.json"},
                  verification=dict(validation_model_building_rmse_checks=18, validation_macro_rmse_checks=6,
                                    test_building_method_rmse_checks=16, original_weekly_rows=672,
                                    all_input_target_pairs_aligned=True, split_boundaries_verified=True,
                                    same_rows_all_validation_candidates=True, shared_winner_reproduced=True,
                                    original_weekly_windows_verified=True, source_files_unchanged=True,
                                    previous_files_unchanged=len(preserved)),
                  limitations=["Previously inspected tests; validation does not guarantee transfer",
                               "Exact-t historical reanalysis weather availability at prediction time is assumed",
                               "L03 scale unresolved and retained; no rescaling or extra target shift",
                               "Negative predictions retained; Figure 5 has independent y scales and an actual-only L14_B03 inset"])
    with (output / "figure_manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(f"Saved six figures, SVG copies, captions, plot data and provenance to {output}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, AssertionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
