# Exploratory timing and L03 follow-up: methodology and findings

The original experiment, original train_models.py, progress report, datasets, models, metrics, predictions and charts are preserved. These follow-ups are exploratory because the original test outcomes have already been inspected. They are not an untouched final-test estimate.

## Prediction timing and documentation evidence

At time t, the intended target is electricity over [t,t+1 hour), divided by gross floor area. For L03/L14 the existing source-end-timestamp convention is retained; for L07 the counter difference already has its two interval bounds. Targets are neither moved nor re-differenced. Metadata enrichment and target export preserve the interval rows.

The dataset PDF says timestamps are UTC moments (p. 5), identifies CERRA/ERA5-Land/ERA5 reanalysis weather and anonymisation (p. 8), and describes harmonisation/resampling and measurement limitations (pp. 16, 19–20). It does not define the selected weather variables' instantaneous/averaged/accumulated interval semantics, per-file product mapping or publication latency. Weather at t therefore cannot be confirmed to have been available for a prediction made at t. It could contain contemporaneous or retrospective information; the available evidence does not resolve which selected variables do. We retain the original alignment only as an explicitly assumed reference.

The one-hour sensitivity uses a timestamp lookup of location weather at exactly t−1 hour, not a row shift. It uses the full original location weather series, including weather records at times when electricity rows are absent; missing timestamp matches remain missing. Lagging reduces reliance on contemporaneous weather but does not establish provider publication latency. All active staged current-weather values were checked against the original exact-t weather sources, without replacing staged data.

Evidence references and source hashes are in documentation_evidence.json and batch_manifest.json. No authoritative instruction was found to divide L03 by 1,000, so its stated kWh and derived kWh/m² units remain unchanged. L03 uses electricity submeter EM02, not the separate virtual aggregate EM01. Distribution differences and diagnostic improvements cannot prove a unit error.

## Fixed design and fitting

The 2×2 design crosses training on L03_B01/L14_B04/L14_B05 (80,665 rows) versus L14_B04/L14_B05 only (71,929 rows), with current versus exact one-hour-lagged weather. Each case uses the same 118,887 test rows from L07_B01 and L14_B01/B02/B03. These are fixed holdouts, not leave-one-site-out cross-validation: L07 is an unseen location, while L14 holdouts are unseen buildings at a partly seen location. Leave-one-site-out would exclude every building at a site and repeat that procedure across site folds; that procedure is not performed here. L03 is a training building or diagnostic exclusion. Training on only two or three buildings limits transfer despite the hourly row count.

Both HistGradientBoostingRegressor models retain the original settings (200 iterations, learning rate 0.08, 31 leaves, minimum leaf size 30, L2=1, max_bins=255, seed 42, early stopping disabled). Model A retains its 22 metadata/calendar predictors; B retains the same plus six weather measurements. No feature selection, tuning, new ML algorithm or source-data cleaning was introduced. UTC calendar construction is unchanged. Electricity, the target, other target-derived columns and building/location IDs are excluded from predictors.

Imputers, encoders and both baselines are refitted using only the relevant training rows. Fitted numerical medians and category vocabularies are independently checked against training data. Unknown held-out categories are handled by the original one-hot encoder. Weather missingness does not change evaluation eligibility.

## Baselines and metrics

The global baseline predicts the row-weighted mean training target. The new calendar/building-use baseline first uses the training mean for building_use × weekday × hour, falling back in order to building_use × hour, weekday × hour across training buildings, and the global training mean. All grouping uses UTC, the same convention as the models. Each lookup has saved means and group counts; fallback usage is recorded. Held-out targets are used only for descriptive distributions and evaluation metrics, never to fit or adjust predictions.

MAE and RMSE are in kWh/m². Mean-normalised RMSE is nRMSE (%) = 100 × RMSE / mean(observed target), computed separately for each test building and pooled location. A non-positive or invalid observed mean yields an undefined value and reason. The equal-weight summary averages L07 and L14 metrics separately, including their nRMSE percentages. It is neither a pooled RMSE nor a pooled nRMSE, and has no pooled normalisation denominator. Percentage error reduction is 100 × (reference error − candidate error) / reference error, undefined for zero/invalid references.

## Original findings and exploratory follow-up findings

The preserved original equal-weight location result was MAE/RMSE 0.293805/0.294841 for the global mean baseline, 0.598728/1.054113 for A and 0.605341/1.083748 for B. Both models failed badly on L14_B03 and neither beat that reference overall. Adding weather worsened overall MAE by 1.10% and RMSE by 2.81%. The with-L03/current-weather case is verified to reproduce original A/B/global-baseline predictions, while adding the new baseline and nRMSE.

Equal-weight means of location metrics for all follow-up cases:

| training_configuration | weather_timing | model | mae_kwh_per_m2 | rmse_kwh_per_m2 | nrmse_pct |
| --- | --- | --- | --- | --- | --- |
| with_L03 | current_weather | baseline_mean | 0.293805 | 0.294841 | 1840.71 |
| with_L03 | current_weather | baseline_calendar_use | 1.23323 | 1.49558 | 13842.6 |
| with_L03 | current_weather | A | 0.598728 | 1.05411 | 10118.7 |
| with_L03 | current_weather | B | 0.605341 | 1.08375 | 10303.6 |
| with_L03 | lagged_weather_1h | baseline_mean | 0.293805 | 0.294841 | 1840.71 |
| with_L03 | lagged_weather_1h | baseline_calendar_use | 1.23323 | 1.49558 | 13842.6 |
| with_L03 | lagged_weather_1h | A | 0.598728 | 1.05411 | 10118.7 |
| with_L03 | lagged_weather_1h | B | 0.594132 | 1.06406 | 10116.2 |
| without_L03 | current_weather | baseline_mean | 0.0516346 | 0.0548483 | 85.6651 |
| without_L03 | current_weather | baseline_calendar_use | 0.0514838 | 0.0542422 | 83.2759 |
| without_L03 | current_weather | A | 0.0543588 | 0.057264 | 94.1006 |
| without_L03 | current_weather | B | 0.0543039 | 0.0572124 | 94.0586 |
| without_L03 | lagged_weather_1h | baseline_mean | 0.0516346 | 0.0548483 | 85.6651 |
| without_L03 | lagged_weather_1h | baseline_calendar_use | 0.0514838 | 0.0542422 | 83.2759 |
| without_L03 | lagged_weather_1h | A | 0.0543588 | 0.057264 | 94.1006 |
| without_L03 | lagged_weather_1h | B | 0.0542952 | 0.0572025 | 94.0173 |

Weather contribution (Model B versus A), reported separately by training configuration and timing:

| training_configuration | weather_timing | mae_kwh_per_m2_reduction_pct | rmse_kwh_per_m2_reduction_pct | nrmse_pct_reduction_pct |
| --- | --- | --- | --- | --- |
| with_L03 | current_weather | -1.10458 | -2.81134 | -1.82728 |
| with_L03 | lagged_weather_1h | 0.767606 | -0.943493 | 0.0253093 |
| without_L03 | current_weather | 0.100929 | 0.0901848 | 0.0445694 |
| without_L03 | lagged_weather_1h | 0.11689 | 0.10745 | 0.0884469 |

Positive percentages improve on A; negative percentages worsen it. Building/location details and comparisons against both baselines are saved separately in every experiment.

- **with_L03, current_weather:** B increases average location MAE by 1.10% and increases average location RMSE by 2.81%.

- **with_L03, lagged_weather_1h:** B reduces average location MAE by 0.77% and increases average location RMSE by 0.94%.

- **without_L03, current_weather:** B reduces average location MAE by 0.10% and reduces average location RMSE by 0.09%.

- **without_L03, lagged_weather_1h:** B reduces average location MAE by 0.12% and reduces average location RMSE by 0.11%.


Removing L03 is compared at each fixed weather timing in l03_influence_by_building.csv and l03_influence_rmse.png; changing weather timing at each fixed training configuration is in weather_timing_comparison.csv. Those factors are not bundled into a single before/after claim. Target distributions follow. All units are retained.

| building_id | count | mean | median | p01 | p05 | p25 | p75 | p95 | p99 | maximum |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L03_B01 | 8736 | 3.1649 | 3.01086 | 0.858835 | 1.00691 | 2.18164 | 3.96101 | 5.9921 | 7.65054 | 11.076 |
| L07_B01 | 9543 | 0.108725 | 0.112001 | 0.0628819 | 0.0669097 | 0.0781944 | 0.133542 | 0.158889 | 0.179097 | 0.202222 |
| L14_B01 | 36360 | 0.00970993 | 0.00788955 | 0.00147929 | 0.00197239 | 0.00394477 | 0.0126561 | 0.0251479 | 0.0368179 | 0.0540763 |
| L14_B02 | 36336 | 0.0147286 | 0.0125926 | 0.00481481 | 0.0062963 | 0.00925926 | 0.0188889 | 0.0288889 | 0.0355556 | 0.0496296 |
| L14_B03 | 36648 | 0.0054097 | 0.00334652 | 0.00152114 | 0.00167326 | 0.0021296 | 0.00790995 | 0.0136903 | 0.0149072 | 0.017341 |
| L14_B04 | 36889 | 0.0153795 | 0.013389 | 0.00930273 | 0.0100852 | 0.0114763 | 0.0190402 | 0.0250391 | 0.0270388 | 0.03269 |
| L14_B05 | 35040 | 0.00769924 | 0.00607287 | 0.00202429 | 0.00303644 | 0.00404858 | 0.0111336 | 0.0172065 | 0.0192308 | 0.0232794 |

## Interpretation, limitations and reproducibility

These results test conditional predictive transfer. Any apparent improvement is exploratory, does not prove L03 has incorrect units, does not establish a causal weather effect, and does not establish production-ready forecasting. Weather timing/publication evidence and the L03-specific unit question remain unresolved. The original test set has been inspected; later model selection needs training-only validation and a genuinely separate final evaluation.

The four experiments share original saved seven-day chart windows; none was selected for prediction quality. All methods share original test IDs, timestamps and row order. Saved predictions are reread to verify metrics, both-baseline comparisons and weather reductions. Saved A/B pipelines are reloaded to verify predictions; original outputs and all read sources are hashed before/after.

The runner creates a fresh UTC-stamped run folder every invocation and refuses output roots inside original outputs or source datasets. It does not call original.run(), regenerate upstream tables, copy replacement staged data or write into original results/charts/models.

Reproduce with the recorded command (a new output directory is created):

```bash
'/Users/bakani/Desktop/E.Consumption_predictionModel/Prediction Model/.venv/bin/python' -B '/Users/bakani/Desktop/E.Consumption_predictionModel/Prediction Model/run_followup_experiments.py' --output-root '/Users/bakani/Desktop/E.Consumption_predictionModel/Prediction Model/experiments/timing_L03' --threads 4
```

Exact Python/library versions are in dependency_versions.json, requirements_versions.txt and environment_freeze.txt. Original code/settings, source hashes and preservation checks are in batch_manifest.json.
