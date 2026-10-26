# Project progress so far

**Project:** Electricity-consumption prediction using building metadata, calendar features and weather.  
**Report date:** 26 October 2026, Australia/Sydney.  
**Latest figure update:** Six academic report figures generated from the saved 25 October validation experiment; no retraining.  
**Scope:** Data preparation; the preserved original fixed-setting experiment; four exploratory timing/L03 sensitivity experiments; the chronological-validation/shared-parameter-selection experiment; and six replacement academic report figures. Results come from saved predictions, CSVs, manifests and verification records. Latest run: `validation/run_20261025T091525_455049Z`; earlier sensitivities: `timing_L03/run_20261025T021409_544191Z`.

**Contents:** [Work completed](#2-work-completed) · [Dataset and experiment](#3-current-dataset-and-experiment-specification) · [Results](#4-actual-evaluation-results) · [Latest validation results](#49-chronological-validation-selected-settings-and-final-refit) · [Report figures](#410-six-academic-report-figures-26-october) · [File guide](#5-file-by-file-guide) · [Verification](#6-verification-completed) · [Open issues](#7-open-issues-and-work-not-yet-completed) · [Run commands](#8-execution-and-reproducibility-reference) · [Milestones](#9-milestones-achieved).

## 1. Current position

The project now has a working path from selected electricity channels to building-level hourly tables, aligned weather, building metadata, electricity-per-area targets, and reproducible model comparisons. Seven buildings provide **199,552 aligned hourly examples**. The original fixed-setting experiment and four exploratory sensitivities are preserved. A separate **chronological validation and three-candidate parameter-selection experiment** has now also been implemented, run and verified.

Both models use `HistGradientBoostingRegressor`: A uses metadata and calendar features; B adds weather. The reference methods now include both the global training-mean `DummyRegressor` and a training-only building-use/weekday/hour baseline with documented fallbacks. Each follow-up refits preprocessing and baselines on its allowed training rows only.

**Neither model beats the global training-mean baseline on the equal-weight test-location average in any completed configuration.** The original configuration transfers very poorly to L14_B03. Excluding L03 substantially reduces that error, but the refitted global-mean and calendar/building-use baselines still outperform both models on the equal-weight average across test locations. Weather gives mixed results with L03 included and only small average gains after excluding it. These follow-ups are exploratory because the original test results were already inspected; they do not establish incorrect L03 units, a causal weather effect or production-ready forecasting.

The follow-ups cross two training configurations with two weather timings, retaining exactly **118,887 original test rows**, unchanged targets, fixed model settings and the original seven-day chart windows. Added outputs include mean-normalised RMSE, target-distribution summaries, both-baseline comparisons, **29 new charts**, and saved fitted models and provenance. The 29 sensitivity figures and three validation figures remain unchanged. The user subsequently removed the six original main-folder PNGs; that folder now contains the six replacement report figures described in Section 4.10.

The new experiment keeps L03_B01/L14_B04/L14_B05 in development and retains original exact-t weather. Per-building earliest-80% fitting uses **64,531 rows**; latest-20% validation uses **16,134 rows**. Validation selected **candidate 2: max_leaf_nodes=15, min_samples_leaf=60**, shared by A and B. Its shared validation score is **0.298002 kWh/m²**, the mean of A's **0.302083** and B's **0.293920** equal-weight validation-building RMSEs. Both models and both baselines were then refitted on all **80,665 development rows**, before evaluating the same **118,887 held-out test rows**.

The three experiment families have distinct purposes and remain saved separately:

| Experiment family | Purpose and fitting policy | Saved outputs |
| --- | --- | --- |
| Original fixed-setting experiment | Compare A/B and the global-mean baseline using the original 31-leaf, minimum-leaf-size-30 settings; no parameter selection. | `Prediction Model/results/`, `models/` and `charts/` |
| Four exploratory sensitivity experiments | Cross L03 inclusion/exclusion with exact-t/one-hour-lagged weather; retain original settings and compare both baselines. | `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/` |
| Chronological validation and parameter selection | Compare exactly three predefined settings on later periods of known buildings; select one shared A/B configuration, refit on full development data, then evaluate held-out buildings. | `Prediction Model/experiments/validation/run_20261025T091525_455049Z/` |

The latest refit's test summary below gives equal weight to L07 and L14. MAE/RMSE are in kWh/m²; nRMSE is the average of the two location percentages, not a pooled normalisation.

| Method | MAE (kWh/m²) | RMSE (kWh/m²) | nRMSE (%) |
| --- | --- | --- | --- |
| Global training-mean baseline | 0.293805 | 0.294841 | 1840.71 |
| Calendar/building-use baseline | 1.233229 | 1.495577 | 13842.59 |
| Model A: metadata and calendar | 0.601854 | 1.050304 | 10068.75 |
| Model B: metadata, calendar and weather | 0.602848 | 1.069989 | 10090.80 |

Both models beat the calendar baseline overall but still lose to the global mean and fail badly on L14_B03. Adding weather increases equal-location RMSE by **1.874%** compared with A in this validation-guided refit. The validation choice therefore does not establish successful transfer or an overall weather benefit.

Validation assesses **later periods within known buildings**, using separate cutoffs because coverage differs. Test results assess transfer to other buildings: **L07 is an unseen location; L14 tests are unseen buildings at a known location**. These tests were already inspected earlier. This is a validation-guided follow-up, not an untouched final test, and validation does not guarantee improved transfer. Three new charts and eight focused tests accompany this experiment.

The project records **83 passing tests across three separately executed suites**: 65 data-preparation, 10 sensitivity and 8 validation tests. The latest independent artifact audit checked all **76 new metric rows** and preprocessing for all **eight fitted pipelines**. The 26 October figure update was checked against saved predictions, selection scores, split boundaries and verification records; it does not represent a new training or test run. All six new report figures are supplied as 320 DPI PNGs and editable SVGs, with captions, plotting code and the exact plotted data.

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

**Weather availability limitation:** the intended task is prediction at time t for electricity over **[t, t+1 hour)**. The dataset PDF identifies the weather as anonymised CERRA/ERA5-Land/ERA5 reanalysis, but does not establish selected-variable interval semantics, product mapping or availability at t. The original exact-t alignment is retained as an explicitly assumed reference, not confirmed operational information. The new sensitivity uses weather at exactly t−1 hour. That reduces contemporaneous dependence but does not establish publication latency. Targets and source timestamp conventions remain unchanged.

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

### 2.11 Reviewed dataset documentation and prediction timing

The local `ADRENALIN_data_description.pdf` was read during the follow-up review. Page 5 describes UTC timestamps; page 8 identifies the reanalysis sources and anonymisation; pages 16 and 19–20 describe harmonisation/resampling and measurement limitations. None establishes a publication-time guarantee or an L03-specific unit correction. The preparation scripts were traced from raw electricity timestamps through interval construction, weather joins, per-area calculation and sequential target export.

The selected L03 electricity channel is **EM02**. The building-info note about virtual aggregate **EM01**, which includes boiler heat, must not be applied to the selected electricity submeter. L03 readings retain their stated kWh unit; no divide-by-1,000 conversion or other source-data rescaling was introduced.

### 2.12 Completed the controlled exploratory follow-ups

`Prediction Model/run_followup_experiments.py` reuses the original feature lists, pipelines and hyperparameters without invoking the original output-writing entry point. It completes this 2×2 design:

| Training configuration | Training buildings | Training rows | Weather variants |
| --- | --- | --- | --- |
| With L03 | L03_B01, L14_B04, L14_B05 | 80,665 | Exact t; exact t−1 hour |
| Without L03 diagnostic | L14_B04, L14_B05 | 71,929 | Exact t; exact t−1 hour |

Every case tests L07_B01 and L14_B01/B02/B03 on the same 118,887 rows. The lagged variant looks up each location's full weather series by exact timestamp, rather than shifting electricity rows. Weather at a missing electricity hour can therefore still be used if its timestamp exists in the location weather data. Unavailable weather matches remain missing. Current staged weather was checked against the original exact-t sources without replacing staged inputs.

The new baseline uses the training mean target for **building_use × weekday × hour**, falling back to **building_use × hour**, then **weekday × hour across training buildings**, then the **global training mean**. No held-out targets fit or adjust it. Its lookup means, counts and observed fallback usage are saved. Mean-normalised RMSE is added alongside MAE/RMSE, including reasons for undefined denominators.

The runner creates a fresh UTC-stamped directory on each invocation and refuses output roots inside original outputs or source-data directories. The original `train_models.py`, saved models, metrics, predictions, charts and staged data were verified unchanged. The original progress report was also unchanged at run completion; its pre-update bytes are now archived as `progress_report_before_followup_update.md` inside the follow-up batch, because the user subsequently requested this document update. Historical preservation hashes still describe that archived prior version.

### 2.13 Added explicit chronological validation and a predefined shared parameter comparison

`Prediction Model/run_validation_experiment.py` imports the original alignment/feature/pipeline code and the earlier baseline/metric helpers. Existing scripts, source data and experiment outputs remain unchanged. Every invocation creates a fresh timestamped directory under `Prediction Model/experiments/validation/`.

For each of L03_B01, L14_B04 and L14_B05, the first `floor(0.8 × unique_timestamp_count)` timestamps fit the methods; the remaining timestamps validate them. All rows at a timestamp stay together, and joint masks preserve source row order. Boundaries, complete development-row membership and eligible-row lists are saved. No within-building timestamp or row overlaps occur. This is future-period validation within known buildings using per-building cutoffs, rather than a global time boundary or unseen-building validation. Cross-building time ranges may overlap under this explicitly requested design.

Before fitting or scoring, `candidate_plan.json` records the three candidates and selection rule. Candidate 1 keeps the original settings; candidate 2 changes only leaves/minimum leaf size to 15/60; candidate 3 changes only those values to 7/120. A and B are each evaluated for all three. The shared winner minimises the average of A's and B's equal-weight validation-building RMSEs. Exact ties prefer fewer leaves, then larger minimum leaf size. No search expansion occurs; random_state=42, early_stopping=False and all other settings stay fixed.

Validation preprocessing and both baselines fit only the earliest-80% pool. The baselines are fitted once and reused across candidates. The selected setting is written before test CSVs are loaded. A/B and both baselines are then refitted on the full development pool and evaluated once on the fixed test buildings. L03 remains included and unscaled, features are unchanged, original exact-t weather is retained, and targets are not shifted. Full candidate pipelines, baseline statistics, fitted preprocessing audits, all validation/test predictions and metrics, three charts, source hashes and stage events are saved.

### 2.14 Generated the six academic report figures

After the user cleared `Prediction Model/charts/`, `generate_report_figures.py` populated it with the requested workflow, building timeline, validation-candidate comparison, per-building test RMSE comparison, four-panel actual/predicted comparison and weather-contribution chart. Every quantitative figure uses the latest saved validation-selected experiment (`candidate_2`), without fitting models or changing predictions. The workflow/timeline describe that same experiment.

The script verifies all seven input/target pairs, split boundaries, the shared validation winner, 18 candidate/model/building RMSEs, six candidate/model validation averages and 16 test building/method RMSEs before plotting. Figure 5 uses the original fixed 168-hour window per held-out building: 672 observations total. Figure 6 subtracts the same A/B test RMSE values plotted in Figure 4. Negative forecasts are preserved; L14_B03 includes an explicitly actual-only inset because its forecasts are much larger than its observed target. All panels use labelled independent vertical scales.

Six PNGs at 320 DPI, six SVGs with editable text, six captions, five plot-data CSVs and a figure manifest are saved in the main charts folder. The plotting code refuses to overwrite existing output filenames; rerendering uses a fresh destination. Earlier experiment-specific figures, metrics, datasets and fitted models remain unchanged. The six user-deleted original main-folder PNGs are recorded as historical removals, rather than silently recreated with different results.

## 3. Current dataset and experiment specification

### 3.1 Original split, diagnostic split and coverage

The original requested split trains on L03_B01 plus L14_B04 and L14_B05. The diagnostic excludes L03 and trains on B04/B05 only. Both keep L07_B01 and all three other L14 buildings held out. L07 is an unseen location; the L14 holdouts are unseen buildings within a location represented in training. L03 is a training building or diagnostic exclusion, never a test building in these runs. The table below records the original allocation and unchanged data coverage.

| Building | Split | Hourly rows | First interval start (UTC) | Last interval start (UTC) | Gross floor area (m²) |
| --- | --- | --- | --- | --- | --- |
| L03_B01 | train | 8,736 | 2022-01-01 11:00:00 | 2022-12-31 10:00:00 | 1013 |
| L07_B01 | test | 9,543 | 2021-11-29 06:00:00 | 2022-12-31 22:00:00 | 450 |
| L14_B01 | test | 36,360 | 2017-12-31 22:00:00 | 2022-03-09 21:00:00 | 6084 |
| L14_B02 | test | 36,336 | 2017-12-31 22:00:00 | 2022-02-22 21:00:00 | 2700 |
| L14_B03 | test | 36,648 | 2017-12-31 22:00:00 | 2022-03-10 21:00:00 | 6574 |
| L14_B04 | train | 36,889 | 2017-12-31 22:00:00 | 2022-03-17 22:00:00 | 11502 |
| L14_B05 | train | 35,040 | 2017-12-31 22:00:00 | 2021-12-31 21:00:00 | 988 |

**Original training rows:** 80,665. **Diagnostic training rows:** 71,929, with L03's 8,736 rows excluded. **Test rows in every experiment:** 118,887. **Total available:** 199,552. All current targets are finite, so no rows were dropped for missing targets. Missing weather does not change the evaluation rows.

This is a fixed building/location holdout design. A leave-one-site-out design would hold out every building at a site and repeat across site folds; that procedure has not been performed. L14 cannot be described as an entirely unseen location when its B04/B05 buildings are in training.

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

The original encoded feature counts are **26 for A** and **38 for B**. Follow-up encoded vocabularies and missingness indicators are refitted on each allowed training set and saved per experiment, while the raw feature lists remain fixed. In the L03-excluded runs, education is also an unseen building-use label because training contains only office and kindergarten uses. The global-mean baseline has no predictive features; the new calendar/building-use baseline uses only its documented grouping keys.

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

These are the preserved **original fixed settings**, also retained in the four earlier sensitivity cases. Those experiments did not use chronological validation or parameter search. Automatic early stopping was disabled. Original and with-L03 fits used all 80,665 allowed rows; L03-excluded fits used 71,929. The new validation experiment in Section 3.5 starts with these settings and compares exactly the two predefined alternatives. Its explicitly requested **per-building cutoffs supersede the earlier recommendation for a common global cutoff** for this experiment. No test data fit preprocessing or select the configuration.

### 3.4 Both reference baselines and evaluation definitions

The original global-mean reference is **0.353135360800 kWh/m²**, fitted from 80,665 eligible training targets. After excluding L03 it is refitted to **0.011638073853 kWh/m²** from 71,929 training rows. Both are row-weighted training means; neither is adjusted using held-out buildings.

The calendar/building-use baseline uses the four-level fallback hierarchy in Section 2.12, consistently in UTC. With L03 included, 73,008 test rows use the full building-use/weekday/hour lookup and 45,879 fall back to weekday/hour. Without L03, all 118,887 test rows use the training weekday/hour fallback because every test building-use category is absent from the two-building training set. The intermediate and global fallbacks are implemented and covered by focused tests, even though these particular held-out rows do not require them.

MAE is mean absolute prediction error. RMSE is the square root of mean squared prediction error. Both are in kWh/m². Mean-normalised RMSE is **nRMSE (%) = 100 × RMSE / mean(observed target)**, calculated independently for each test building and pooled test location. Non-positive or invalid observed means yield an undefined percentage with a recorded reason. Held-out targets supply evaluation denominators only, not fitted baseline adjustments.

Results are reported per test building, pooled within each location, and as an equal-weight average of the two location metrics. This averages location MAEs, location RMSEs and location nRMSE percentages separately. The average of location RMSEs is not pooled RMSE; the average of location nRMSE values has no pooled normalisation denominator. Large percentages are possible when observed target means are small relative to prediction errors.

```text
Weather error reduction (%) = 100 × (error_A − error_B) / error_A
Baseline error reduction (%) = 100 × (error_baseline − error_model) / error_baseline
```

Positive reduction means improvement; negative reduction means deterioration. A zero reference error produces an empty percentage and an explanatory note, avoiding division by zero.

### 3.5 New per-building validation and shared selection policy

| Building | Fitting rows | Validation rows | Last fitting start (UTC) | First validation start (UTC) | Last validation start (UTC) |
| --- | --- | --- | --- | --- | --- |
| L03_B01 | 6988 | 1748 | 2022-10-19T14:00:00+00:00 | 2022-10-19T15:00:00+00:00 | 2022-12-31T10:00:00+00:00 |
| L14_B04 | 29511 | 7378 | 2021-05-14T12:00:00+00:00 | 2021-05-14T13:00:00+00:00 | 2022-03-17T22:00:00+00:00 |
| L14_B05 | 28032 | 7008 | 2021-03-13T21:00:00+00:00 | 2021-03-13T22:00:00+00:00 | 2021-12-31T21:00:00+00:00 |

Each building currently has unique interval-start timestamps, so timestamp and row percentages coincide apart from integer rounding. Fitting uses floor(80%); validation contains the remainder, which may slightly exceed 20%. Counts are **64,531 fitting + 16,134 validation = 80,665 development rows**. All targets are finite, and no weather-related row exclusions occur.

This validation asks how methods perform in later periods of the **same three buildings**. It does not test unseen building metadata or unseen-location transfer. Fitting periods can extend beyond another building's validation dates, because the cutoffs are per building rather than global. All methods use the same validation rows; each building receives one-third weight in validation metric averages regardless of row count.

The shared selection score is `(macro_building_RMSE_A + macro_building_RMSE_B) / 2`, in kWh/m². It is fixed before scoring and is not replaced by nRMSE or test error after inspecting results. Because raw RMSE retains differences in target scale, L03's much larger scale can dominate this criterion even with equal building weights. All other parameters match Section 3.3. The selected final configuration uses **15 leaves and minimum leaf size 60**, with the same features and exact-t weather as the original experiment. Full-development refitting uses 80,665 rows, and final testing uses the same 118,887 original test rows.

## 4. Actual evaluation results

Sections 4.1–4.3 preserve the original fixed-setting results; Sections 4.4–4.8 cover the four exploratory sensitivities; Section 4.9 covers the new validation-guided selection and refit. These are distinct experiment families. Earlier saved results were not overwritten.

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

The original experiment produced two location-level baseline/A/B bar charts and four building time-series charts. These six historical PNGs were removed by the user on 26 October; the saved original metrics and predictions remain available. The original time-series charts showed actual consumption and all three predictions over the same seven-day period within each test building. Each period is the **first 168 consecutive hourly rows** available; periods are selected from time coverage, not from prediction quality. The baseline is shown as a dashed constant line.

| Building | Period start (UTC) | Period end, exclusive (UTC) | Hourly rows |
| --- | --- | --- | --- |
| L07_B01 | 2021-12-01T22:00:00+00:00 | 2021-12-08T22:00:00+00:00 | 168 |
| L14_B01 | 2017-12-31T22:00:00+00:00 | 2018-01-07T22:00:00+00:00 | 168 |
| L14_B02 | 2017-12-31T22:00:00+00:00 | 2018-01-07T22:00:00+00:00 | 168 |
| L14_B03 | 2017-12-31T22:00:00+00:00 | 2018-01-07T22:00:00+00:00 | 168 |

The original numerical comparisons remain in `Prediction Model/results/metrics.csv` and the corresponding prediction CSVs. For the current report, use the six latest-model figures in Section 4.10 and [their captions](<Prediction Model/charts/captions.md>). Their time-series panels reuse the exact original windows above. No unavailable historical PNG is linked as if it were still present.

### 4.4 Exploratory follow-up results: training pool and weather timing

Four follow-ups vary the training pool and weather timing independently. Settings, raw predictors, target intervals, evaluation rows and saved seven-day windows remain fixed. Preprocessing and baselines are refitted only on the relevant training data. Because the original test results were already inspected, these are exploratory diagnostics rather than untouched final-test estimates.

The with-L03/current-weather case reproduces the original A/B/global-mean predictions. Below are **equal-weight averages of the L07 and L14 location metrics**, not pooled all-test metrics. MAE and RMSE are in kWh/m²; nRMSE is a percentage.

| Training | Weather | Method | MAE | RMSE | nRMSE (%) |
| --- | --- | --- | --- | --- | --- |
| with_L03 | current_weather | baseline_mean | 0.293805 | 0.294841 | 1840.71 |
| with_L03 | current_weather | baseline_calendar_use | 1.233229 | 1.495577 | 13842.59 |
| with_L03 | current_weather | A | 0.598728 | 1.054113 | 10118.71 |
| with_L03 | current_weather | B | 0.605341 | 1.083748 | 10303.61 |
| with_L03 | lagged_weather_1h | baseline_mean | 0.293805 | 0.294841 | 1840.71 |
| with_L03 | lagged_weather_1h | baseline_calendar_use | 1.233229 | 1.495577 | 13842.59 |
| with_L03 | lagged_weather_1h | A | 0.598728 | 1.054113 | 10118.71 |
| with_L03 | lagged_weather_1h | B | 0.594132 | 1.064059 | 10116.15 |
| without_L03 | current_weather | baseline_mean | 0.051635 | 0.054848 | 85.67 |
| without_L03 | current_weather | baseline_calendar_use | 0.051484 | 0.054242 | 83.28 |
| without_L03 | current_weather | A | 0.054359 | 0.057264 | 94.10 |
| without_L03 | current_weather | B | 0.054304 | 0.057212 | 94.06 |
| without_L03 | lagged_weather_1h | baseline_mean | 0.051635 | 0.054848 | 85.67 |
| without_L03 | lagged_weather_1h | baseline_calendar_use | 0.051484 | 0.054242 | 83.28 |
| without_L03 | lagged_weather_1h | A | 0.054359 | 0.057264 | 94.10 |
| without_L03 | lagged_weather_1h | B | 0.054295 | 0.057202 | 94.02 |

Removing L03 substantially reduces model error, but both models still lose to both refitted baselines overall. With L03 excluded, average location RMSE is **0.054848** for the global mean and **0.054242** for the calendar/building-use baseline. Model A gives **0.057264**; B gives **0.057212** with current weather and **0.057202** with lagged weather. The calendar/building-use baseline also has lower average nRMSE: **83.28%**, compared with roughly **94%** for the models.

The calendar/building-use baseline is not uniformly strong: with L03 included, its average RMSE is **1.495577**, worse than either model and the global mean. All reference methods are retained and reported; a favourable baseline is not selected after looking at the tests.

### 4.5 Weather contribution in each follow-up

Model B versus A under each fixed training configuration and weather timing. Positive reduction improves on A; negative reduction worsens it. These percentages compare the equal-weight averages of the location metrics.

| Training | Weather | MAE reduction (%) | RMSE reduction (%) | nRMSE reduction (%) |
| --- | --- | --- | --- | --- |
| with_L03 | current_weather | -1.105 | -2.811 | -1.827 |
| with_L03 | lagged_weather_1h | 0.768 | -0.943 | 0.025 |
| without_L03 | current_weather | 0.101 | 0.090 | 0.045 |
| without_L03 | lagged_weather_1h | 0.117 | 0.107 | 0.088 |

With L03 included, current weather worsens both MAE and RMSE; lagged weather improves MAE slightly but worsens RMSE. Without L03, weather yields only small average gains, around **0.10–0.12% in MAE** and **0.09–0.11% in RMSE**. Location-level results can differ: in the L03-excluded/current-weather case, pooled L14 RMSE slightly worsens even though the average across locations slightly improves. Per-building/location files retain that detail. Model A and both baselines are verified unchanged between weather-timing variants for a fixed training pool.

### 4.6 L03 influence by held-out building

For Model B with current weather, the controlled change is exclusion of L03 from fitting. The following test rows and targets are identical in both runs; only the permitted fitting pool changes. This is diagnostic evidence of training-pool influence, not proof of a unit error.

| Building | MAE with L03 | MAE without L03 | RMSE with L03 | RMSE without L03 | RMSE reduction (%) |
| --- | --- | --- | --- | --- | --- |
| L07_B01 | 0.110743 | 0.101304 | 0.131937 | 0.105362 | 20.14 |
| L14_B01 | 0.014737 | 0.004015 | 0.021664 | 0.005992 | 72.34 |
| L14_B02 | 0.015344 | 0.007915 | 0.022243 | 0.010073 | 54.71 |
| L14_B03 | 3.251975 | 0.009962 | 3.515921 | 0.010433 | 99.70 |

The largest change is L14_B03: RMSE falls from **3.515921 to 0.010433 kWh/m²** with current weather. Both A/B and both timing variants, including baseline changes, are recorded in `l03_influence_by_building.csv`; `weather_timing_comparison.csv` isolates the timing factor separately.

### 4.7 Target distributions without invented unit corrections

All values below are hourly kWh/m², retaining the stated source units. Counts, means, medians, selected percentiles and maxima were calculated descriptively. No test distribution statistic was used to fit or adjust predictions.

| Building | Count | Mean | Median | P01 | P05 | P25 | P75 | P95 | P99 | Maximum |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L03_B01 | 8,736 | 3.164898 | 3.010859 | 0.858835 | 1.006910 | 2.181639 | 3.961007 | 5.992103 | 7.650543 | 11.076012 |
| L07_B01 | 9,543 | 0.108725 | 0.112001 | 0.062882 | 0.066910 | 0.078194 | 0.133542 | 0.158889 | 0.179097 | 0.202222 |
| L14_B01 | 36,360 | 0.009710 | 0.007890 | 0.001479 | 0.001972 | 0.003945 | 0.012656 | 0.025148 | 0.036818 | 0.054076 |
| L14_B02 | 36,336 | 0.014729 | 0.012593 | 0.004815 | 0.006296 | 0.009259 | 0.018889 | 0.028889 | 0.035556 | 0.049630 |
| L14_B03 | 36,648 | 0.005410 | 0.003347 | 0.001521 | 0.001673 | 0.002130 | 0.007910 | 0.013690 | 0.014907 | 0.017341 |
| L14_B04 | 36,889 | 0.015379 | 0.013389 | 0.009303 | 0.010085 | 0.011476 | 0.019040 | 0.025039 | 0.027039 | 0.032690 |
| L14_B05 | 35,040 | 0.007699 | 0.006073 | 0.002024 | 0.003036 | 0.004049 | 0.011134 | 0.017206 | 0.019231 | 0.023279 |

L03 is much larger in scale than the other selected targets, but the reviewed documentation does not provide an authoritative L03-specific correction. Excluding it and observing improved transfer does not establish why its scale differs. No source value was divided by 1,000, re-differenced or otherwise rescaled.

### 4.8 New charts, saved outputs and report-ready methodology

Each of the four named cases has separate `results/`, `models/` and `charts/` directories under `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z`. The cases contain **28 metrics each**, aligned actual/predicted values for all four methods, both-baseline comparisons, weather-related reductions, split membership, feature lists, fitted pipelines, baseline information and manifests.

There are **29 new figures**: three location-level metric charts (MAE, RMSE and nRMSE) plus four fixed-window time-series plots per case, and one compact L03-influence chart. All time-series plots reuse the original saved windows from Section 4.3. No window was reselected based on prediction quality.

![Controlled L03-exclusion RMSE comparison](<Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/l03_influence_rmse.png>)

![L03-excluded, lagged-weather nRMSE by test location](<Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/charts/nrmse_pct_by_test_location.png>)

The concise methodology and findings are in [methodology_and_findings.md](<Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/methodology_and_findings.md>). The original output directories remain unchanged; new results are not presented as a replacement for the historical original experiment.

### 4.9 Chronological validation, selected settings and final refit

The completed run is [validation/run_20261025T091525_455049Z/methodology_and_results.md](<Prediction Model/experiments/validation/run_20261025T091525_455049Z/methodology_and_results.md>). Candidate configurations and selection rules were saved before fitting/scoring; stage events record that the chosen setting was saved before any test CSV was loaded. No previous test metrics entered selection.

All candidate scores below are in kWh/m² and average validation-building RMSEs with equal building weights. The shared score gives A and B equal weight.

| Candidate | A validation RMSE | B validation RMSE | Shared score | Leaves | Minimum leaf size | Selected |
| --- | --- | --- | --- | --- | --- | --- |
| candidate_1 | 0.302666 | 0.298253 | 0.300459 | 31 | 30 | False |
| candidate_2 | 0.302083 | 0.293920 | 0.298002 | 15 | 60 | True |
| candidate_3 | 0.328358 | 0.311257 | 0.319807 | 7 | 120 | False |

**Candidate 2 is selected for both models.** No further settings were tried. For the selected candidate, validation metrics are:

| scope | name | model | mae_kwh_per_m2 | rmse_kwh_per_m2 | nrmse_pct |
| --- | --- | --- | --- | --- | --- |
| building | L03_B01 | baseline_mean | 3.244439 | 3.472252 | 96.818027 |
| building | L03_B01 | baseline_calendar_use | 0.821878 | 1.057197 | 29.478191 |
| building | L03_B01 | A | 0.569421 | 0.866998 | 24.174804 |
| building | L03_B01 | B | 0.542249 | 0.857983 | 23.923441 |
| building | L14_B04 | baseline_mean | 0.328215 | 0.328240 | 2393.240041 |
| building | L14_B04 | baseline_calendar_use | 0.002138 | 0.002605 | 18.996442 |
| building | L14_B04 | A | 0.005277 | 0.018255 | 133.099859 |
| building | L14_B04 | B | 0.003433 | 0.012273 | 89.483302 |
| building | L14_B05 | baseline_mean | 0.334740 | 0.334770 | 4655.662892 |
| building | L14_B05 | baseline_calendar_use | 0.001586 | 0.002420 | 33.656711 |
| building | L14_B05 | A | 0.006680 | 0.020996 | 291.999282 |
| building | L14_B05 | B | 0.004226 | 0.011505 | 160.006990 |
| equal_weight_buildings | development_buildings | baseline_mean | 1.302465 | 1.378421 | 2381.906987 |
| equal_weight_buildings | development_buildings | baseline_calendar_use | 0.275201 | 0.354074 | 27.377115 |
| equal_weight_buildings | development_buildings | A | 0.193793 | 0.302083 | 149.757982 |
| equal_weight_buildings | development_buildings | B | 0.183303 | 0.293920 | 91.137911 |

On equal-weight validation-building RMSE, A (**0.302083**) and B (**0.293920**) outperform the calendar baseline (**0.354074**) and global mean (**1.378421**). The calendar baseline nevertheless has much lower mean nRMSE (**27.38%**, versus **149.76% for A** and **91.14% for B**) and beats both models on each L14 validation building. L03's scale strongly influences the predefined raw-RMSE criterion. These findings do not justify changing the preregistered criterion after scoring.

After refitting all four methods on all development rows, final held-out metrics are:

| scope | name | model | mae_kwh_per_m2 | rmse_kwh_per_m2 | nrmse_pct |
| --- | --- | --- | --- | --- | --- |
| building | L07_B01 | baseline_mean | 0.244410 | 0.246401 | 226.627081 |
| building | L07_B01 | baseline_calendar_use | 0.244578 | 0.264407 | 243.188294 |
| building | L07_B01 | A | 0.102940 | 0.109689 | 100.886915 |
| building | L07_B01 | B | 0.122098 | 0.148197 | 136.304072 |
| building | L14_B01 | baseline_mean | 0.343425 | 0.343511 | 3537.725473 |
| building | L14_B01 | baseline_calendar_use | 3.158873 | 3.326892 | 34262.777810 |
| building | L14_B01 | A | 0.044939 | 0.065300 | 672.504259 |
| building | L14_B01 | B | 0.020157 | 0.029735 | 306.234612 |
| building | L14_B02 | baseline_mean | 0.338407 | 0.338482 | 2298.127214 |
| building | L14_B02 | baseline_calendar_use | 0.338313 | 0.357611 | 2428.005689 |
| building | L14_B02 | A | 0.047073 | 0.066911 | 454.294371 |
| building | L14_B02 | B | 0.017874 | 0.029196 | 198.223469 |
| building | L14_B03 | baseline_mean | 0.347726 | 0.347750 | 6428.255756 |
| building | L14_B03 | baseline_calendar_use | 3.159781 | 3.328016 | 61519.393857 |
| building | L14_B03 | A | 3.193025 | 3.437690 | 63546.744081 |
| building | L14_B03 | B | 3.195333 | 3.440189 | 63592.943590 |
| location | L07 | baseline_mean | 0.244410 | 0.246401 | 226.627081 |
| location | L07 | baseline_calendar_use | 0.244578 | 0.264407 | 243.188294 |
| location | L07 | A | 0.102940 | 0.109689 | 100.886915 |
| location | L07 | B | 0.122098 | 0.148197 | 136.304072 |
| location | L14 | baseline_mean | 0.343199 | 0.343281 | 3454.783165 |
| location | L14 | baseline_calendar_use | 2.221880 | 2.726747 | 27441.994302 |
| location | L14 | A | 1.100768 | 1.990919 | 20036.618571 |
| location | L14 | B | 1.083598 | 1.991781 | 20045.293192 |
| equal_weight_locations | L07_and_L14 | baseline_mean | 0.293805 | 0.294841 | 1840.705123 |
| equal_weight_locations | L07_and_L14 | baseline_calendar_use | 1.233229 | 1.495577 | 13842.591298 |
| equal_weight_locations | L07_and_L14 | A | 0.601854 | 1.050304 | 10068.752743 |
| equal_weight_locations | L07_and_L14 | B | 0.602848 | 1.069989 | 10090.798632 |

The refitted global mean and calendar/building-use baselines match their original with-L03/current-weather values, because their fitting pool and definitions are unchanged. On equal-weight test-location RMSE, A/B are **256.23%/262.90% worse than the global mean**, but **29.77%/28.46% better than the calendar baseline**. Their MAEs are also worse than the global mean and better than the calendar baseline. Full percentage tables are saved alongside metrics. Positive error reduction means improvement, and zero references are handled with empty values and reasons.

Weather still has mixed transfer results. Compared with A, B increases equal-location MAE by **0.165%** and RMSE by **1.874%**. B reduces RMSE for L14_B01/B02 but worsens L07 and slightly worsens L14_B03. L14_B03 RMSE remains **3.437690 for A** and **3.440189 for B**. Thus validation-selected settings do not establish satisfactory transfer or a general weather benefit.

These tests are **previously inspected**. This is a validation-guided follow-up, not a new untouched final-test estimate. Validation measures later periods of known buildings; test metrics measure transfer to unseen buildings, with L07 also an unseen location. Better known-building validation does not guarantee transfer improvement. No L03 rescaling/exclusion, feature change, weather-timing change, target shift or extra search was introduced in response to these results. Predictive differences do not establish causation.

![Validation comparison for the three predefined candidates](<Prediction Model/experiments/validation/run_20261025T091525_455049Z/charts/validation_candidate_comparison.png>)

![Validation-guided final RMSE by test location](<Prediction Model/experiments/validation/run_20261025T091525_455049Z/charts/final_rmse_by_test_location.png>)

The final MAE chart, every candidate's predictions/metrics, all fitted pipelines, both fitting-stage baselines, exact split membership and provenance are included in the file guide.

### 4.10 Six academic report figures (26 October)

These figures replace the user-cleared **main** `Prediction Model/charts/` folder. They use the latest validation-selected/refitted models, while the earlier experiment-specific charts remain available in their own folders. This is a presentation update from saved results, not a new experiment or new model selection.

| Figure | Visual | PNG | SVG |
| --- | --- | --- | --- |
| 1 | Experimental workflow | [figure_1_workflow.png](<Prediction Model/charts/figure_1_workflow.png>) | [Vector SVG](<Prediction Model/charts/figure_1_workflow.svg>) |
| 2 | Training, validation and test timeline | [figure_2_data_split.png](<Prediction Model/charts/figure_2_data_split.png>) | [Vector SVG](<Prediction Model/charts/figure_2_data_split.svg>) |
| 3 | Validation candidate comparison | [figure_3_validation_rmse.png](<Prediction Model/charts/figure_3_validation_rmse.png>) | [Vector SVG](<Prediction Model/charts/figure_3_validation_rmse.svg>) |
| 4 | Models and baselines by test building | [figure_4_test_rmse.png](<Prediction Model/charts/figure_4_test_rmse.png>) | [Vector SVG](<Prediction Model/charts/figure_4_test_rmse.svg>) |
| 5 | Actual versus predicted consumption | [figure_5_actual_vs_predicted.png](<Prediction Model/charts/figure_5_actual_vs_predicted.png>) | [Vector SVG](<Prediction Model/charts/figure_5_actual_vs_predicted.svg>) |
| 6 | Weather contribution | [figure_6_weather_contribution.png](<Prediction Model/charts/figure_6_weather_contribution.png>) | [Vector SVG](<Prediction Model/charts/figure_6_weather_contribution.svg>) |

[The caption document](<Prediction Model/charts/captions.md>) supplies an academic caption and preview for every figure, plus reproduction information. [generate_report_figures.py](<Prediction Model/generate_report_figures.py>) is the plotting source; `figure_manifest.json` records exact versions, source/output hashes, colour assignments, pixel sizes, checks and the original windows. Five `figure_*_plot_data.csv` files expose the plotted numerical values and 672 selected time-series rows.

Figure 3 uses the three-candidate validation RMSEs in Section 4.9. Figure 4 compares all four methods separately for L07_B01 and L14_B01/B02/B03; it does not substitute location averages for building results. Figure 6 uses exactly those same building-level errors:

| Building | RMSE A (kWh/m²) | RMSE B (kWh/m²) | Delta RMSE (kWh/m²) | Weather comparison |
| --- | --- | --- | --- | --- |
| L07_B01 | 0.109689 | 0.148197 | -0.038507 | Higher error with weather |
| L14_B01 | 0.065300 | 0.029735 | +0.035565 | Lower error with weather |
| L14_B02 | 0.066911 | 0.029196 | +0.037716 | Lower error with weather |
| L14_B03 | 3.437690 | 3.440189 | -0.002499 | Higher error with weather |

Figure 5 shows genuine forecast failures, including negative values and large L14_B03 errors; no clipping, smoothing, rescaling or favourable period selection was applied. Its actual-only inset makes that building's demand variation visible without disguising the full-scale forecast discrepancy. Weather differences remain conditional predictive comparisons under the existing availability assumption, not causal evidence. Validation and final tests retain the limitations in Sections 3–4.

![Latest-model actual-versus-predicted report figure](<Prediction Model/charts/figure_5_actual_vs_predicted.png>)

## 5. File-by-file guide

This guide covers every current substantive project file individually, plus this report. It excludes `.git` internals, installed dependency files inside `.venv`, Python bytecode caches and macOS `.DS_Store` files. Those are described as folder/system roles below. CSV row counts exclude headers; a dash means that a row count is not applicable.

### 5.1 Project-root files

5 files.

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `.gitignore` | Currently empty root-level Git-ignore placeholder; the modelling folder has its own active ignore rules. | — |
| `ADRENALIN_data_description.pdf` | Dataset reference PDF, now reviewed for UTC timestamps, reanalysis weather sources, anonymisation, resampling and measurement limitations; it does not establish selected-weather availability or an L03-specific unit correction. | — |
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

### 5.4 Original modelling inputs, implementation and preserved artifacts

33 currently present files. Six historical main-folder PNGs were removed by the user on 26 October; their replacement figure set is documented in Section 5.7.

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
| `Prediction Model/train_models.py` | Preserved original training/evaluation implementation. The follow-up runner reuses its fixed feature, pipeline and setting definitions without invoking its original output-writing entry point. | — |

### 5.5 New follow-up implementation and outputs

The following files extend the original inventory. The four cases are saved separately, and repeated artifact names have the same role within their explicitly named case.

#### Follow-up implementation

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `Prediction Model/run_followup_experiments.py` | New safe runner for the four fixed exploratory experiments; exact timestamp weather joins, both baselines, nRMSE, checks, charts and separate per-run outputs. Reuses the original model definitions. | — |
| `Prediction Model/test_followup_experiments.py` | Ten focused persisted tests for fallback levels/row weighting, lag gaps and location isolation, undefined nRMSE/reference errors, original windows, unique/protected output paths and fixed features/settings. | — |

#### Follow-up batch summaries, provenance and archived report

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/all_experiment_metrics.csv` | All 112 metric rows across four experiments, with explicit training configuration and weather timing, MAE/RMSE, nRMSE and undefined-reason/aggregation fields. | 112 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/batch_manifest.json` | Completed batch provenance: settings/features, versions, source hashes, experiment names, original preservation checks, shared evaluation rows and reused chart windows. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/command.txt` | Canonical exact reproduction command with environment, output root and thread settings; reruns create a new run directory. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/dependency_versions.json` | Exact Python and direct modelling-library versions for the follow-up batch. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/documentation_evidence.json` | Reviewed local PDF page/code evidence and unresolved prediction-timing, weather-availability and L03-unit questions. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/environment_freeze.txt` | Complete pip-freeze environment snapshot captured for the follow-up run. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/l03_influence_all_groups.csv` | Controlled with-L03 versus without-L03 error differences/reductions for each fixed timing, method, building/location and location average. | 56 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/l03_influence_by_building.csv` | Compact 32-row building-specific L03 influence comparison across both timings and all four methods. | 32 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/l03_influence_rmse.png` | Four-panel RMSE comparison showing removal of L03 for A/B under each fixed weather timing. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/methodology_and_findings.md` | Report-ready timing evidence, fixed design, baselines, nRMSE definition, actual follow-up findings, limitations and reproduction information. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/original_preservation_hashes.json` | Historical hashes of 25 original/progress files at run completion. The prior root-report hash is now traceable via the archived pre-update report. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/progress_report_before_followup_update.md` | Verbatim pre-update progress report, archived before the subsequently authorised root-report update; matches the report hash recorded at follow-up completion. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/requirements_versions.txt` | Pinned direct dependency versions for reproducing the follow-up environment. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/target_distributions.csv` | Seven building distributions: count, mean, median, selected percentiles, minimum/maximum, retained units and original/diagnostic roles. | 7 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/verification_summary.json` | Independent verification record: 10 focused tests, 112 metric rows, training-only baseline reconstruction, timing/row/window invariance, hashes and 29 charts. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/weather_effect_all_experiments.csv` | Model B versus A MAE/RMSE/nRMSE reductions for every building, location and location average in all four cases. | 28 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/weather_join_audit.csv` | 84 per-field weather-join audit rows: seven buildings × six fields × two timings, with exact matches and missing values. | 84 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/weather_timing_comparison.csv` | Controlled current versus t−1-hour weather comparison at each fixed training pool and method; non-weather methods are invariant. | 56 |

#### Case: `with_L03__current_weather`

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/charts/L07_B01_original_seven_day_window.png` | Actual versus both baselines and A/B for L07_B01, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/charts/L14_B01_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B01, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/charts/L14_B02_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B02, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/charts/L14_B03_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B03, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/charts/mae_kwh_per_m2_by_test_location.png` | MAE bar chart by test location for both baselines and both models; kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/charts/nrmse_pct_by_test_location.png` | Mean-normalised RMSE bar chart by location for all four methods; percentage of the location observed mean. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/charts/rmse_kwh_per_m2_by_test_location.png` | RMSE bar chart by test location for both baselines and both models; kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/models/baseline_mean.joblib` | Refitted global training-mean DummyRegressor for this training pool. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/models/calendar_use_baseline.json` | Training-only calendar/building-use lookup means and counts, four-level fallback, UTC convention and fit-building identities. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/models/fitted_preprocessing_audit.json` | A/B training rows/IDs, fitted numerical medians, category vocabularies, encoded features and training-only verification flags. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/models/model_A_pipeline.joblib` | Fitted original-definition Model A and preprocessing for this training pool; no weather predictors. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/models/model_B_pipeline.joblib` | Fitted original-definition Model B and preprocessing for this training pool and weather timing. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/results/baseline_comparisons.csv` | 28 A/B comparisons against both baselines, including MAE/RMSE/nRMSE reductions and undefined-reference reasons. | 28 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/results/chart_periods.csv` | Unchanged four original seven-day chart windows; no performance-based reselection. | 4 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/results/metrics.csv` | 28 metric rows: four methods for four buildings, two pooled locations and the equal-weight average of location metrics. | 28 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/results/predictors.csv` | Exact raw and training-fitted encoded predictor lists for A/B in this experiment. | 114 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/results/run_manifest.json` | Case-specific training/test allocation, rows, fixed settings/features, timing, baselines/fallbacks, hashes and verification results. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/results/run_summary.txt` | Readable case summary with assumptions, all metrics, weather reductions and both-baseline comparisons. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/results/split_membership.csv` | Seven building roles and row counts; L03 is excluded only in the diagnostic cases. | 7 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/results/test_predictions.csv` | 118,887 original-aligned actuals and all four predictions, IDs, source row numbers, interval/weather timestamps and baseline fallback levels. | 118,887 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__current_weather/results/weather_error_reductions.csv` | Seven Model B-versus-A comparisons with MAE/RMSE/nRMSE reductions at building/location/equal-weight levels. | 7 |

#### Case: `with_L03__lagged_weather_1h`

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/charts/L07_B01_original_seven_day_window.png` | Actual versus both baselines and A/B for L07_B01, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/charts/L14_B01_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B01, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/charts/L14_B02_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B02, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/charts/L14_B03_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B03, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/charts/mae_kwh_per_m2_by_test_location.png` | MAE bar chart by test location for both baselines and both models; kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/charts/nrmse_pct_by_test_location.png` | Mean-normalised RMSE bar chart by location for all four methods; percentage of the location observed mean. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/charts/rmse_kwh_per_m2_by_test_location.png` | RMSE bar chart by test location for both baselines and both models; kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/models/baseline_mean.joblib` | Refitted global training-mean DummyRegressor for this training pool. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/models/calendar_use_baseline.json` | Training-only calendar/building-use lookup means and counts, four-level fallback, UTC convention and fit-building identities. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/models/fitted_preprocessing_audit.json` | A/B training rows/IDs, fitted numerical medians, category vocabularies, encoded features and training-only verification flags. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/models/model_A_pipeline.joblib` | Fitted original-definition Model A and preprocessing for this training pool; no weather predictors. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/models/model_B_pipeline.joblib` | Fitted original-definition Model B and preprocessing for this training pool and weather timing. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/results/baseline_comparisons.csv` | 28 A/B comparisons against both baselines, including MAE/RMSE/nRMSE reductions and undefined-reference reasons. | 28 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/results/chart_periods.csv` | Unchanged four original seven-day chart windows; no performance-based reselection. | 4 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/results/metrics.csv` | 28 metric rows: four methods for four buildings, two pooled locations and the equal-weight average of location metrics. | 28 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/results/predictors.csv` | Exact raw and training-fitted encoded predictor lists for A/B in this experiment. | 114 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/results/run_manifest.json` | Case-specific training/test allocation, rows, fixed settings/features, timing, baselines/fallbacks, hashes and verification results. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/results/run_summary.txt` | Readable case summary with assumptions, all metrics, weather reductions and both-baseline comparisons. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/results/split_membership.csv` | Seven building roles and row counts; L03 is excluded only in the diagnostic cases. | 7 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/results/test_predictions.csv` | 118,887 original-aligned actuals and all four predictions, IDs, source row numbers, interval/weather timestamps and baseline fallback levels. | 118,887 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/with_L03__lagged_weather_1h/results/weather_error_reductions.csv` | Seven Model B-versus-A comparisons with MAE/RMSE/nRMSE reductions at building/location/equal-weight levels. | 7 |

#### Case: `without_L03__current_weather`

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/charts/L07_B01_original_seven_day_window.png` | Actual versus both baselines and A/B for L07_B01, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/charts/L14_B01_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B01, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/charts/L14_B02_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B02, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/charts/L14_B03_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B03, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/charts/mae_kwh_per_m2_by_test_location.png` | MAE bar chart by test location for both baselines and both models; kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/charts/nrmse_pct_by_test_location.png` | Mean-normalised RMSE bar chart by location for all four methods; percentage of the location observed mean. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/charts/rmse_kwh_per_m2_by_test_location.png` | RMSE bar chart by test location for both baselines and both models; kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/models/baseline_mean.joblib` | Refitted global training-mean DummyRegressor for this training pool. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/models/calendar_use_baseline.json` | Training-only calendar/building-use lookup means and counts, four-level fallback, UTC convention and fit-building identities. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/models/fitted_preprocessing_audit.json` | A/B training rows/IDs, fitted numerical medians, category vocabularies, encoded features and training-only verification flags. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/models/model_A_pipeline.joblib` | Fitted original-definition Model A and preprocessing for this training pool; no weather predictors. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/models/model_B_pipeline.joblib` | Fitted original-definition Model B and preprocessing for this training pool and weather timing. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/results/baseline_comparisons.csv` | 28 A/B comparisons against both baselines, including MAE/RMSE/nRMSE reductions and undefined-reference reasons. | 28 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/results/chart_periods.csv` | Unchanged four original seven-day chart windows; no performance-based reselection. | 4 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/results/metrics.csv` | 28 metric rows: four methods for four buildings, two pooled locations and the equal-weight average of location metrics. | 28 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/results/predictors.csv` | Exact raw and training-fitted encoded predictor lists for A/B in this experiment. | 110 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/results/run_manifest.json` | Case-specific training/test allocation, rows, fixed settings/features, timing, baselines/fallbacks, hashes and verification results. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/results/run_summary.txt` | Readable case summary with assumptions, all metrics, weather reductions and both-baseline comparisons. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/results/split_membership.csv` | Seven building roles and row counts; L03 is excluded only in the diagnostic cases. | 7 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/results/test_predictions.csv` | 118,887 original-aligned actuals and all four predictions, IDs, source row numbers, interval/weather timestamps and baseline fallback levels. | 118,887 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__current_weather/results/weather_error_reductions.csv` | Seven Model B-versus-A comparisons with MAE/RMSE/nRMSE reductions at building/location/equal-weight levels. | 7 |

#### Case: `without_L03__lagged_weather_1h`

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/charts/L07_B01_original_seven_day_window.png` | Actual versus both baselines and A/B for L07_B01, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/charts/L14_B01_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B01, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/charts/L14_B02_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B02, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/charts/L14_B03_original_seven_day_window.png` | Actual versus both baselines and A/B for L14_B03, using its original fixed seven-day window, UTC and kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/charts/mae_kwh_per_m2_by_test_location.png` | MAE bar chart by test location for both baselines and both models; kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/charts/nrmse_pct_by_test_location.png` | Mean-normalised RMSE bar chart by location for all four methods; percentage of the location observed mean. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/charts/rmse_kwh_per_m2_by_test_location.png` | RMSE bar chart by test location for both baselines and both models; kWh/m². | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/models/baseline_mean.joblib` | Refitted global training-mean DummyRegressor for this training pool. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/models/calendar_use_baseline.json` | Training-only calendar/building-use lookup means and counts, four-level fallback, UTC convention and fit-building identities. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/models/fitted_preprocessing_audit.json` | A/B training rows/IDs, fitted numerical medians, category vocabularies, encoded features and training-only verification flags. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/models/model_A_pipeline.joblib` | Fitted original-definition Model A and preprocessing for this training pool; no weather predictors. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/models/model_B_pipeline.joblib` | Fitted original-definition Model B and preprocessing for this training pool and weather timing. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/results/baseline_comparisons.csv` | 28 A/B comparisons against both baselines, including MAE/RMSE/nRMSE reductions and undefined-reference reasons. | 28 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/results/chart_periods.csv` | Unchanged four original seven-day chart windows; no performance-based reselection. | 4 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/results/metrics.csv` | 28 metric rows: four methods for four buildings, two pooled locations and the equal-weight average of location metrics. | 28 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/results/predictors.csv` | Exact raw and training-fitted encoded predictor lists for A/B in this experiment. | 110 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/results/run_manifest.json` | Case-specific training/test allocation, rows, fixed settings/features, timing, baselines/fallbacks, hashes and verification results. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/results/run_summary.txt` | Readable case summary with assumptions, all metrics, weather reductions and both-baseline comparisons. | — |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/results/split_membership.csv` | Seven building roles and row counts; L03 is excluded only in the diagnostic cases. | 7 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/results/test_predictions.csv` | 118,887 original-aligned actuals and all four predictions, IDs, source row numbers, interval/weather timestamps and baseline fallback levels. | 118,887 |
| `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/without_L03__lagged_weather_1h/results/weather_error_reductions.csv` | Seven Model B-versus-A comparisons with MAE/RMSE/nRMSE reductions at building/location/equal-weight levels. | 7 |

### 5.6 New validation implementation and artifacts

65 new files. Validation candidates retain separate model/result folders; shared fitting-stage baselines are saved once. Final refits and tests have their own folders. Earlier outputs remain intact.

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `Prediction Model/run_validation_experiment.py` | Separate safe validation runner: per-building chronology, three preregistered candidates, shared validation-only selection, full-development refit, baselines, checks and new outputs. | — |
| `Prediction Model/test_validation_experiment.py` | Eight focused tests for duplicate timestamp grouping, per-building cutoffs/rounding, missing targets, shared selection/ties, fixed candidates, metric aggregation and fitting isolation. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/alignment_audits.json` | Seven existing-loader audits of source identity, row counts, mirrored target alignment, timestamps, hashes and eligibility. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/candidate_plan.json` | Candidate configurations, raw predictor lists, split and selection rules preregistered before fitting/scoring; test data not loaded. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/charts/final_mae_by_test_location.png` | Final location MAE comparison for both baselines and models, distinguishing unseen-location/building tests. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/charts/final_rmse_by_test_location.png` | Final location RMSE comparison for both baselines and models, distinguishing unseen-location/building tests. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/charts/validation_candidate_comparison.png` | Labelled A/B validation RMSE bars, both baseline references, shared selection scores and chosen candidate. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/command.txt` | Exact command and thread setting; reruns create another timestamped directory. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/dependency_versions.json` | Exact Python and modelling-library versions. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/development_row_membership.csv` | Complete development row identities/timestamps, fit/validation role and finite-target eligibility. | 80665 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/environment_freeze.txt` | Complete pip-freeze environment snapshot. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/models/baseline_mean.joblib` | Full-development fitted global-mean DummyRegressor; shared across candidates during validation. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/models/calendar_use_baseline.json` | Full-development training-only calendar/building-use lookup means, counts and fallback rules. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/models/fitted_preprocessing_audit.json` | Full-development refit: verified medians, categorical vocabularies, encoded predictors and fitting identities/counts for A/B. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/models/model_A_pipeline.joblib` | Full-development refit: fitted Model A HistGradientBoostingRegressor and its training-only preprocessing. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/models/model_B_pipeline.joblib` | Full-development refit: fitted Model B HistGradientBoostingRegressor and its training-only preprocessing. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/models/predictors.csv` | Full-development refit: exact raw and fitted encoded predictors for A and B. | 114 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/results/L07_B01_predictions.csv` | L07_B01 final held-out actuals/predictions, preserving original test row identities and timestamps. | 9543 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/results/L14_B01_predictions.csv` | L14_B01 final held-out actuals/predictions, preserving original test row identities and timestamps. | 36360 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/results/L14_B02_predictions.csv` | L14_B02 final held-out actuals/predictions, preserving original test row identities and timestamps. | 36336 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/results/L14_B03_predictions.csv` | L14_B03 final held-out actuals/predictions, preserving original test row identities and timestamps. | 36648 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/results/baseline_comparisons.csv` | Final test A/B comparisons against both baselines; MAE/RMSE/nRMSE percentage reductions and undefined reasons. | 28 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/results/metrics.csv` | 28 final test metrics: buildings, pooled locations and equal-location average, for both models/baselines with MAE/RMSE/nRMSE. | 28 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/results/test_predictions.csv` | 118,887 original-aligned test rows, actuals, all four predictions, identities/timestamps and calendar fallback levels. | 118887 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/final/results/weather_error_reductions.csv` | Final test B-versus-A MAE/RMSE/nRMSE comparisons with safe reference-denominator handling. | 7 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/independent_verification.json` | Independent 76-row metric recomputation, all-stage preprocessing/alignment/selection checks, eight passing tests and preservation evidence. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/methodology_and_results.md` | Concise experiment design, known-building validation interpretation, actual scores/results, limitations and commands. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/preservation_hashes.json` | SHA-256 snapshot of 223 pre-existing substantive files, including all prior experiments and sources, verified unchanged before report update. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/progress_report_before_validation_update.md` | Verbatim report immediately before this update; preserves its historical hash without altering either older experiment family. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/requirements_versions.txt` | Pinned direct dependency versions for this experiment. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/run_manifest.json` | Completed run provenance: splits, candidates, chosen settings, stage events, features, versions, hashes, assumptions and counts. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/selected_settings.json` | Single shared selected configuration and selection scores, saved before loading test data. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/selection_scores.csv` | Three A/B validation-building macro RMSE pairs, shared scores, settings and selected flag. | 3 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/split_boundaries.csv` | Per-building earliest-80%/latest-20% boundaries, unique timestamp counts, raw/eligible rows and zero-overlap checks. | 3 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/stage_events.json` | UTC event sequence: preregistration, candidate fits, saved selection, full refit, test load and verification. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/all_candidate_metrics.csv` | All 48 validation metric rows: three candidates × four methods × three buildings plus equal-building average. | 48 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/baselines/baseline_mean.joblib` | Earliest-80% fitted global-mean DummyRegressor; shared across candidates during validation. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/baselines/calendar_use_baseline.json` | Earliest-80% training-only calendar/building-use lookup means, counts and fallback rules. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_1/models/fitted_preprocessing_audit.json` | Earliest-80% candidate fit: verified medians, categorical vocabularies, encoded predictors and fitting identities/counts for A/B. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_1/models/model_A_pipeline.joblib` | Earliest-80% candidate fit: fitted Model A HistGradientBoostingRegressor and its training-only preprocessing. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_1/models/model_B_pipeline.joblib` | Earliest-80% candidate fit: fitted Model B HistGradientBoostingRegressor and its training-only preprocessing. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_1/models/predictors.csv` | Earliest-80% candidate fit: exact raw and fitted encoded predictors for A and B. | 114 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_1/results/baseline_comparisons.csv` | Candidate validation A/B comparisons against both baselines; MAE/RMSE/nRMSE percentage reductions and undefined reasons. | 16 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_1/results/metrics.csv` | 16 validation metrics: three buildings and equal-building average, for both models/baselines with MAE/RMSE/nRMSE. | 16 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_1/results/validation_predictions.csv` | 16,134 identical validation rows, source identities/timestamps, actuals, all four predictions and calendar fallback levels. | 16134 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_1/results/weather_error_reductions.csv` | Candidate validation B-versus-A MAE/RMSE/nRMSE comparisons with safe reference-denominator handling. | 4 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_2/models/fitted_preprocessing_audit.json` | Earliest-80% candidate fit: verified medians, categorical vocabularies, encoded predictors and fitting identities/counts for A/B. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_2/models/model_A_pipeline.joblib` | Earliest-80% candidate fit: fitted Model A HistGradientBoostingRegressor and its training-only preprocessing. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_2/models/model_B_pipeline.joblib` | Earliest-80% candidate fit: fitted Model B HistGradientBoostingRegressor and its training-only preprocessing. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_2/models/predictors.csv` | Earliest-80% candidate fit: exact raw and fitted encoded predictors for A and B. | 114 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_2/results/baseline_comparisons.csv` | Candidate validation A/B comparisons against both baselines; MAE/RMSE/nRMSE percentage reductions and undefined reasons. | 16 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_2/results/metrics.csv` | 16 validation metrics: three buildings and equal-building average, for both models/baselines with MAE/RMSE/nRMSE. | 16 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_2/results/validation_predictions.csv` | 16,134 identical validation rows, source identities/timestamps, actuals, all four predictions and calendar fallback levels. | 16134 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_2/results/weather_error_reductions.csv` | Candidate validation B-versus-A MAE/RMSE/nRMSE comparisons with safe reference-denominator handling. | 4 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_3/models/fitted_preprocessing_audit.json` | Earliest-80% candidate fit: verified medians, categorical vocabularies, encoded predictors and fitting identities/counts for A/B. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_3/models/model_A_pipeline.joblib` | Earliest-80% candidate fit: fitted Model A HistGradientBoostingRegressor and its training-only preprocessing. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_3/models/model_B_pipeline.joblib` | Earliest-80% candidate fit: fitted Model B HistGradientBoostingRegressor and its training-only preprocessing. | — |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_3/models/predictors.csv` | Earliest-80% candidate fit: exact raw and fitted encoded predictors for A and B. | 114 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_3/results/baseline_comparisons.csv` | Candidate validation A/B comparisons against both baselines; MAE/RMSE/nRMSE percentage reductions and undefined reasons. | 16 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_3/results/metrics.csv` | 16 validation metrics: three buildings and equal-building average, for both models/baselines with MAE/RMSE/nRMSE. | 16 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_3/results/validation_predictions.csv` | 16,134 identical validation rows, source identities/timestamps, actuals, all four predictions and calendar fallback levels. | 16134 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/candidate_3/results/weather_error_reductions.csv` | Candidate validation B-versus-A MAE/RMSE/nRMSE comparisons with safe reference-denominator handling. | 4 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/fitting_rows.csv` | 64,531 eligible fitting row IDs, source positions and interval timestamps. | 64531 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/validation/validation_rows.csv` | 16,134 eligible validation row IDs, source positions and interval timestamps. | 16134 |
| `Prediction Model/experiments/validation/run_20261025T091525_455049Z/verification_summary.json` | Automated experiment checks for split/row isolation, training-only fits, saved estimators/metrics, preregistration and preservation. | — |

### 5.7 Academic report figure implementation and outputs

20 files added for the report figure set, replacing the six user-removed main-folder images. The 29 sensitivity and three validation-specific images are preserved separately.

| File | Purpose | CSV data rows |
| --- | --- | --- |
| `Prediction Model/generate_report_figures.py` | Read-only plotting entry point for all six academic figures; checks saved results/alignment, exports PNG/SVG/captions/data/provenance and protects existing filenames. | — |
| `Prediction Model/charts/figure_1_workflow.png` | Experimental workflow: 320 DPI raster figure. Three sources, feature/target construction, development/test separation, chronological validation, full refit and final evaluation. Test data bypass model development. | — |
| `Prediction Model/charts/figure_1_workflow.svg` | Experimental workflow: matching vector figure with editable text. | — |
| `Prediction Model/charts/figure_2_data_split.png` | Training, validation and test timeline: 320 DPI raster figure. Seven building bars with per-building chronological cutoffs, actual UTC coverage and fitting/validation/test row counts. Coverage spans include gaps; widths represent elapsed time. | — |
| `Prediction Model/charts/figure_2_data_split.svg` | Training, validation and test timeline: matching vector figure with editable text. | — |
| `Prediction Model/charts/figure_3_validation_rmse.png` | Validation candidate comparison: 320 DPI raster figure. Two bars per predefined configuration; equal-weight validation-building RMSE. Configuration 2 is best for both models and is the shared selected setting. | — |
| `Prediction Model/charts/figure_3_validation_rmse.svg` | Validation candidate comparison: matching vector figure with editable text. | — |
| `Prediction Model/charts/figure_4_test_rmse.png` | Models and baselines by test building: 320 DPI raster figure. Four adjacent method bars per held-out building using RMSE recomputed from the latest final predictions. | — |
| `Prediction Model/charts/figure_4_test_rmse.svg` | Models and baselines by test building: matching vector figure with editable text. | — |
| `Prediction Model/charts/figure_5_actual_vs_predicted.png` | Actual versus predicted consumption: 320 DPI raster figure. Four panels of actual/A/B over the original first complete seven-day window per building. Independent y scales; negative predictions retained; actual-only L14_B03 inset. | — |
| `Prediction Model/charts/figure_5_actual_vs_predicted.svg` | Actual versus predicted consumption: matching vector figure with editable text. | — |
| `Prediction Model/charts/figure_6_weather_contribution.png` | Weather contribution: 320 DPI raster figure. Delta RMSE = RMSE(A) minus RMSE(B), using Figure 4 values. Positive improves accuracy with weather; negative worsens it. Zero reference line and signed labels. | — |
| `Prediction Model/charts/figure_6_weather_contribution.svg` | Weather contribution: matching vector figure with editable text. | — |
| `Prediction Model/charts/captions.md` | Six concise academic captions and figure previews; source-experiment identity, limitations, dependencies and rendering command. | — |
| `Prediction Model/charts/figure_manifest.json` | Selected experiment/settings, exact library versions, source/output hashes, colour mapping, 320 DPI dimensions, verification and six user-removed historical chart paths. | — |
| `Prediction Model/charts/figure_2_plot_data.csv` | Ten chronological timeline segments: three fit, three validation and four test, with UTC boundaries and counts. | 10 |
| `Prediction Model/charts/figure_3_plot_data.csv` | Six candidate/model validation macro RMSE values and their actual leaf settings. | 6 |
| `Prediction Model/charts/figure_4_plot_data.csv` | Sixteen building/method test RMSEs recomputed from the saved final predictions. | 16 |
| `Prediction Model/charts/figure_5_plot_data.csv` | 672 original-window observations with source row numbers, timestamps, actual consumption and latest A/B predictions. | 672 |
| `Prediction Model/charts/figure_6_plot_data.csv` | Four building-specific A/B RMSE pairs and their signed difference, identical to the values used in Figure 4. | 4 |

### 5.8 Supporting folders and system files

- `Prediction Model/.venv/`: installed Python environment used to execute training and make charts. Its package internals are not individual project implementations and are excluded from the file-by-file tables.
- `.git/`: version-control database and history, not an input to the modelling pipeline.
- `__pycache__/` and `*.pyc`, when present: generated Python bytecode caches.
- `.DS_Store`, when present: macOS Finder metadata, unrelated to consumption or model results.

The guide contains **300 currently present project files**, including this report and both archived prior versions. Relative to the 286-file validation inventory, the user removed six original main-folder PNGs and this task added 20 plotting/figure artifacts. The 65 validation implementation/artifact files remain intact. No absent IDE placeholders or deleted images are counted.

## 6. Verification completed

### 6.1 Existing automated tests

During preparation of the initial report, all 65 existing data-cleaning tests passed using temporary fixtures. A further 10 focused follow-up tests passed during the correction work; the latter are recorded separately below. The earlier suites were not rerun for the new experiment; eight focused validation tests were run separately, and the requested new models were fitted as described in Section 6.4. The earlier preparation-suite result was:

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

### 6.3 Follow-up verification

`Prediction Model/test_followup_experiments.py` passed **10 focused tests**, covering all four calendar-baseline fallback levels, training-row weighting and persistence, exact lag joins across gaps and locations, duplicate-weather rejection, nRMSE/zero-denominator handling, equal-location aggregation, fixed chart windows, unique output directories and protected original paths. Together with the earlier 65-test preparation suite, this records **75 passing tests across the two suites**; they were not a single combined test invocation.

The completed follow-up batch additionally verified:

- All four cases use the same original **118,887 test rows**, IDs, timestamps, row order and targets; no additional target shift or weather-based eligibility filter was introduced.
- Active staged inputs/targets match the original saved hashes. Original weather sources, preparation code, documentation and model definitions were hashed before and after the runs.
- Fitted imputer medians and categorical vocabularies match allowed training rows only. Both baselines' means and all calendar lookup group counts were independently reconstructed from each allowed training pool.
- The with-L03/current-weather case reproduces original A/B/global-mean predictions. A and both baselines are invariant to the weather-timing change within a fixed training pool.
- All **112** saved metric rows agree with predictions. Independent numerical checks covered **96** building/location rows and the **16** location-average rows; saved comparison reductions were also checked.
- Saved pipelines and baseline information reproduce their predictions. All **29** new charts use the original windows or the explicit location/diagnostic comparisons.
- The 25 original/code/progress files recorded at run completion were unchanged then. This later authorised progress-report edit is documented separately: the archived pre-update report matches its historical SHA-256, while original model/data/output files still retain their hashes.

See `Prediction Model/experiments/timing_L03/run_20261025T021409_544191Z/verification_summary.json`, the batch manifest and each case's verification fields. Test commands and exact dependency versions are retained. The sensitivity artifacts remain unchanged. Section 4.10 documents the subsequent user removal of six original main-folder images and their replacement with the latest-model academic figure set; source datasets, settings, metrics, predictions and fitted models are unchanged.

### 6.4 Chronological validation and selection verification

Eight tests in `Prediction Model/test_validation_experiment.py` passed. They cover joint row/timestamp membership with unsorted and duplicate timestamps; per-building cutoffs and floor rounding; missing targets without moving cutoffs; the shared A/B validation-only selection and tie-break; unchanged other settings; equal-building metrics/undefined reasons; training-only preprocessing; and rejection of test buildings during fitting. Across the three separately executed persisted suites, **83 tests have passed** (65 preparation + 10 sensitivity + 8 validation); this is not a single combined invocation.

The completed experiment and independent artifact audit additionally checked:

- Fitting/validation timestamps and source-row IDs are disjoint within every building and together cover all development rows; duplicate timestamps cannot cross the boundary.
- All seven staged input/target pairs match row by row. Predictions retain source row positions, interval bounds and actual targets; the same 16,134 validation rows are used by all candidates/methods and the same original 118,887 test rows are retained.
- Candidate registration precedes fitting/scoring; the shared winner is independently reconstructed from validation scores. Selected settings precede test loading and refitting uses only development rows. The recorded sequence is registration → candidate fitting/scoring → saved selection → full-development refit → test load/evaluation.
- Numerical medians and one-hot category vocabularies were checked against permitted fitting rows for all **eight fitted pipelines** (three candidates × A/B plus final A/B). Both baselines' group means/counts were reconstructed from their permitted training pools; no validation/test targets fit them.
- Saved pipelines and baseline objects reproduce predictions. All **76 metric rows** (48 validation + 28 final test) were independently recomputed from saved predictions; comparison percentages and undefined reasons were checked. Equal-building and equal-location metrics use their documented arithmetic means.
- All **223 pre-existing substantive files**, including every earlier experiment, source dataset and reused script, retained their hashes and file set at experiment completion. Three charts were generated, with the validation and final RMSE figures visually inspected.

Evidence is saved in `verification_summary.json`, `independent_verification.json`, `stage_events.json`, preprocessing audits and the run manifest under `validation/run_20261025T091525_455049Z`. At the validation report update, its archived pre-update bytes matched the preservation hash and all other prior files were unchanged. On 26 October the user removed six historical main-folder PNGs; Section 6.5 records that later change separately. The original result CSVs, fitted models and all sensitivity/validation-specific artifacts remain unchanged.

### 6.5 Academic report figure verification

The plotting step checks the actual saved experiment, rather than fitting another model. It verified all seven mirrored input/target pairs, the original per-building split boundaries, identical validation row identities across candidates, and the selected shared configuration. It independently reconstructed **18 candidate/model/building validation RMSEs**, **six equal-building validation RMSE averages**, and **16 final building/method test RMSEs** before rendering.

All four plotted weeks match the original saved 168-consecutive-hour windows, totalling **672 aligned observations**. Figure 6 differences match the same A/B values plotted in Figure 4. All six figures were visually reviewed; overlapping labels were corrected before delivery. PNG metadata confirms at least 300 DPI (320 DPI requested), and every PNG has a matching SVG. Plotted data, source hashes and output hashes are recorded in `Prediction Model/charts/figure_manifest.json`.

The validation preservation snapshot still matches **216 historical files** other than the authorised root-report edits and the six main-folder PNGs already removed by the user. All 29 sensitivity figures, the three validation figures, source datasets, metric/prediction CSVs and fitted models remain unchanged. This plotting task does not add to the historical 83-test total and does not retrain or reevaluate model selection.

## 7. Open issues and work not yet completed

1. **Overall generalisation remains inadequate.** In the earlier exclusion sensitivity, both models lose to both refitted baselines overall. In the new validation-guided with-L03 refit, both models beat the calendar/building-use baseline overall but still lose to the global mean; L14_B03 transfer remains poor. Known-building validation does not ensure transfer to other building types/locations.
2. **L03's unit/scale question remains unresolved.** The PDF acknowledges possible labelling/comparability issues generally but gives no L03-specific correction. Its unusually large target distribution and the exclusion diagnostic do not prove an incorrect unit. Stated units and source values remain unchanged.
3. **Electricity interval timing is partly a project convention.** L03/L14 source timestamps are still treated as interval ends; L07 retains its processed counter-difference bounds. The intended prediction is at t for [t,t+1 hour), with no additional target shift.
4. **Weather availability and detailed interval semantics remain undocumented.** The reviewed PDF establishes reanalysis sources and anonymisation, not release time at t. Exact one-hour lagging is a sensitivity check, not evidence of sufficient publication lead time.
5. **Metadata remains incomplete.** L03 floor count is contradictory, L14 floor counts are missing, and L14_B02 opening year is missing. Training-fitted imputation does not resolve those source uncertainties.
6. **Building-type coverage remains narrow.** Two- or three-building training pools contain limited static metadata diversity regardless of hourly row count. The diagnostic excludes the only training education category; unknown labels are handled computationally, without guaranteeing accurate transfer.
7. **The fixed holdout is not leave-one-site-out validation.** L07 is an unseen location, while held-out L14 buildings share a location with training. No repeated all-site folds or independent new final-test set have been evaluated.
8. **Validation and limited parameter selection are completed, but independent final evaluation remains outstanding.** The new run uses the latest 20% of unique timestamps separately in each development building, compares exactly three predefined settings and selects one shared A/B configuration before test loading. These per-building cutoffs intentionally replace the earlier common-cutoff proposal for this experiment. They assess future periods of known buildings. The already inspected test set remains a follow-up evaluation, and no new untouched final set or repeated validation folds were introduced. The raw-RMSE selection criterion is sensitive to L03's much larger target scale.
9. **Operational forecasting and causal claims are not established.** No extra target shifting, future-lag-target model, persistence/seasonal-naive benchmark, source rescaling, causal analysis or production deployment was added. The global-mean and calendar/building-use references are now both implemented.
10. **Upstream path/configuration synchronisation is still outstanding.** Active training reads the staged Prediction Model directories; upstream scripts write under Data and retain historical L06 configuration references absent from the current tree. The follow-ups did not regenerate or silently replace staged data.

Timing review, the L03-exclusion diagnostic, nRMSE, both baselines, per-building chronological validation, the predefined shared parameter selection and persisted sensitivity/validation tests are completed. Weather availability, source-scale uncertainty and predictive-transfer shortcomings remain open. The original fixed experiments, earlier exploratory sensitivities and current validation-guided experiment remain separately documented and preserved.

## 8. Execution and reproducibility reference

Run from the project root. The existing local model environment is `Prediction Model/.venv/`.

Render the six academic report figures from saved results into a **fresh** folder, without retraining:

```bash
PYTHONDONTWRITEBYTECODE=1 "Prediction Model/.venv/bin/python" -B "Prediction Model/generate_report_figures.py" --output-dir "Prediction Model/report_figures_rerun"
```

The current requested set is already in `Prediction Model/charts/`; existing output filenames are protected. Choose another fresh destination for each additional rendering. Plotting needs numpy, pandas and matplotlib; exact versions and captions are saved with the figures.

Run the new chronological validation and shared parameter-selection experiment:

```bash
PYTHONDONTWRITEBYTECODE=1 "Prediction Model/.venv/bin/python" -B "Prediction Model/run_validation_experiment.py"
```

Every invocation creates a new directory under `Prediction Model/experiments/validation/`. It records the candidate plan before scoring, keeps test data out of selection, and performs the full-development refit and held-out evaluation. Exact saved dependencies can be installed with:

```bash
"Prediction Model/.venv/bin/python" -m pip install -r "Prediction Model/experiments/validation/run_20261025T091525_455049Z/requirements_versions.txt"
```

Run the eight new validation tests:

```bash
PYTHONDONTWRITEBYTECODE=1 "Prediction Model/.venv/bin/python" -B -W ignore::DeprecationWarning -m unittest discover -s "Prediction Model" -p 'test_validation_experiment.py'
```

Check modelling data without fitting or writing model outputs:

```bash
"Prediction Model/.venv/bin/python" "Prediction Model/train_models.py" --check-data
```

Run the full exploratory 2×2 follow-up batch, including both baselines:

```bash
"Prediction Model/.venv/bin/python" "Prediction Model/run_followup_experiments.py"
```

Each invocation creates a fresh UTC-stamped folder under `Prediction Model/experiments/timing_L03/`. Use this entry point for further reproductions. The preserved `train_models.py` still has its historical default output locations, so its default fitting command is not recommended when preserving the original result. The new runner already reproduces the original configuration inside a separate case folder without invoking that output-writing entry point.

The completed batch records its expanded reproduction command in `command.txt`, exact versions in `dependency_versions.json`/`requirements_versions.txt`, and the full environment in `environment_freeze.txt`.

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
| scipy | 1.10.0 |
| threadpoolctl | 3.6.0 |

Run the existing data-preparation tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s Data_cleaning -p 'test_*.py'
```

Run the focused follow-up tests:

```bash
PYTHONDONTWRITEBYTECODE=1 "Prediction Model/.venv/bin/python" -B -W ignore::DeprecationWarning -m unittest discover -s "Prediction Model" -p 'test_followup_experiments.py'
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
- [x] Reviewed the local dataset PDF and traced electricity intervals, weather timestamps and target alignment using code/documentation evidence.
- [x] Retained the intended [t,t+1 hour) target and existing source timestamp conventions without shifting targets again.
- [x] Summarised every building's target count, mean, median, selected percentiles and maximum while retaining stated units.
- [x] Completed the four controlled exploratory combinations of L03 inclusion/exclusion and current/one-hour-lagged weather with fixed model settings/features.
- [x] Implemented exact same-location t−1-hour weather joins respecting gaps, with unavailable matches left missing and per-field audits saved.
- [x] Added and evaluated the training-only building-use/weekday/hour baseline with all four fallback levels and saved group means/counts.
- [x] Added mean-normalised RMSE, undefined-denominator reasons and explicit equal-weight location aggregation.
- [x] Saved 112 follow-up metric rows, both-baseline/weather comparisons, same-row predictions, fitted models and full provenance in separate case folders.
- [x] Created 29 new figures, including fixed-original-window time-series plots and a compact L03-influence comparison.
- [x] Passed 10 focused follow-up tests and independent checks of metrics, training-only statistics, timing, row/window invariance and original preservation.
- [x] Established a safe follow-up rerun entry point that creates a new named output directory on every invocation.
- [x] Updated this report with exploratory findings, new file descriptions, revised open issues and milestones, while archiving the prior report and preserving original model/data artifacts.

- [x] Added a separate timestamped validation experiment while preserving all previous source data, scripts and experiments.
- [x] Split each development building chronologically by unique timestamps into earliest-80% fitting and latest-20% validation, saving exact boundaries and membership.
- [x] Verified 64,531 fitting and 16,134 validation rows with no within-building row/timestamp overlap and no independent input/target sorting.
- [x] Preregistered three candidates and the shared A/B validation-building RMSE criterion, with deterministic complexity tie-breaks.
- [x] Evaluated both models and both training-only baselines on identical validation rows; saved 48 validation metric rows and all candidate predictions/pipelines.
- [x] Selected shared candidate 2 (15 leaves, minimum leaf size 60) before test data loading, then refitted all methods on 80,665 development rows.
- [x] Evaluated the locked configuration on 118,887 original test rows, saving 28 final metric rows, baseline/weather comparisons and aligned predictions.
- [x] Generated three new validation/final comparison charts and saved commands, exact dependencies, source hashes and stage events.
- [x] Passed eight focused validation tests and independent checks of all 76 new metric rows, all eight model preprocessing fits and original-file preservation.
- [x] Distinguished later-period known-building validation from unseen-building/location testing and documented that the inspected tests are not an untouched final estimate.
- [x] Recorded the remaining global-mean baseline shortfall and L14_B03 transfer failure without altering L03 scale, features, weather alignment, training membership or search scope.

- [x] Replaced the user-cleared main charts folder with six academic report figures based on the latest validation-selected experiment.
- [x] Exported all six figures as 320 DPI PNGs and editable SVGs, with captions, reproducible plotting code, plotted-data CSVs and source/output hashes.
- [x] Verified every plotted validation/test RMSE, consistent Figure 4/6 comparisons, seven-building split membership and the original 672 weekly observations without retraining.
- [x] Retained genuine negative forecasts and the full L14_B03 error while adding a clearly labelled actual-only detail inset.
- [x] Recorded the six user-removed historical chart files, refreshed figure links and updated the file guide while preserving all remaining experiment/model/data artifacts.
