# Chronological validation and shared parameter selection

This is a validation-guided follow-up. The four test buildings were already inspected in earlier fixed-setting and sensitivity experiments; they are not a newly untouched final test. Original files/results remain preserved.

## Design and isolation

Within EACH development building sort unique UTC interval-start timestamps; fit on the first floor(0.8 * unique_count), validate on the remainder. Keep all rows at a timestamp together and preserve original row order. This is future-period validation within known buildings, with per-building cutoffs, not unseen-building validation or a common global time cutoff.

Development: L03_B01, L14_B04, L14_B05. Test: L07_B01, L14_B01/B02/B03. Cross-building time ranges can overlap: only the within-building future boundary is enforced. Validation measures later periods of known buildings. Held-out testing measures transfer: L07 is an unseen location; L14 contains unseen buildings within a known location.

| building_id | total_rows | unique_timestamps | fit_unique_timestamps | validation_unique_timestamps | validation_start_utc | within_building_timestamp_overlap | within_building_row_overlap | fit_rows | fit_eligible_rows | fit_first_utc | fit_last_utc | validation_rows | validation_eligible_rows | validation_first_utc | validation_last_utc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L03_B01 | 8736 | 8736 | 6988 | 1748 | 2022-10-19T15:00:00+00:00 | 0 | 0 | 6988 | 6988 | 2022-01-01T11:00:00+00:00 | 2022-10-19T14:00:00+00:00 | 1748 | 1748 | 2022-10-19T15:00:00+00:00 | 2022-12-31T10:00:00+00:00 |
| L14_B04 | 36889 | 36889 | 29511 | 7378 | 2021-05-14T13:00:00+00:00 | 0 | 0 | 29511 | 29511 | 2017-12-31T22:00:00+00:00 | 2021-05-14T12:00:00+00:00 | 7378 | 7378 | 2021-05-14T13:00:00+00:00 | 2022-03-17T22:00:00+00:00 |
| L14_B05 | 35040 | 35040 | 28032 | 7008 | 2021-03-13T22:00:00+00:00 | 0 | 0 | 28032 | 28032 | 2017-12-31T22:00:00+00:00 | 2021-03-13T21:00:00+00:00 | 7008 | 7008 | 2021-03-13T22:00:00+00:00 | 2021-12-31T21:00:00+00:00 |

## Preregistered comparison

Minimise (equal-weight validation-building RMSE of A + equal-weight validation-building RMSE of B) / 2. Choose one shared configuration. Exact numerical ties: fewer max_leaf_nodes, then larger min_samples_leaf. Only the three predefined candidates; no test performance is consulted.

candidate_1 uses all original settings. candidate_2 changes only max_leaf_nodes=15 and min_samples_leaf=60; candidate_3 changes only max_leaf_nodes=7 and min_samples_leaf=120. Both models retain 200 iterations, learning rate 0.08, L2=1, max_bins=255, seed 42 and early_stopping=False. candidate_plan.json was written before fitting or scoring. selected_settings.json was written before any test-building data was loaded. No search expansion occurred.

| candidate | A_validation_macro_rmse | B_validation_macro_rmse | selection_score | max_leaf_nodes | min_samples_leaf | selected |
| --- | --- | --- | --- | --- | --- | --- |
| candidate_1 | 0.302666 | 0.298253 | 0.300459 | 31 | 30 | False |
| candidate_2 | 0.302083 | 0.29392 | 0.298002 | 15 | 60 | True |
| candidate_3 | 0.328358 | 0.311257 | 0.319807 | 7 | 120 | False |

Selected shared configuration: **candidate_2**.

## Features, preprocessing, baselines and alignment

Existing train_models.py builds the exact original 22 metadata/calendar predictors for A and the same plus six weather predictors for B. Raw and encoded names are saved in predictors.csv and fitted_preprocessing_audit.json at every fitting stage. Electricity, target-derived columns, IDs and raw timestamps are excluded by the existing allowlist; no target shift or source rescaling occurs.

Calendar features use UTC because no documented local mapping is available. Original exact-t weather is used without changing staged values. Reanalysis weather's per-variable interval semantics and publication latency are not documented: availability at prediction time t for [t,t+1 hour) remains an assumption, so these are conditional predictive comparisons.

For validation, medians, missingness indicators and one-hot vocabularies are fitted on earliest-80% rows only. Unknown categories use the original ignore policy. Both baselines fit those same rows: global row-weighted target mean, and building_use×weekday×hour means falling back to building_use×hour, weekday×hour, then global mean. Means/counts and preprocessing are independently checked against allowed rows. Baselines are fitted once and shared across all candidates.

Inputs/targets are paired by building and checked by the existing loader. Current target-only files preserve exporter order and must exactly match mirrored input targets row by row. Masks are applied jointly to features/targets/tracking without independently sorting files. Only non-finite targets are ineligible; weather missingness does not change comparison rows.

## Validation results

MAE/RMSE use kWh/m². nRMSE (%) = 100 × RMSE / observed mean target, undefined with a reason for non-positive/invalid means. Validation averages give equal weight to the three buildings' metrics, not their row counts. The nRMSE average is a mean of percentages, not a pooled normalisation.

| model | mae_kwh_per_m2 | rmse_kwh_per_m2 | nrmse_pct |
| --- | --- | --- | --- |
| baseline_mean | 1.30246 | 1.37842 | 2381.91 |
| baseline_calendar_use | 0.275201 | 0.354074 | 27.3771 |
| A | 0.193793 | 0.302083 | 149.758 |
| B | 0.183303 | 0.29392 | 91.1379 |

All candidates' building-level metrics and aligned predictions are retained in validation/.

## Full-development refit and previously inspected test results

After selection, both pipelines and both baselines were refitted on the full three-building development pool. The locked setting was evaluated once on the four tests. Test results did not change the candidate, training pool, features, L03 units or weather timing. Repeated numerical verification uses the same saved predictions and is not another selection step.

| scope | name | model | mae_kwh_per_m2 | rmse_kwh_per_m2 | nrmse_pct |
| --- | --- | --- | --- | --- | --- |
| building | L07_B01 | baseline_mean | 0.24441 | 0.246401 | 226.627 |
| building | L07_B01 | baseline_calendar_use | 0.244578 | 0.264407 | 243.188 |
| building | L07_B01 | A | 0.10294 | 0.109689 | 100.887 |
| building | L07_B01 | B | 0.122098 | 0.148197 | 136.304 |
| building | L14_B01 | baseline_mean | 0.343425 | 0.343511 | 3537.73 |
| building | L14_B01 | baseline_calendar_use | 3.15887 | 3.32689 | 34262.8 |
| building | L14_B01 | A | 0.0449392 | 0.0652997 | 672.504 |
| building | L14_B01 | B | 0.0201572 | 0.0297352 | 306.235 |
| building | L14_B02 | baseline_mean | 0.338407 | 0.338482 | 2298.13 |
| building | L14_B02 | baseline_calendar_use | 0.338313 | 0.357611 | 2428.01 |
| building | L14_B02 | A | 0.0470734 | 0.0669112 | 454.294 |
| building | L14_B02 | B | 0.0178735 | 0.0291955 | 198.223 |
| building | L14_B03 | baseline_mean | 0.347726 | 0.34775 | 6428.26 |
| building | L14_B03 | baseline_calendar_use | 3.15978 | 3.32802 | 61519.4 |
| building | L14_B03 | A | 3.19302 | 3.43769 | 63546.7 |
| building | L14_B03 | B | 3.19533 | 3.44019 | 63592.9 |
| location | L07 | baseline_mean | 0.24441 | 0.246401 | 226.627 |
| location | L07 | baseline_calendar_use | 0.244578 | 0.264407 | 243.188 |
| location | L07 | A | 0.10294 | 0.109689 | 100.887 |
| location | L07 | B | 0.122098 | 0.148197 | 136.304 |
| location | L14 | baseline_mean | 0.343199 | 0.343281 | 3454.78 |
| location | L14 | baseline_calendar_use | 2.22188 | 2.72675 | 27442 |
| location | L14 | A | 1.10077 | 1.99092 | 20036.6 |
| location | L14 | B | 1.0836 | 1.99178 | 20045.3 |
| equal_weight_locations | L07_and_L14 | baseline_mean | 0.293805 | 0.294841 | 1840.71 |
| equal_weight_locations | L07_and_L14 | baseline_calendar_use | 1.23323 | 1.49558 | 13842.6 |
| equal_weight_locations | L07_and_L14 | A | 0.601854 | 1.0503 | 10068.8 |
| equal_weight_locations | L07_and_L14 | B | 0.602848 | 1.06999 | 10090.8 |

Test location metrics pool that location's rows. The final equal-location summary averages L07/L14 metrics separately; it is neither pooled RMSE nor pooled nRMSE. Baseline and B-versus-A percentage reductions are 100×(reference error−model error)/reference error; zero/undefined references leave an empty percentage and reason. Positive means improvement.

## Interpretation and reproducibility

Validation performance does not guarantee improved transfer to other buildings. Limited training building diversity, unresolved L03 scale, UTC-only calendar assumptions, weather availability and previous test inspection remain limitations. Predictive weather differences are not causal evidence. No correction is inferred merely from a distribution or model error.

Split boundaries and row membership, candidate plan, settings, all predictions/metrics, stage events, fitted preprocessing/baselines and source hashes are saved. Saved estimators were reloaded to reproduce predictions; metrics and comparison percentages were recomputed from saved CSVs. Existing project files were hashed before and after. The pre-update progress report is archived here so a later authorised report update retains its historical hash.

Reproduce from the project root (creates a new timestamped directory):

```bash
PYTHONDONTWRITEBYTECODE=1 '/Users/bakani/Desktop/E.Consumption_predictionModel/Prediction Model/.venv/bin/python' -B '/Users/bakani/Desktop/E.Consumption_predictionModel/Prediction Model/run_validation_experiment.py' --threads 4
```

Install pinned dependencies with `"Prediction Model/.venv/bin/python" -m pip install -r "Prediction Model/experiments/validation/run_20261025T091525_455049Z/requirements_versions.txt"`. Exact versions, full pip freeze and the command are retained alongside the manifest.
