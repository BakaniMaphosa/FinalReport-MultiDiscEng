# Project progress so far

**Project:** Electricity-consumption prediction using building metadata, calendar features and weather.  
**Report date:** 25 October 2026, Australia/Sydney.  
**Scope:** Current project files, existing preparation scripts and reports, and the completed model/baseline experiments. Results below come from the saved CSVs and run manifest, rather than estimates.

**Contents:** [Work completed](#2-work-completed) · [Dataset and experiment](#3-current-dataset-and-experiment-specification) · [Results](#4-actual-evaluation-results) · [File guide](#5-file-by-file-guide) · [Verification](#6-verification-completed) · [Open issues](#7-open-issues-and-work-not-yet-completed) · [Run commands](#8-execution-and-reproducibility-reference) · [Milestones](#9-milestones-achieved).

## 1. Current position

The project now has a working path from selected electricity channels to building-level hourly tables, aligned weather, building metadata, electricity-per-area targets, and a reproducible first model comparison. Seven buildings provide **199,552 aligned hourly examples**.

Two `HistGradientBoostingRegressor` models have been fitted and tested. Model A uses building metadata and calendar features. Model B uses the same features plus weather. A separate `DummyRegressor(strategy="mean")` provides a simple reference benchmark fitted only on training targets.

**The current models do not beat that simple baseline on the equal-weight average across the test locations.** They beat it on three of the four test buildings, but both transfer very poorly to L14_B03. Adding weather improves L14_B01 and L14_B02 but worsens the overall comparison. A working experiment and an evaluation framework have been achieved; satisfactory generalisation has not yet been demonstrated.

## 2. Work completed

### 2.1 Organised the selected building and meter channels

The data is organised by location and building under `Data/BuildingsByLocation/`. A filename-based channel-selection utility was implemented with an explicit building/meter allowlist. It preserves weather folders, metadata, non-CSV files, unlisted buildings and symbolic links.

`filter_csv_files.py` **deletes unmatched CSV files inside selected buildings' `1h` folders**. It is an earlier selection utility, not a read-only analysis step. No deletion counts can be reconstructed reliably from the present files, and it was not run to prepare this progress report.

The selected electricity sources used by the current seven-building pipeline are:

| Building | Selected channel | Treatment |
| --- | --- | --- |
| L03_B01 | EM02.Pt | Values used directly as hourly energy under the project convention; stated kWh retained; scale concern unresolved. |
| L07_B01 | EM01.Pt | Confirmed cumulative counter, converted to hourly differences before table construction. |
| L14_B01 | EM01.Pt | Values used directly as hourly energy. |
| L14_B02 | EM01.Pt | Values used directly as hourly energy. |
| L14_B03 | EM02.Pt | Values used directly as hourly energy. |
| L14_B04 | EM02.Pt | Values used directly as hourly energy. |
| L14_B05 | EM02.Pt | Values used directly as hourly energy. |

The earlier selection, inspection and cumulative-channel configuration also reference L06_B01. No L06 directory is present in the current data tree, and L06 is not part of the current seven-building experiment. Historical configuration entries should not be read as evidence that L06 was included in training.

### 2.2 Inspected electricity readings before conversion

`inspect_energy_readings.py` provides a read-only inspection of the explicitly selected channels. Its saved report includes source schemas and units, row counts, time coverage, duplicate/invalid timestamps, missing/non-finite values, numerical changes and examples of decreases.

It separates comparisons across arbitrary time gaps from exactly-one-hour comparisons. Invalid rows and duplicate timestamps form barriers, so the inspection does not invent changes across missing information. Numerical suggestions about cumulative versus hourly values are exploratory and do not authorise conversion by themselves. The historical report covers ten selected channels, including L06 entries no longer present in the current tree.

### 2.3 Converted confirmed cumulative readings into hourly energy

`convert_cumulative_to_hourly.py` uses explicit confirmations in `cumulative_channels.json`. It computes the difference between adjacent original readings and retains eligible one-hour intervals. It records exclusions separately, preserves original counter files and does not automatically difference L14 data.

The conservative rules exclude intervals with negative changes and protect the immediately following original interval. They also handle gaps, duplicate or invalid timestamps, and missing readings without bridging them. Positive changes and true zeros are not automatically trimmed or replaced.

The saved **L07_B01** conversion is complete:

- Original counter readings: **9,545**.
- Adjacent intervals: **9,544**; the first counter reading supplies the initial reference, not an extra interval target.
- Accepted hourly intervals: **9,543**.
- Excluded intervals: **1**, because the interval lasted two hours rather than one.
- The excluded interval was **2021-12-01 20:00–22:00 UTC**. Its total change was recorded, but was not divided across two hours or interpolated.

The converter contains reset/decrease rules, but the current L07 processing report records only that gap-based exclusion. Its general limitations should not be mistaken for evidence that resets were observed in this particular run.

### 2.4 Built seven separate electricity-consumption tables

`build_consumption_tables.py` creates `<building_id>_consumption.csv` with `building_id`, `interval_start_utc`, `interval_end_utc` and `electricity_kwh`.

For L03 and L14, the project convention interprets each source timestamp as the interval end and subtracts one hour to obtain its start. This is an explicitly recorded project assumption. Their source energy values are used directly, without differencing or unit rescaling. The L03 magnitude/unit-scale concern remains open.

For L07, the builder reads only the processed hourly-energy file, preserves its interval bounds and renames `energy_kwh` to `electricity_kwh`. It does not fall back to the cumulative counter.

This construction stage sorts source rows chronologically in memory. Later enrichment and target extraction preserve the resulting order. Gaps, duplicate rows and missing values are not silently removed by the table builder.

### 2.5 Joined location weather to the electricity intervals

`join_weather_data.py` left-joins each location's weather onto each building's consumption table using **exact `interval_start_utc` equality**. It verifies weather units and timestamp uniqueness, retains unmatched electricity rows and leaves unmatched weather empty. Electricity and existing timestamp values are not shifted by this join.

| Weather source suffix | Model-input column | Unit |
| --- | --- | --- |
| T | temperature_c | °C |
| Rh | relative_humidity_pct | % |
| Ws | wind_speed_kmh | km/h |
| Wd | wind_direction_deg | degrees |
| Rd | direct_solar_radiation_wm2 | W/m² |
| Rr | diffuse_solar_radiation_wm2 | W/m² |

The saved tables retain two rows without weather at the beginning of each L14 building's series: ten rows across five buildings. These rows remain in the model data; missing weather is handled by training-fitted preprocessing.

**Weather availability assumption:** historical/reanalysis weather labelled at the prediction interval start is treated as available then. Its real publication latency and aggregation timing have not been established. The evaluation is conditional on this assumption, and does not yet demonstrate an operational future-weather forecasting system.

### 2.6 Added building metadata conservatively

`add_building_metadata.py` was implemented after inspecting the actual `*-building_info.txt` files. It appends fourteen metadata columns to every hourly row for each building:

`floor_area_m2`, `heated_area_m2`, `building_use`, `climate_zone`, `year_opened`, `number_of_floors`, `ventilation_system_count`, `ventilation_used_for_heating`, `ventilation_used_for_cooling`, `has_direct_electric_heating`, `has_district_heating`, `has_district_cooling`, `has_heat_pump`, `has_solar_pv`.

Gross total floor area and gross total heated area are used. Categorical text remains readable, with conservative whitespace/label normalisation. Explicit YES/NO becomes 1/0; missing or ambiguous fields remain empty. Original CSV values are copied as text so enrichment does not introduce rounding or alter timestamp spelling.

The parser handles equipment qualifiers such as electric boilers and ground-source heat pumps, opening-year renovation notes, and inconsistent section labels. Heating/cooling flags are extracted from that section, so a tap-water heat pump or district-heating entry cannot overwrite a space-heating/cooling flag.

L03_B01 lists both four floors and one floor. Its `number_of_floors` is therefore left empty and the conflict is reported. All L14 floor counts are explicitly missing. L14_B02 also has no opening year. Positive supplied floor areas, building identities, matching metadata sources, row counts, row order and original values are verified. Reruns use exact source filenames and do not rediscover enriched outputs as inputs.

### 2.7 Derived the electricity-per-floor-area target

The enrichment script was extended to add:

```text
electricity_kwh_per_m2 = electricity_kwh / floor_area_m2
```

Here `m2` means square metres (m²). The target is the electricity used during one hourly interval divided by gross floor area; it is not an annual energy-intensity total. For example, L07_B01's `66.19921875 kWh / 450 m² = 0.147109375 kWh/m²` for that hour. Values below one are mathematically expected.

The calculation uses decimal arithmetic with 28 significant digits. Missing/non-numeric/non-finite electricity or missing area produces an empty derived cell. Zero and negative numeric readings are not silently replaced. All seven enriched tables now have **25 columns**: ten original columns, fourteen metadata columns and the derived target.

### 2.8 Exported aligned single-column target files and staged the modelling data

`export_prediction_targets.py` copies only `electricity_kwh_per_m2` into `<building_id>_targets.csv`. It preserves exact value text, empty target rows and original row order, and verifies the export against its source before replacing generated targets. It does not remove the target column from the enriched input tables, shift values, select a horizon, split rows or train a model.

The active modelling inputs and targets are currently stored in `Prediction Model/Input Data/` and `Prediction Model/Target Set/`. There are seven corresponding files in each directory. Targets already correspond to their own prediction intervals.

**Path distinction:** upstream enrichment and export scripts still generate their outputs beside the unified tables under `Data/BuildingsByLocation/`. The current staged copies live under `Prediction Model/`. Regenerating upstream data does not automatically refresh those staged copies. The saved metadata report retains its original upstream output paths. IDE tabs for older paths, including `Prediction Model/INPUT DATA/x.txt`, do not establish that those files exist in the current tree.

### 2.9 Implemented and ran the two-model experiment

One readable implementation file, `Prediction Model/train_models.py`, handles identity-based pairing, alignment checks, feature creation, training, evaluation, persistence and chart generation. It checks row counts and verifies any available target IDs/timestamps. For the current target-only files, the upstream exporter's sequential behaviour was reviewed and target values are also checked against the mirrored input target column row by row. A mismatch fails clearly before fitting.

Predictive inputs use an explicit allowlist. Current `electricity_kwh`, `electricity_kwh_per_m2`, other target-derived columns, building/location IDs and raw timestamp columns are excluded. IDs are used for splitting and tracking. Calendar features are derived from interval start. No target shifting is performed.

### 2.10 Added a separate simple reference baseline and compared against it

Model A provides the weather-ablation comparison for Model B. A separate `DummyRegressor(strategy="mean")` was then added to establish whether the trained models beat a simple prediction rule. It always predicts the mean of all eligible training targets, with equal weight per training row. No held-out targets or held-out building adjustments are used to fit it.

The baseline, A and B use the same test rows. Metrics, percentage error reductions, prediction CSVs and all six charts were updated to include the reference. A saved baseline estimator is available alongside the two trained model pipelines. Model A/B settings and predictions were verified to remain unchanged when the baseline was added.

## 3. Current dataset and experiment specification

### 3.1 Final building split and coverage

The final requested split trains on L03_B01 plus L14_B04 and L14_B05. L07_B01 and all three other L14 buildings are held out. L07 is an unseen location. The L14 holdouts are unseen buildings within a location represented in training. L03 is training data and is not reported as an unseen test location.

| Building | Split | Hourly rows | First interval start (UTC) | Last interval start (UTC) | Gross floor area (m²) |
| --- | --- | --- | --- | --- | --- |
| L03_B01 | train | 8,736 | 2022-01-01 11:00:00 | 2022-12-31 10:00:00 | 1013 |
| L07_B01 | test | 9,543 | 2021-11-29 06:00:00 | 2022-12-31 22:00:00 | 450 |
| L14_B01 | test | 36,360 | 2017-12-31 22:00:00 | 2022-03-09 21:00:00 | 6084 |
| L14_B02 | test | 36,336 | 2017-12-31 22:00:00 | 2022-02-22 21:00:00 | 2700 |
| L14_B03 | test | 36,648 | 2017-12-31 22:00:00 | 2022-03-10 21:00:00 | 6574 |
| L14_B04 | train | 36,889 | 2017-12-31 22:00:00 | 2022-03-17 22:00:00 | 11502 |
| L14_B05 | train | 35,040 | 2017-12-31 22:00:00 | 2021-12-31 21:00:00 | 988 |

**Training rows:** 80,665. **Test rows:** 118,887. **Total:** 199,552. No buildings are excluded. All current targets are finite, so no rows were dropped for missing targets. Missing weather does not change the rows used by either model.

| Building | Building use | Climate zone | Opening year | Floors |
| --- | --- | --- | --- | --- |
| L03_B01 | INSTITUTIONAL (EDUCATION) | Cfb | 2013 | Ambiguous: 4 vs 1 |
| L07_B01 | COMMERCIAL (GROCERY STORE) | Cfb | 1999 | 1 |
| L14_B01 | INSTITUTIONAL (EDUCATION) | Cfb | 1914 | Missing |
| L14_B02 | SERVICE (NURSING HOME) | Dfb | Missing | Missing |
| L14_B03 | INSTITUTIONAL (EDUCATION) | Cfb | 2010 | Missing |
| L14_B04 | PUBLIC BUILDING (OFFICE) | Dfb | 1871 | Missing |
| L14_B05 | PUBLIC BUILDING (KINDERGARTEN) | Dfb | 1990 | Missing |

For each building, its stated gross heated area equals its stated gross floor area. Those values are repeated per hourly row rather than aggregated across buildings. The full extracted equipment flags and source files are recorded in `Data_cleaning/building_metadata_report.txt` and the model-input tables.

### 3.2 Exact predictor sets and preprocessing

**Model A: 22 input predictors**

```text
floor_area_m2
heated_area_m2
year_opened
number_of_floors
ventilation_system_count
ventilation_used_for_heating
ventilation_used_for_cooling
has_direct_electric_heating
has_district_heating
has_district_cooling
has_heat_pump
has_solar_pv
hour_sin
hour_cos
weekday_sin
weekday_cos
annual_sin
annual_cos
is_weekend
calendar_year
building_use
climate_zone
```

**Model B: the same 22 predictors plus these six weather predictors, for 28 total**

```text
temperature_c
relative_humidity_pct
wind_speed_kmh
wind_direction_deg
direct_solar_radiation_wm2
diffuse_solar_radiation_wm2
```

Calendar features use **UTC**, because no documented local time-zone mapping was found in the project. Hour, weekday and annual phase are encoded as sine/cosine pairs; annual phase accounts for leap years. Weekend status and calendar year are also included. No holiday calendar or local daylight-saving adjustment has been fitted.

Categorical preprocessing uses constant missing-category imputation and `OneHotEncoder(handle_unknown="ignore", sparse_output=False)`. It is fitted on training rows only. Categories are never supplied as arbitrary ordered numerical codes. The held-out building-use categories `COMMERCIAL (GROCERY STORE)` and `SERVICE (NURSING HOME)` are handled without fitting new categories on the tests; unknown categories produce all-zero indicators for that categorical feature.

Numerical preprocessing uses training-fitted median imputation with missingness indicators. An entirely missing training feature uses a fixed zero plus a missingness indicator inside the model pipeline; the source dataset is unchanged. This accommodates the entirely missing training `number_of_floors` column and avoids an all-NaN binning failure encountered during synthetic verification with the installed scikit-learn version. No feature scaling is applied.

The resulting encoded feature counts are **26 for A** and **38 for B**. All raw and encoded feature names are saved in `results/predictors.csv`, `results/run_manifest.json` and `models/feature_schema.json`. The baseline has no predictive features.

### 3.3 Fixed settings and fitting policy

```json
{
  "loss": "squared_error",
  "learning_rate": 0.08,
  "max_iter": 200,
  "max_leaf_nodes": 31,
  "min_samples_leaf": 30,
  "l2_regularization": 1.0,
  "max_bins": 255,
  "categorical_features": null,
  "early_stopping": false,
  "random_state": 42
}
```

Both models use the same settings and seed. Settings were fixed before held-out evaluation. No parameter search, feature selection or model selection was performed using test data. No validation split was needed for this fixed experiment, and automatic early stopping was disabled to avoid a random internal split. Final models were fitted directly on all 80,665 training rows. A common chronological training-only validation cutoff remains a requirement if later work introduces tuning; such validation has not been run here.

### 3.4 Reference baseline and evaluation definitions

The reference constant is **0.353135360800 kWh/m²**, fitted from the 80,665 eligible training targets. It uses a row-weighted global training mean, not a mean calculated separately from the held-out buildings.

MAE is mean absolute prediction error. RMSE is the square root of mean squared prediction error. Both are reported in kWh/m² for the hourly target. Results are calculated per test building, pooled within each test location, and as an equal-weight average of the L07 and L14 location metrics. The average of the two location RMSEs is reported explicitly; it is not a pooled all-test-row RMSE.

```text
Weather error reduction (%) = 100 × (error_A − error_B) / error_A
Baseline error reduction (%) = 100 × (error_baseline − error_model) / error_baseline
```

Positive reduction means improvement; negative reduction means deterioration. A zero reference error produces an empty percentage and an explanatory note, avoiding division by zero.

## 4. Actual evaluation results

### 4.1 MAE and RMSE against the simple baseline

All values below are kWh/m². Lower is better. The L07 location has one building, so its location and building results coincide.

| Test group | Baseline MAE | A MAE | B MAE | Baseline RMSE | A RMSE | B RMSE |
| --- | --- | --- | --- | --- | --- | --- |
| L07 (location) | 0.244410 | 0.099096 | 0.110743 | 0.246401 | 0.107146 | 0.131937 |
| L14 (location) | 0.343199 | 1.098359 | 1.099939 | 0.343281 | 2.001080 | 2.035559 |
| L07_B01 (building) | 0.244410 | 0.099096 | 0.110743 | 0.246401 | 0.107146 | 0.131937 |
| L14_B01 (building) | 0.343425 | 0.040771 | 0.014737 | 0.343511 | 0.059323 | 0.021664 |
| L14_B02 (building) | 0.338407 | 0.044909 | 0.015344 | 0.338482 | 0.063958 | 0.022243 |
| L14_B03 (building) | 0.347726 | 3.192118 | 3.251975 | 0.347750 | 3.455410 | 3.515921 |
| L07_and_L14 (equal weight locations) | 0.293805 | 0.598728 | 0.605341 | 0.294841 | 1.054113 | 1.083748 |

Both A and B beat the training-mean baseline on L07_B01, L14_B01 and L14_B02. Both are substantially worse than the baseline on L14_B03. Its large error dominates the pooled L14 results and leads both models to underperform the simple baseline on the equal-weight location average.

The equal-weight average MAE is **0.293805** for the baseline, **0.598728** for A and **0.605341** for B. Equal-weight RMSE is **0.294841**, **1.054113** and **1.083748**, respectively.

### 4.2 Percentage comparisons

Weather contribution: Model B compared with Model A. Positive percentages improve on A.

| Group | MAE reduction (%) | RMSE reduction (%) |
| --- | --- | --- |
| L07 (location) | -11.75 | -23.14 |
| L14 (location) | -0.14 | -1.72 |
| L07_B01 (building) | -11.75 | -23.14 |
| L14_B01 (building) | 63.85 | 63.48 |
| L14_B02 (building) | 65.83 | 65.22 |
| L14_B03 (building) | -1.88 | -1.75 |
| L07_and_L14 (equal weight locations) | -1.10 | -2.81 |

Adding weather increases equal-weight MAE by **1.10%** and RMSE by **2.81%** in this experiment, while reducing errors by roughly 64–66% for L14_B01 and L14_B02. The overall evidence therefore does not support claiming that weather improved this model's transfer performance.

Both models compared with the simple training-mean baseline. Positive percentages beat the baseline; negative percentages are worse.

| Group | A MAE reduction (%) | B MAE reduction (%) | A RMSE reduction (%) | B RMSE reduction (%) |
| --- | --- | --- | --- | --- |
| L07 (location) | 59.45 | 54.69 | 56.52 | 46.45 |
| L14 (location) | -220.04 | -220.50 | -482.93 | -492.97 |
| L07_B01 (building) | 59.45 | 54.69 | 56.52 | 46.45 |
| L14_B01 (building) | 88.13 | 95.71 | 82.73 | 93.69 |
| L14_B02 (building) | 86.73 | 95.47 | 81.10 | 93.43 |
| L14_B03 (building) | -818.00 | -835.21 | -893.65 | -911.05 |
| L07_and_L14 (equal weight locations) | -103.78 | -106.04 | -257.52 | -267.57 |

These are predictive comparisons under the stated split, source-unit conventions and weather-availability assumption. They do not establish that weather causes a change in consumption. The source of the poor L14_B03 transfer has not been established by this experiment.

### 4.3 Charts and fixed time-series periods

Two location-level bar charts compare the baseline, A and B for MAE and RMSE. Four time-series charts show actual consumption and all three predictions for the same seven-day period within each test building. Each period is the **first 168 consecutive hourly rows** available; periods are selected from time coverage, not from prediction quality. The baseline is shown as a dashed constant line.

| Building | Period start (UTC) | Period end, exclusive (UTC) | Hourly rows |
| --- | --- | --- | --- |
| L07_B01 | 2021-12-01T22:00:00+00:00 | 2021-12-08T22:00:00+00:00 | 168 |
| L14_B01 | 2017-12-31T22:00:00+00:00 | 2018-01-07T22:00:00+00:00 | 168 |
| L14_B02 | 2017-12-31T22:00:00+00:00 | 2018-01-07T22:00:00+00:00 | 168 |
| L14_B03 | 2017-12-31T22:00:00+00:00 | 2018-01-07T22:00:00+00:00 | 168 |

View the saved comparison figures:

![MAE comparison by test location](<Prediction Model/charts/mae_by_test_location.png>)

![RMSE comparison by test location](<Prediction Model/charts/rmse_by_test_location.png>)

The individual building plots are listed in the file guide below. Figures use UTC on the time axis and kWh/m² on the consumption/error axes.

## 5. File-by-file guide

This guide covers every current substantive project file individually, plus this report. It excludes `.git` internals, installed dependency files inside `.venv`, Python bytecode caches and macOS `.DS_Store` files. Those are described as folder/system roles below. CSV row counts exclude headers; a dash means that a row count is not applicable.

### 5.1 Project-root files

5 files.

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `.gitignore` | Currently empty root-level Git-ignore placeholder; the modelling folder has its own active ignore rules. | — |
| `ADRENALIN_data_description.pdf` | Supplied ADRENALIN dataset description/reference PDF. No claim is made here that it resolves the open unit-scale or timestamp assumptions. | — |
| `README.md` | Brief existing repository introduction for the multidisciplinary final-report software project. | — |
| `progress_so_far.md` | This project-wide progress report, file guide, evaluation summary and achieved-milestone record. | — |
| `test` | Two-line workspace/editor visibility smoke-test artifact. It is unrelated to model fitting and is not a unit-test suite. | — |

### 5.2 Data-preparation scripts, tests, configuration and reports

16 files.

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `Data_cleaning/add_building_metadata.py` | Parses matching building-info text, appends fourteen metadata fields and electricity_kwh_per_m2, verifies original-cell preservation and writes metadata provenance. | — |
| `Data_cleaning/build_consumption_tables.py` | Builds seven separate consumption tables from explicit raw/processed sources with documented interval conventions. | — |
| `Data_cleaning/building_metadata_report.txt` | Extracted values and source TXT paths for all seven buildings, missing/ambiguous fields and verification notes; output paths refer to the upstream generation location. | — |
| `Data_cleaning/convert_cumulative_to_hourly.py` | Converts explicitly confirmed cumulative channels to one-hour differences; records excluded intervals and processing limitations without altering counters. | — |
| `Data_cleaning/cumulative_channels.json` | Explicit confirmation/configuration for L07 EM01.Pt and three historical L06 channels. L03 and L14 are not configured for differencing. | — |
| `Data_cleaning/energy_readings_report.txt` | Saved historical inspection of ten channels, including units, gaps, changes and numerical interpretation suggestions; references L06 data absent from the current tree. | — |
| `Data_cleaning/export_prediction_targets.py` | Exports exact, single-column electricity_kwh_per_m2 targets in input row order and verifies alignment. | — |
| `Data_cleaning/filter_csv_files.py` | Filename-only electricity-channel selection. Deletes unmatched CSVs only within selected 1h folders; preserves weather, metadata and excluded paths. | — |
| `Data_cleaning/inspect_energy_readings.py` | Read-only numerical/schema/timestamp inspection of selected energy channels; writes the inspection report without converting readings. | — |
| `Data_cleaning/join_weather_data.py` | Exact-UTC-start left join of six weather measurements onto each building table; validates units and weather timestamp uniqueness. | — |
| `Data_cleaning/test_add_building_metadata.py` | Twelve temporary-fixture tests for metadata conflicts, equipment scope, identity, units/areas, per-area arithmetic, source preservation and reruns. | — |
| `Data_cleaning/test_build_consumption_tables.py` | Ten temporary-fixture tests for explicit sources, interval construction, exact values, missingness, ordering, reruns and path protection. | — |
| `Data_cleaning/test_convert_cumulative_to_hourly.py` | Fourteen temporary-fixture tests for conversion, resets/decreases, following-interval protection, gaps, invalid values, confirmation and preserved sources. | — |
| `Data_cleaning/test_filter_csv_files.py` | Six temporary-fixture tests covering channel matching, deletion boundaries, weather/link preservation, defaults and errors. | — |
| `Data_cleaning/test_inspect_energy_readings.py` | Eleven temporary-fixture tests for read-only inspection, missing/invalid barriers, duplicates, semantics, discovery and CLI behaviour. | — |
| `Data_cleaning/test_join_weather_data.py` | Twelve temporary-fixture tests for exact UTC weather matching, units, duplicates, missing weather, row preservation and reruns. | — |

### 5.3 Original data, building documentation and unified tables

57 files.

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `Data/BuildingsByLocation/L03/L03_B01/1h/adrenalin.1h.L03.B01.EM02.Pt.csv` | Original selected L03_B01 EM02.Pt meter readings. Used directly by the table builder under the recorded hourly/end-timestamp conventions. | 8,736 |
| `Data/BuildingsByLocation/L03/L03_B01/L03_B01-building_info.txt` | Source building metadata for L03_B01: use, climate zone, gross areas, opening year, floors, ventilation and heating/cooling/PV information. | — |
| `Data/BuildingsByLocation/L03/L03_B01/L03_B01-topology.txt` | Meter/submeter and equipment topology for L03_B01; helps interpret the selected channel and temperature-dependent-load annotations. | — |
| `Data/BuildingsByLocation/L03/L03_WS/adrenalin.1h.L03.WS01.Rd.csv` | Original L03 weather-station direct solar radiation series, joined to buildings in that location by exact UTC interval start. | 55,488 |
| `Data/BuildingsByLocation/L03/L03_WS/adrenalin.1h.L03.WS01.Rh.csv` | Original L03 weather-station relative humidity series, joined to buildings in that location by exact UTC interval start. | 55,488 |
| `Data/BuildingsByLocation/L03/L03_WS/adrenalin.1h.L03.WS01.Rr.csv` | Original L03 weather-station diffuse solar radiation series, joined to buildings in that location by exact UTC interval start. | 55,488 |
| `Data/BuildingsByLocation/L03/L03_WS/adrenalin.1h.L03.WS01.T.csv` | Original L03 weather-station air temperature series, joined to buildings in that location by exact UTC interval start. | 55,488 |
| `Data/BuildingsByLocation/L03/L03_WS/adrenalin.1h.L03.WS01.Wd.csv` | Original L03 weather-station wind direction series, joined to buildings in that location by exact UTC interval start. | 55,488 |
| `Data/BuildingsByLocation/L03/L03_WS/adrenalin.1h.L03.WS01.Ws.csv` | Original L03 weather-station wind speed series, joined to buildings in that location by exact UTC interval start. | 55,488 |
| `Data/BuildingsByLocation/L03/unifieddataconsumption/L03_B01_consumption.csv` | Four-column unified electricity table for L03_B01: building ID, interval start/end and electricity_kwh. | 8,736 |
| `Data/BuildingsByLocation/L03/unifieddataconsumption/L03_B01_consumption_weather.csv` | Ten-column L03_B01 consumption table with six exact-start weather measurements; source for metadata enrichment. | 8,736 |
| `Data/BuildingsByLocation/L07/L07_B01/1h/adrenalin.1h.L07.B01.EM01.Pt.csv` | Original selected L07_B01 EM01.Pt meter readings. Confirmed cumulative counter; never fed directly to the model as hourly consumption. | 9,545 |
| `Data/BuildingsByLocation/L07/L07_B01/L07_B01-building_info.txt` | Source building metadata for L07_B01: use, climate zone, gross areas, opening year, floors, ventilation and heating/cooling/PV information. | — |
| `Data/BuildingsByLocation/L07/L07_B01/L07_B01-topology.txt` | Meter/submeter and equipment topology for L07_B01; helps interpret the selected channel and temperature-dependent-load annotations. | — |
| `Data/BuildingsByLocation/L07/L07_B01/processed/adrenalin.1h.L07.B01.EM01.Pt.excluded_intervals.csv` | Excluded L07_B01 counter intervals with original readings, difference, exclusion reason and source row numbers; currently one two-hour gap. | 1 |
| `Data/BuildingsByLocation/L07/L07_B01/processed/adrenalin.1h.L07.B01.EM01.Pt.hourly_energy.csv` | Accepted L07_B01 EM01.Pt one-hour counter differences: interval_start_utc, interval_end_utc and energy_kwh; source for the L07 consumption table. | 9,543 |
| `Data/BuildingsByLocation/L07/L07_B01/processed/adrenalin.1h.L07.B01.EM01.Pt.processing_report.txt` | Saved L07_B01 conversion provenance, COMPLETE status, 9,545 readings, 9,543 accepted intervals, one exclusion and limitations. | — |
| `Data/BuildingsByLocation/L07/L07_WS/adrenalin.1h.L07.WS01.Rd.csv` | Original L07 weather-station direct solar radiation series, joined to buildings in that location by exact UTC interval start. | 73,752 |
| `Data/BuildingsByLocation/L07/L07_WS/adrenalin.1h.L07.WS01.Rh.csv` | Original L07 weather-station relative humidity series, joined to buildings in that location by exact UTC interval start. | 73,752 |
| `Data/BuildingsByLocation/L07/L07_WS/adrenalin.1h.L07.WS01.Rr.csv` | Original L07 weather-station diffuse solar radiation series, joined to buildings in that location by exact UTC interval start. | 73,752 |
| `Data/BuildingsByLocation/L07/L07_WS/adrenalin.1h.L07.WS01.T.csv` | Original L07 weather-station air temperature series, joined to buildings in that location by exact UTC interval start. | 73,752 |
| `Data/BuildingsByLocation/L07/L07_WS/adrenalin.1h.L07.WS01.Wd.csv` | Original L07 weather-station wind direction series, joined to buildings in that location by exact UTC interval start. | 73,752 |
| `Data/BuildingsByLocation/L07/L07_WS/adrenalin.1h.L07.WS01.Ws.csv` | Original L07 weather-station wind speed series, joined to buildings in that location by exact UTC interval start. | 73,752 |
| `Data/BuildingsByLocation/L07/unifieddataconsumption/L07_B01_consumption.csv` | Four-column unified electricity table for L07_B01: building ID, interval start/end and electricity_kwh. | 9,543 |
| `Data/BuildingsByLocation/L07/unifieddataconsumption/L07_B01_consumption_weather.csv` | Ten-column L07_B01 consumption table with six exact-start weather measurements; source for metadata enrichment. | 9,543 |
| `Data/BuildingsByLocation/L14/L14_B01/1h/adrenalin.1h.L14.B01.EM01.Pt.csv` | Original selected L14_B01 EM01.Pt meter readings. Used directly by the table builder under the recorded hourly/end-timestamp conventions. | 36,360 |
| `Data/BuildingsByLocation/L14/L14_B01/L14_B01-building_info.txt` | Source building metadata for L14_B01: use, climate zone, gross areas, opening year, floors, ventilation and heating/cooling/PV information. | — |
| `Data/BuildingsByLocation/L14/L14_B01/L14_B01-topology.txt` | Meter/submeter and equipment topology for L14_B01; helps interpret the selected channel and temperature-dependent-load annotations. | — |
| `Data/BuildingsByLocation/L14/L14_B02/1h/adrenalin.1h.L14.B02.EM01.Pt.csv` | Original selected L14_B02 EM01.Pt meter readings. Used directly by the table builder under the recorded hourly/end-timestamp conventions. | 36,336 |
| `Data/BuildingsByLocation/L14/L14_B02/L14_B02-building_info.txt` | Source building metadata for L14_B02: use, climate zone, gross areas, opening year, floors, ventilation and heating/cooling/PV information. | — |
| `Data/BuildingsByLocation/L14/L14_B02/L14_B02-topology.txt` | Meter/submeter and equipment topology for L14_B02; helps interpret the selected channel and temperature-dependent-load annotations. | — |
| `Data/BuildingsByLocation/L14/L14_B03/1h/adrenalin.1h.L14.B03.EM02.Pt.csv` | Original selected L14_B03 EM02.Pt meter readings. Used directly by the table builder under the recorded hourly/end-timestamp conventions. | 36,648 |
| `Data/BuildingsByLocation/L14/L14_B03/L14_B03-building_info.txt` | Source building metadata for L14_B03: use, climate zone, gross areas, opening year, floors, ventilation and heating/cooling/PV information. | — |
| `Data/BuildingsByLocation/L14/L14_B03/L14_B03-topology.txt` | Meter/submeter and equipment topology for L14_B03; helps interpret the selected channel and temperature-dependent-load annotations. | — |
| `Data/BuildingsByLocation/L14/L14_B04/1h/adrenalin.1h.L14.B04.EM02.Pt.csv` | Original selected L14_B04 EM02.Pt meter readings. Used directly by the table builder under the recorded hourly/end-timestamp conventions. | 36,889 |
| `Data/BuildingsByLocation/L14/L14_B04/L14_B04-building_info.txt` | Source building metadata for L14_B04: use, climate zone, gross areas, opening year, floors, ventilation and heating/cooling/PV information. | — |
| `Data/BuildingsByLocation/L14/L14_B04/L14_B04-topology.txt` | Meter/submeter and equipment topology for L14_B04; helps interpret the selected channel and temperature-dependent-load annotations. | — |
| `Data/BuildingsByLocation/L14/L14_B05/1h/adrenalin.1h.L14.B05.EM02.Pt.csv` | Original selected L14_B05 EM02.Pt meter readings. Used directly by the table builder under the recorded hourly/end-timestamp conventions. | 35,040 |
| `Data/BuildingsByLocation/L14/L14_B05/L14_B05-building_info.txt` | Source building metadata for L14_B05: use, climate zone, gross areas, opening year, floors, ventilation and heating/cooling/PV information. | — |
| `Data/BuildingsByLocation/L14/L14_B05/L14_B05-topology.txt` | Meter/submeter and equipment topology for L14_B05; helps interpret the selected channel and temperature-dependent-load annotations. | — |
| `Data/BuildingsByLocation/L14/L14_WS/adrenalin.1h.L14.WS01.Rd.csv` | Original L14 weather-station direct solar radiation series, joined to buildings in that location by exact UTC interval start. | 43,824 |
| `Data/BuildingsByLocation/L14/L14_WS/adrenalin.1h.L14.WS01.Rh.csv` | Original L14 weather-station relative humidity series, joined to buildings in that location by exact UTC interval start. | 43,824 |
| `Data/BuildingsByLocation/L14/L14_WS/adrenalin.1h.L14.WS01.Rr.csv` | Original L14 weather-station diffuse solar radiation series, joined to buildings in that location by exact UTC interval start. | 43,824 |
| `Data/BuildingsByLocation/L14/L14_WS/adrenalin.1h.L14.WS01.T.csv` | Original L14 weather-station air temperature series, joined to buildings in that location by exact UTC interval start. | 43,824 |
| `Data/BuildingsByLocation/L14/L14_WS/adrenalin.1h.L14.WS01.Wd.csv` | Original L14 weather-station wind direction series, joined to buildings in that location by exact UTC interval start. | 43,824 |
| `Data/BuildingsByLocation/L14/L14_WS/adrenalin.1h.L14.WS01.Ws.csv` | Original L14 weather-station wind speed series, joined to buildings in that location by exact UTC interval start. | 43,824 |
| `Data/BuildingsByLocation/L14/unifieddataconsumption/L14_B01_consumption.csv` | Four-column unified electricity table for L14_B01: building ID, interval start/end and electricity_kwh. | 36,360 |
| `Data/BuildingsByLocation/L14/unifieddataconsumption/L14_B01_consumption_weather.csv` | Ten-column L14_B01 consumption table with six exact-start weather measurements; source for metadata enrichment. | 36,360 |
| `Data/BuildingsByLocation/L14/unifieddataconsumption/L14_B02_consumption.csv` | Four-column unified electricity table for L14_B02: building ID, interval start/end and electricity_kwh. | 36,336 |
| `Data/BuildingsByLocation/L14/unifieddataconsumption/L14_B02_consumption_weather.csv` | Ten-column L14_B02 consumption table with six exact-start weather measurements; source for metadata enrichment. | 36,336 |
| `Data/BuildingsByLocation/L14/unifieddataconsumption/L14_B03_consumption.csv` | Four-column unified electricity table for L14_B03: building ID, interval start/end and electricity_kwh. | 36,648 |
| `Data/BuildingsByLocation/L14/unifieddataconsumption/L14_B03_consumption_weather.csv` | Ten-column L14_B03 consumption table with six exact-start weather measurements; source for metadata enrichment. | 36,648 |
| `Data/BuildingsByLocation/L14/unifieddataconsumption/L14_B04_consumption.csv` | Four-column unified electricity table for L14_B04: building ID, interval start/end and electricity_kwh. | 36,889 |
| `Data/BuildingsByLocation/L14/unifieddataconsumption/L14_B04_consumption_weather.csv` | Ten-column L14_B04 consumption table with six exact-start weather measurements; source for metadata enrichment. | 36,889 |
| `Data/BuildingsByLocation/L14/unifieddataconsumption/L14_B05_consumption.csv` | Four-column unified electricity table for L14_B05: building ID, interval start/end and electricity_kwh. | 35,040 |
| `Data/BuildingsByLocation/L14/unifieddataconsumption/L14_B05_consumption_weather.csv` | Ten-column L14_B05 consumption table with six exact-start weather measurements; source for metadata enrichment. | 35,040 |
| `Data/Explanation.md` | Currently empty data-explanation placeholder. | — |

### 5.4 Modelling inputs, targets, implementation and saved artifacts

39 files.

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `Prediction Model/.gitignore` | Ignores the local .venv environment and __pycache__ bytecode directories within the modelling folder. | — |
| `Prediction Model/Input Data/L03_B01_model_input.csv` | Active staged 25-column hourly input table for L03_B01; includes metadata, weather and mirrored target. Train building; leakage columns excluded by the training allowlist. | 8,736 |
| `Prediction Model/Input Data/L07_B01_model_input.csv` | Active staged 25-column hourly input table for L07_B01; includes metadata, weather and mirrored target. Test building; leakage columns excluded by the training allowlist. | 9,543 |
| `Prediction Model/Input Data/L14_B01_model_input.csv` | Active staged 25-column hourly input table for L14_B01; includes metadata, weather and mirrored target. Test building; leakage columns excluded by the training allowlist. | 36,360 |
| `Prediction Model/Input Data/L14_B02_model_input.csv` | Active staged 25-column hourly input table for L14_B02; includes metadata, weather and mirrored target. Test building; leakage columns excluded by the training allowlist. | 36,336 |
| `Prediction Model/Input Data/L14_B03_model_input.csv` | Active staged 25-column hourly input table for L14_B03; includes metadata, weather and mirrored target. Test building; leakage columns excluded by the training allowlist. | 36,648 |
| `Prediction Model/Input Data/L14_B04_model_input.csv` | Active staged 25-column hourly input table for L14_B04; includes metadata, weather and mirrored target. Train building; leakage columns excluded by the training allowlist. | 36,889 |
| `Prediction Model/Input Data/L14_B05_model_input.csv` | Active staged 25-column hourly input table for L14_B05; includes metadata, weather and mirrored target. Train building; leakage columns excluded by the training allowlist. | 35,040 |
| `Prediction Model/Target Set/L03_B01_targets.csv` | Active single-column electricity_kwh_per_m2 labels for L03_B01; one value per corresponding input row, including any empty labels. | 8,736 |
| `Prediction Model/Target Set/L07_B01_targets.csv` | Active single-column electricity_kwh_per_m2 labels for L07_B01; one value per corresponding input row, including any empty labels. | 9,543 |
| `Prediction Model/Target Set/L14_B01_targets.csv` | Active single-column electricity_kwh_per_m2 labels for L14_B01; one value per corresponding input row, including any empty labels. | 36,360 |
| `Prediction Model/Target Set/L14_B02_targets.csv` | Active single-column electricity_kwh_per_m2 labels for L14_B02; one value per corresponding input row, including any empty labels. | 36,336 |
| `Prediction Model/Target Set/L14_B03_targets.csv` | Active single-column electricity_kwh_per_m2 labels for L14_B03; one value per corresponding input row, including any empty labels. | 36,648 |
| `Prediction Model/Target Set/L14_B04_targets.csv` | Active single-column electricity_kwh_per_m2 labels for L14_B04; one value per corresponding input row, including any empty labels. | 36,889 |
| `Prediction Model/Target Set/L14_B05_targets.csv` | Active single-column electricity_kwh_per_m2 labels for L14_B05; one value per corresponding input row, including any empty labels. | 35,040 |
| `Prediction Model/charts/L07_B01_first_seven_days.png` | Actual versus baseline/A/B predictions for L07_B01 over its first suitable consecutive seven-day period; UTC and kWh/m² labels. | — |
| `Prediction Model/charts/L14_B01_first_seven_days.png` | Actual versus baseline/A/B predictions for L14_B01 over its first suitable consecutive seven-day period; UTC and kWh/m² labels. | — |
| `Prediction Model/charts/L14_B02_first_seven_days.png` | Actual versus baseline/A/B predictions for L14_B02 over its first suitable consecutive seven-day period; UTC and kWh/m² labels. | — |
| `Prediction Model/charts/L14_B03_first_seven_days.png` | Actual versus baseline/A/B predictions for L14_B03 over its first suitable consecutive seven-day period; UTC and kWh/m² labels. | — |
| `Prediction Model/charts/mae_by_test_location.png` | Labelled location-level MAE bar chart for the training-mean baseline, Model A and Model B; units kWh/m². | — |
| `Prediction Model/charts/rmse_by_test_location.png` | Labelled location-level RMSE bar chart for the training-mean baseline, Model A and Model B; units kWh/m². | — |
| `Prediction Model/models/baseline_mean.joblib` | Fitted sklearn DummyRegressor containing the training-only mean reference constant. | — |
| `Prediction Model/models/feature_schema.json` | Expected feature names, encoded names, categorical vocabularies, UTC calendar convention, baseline definition and model-use instructions. | — |
| `Prediction Model/models/model_A_pipeline.joblib` | Fitted Model A pipeline, including training-fitted numerical/categorical preprocessing and HistGradientBoostingRegressor. | — |
| `Prediction Model/models/model_B_pipeline.joblib` | Fitted Model B pipeline with weather, including preprocessing and HistGradientBoostingRegressor. | — |
| `Prediction Model/results/L07_B01_predictions.csv` | Building-specific aligned actuals and baseline/A/B predictions for held-out L07_B01, with IDs, source row numbers and interval bounds. | 9,543 |
| `Prediction Model/results/L14_B01_predictions.csv` | Building-specific aligned actuals and baseline/A/B predictions for held-out L14_B01, with IDs, source row numbers and interval bounds. | 36,360 |
| `Prediction Model/results/L14_B02_predictions.csv` | Building-specific aligned actuals and baseline/A/B predictions for held-out L14_B02, with IDs, source row numbers and interval bounds. | 36,336 |
| `Prediction Model/results/L14_B03_predictions.csv` | Building-specific aligned actuals and baseline/A/B predictions for held-out L14_B03, with IDs, source row numbers and interval bounds. | 36,648 |
| `Prediction Model/results/baseline_comparisons.csv` | Fourteen A/B comparisons against the training-mean baseline, with MAE/RMSE, percentage reductions, better/worse flags and zero-reference notes. | 14 |
| `Prediction Model/results/chart_periods.csv` | The four predetermined seven-day chart windows, endpoints, 168-row counts and first-suitable-period selection rule. | 4 |
| `Prediction Model/results/metrics.csv` | Twenty-one metric rows: baseline/A/B for two locations, four buildings and the equal-weight location average. | 21 |
| `Prediction Model/results/predictors.csv` | All 114 input/encoded predictor-list entries across A and B, documenting the exact columns and representation used. | 114 |
| `Prediction Model/results/run_manifest.json` | Detailed machine-readable experiment provenance: split, source/code hashes, settings, features, preprocessing, baseline, versions, audits and assumptions. | — |
| `Prediction Model/results/run_summary.txt` | Readable saved run summary with splits, row counts, baseline definition, all evaluation tables, comparison percentages and interpretation notes. | — |
| `Prediction Model/results/split_summary.csv` | One row per building with train/test membership, source paths, row counts, UTC coverage, duplicates and alignment-check status. | 7 |
| `Prediction Model/results/test_predictions.csv` | All 118,887 aligned test actuals, baseline/A/B predictions, building/location IDs, source row numbers and interval timestamps. | 118,887 |
| `Prediction Model/results/weather_error_reductions.csv` | Seven comparisons of Model B with A by location, building and equal-weight location average; negative reductions indicate worsening. | 7 |
| `Prediction Model/train_models.py` | Single training/evaluation implementation: validates pairs, uses the requested split, builds features, fits A/B plus the training-mean baseline and saves all outputs. | — |

### 5.5 Supporting folders and system files

- `Prediction Model/.venv/`: installed Python environment used to execute training and make charts. Its package internals are not individual project implementations and are excluded from the file-by-file tables.
- `.git/`: version-control database and history, not an input to the modelling pipeline.
- `__pycache__/` and `*.pyc`, when present: generated Python bytecode caches.
- `.DS_Store`, when present: macOS Finder metadata, unrelated to consumption or model results.

The guide contains **117 project files including this report**. No absent IDE placeholder files are counted.

## 6. Verification completed

### 6.1 Existing automated tests

During preparation of this report, the full existing data-cleaning suite was executed using temporary test fixtures:

```text
Ran 65 tests
OK
```

| Test file | Tests |
| --- | --- |
| test_add_building_metadata.py | 12 |
| test_build_consumption_tables.py | 10 |
| test_convert_cumulative_to_hourly.py | 14 |
| test_filter_csv_files.py | 6 |
| test_inspect_energy_readings.py | 11 |
| test_join_weather_data.py | 12 |

These are persisted tests for data preparation. They do not constitute a dedicated persisted unit-test suite for `train_models.py` or the target-export script.

### 6.2 Additional checks performed during the project

- Verified all 199,552 original hourly rows, values and timestamps were preserved when metadata and per-area values were added; checked all seven derived-value streams and matching building-info sources.
- Confirmed enrichment reruns produced identical outputs and did not duplicate columns; source CSV/TXT files were checked with SHA-256 hashes.
- Checked target extraction preserves high-precision text, empty target rows, zero/negative values and row order; mismatched building IDs stop exports before replacing valid outputs.
- Verified the active staged input tables still contain the exact original ten-column consumption/weather values in the same row order.
- Ran synthetic end-to-end training checks for split isolation, unknown categories, entirely missing metadata, fixed 200-iteration fits, metric/figure creation, model saving/loading and rejection of reordered target-only rows.
- Reloaded the fitted A/B pipelines and reproduced their saved predictions; verified imputer statistics and categorical vocabularies came from training data only.
- Independently recomputed saved MAE/RMSE values, the equal-weight location averages and first suitable seven-day periods.
- Checked known numerical metric examples and zero-denominator handling after adding the baseline.
- Verified the persisted baseline equals the mean of training targets and reproduces every saved baseline prediction. Independently checked all **21** metric rows and **14** A/B-to-baseline comparison rows.
- Confirmed adding the baseline left A/B settings and predictions, test alignment and chart windows unchanged.
- Checked recorded source hashes against the current staged datasets and the training-script hash before generating this report. No models were retrained merely to write this document.

## 7. Open issues and work not yet completed

1. **Generalisation remains inadequate overall.** Both models fail badly on L14_B03 and lose to the simple baseline on the equal-weight location average. This has been measured, not resolved.
2. **L03's magnitude/unit-scale concern remains open.** The table builder explicitly retains its stated kWh label without automatic rescaling. Current mean target magnitudes are listed below; their differences are a reason to review provenance and measurement comparability, not proof of a particular unit error or the sole cause of model failure.

| Building | Split | Observed mean hourly target (kWh/m²) |
| --- | --- | --- |
| L03_B01 | train | 3.164898 |
| L07_B01 | test | 0.108725 |
| L14_B01 | test | 0.009710 |
| L14_B02 | test | 0.014729 |
| L14_B03 | test | 0.005410 |
| L14_B04 | train | 0.015379 |
| L14_B05 | train | 0.007699 |

3. **Interval timing is partly assumed.** L03/L14 end-timestamp interpretation is a project convention. No additional target shift was introduced in modelling.
4. **Weather availability is assumed rather than operationally established.** Publication latency, actual forecast feeds and future availability must be checked before claiming deployment-time forecasting performance.
5. **Metadata is incomplete.** L03 floor count is contradictory, L14 floor counts are missing, and L14_B02 opening year is missing. Imputation is inside training-fitted pipelines and does not resolve the source uncertainty.
6. **Unseen categorical uses are handled computationally, but transfer is not guaranteed.** Grocery-store and nursing-home labels were absent from the training vocabulary.
7. **Only three buildings were used for fitting.** Many hourly rows share the same static building metadata. The row count should not be mistaken for equally broad coverage of building types and locations.
8. **No tuning or chronological validation experiment has been carried out.** If future work tunes models, reserve the latest 20% of unique training timestamps using a common chronological cutoff across the training pool only, including its L03 rows. The current held-out results must not be used to choose better settings and then described as an untouched test estimate. With tuning, final models should be refitted on all allowed training rows before a separate final evaluation.
9. **The current task is same-interval conditional prediction.** No future forecast horizon, lag-target model, persistence/seasonal-naive benchmark, target scaling, causal analysis or production deployment has been implemented. The existing simple benchmark is the global training mean.
10. **Path/configuration synchronisation is incomplete upstream.** Current training reads the staged `Prediction Model` directories. Upstream scripts still write to `Data`; current L06 configuration entries refer to data absent from the tree. Those details need an explicit regeneration/staging decision before treating the entire historical preparation process as a one-command pipeline.
11. **No independent automated training-test file exists yet.** Training was checked with temporary synthetic examples and saved-artifact verification; the persisted 65-test suite covers data preparation.

These are outstanding investigation and implementation items. No changes to source units, datasets, model settings or splits were made while documenting them.

## 8. Execution and reproducibility reference

Run from the project root. The existing local model environment is `Prediction Model/.venv/`.

Check modelling data without fitting or writing model outputs:

```bash
"Prediction Model/.venv/bin/python" "Prediction Model/train_models.py" --check-data
```

Run the current requested experiment, including the reference baseline:

```bash
"Prediction Model/.venv/bin/python" "Prediction Model/train_models.py"
```

The equivalent explicit L14 training selection is:

```bash
"Prediction Model/.venv/bin/python" "Prediction Model/train_models.py" --train-l14 L14_B04 L14_B05
```

Dependencies, if installation is required in that environment:

```bash
"Prediction Model/.venv/bin/python" -m pip install numpy pandas "scikit-learn>=1.2" matplotlib joblib threadpoolctl
```

For a fresh environment, create it first with `python3 -m venv "Prediction Model/.venv"`. Installed versions for the saved experiment are:

| Component | Saved-run version |
| --- | --- |
| python | 3.11.1 |
| numpy | 1.26.4 |
| pandas | 1.5.3 |
| scikit_learn | 1.9.0 |
| matplotlib | 3.9.4 |
| joblib | 1.5.3 |

Run the existing data-preparation tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s Data_cleaning -p 'test_*.py'
```

Upstream generation entry points, when intentionally regenerating their derived artifacts, are:

```bash
python3 Data_cleaning/build_consumption_tables.py
python3 Data_cleaning/join_weather_data.py
python3 Data_cleaning/add_building_metadata.py
python3 Data_cleaning/export_prediction_targets.py
```

These commands write generated tables under `Data/BuildingsByLocation/` and do not update the active staged modelling files automatically. They assume the selected raw/processed sources exist. The current staged datasets were preserved while producing this report. No destructive filtering or cumulative conversion is included in this regeneration command block; those earlier stages have separate source/configuration requirements described above.

The saved `run_manifest.json` contains source-dataset hashes, training-script and target-exporter hashes, precise feature names, versions, split membership and assumptions. The fitted model pipelines include their preprocessing, while the deterministic calendar-feature construction remains in `train_models.py`.

## 9. Milestones achieved

- [x] Established the location/building folder structure and explicit electricity-channel selection rules.
- [x] Implemented read-only energy-quality and cumulative-versus-hourly inspection with an auditable report.
- [x] Implemented confirmation-driven cumulative conversion with exclusions and source preservation.
- [x] Produced and audited 9,543 valid L07 hourly intervals from 9,545 counter readings.
- [x] Created seven separate unified hourly consumption tables with explicit interval boundaries.
- [x] Joined all six weather measurements using exact UTC prediction-interval starts and documented the availability assumption.
- [x] Parsed fourteen building metadata fields from the actual text formats, preserving missing and conflicting values.
- [x] Created seven enriched 25-column input tables while preserving existing hourly cells and order.
- [x] Calculated electricity consumption per gross square metre consistently in kWh/m².
- [x] Exported seven aligned single-column target CSVs without shifting targets or dropping empty rows.
- [x] Staged matching inputs and targets for seven buildings, totalling 199,552 hourly examples.
- [x] Implemented the requested training/test allocation: L03_B01/L14_B04/L14_B05 for training; L07_B01/L14_B01–B03 for testing.
- [x] Implemented training-only preprocessing, unknown-category handling and explicit protection against target-derived predictors.
- [x] Fitted Model A and Model B using HistGradientBoostingRegressor with identical fixed settings and seed.
- [x] Established a separate training-mean DummyRegressor benchmark and compared both models against it on identical test rows.
- [x] Saved per-building, per-location and equal-weight metrics, percentage comparisons and 118,887 aligned test predictions.
- [x] Generated two labelled metric-comparison bar charts and four first-suitable-seven-day time-series plots, including the baseline.
- [x] Saved both fitted model/preprocessing pipelines, the baseline estimator and machine-readable experiment provenance.
- [x] Passed all 65 existing data-cleaning tests and additional synthetic/artifact checks for training and baseline evaluation.
- [x] Recorded the measured performance shortfall and unresolved assumptions without claiming a baseline improvement or causal result.
- [x] Created this root-level progress report with a complete file guide and current milestone record.
