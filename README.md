# FinalReport-MultiDiscEng — hourly building electricity prediction

Our ENGG2112 group project investigates predicting next-hour electricity consumption per gross floor area (kWh/m²) for buildings excluded from model fitting, using the ADRENALIN dataset. Model A uses building metadata and calendar features; Model B adds six weather variables. Both use `HistGradientBoostingRegressor`, with training-only preprocessing and comparisons against global-mean and calendar/building-use baselines. We prepared seven building datasets, investigated L03/weather sensitivities, and selected shared model settings using chronological validation within three development buildings before refitting and evaluating four held-out buildings. Neither model beat the global-mean baseline on the equal-weight test-location average; weather had a building-dependent effect. These results do not establish a causal weather effect, and our workflow is not ready for operational use.

## Repository structure

```text
Data/
  BuildingsByLocation/         Preserved L03/L07/L14 meter, weather, metadata and derived tables
  Explanation.md              Data layout, units, building roles and preparation assumptions
Data_cleaning/                 Preparation scripts, cumulative-channel configuration, reports and tests
Prediction Model/
  Input Data/                 Seven staged model-input CSVs (metadata, weather and mirrored target)
  Target Set/                 Seven matching, row-aligned, single-column target CSVs
  results/                    EARLIER fixed-setting metrics, predictions and provenance
  models/                     EARLIER fixed-setting pipelines and global-mean baseline
  charts/                     Six final-report PNG/SVG figures, captions, plot data and provenance
  experiments/
    validation/               Timestamped chronological-validation and selected-refit results
    timing_L03/               Timestamped exploratory L03/weather sensitivity results
  train_models.py             Original fixed-setting experiment and data checks
  run_validation_experiment.py Shared parameter selection, full-development refit and test evaluation
  run_followup_experiments.py Four fixed-setting sensitivity experiments and both baselines
  generate_report_figures.py  Six report figures drawn from saved validation-selected results
  test_*.py                   Focused sensitivity and validation unit tests
progress_so_far.md            Historical progress, detailed file guide, results and limitations
ADRENALIN_data_description.pdf Local dataset reference
CONTRIBUTIONS.md              Team contribution template requiring team confirmation
```

## Environment setup

The saved validation experiment used **Python 3.11.1**. Its [requirements](<Prediction Model/experiments/validation/run_20261025T091525_455049Z/requirements_versions.txt>) and [version record](<Prediction Model/experiments/validation/run_20261025T091525_455049Z/dependency_versions.json>) specify:

| Package | Saved version |
| --- | --- |
| numpy | 1.26.4 |
| pandas | 1.5.3 |
| scipy | 1.10.0 |
| scikit-learn | 1.9.0 |
| matplotlib | 3.9.4 |
| joblib | 1.5.3 |
| threadpoolctl | 3.6.0 |

From the project root, with Python 3.11 installed (3.11.1 matches the saved interpreter):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r "Prediction Model/experiments/validation/run_20261025T091525_455049Z/requirements_versions.txt"
python -m pip check
```

The new root `.venv/` keeps the existing `Prediction Model/.venv/` separate. The saved requirements pin direct dependencies; transitive dependencies can differ from the original run. The experiment also preserves `environment_freeze.txt`. No environment or dependency record inside a protected folder needs to be edited.

## Pipeline order and verified command reference

The following purposes, inputs, outputs and command-line options were checked by reading the scripts, [the saved validation command](<Prediction Model/experiments/validation/run_20261025T091525_455049Z/command.txt>) and Section 8 of [our progress report](progress_so_far.md). **These are reproduction references, not a batch to execute in the preserved checkout.** No pipeline stage was executed during housekeeping. Preparation writes derived data; training/experiment commands fit models; plotting generates figures. The saved data, experiments, models and charts remain protected. Any later reproduction requires a separately authorised working copy and fresh output destinations.

All commands below assume the activated environment and project-root working directory. “Unified tables” means `Data/BuildingsByLocation/L*/unifieddataconsumption/`.

| Stage | Purpose | Inputs | Outputs / write behaviour |
| --- | --- | --- | --- |
| 1. `filter_csv_files.py` | Select explicitly allowed channels by filename | Listed buildings' `1h/` CSVs | **Deletes unmatched CSVs in those folders**; preserves weather, non-CSV files and unlisted buildings |
| 2. `inspect_energy_readings.py` | Inspect schemas, units, timestamps, gaps and numerical changes | Ten configured channels, including historical L06 entries | Replaces `Data_cleaning/energy_readings_report.txt`; reads source CSVs without changing them |
| 3. `convert_cumulative_to_hourly.py` | Difference explicitly confirmed cumulative channels | Raw counters and `cumulative_channels.json` | Per-channel `processed/*.hourly_energy.csv`, `*.excluded_intervals.csv`, `*.processing_report.txt`; retains counters |
| 4. `build_consumption_tables.py` | Build separate interval tables for seven buildings | Selected L03/L14 raw channels; processed L07 hourly differences | Unified `<building>_consumption.csv`; replaces generated outputs |
| 5. `join_weather_data.py` | Left-join six weather fields by exact UTC interval start | Consumption CSVs and matching location weather | Unified `<building>_consumption_weather.csv`; unmatched weather stays empty |
| 6. `add_building_metadata.py` | Add fourteen metadata fields and electricity per gross m² | Consumption/weather CSVs and matching `*-building_info.txt` | Unified `<building>_model_input.csv` plus `Data_cleaning/building_metadata_report.txt` |
| 7. `export_prediction_targets.py` | Export targets without shifting or changing row order | Unified model-input CSVs | Unified `<building>_targets.csv`; retains input files |
| 8. `train_models.py` | Original fixed-setting A/B/global-mean experiment, or alignment checks only | Staged `Input Data/` and `Target Set/` | `results/`, `models/`, `charts/` under `--output-dir`; defaults would replace earlier outputs |
| 9. `run_validation_experiment.py` | Three predefined candidates, chronological validation, shared selection, full refit and testing | Staged inputs/targets, original manifest and reused feature/baseline definitions | A fresh `experiments/validation/run_*/` with splits, candidates, pipelines, metrics, predictions and charts |
| 10. `run_followup_experiments.py` | Cross L03 inclusion/exclusion with exact-t/one-hour-lagged weather | Staged inputs/targets, full weather series, original results and saved chart windows | A fresh `experiments/timing_L03/run_*/` with four cases and both baselines |
| 11. `generate_report_figures.py` | Draw six academic figures from the saved selected refit | The fixed saved validation run, its predictions/metrics/splits, staged data and original windows | Six PNG/SVG pairs, captions, five plot-data CSVs and a manifest; refuses existing output filenames |

### 1–3: historical selection, inspection and cumulative conversion

```bash
python -B Data_cleaning/filter_csv_files.py --root "Data/BuildingsByLocation"
python -B Data_cleaning/inspect_energy_readings.py --root "Data/BuildingsByLocation"
python -B Data_cleaning/convert_cumulative_to_hourly.py --root "Data/BuildingsByLocation" --config Data_cleaning/cumulative_channels.json
```

The filter's code default is `./datasets`, so the reference command explicitly supplies our data root. It has no dry-run option. It must not be used against preserved data.

The inspector/configuration still reference three L06 channels, but L06 is absent from the current tree. The inspector reports missing channels and returns a nonzero status; the converter reports/skips missing configured channels and may still process available L07 data. Those defaults are therefore **not a clean unattended regeneration path**. Any later working-copy reproduction needs a reviewed configuration; the retained historical configuration has not been changed.

### 4–7: consumption, weather, metadata and target construction

```bash
python -B Data_cleaning/build_consumption_tables.py
python -B Data_cleaning/join_weather_data.py
python -B Data_cleaning/add_building_metadata.py
python -B Data_cleaning/export_prediction_targets.py
```

These scripts write derived tables under `Data/BuildingsByLocation/`. The active modelling copies are instead under `Prediction Model/Input Data/` and `Prediction Model/Target Set/`. **No script automatically stages those upstream outputs into the modelling folders.** Any authorised future refresh must preserve input/target identities, exact row order and timestamp alignment; this housekeeping task did not copy or regenerate datasets. Targets already correspond to their prediction intervals and must not be shifted again.

### 8: original fixed-setting modelling and read-only checks

The original settings use 31 leaf nodes and a minimum of 30 samples per leaf. A separate output destination avoids the historical default folders in a future authorised reproduction:

```bash
python -B "Prediction Model/train_models.py" --train-l14 L14_B04 L14_B05 --output-dir "Prediction Model/reproduction_fixed"
```

Choose a fresh destination; this original runner can replace generated files at an existing destination. To check current staged data without fitting preprocessing, training models or writing outputs, the code provides:

```bash
python -B "Prediction Model/train_models.py" --check-data
```

### 9: chronological validation and shared parameter selection

The saved `command.txt` uses the original machine's absolute interpreter/script paths with `-B --threads 4`. The equivalent repository-relative command is:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B "Prediction Model/run_validation_experiment.py" --threads 4
```

Each of L03_B01/L14_B04/L14_B05 uses its own earliest-80% fitting/latest-20% validation cutoff over unique interval-start timestamps. This assesses future periods of known buildings. The three candidate leaf/minimum-leaf settings are 31/30, 15/60 and 7/120, with all other parameters fixed. One shared configuration minimises the mean of A's and B's equal-weight validation-building RMSEs; ties prefer fewer leaves, then larger minimum leaf size. Candidate 2 (15/60) was selected before test data loading. Both models, preprocessing and both baselines were refitted on all development rows before held-out testing. The runner writes into the protected experiments tree, so it is documented here but was not run during housekeeping.

### 10: earlier exploratory sensitivity experiments

```bash
PYTHONDONTWRITEBYTECODE=1 python -B "Prediction Model/run_followup_experiments.py" --output-root "Prediction Model/experiments/timing_L03" --threads 4
```

This matches the saved sensitivity command's arguments, expressed relative to the project root. It retains the original settings while varying the training pool and weather timing, and creates a fresh timestamped batch. Its test buildings had already been inspected; its results are exploratory. It was not rerun during housekeeping.

### 11: report figures from saved predictions

```bash
PYTHONDONTWRITEBYTECODE=1 python -B "Prediction Model/generate_report_figures.py" --output-dir "Prediction Model/report_figures_rerun"
```

The code's default is `Prediction Model/charts/`, which already contains the report figures and is protected. The command above documents the verified fresh-output option; no figures were generated during housekeeping. The plotting script is tied to the saved validation run named below and keeps the original first complete seven-day window per test building.

## Unit tests and fresh-environment verification

With the environment above active, run all eight existing `test_*.py` files in their two discovery roots:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -W ignore::DeprecationWarning -m unittest discover -s Data_cleaning -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 python -B -W ignore::DeprecationWarning -m unittest discover -s "Prediction Model" -p 'test_*.py'
```

On **28 October 2026 (Australia/Sydney)**, we verified the saved requirements in a newly created, isolated **Python 3.11.1** virtual environment outside the repository, without system-site packages:

| Suite | Passed | Failures | Errors |
| --- | --- | --- | --- |
| Data preparation: six test files | 65 | 0 | 0 |
| Sensitivity and validation: two test files | 18 | 0 | 0 |
| Total | **83** | **0** | **0** |

`python -m pip check` reported **No broken requirements found**. Tests use temporary fixtures; the validation suite includes a small synthetic fit in a temporary directory. These tests do not retrain saved project models, invoke the full experiments or regenerate report figures. `PYTHONDONTWRITEBYTECODE=1` also applies to test subprocesses so repository bytecode files are not written. The warning filter suppresses dependency deprecation noise, not failed assertions. Passing tests do not establish operational forecasting accuracy.

## Where are the final report numbers?

The report's final numerical results come from:

**[`Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/results/metrics.csv`](<Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/results/metrics.csv>)**

The same run contains final aligned predictions in `final/results/test_predictions.csv`, fitted preprocessing/models in `final/models/`, validation scores in `selection_scores.csv`, and settings in `selected_settings.json`. MAE/RMSE use kWh/m²; nRMSE is `100 × RMSE / observed mean`, with explicit handling of invalid/non-positive denominators. Location metrics pool rows within a location; the overall summary averages the L07 and L14 metrics equally and is not a pooled RMSE.

`Prediction Model/results/` and `Prediction Model/models/` hold the **earlier fixed-setting run**, with **31 leaves / minimum leaf size 30**, rather than the validation-selected **15/60** refit. Their numbers therefore differ. For example, L07 Model A RMSE is **0.1071** in the earlier results versus **0.1097 kWh/m²** in the final report. The latest equal-location RMSEs are **0.294841** for the global-mean baseline, **1.495577** for the calendar/building-use baseline, **1.050304** for A and **1.069989** for B. Both models still lose to the global mean overall. No numerical result was changed during housekeeping.

The final report figure files are:

| Report figure | Content | PNG in `Prediction Model/charts/` |
| --- | --- | --- |
| 1 | Experimental workflow | [figure_1_workflow.png](<Prediction Model/charts/figure_1_workflow.png>) |
| 2 | Building-level chronological split | [figure_2_data_split.png](<Prediction Model/charts/figure_2_data_split.png>) |
| 3 | Validation candidate RMSE | [figure_3_validation_rmse.png](<Prediction Model/charts/figure_3_validation_rmse.png>) |
| 4 | Models and baselines: test-building RMSE | [figure_4_test_rmse.png](<Prediction Model/charts/figure_4_test_rmse.png>) |
| 5 | Actual versus predicted: four held-out buildings | [figure_5_actual_vs_predicted.png](<Prediction Model/charts/figure_5_actual_vs_predicted.png>) |
| 6 | Weather contribution: RMSE(A) minus RMSE(B) | [figure_6_weather_contribution.png](<Prediction Model/charts/figure_6_weather_contribution.png>) |

Matching SVGs, [captions](<Prediction Model/charts/captions.md>), plotted-data CSVs and `figure_manifest.json` are in the same folder. Figure 5 retains negative predictions and independent y scales, with an explicitly actual-only L14_B03 inset. These figures represent the validation-selected refit; the charts within older experiment directories represent their own runs.

## Known limitations

- **L03 scale:** its unusually large consumption-per-area scale remains unresolved. Stated kWh values were retained; no authoritative divide-by-1,000 correction was established.
- **Timestamp conventions:** L03/L14 timestamps are treated as interval ends by project assumption; L07 uses processed counter-difference bounds. Calendar features use UTC because no local time-zone mapping is documented.
- **Weather availability:** exact-t historical/reanalysis weather is assumed available at prediction time for `[t, t + 1 hour)`. Publication latency and selected-variable interval semantics remain unverified; lagging one hour does not establish availability.
- **Metadata gaps:** L03 floor counts conflict, L14 floor counts are missing, and L14_B02 lacks an opening year. Training-only imputation does not resolve source uncertainty.
- **Limited coverage and transfer:** only two or three training buildings are represented in the completed configurations. Selected meter channels are not independently confirmed as complete whole-building totals. Large L14_B03 errors remain; validation does not guarantee transfer.
- **Previously inspected tests:** L07 is an unseen location, but L14 tests are unseen buildings at a partly represented location. These tests were inspected before follow-up work; there is no new untouched final set or leave-one-site-out study.
- **Absolute provenance paths:** saved split/alignment records, manifests and commands contain original-machine paths such as `/Users/bakani/...`. They are preserved as-is. Some runners verify those paths/hashes, so a relocated clone may need a separately reviewed reproduction setup; editing protected records is not a portability fix.
- **Legacy L06 and staging configuration:** early selection/inspection/cumulative configuration retains an old L06 setup absent from the current tree. Upstream generators write under `Data/`, while training uses separately staged `Prediction Model/` inputs/targets; synchronisation is not automatic.
- **Operational and causal scope:** future-target/persistence benchmarks, independent operational weather feeds, deployment and causal analysis are not established. Negative predictions remain in the saved results without clipping.

Section 7 of [our progress report](progress_so_far.md) provides the fuller discussion. Its file inventory is a historical snapshot and can include artifacts removed during later housekeeping.

## Data

Our data source is **ADRENALIN**, [Zenodo DOI 10.5281/zenodo.15012288](https://doi.org/10.5281/zenodo.15012288). `Data/BuildingsByLocation/` contains the selected L03/L07/L14 raw meter channels, location weather CSVs, building metadata/topology text, L07 processed counter differences and unified consumption/weather tables. [Data/Explanation.md](Data/Explanation.md) describes file naming, units and roles, while [ADRENALIN_data_description.pdf](ADRENALIN_data_description.pdf) supplies the local dataset reference.

Retained raw meter/weather readings are treated as read-only; conversion, joins and enrichment create separate derived files. The historical channel selector deletes unwanted CSV files and belongs only on an authorised working copy. No raw data, staged datasets, saved runs, models or figures were modified during this housekeeping task.

## Repository housekeeping boundaries

The root ignore file covers `.DS_Store`, virtual environments, Python caches, notebook checkpoints and editor metadata; the existing modelling-folder ignore entries remain intact. The stray root `test` artifact and the three tracked `.DS_Store` files outside protected folders were removed. **Seventeen tracked `.DS_Store` files remain inside protected folders**, because the explicit no-change rule takes precedence over the request to remove every committed `.DS_Store`. Ignore rules do not untrack files that are already committed. No protected path was changed in the cleanup commit.

## Team contributions

[CONTRIBUTIONS.md](CONTRIBUTIONS.md) lists Bakani Maphosa, Yash Makija, Jayden Saldanha and Jeet Prabhakar and leaves responsibility assignments for team completion. Git author identities do not establish offline work or individual responsibility.

## AI tool use

`<TEAM TO COMPLETE: state honestly which AI tools (e.g. Codex) were used, for which tasks, and how outputs were reviewed and verified, per ENGG2112 policy>`
