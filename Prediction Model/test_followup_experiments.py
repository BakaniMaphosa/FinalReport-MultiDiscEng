"""Focused tests for timing, baseline fallbacks, metrics and original protection."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import run_followup_experiments as followup

np, pd = followup.np, followup.pd


class FollowupTests(unittest.TestCase):
    def test_calendar_baseline_all_four_fallback_levels_and_persistence(self):
        training = pd.DataFrame({"building_use": ["A", "A", "B"], "weekday": [0, 1, 2], "hour": [10, 10, 11]})
        baseline = followup.CalendarUseBaseline().fit(training, [2., 4., 9.])
        held_out = pd.DataFrame({"building_use": ["A", "A", "unseen", "unseen"],
                                 "weekday": [0, 5, 2, 6], "hour": [10, 10, 11, 23]})
        values, levels = baseline.predict(held_out)
        np.testing.assert_allclose(values, [2., 3., 9., 5.])
        self.assertEqual(levels.tolist(), ["building_usexweekdayxhour", "building_usexhour", "weekdayxhour", "global_training_mean"])
        snapshot = json.dumps(baseline.state(), sort_keys=True)
        # Prediction has no target argument; repeated held-out queries never fit/adjust means.
        baseline.predict(pd.concat([held_out] * 3, ignore_index=True))
        self.assertEqual(json.dumps(baseline.state(), sort_keys=True), snapshot)
        restored = followup.CalendarUseBaseline.from_state(json.loads(snapshot))
        np.testing.assert_allclose(restored.predict(held_out)[0], values)

    def test_baseline_grouping_is_row_weighted_not_building_weighted(self):
        keys = pd.DataFrame({"building_use": ["A"] * 3, "weekday": [0] * 3, "hour": [0] * 3})
        baseline = followup.CalendarUseBaseline().fit(keys, [1., 1., 10.])
        self.assertEqual(baseline.predict(keys.iloc[:1])[0][0], 4.)
        self.assertEqual(baseline.state()["lookup_tables"][0]["groups"][0]["count"], 3)

    def test_lagged_weather_exact_timestamp_gaps_and_location_isolation(self):
        stamps = pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-01T02:00:00Z"], utc=True)
        weather = {location: {column: pd.Series(values, index=stamps) for column in followup.original.WEATHER}
                   for location, values in (("L03", [10., 20.]), ("L07", [100., 200.]))}
        starts = pd.to_datetime(["2024-01-01T01:00:00Z", "2024-01-01T02:00:00Z", "2024-01-01T03:00:00Z"], utc=True)
        lagged, requested, matched = followup.exact_weather_at(starts, "L03", weather, 1)
        np.testing.assert_allclose(lagged.iloc[0], 10.)
        self.assertTrue(lagged.iloc[1].isna().all())  # t-1 is missing, although a previous row exists.
        np.testing.assert_allclose(lagged.iloc[2], 20.)  # A weather record exists despite no energy row at 02:00 in the queried series.
        self.assertEqual(matched.tolist(), [6, 0, 6])
        self.assertTrue((requested == starts - pd.Timedelta(hours=1)).all())
        other, _, _ = followup.exact_weather_at(starts, "L07", weather, 1)
        np.testing.assert_allclose(other.iloc[0], 100.)
        np.testing.assert_allclose(other.iloc[2], 200.)

    def test_duplicate_weather_times_fail_instead_of_guessing(self):
        index = pd.to_datetime(["2024-01-01T00:00:00Z"] * 2)
        weather = {"L03": {c: pd.Series([1., 2.], index=index) for c in followup.original.WEATHER}}
        with self.assertRaisesRegex(followup.original.DataError, "Duplicate weather"):
            followup.exact_weather_at(index[:1], "L03", weather, 1)

    def test_nrmse_and_undefined_denominators(self):
        result = followup.metric_values([1., 3.], [2., 2.])
        self.assertEqual(result["mae_kwh_per_m2"], 1.)
        self.assertEqual(result["rmse_kwh_per_m2"], 1.)
        self.assertEqual(result["nrmse_pct"], 50.)
        self.assertEqual(result["nrmse_undefined_reason"], "")
        for actual in ([0., 0.], [-1., -3.]):
            result = followup.metric_values(actual, [0., 0.])
            self.assertTrue(np.isnan(result["nrmse_pct"]))
            self.assertIn("non-positive", result["nrmse_undefined_reason"])
        for mean in (np.nan, np.inf):
            value, reason = followup.normalised_rmse(1., mean)
            self.assertTrue(np.isnan(value))
            self.assertIn("invalid", reason)
        with self.assertRaisesRegex(followup.original.DataError, "aligned"):
            followup.metric_values([1., 2.], [1.])

    def predictions(self):
        frame = pd.DataFrame({"building_id": ["L07_B01"] * 2 + ["L14_B01"] * 2,
                              "location_id": ["L07"] * 2 + ["L14"] * 2,
                              "actual_kwh_per_m2": [1., 3., 2., 4.]})
        for method in followup.METHODS:
            frame[f"predicted_{method}_kwh_per_m2"] = [2., 2., 3., 3.]
        return frame

    def test_equal_weight_metrics_are_location_averages_not_pooled(self):
        frame = self.predictions()
        frame.loc[frame.location_id == "L14", "predicted_A_kwh_per_m2"] = [2., 4.]
        metrics = followup.evaluate(frame)
        average = metrics[(metrics.scope == "equal_weight_locations") & (metrics.model == "A")].iloc[0]
        self.assertEqual(average.rmse_kwh_per_m2, 0.5)
        self.assertEqual(average.nrmse_pct, 25.)
        self.assertTrue(np.isnan(average.mean_observed_target_kwh_per_m2))
        self.assertEqual(average.aggregation, "equal_weight_mean_of_location_metrics")
        frame.loc[frame.location_id == "L07", "actual_kwh_per_m2"] = 0.
        metrics = followup.evaluate(frame)
        average = metrics[(metrics.scope == "equal_weight_locations") & (metrics.model == "A")].iloc[0]
        self.assertTrue(np.isnan(average.nrmse_pct))
        self.assertIn("L07", average.nrmse_undefined_reason)

    def test_comparison_with_perfect_reference_handles_zero(self):
        frame = self.predictions()
        frame.predicted_baseline_mean_kwh_per_m2 = frame.actual_kwh_per_m2
        metrics = followup.evaluate(frame)
        comparisons = followup.compare_metrics(metrics, "baseline_mean", ("A", "B"))
        for metric in followup.METRICS:
            self.assertTrue(comparisons[f"{metric}_reduction_pct"].isna().all())
            self.assertTrue(comparisons[f"{metric}_undefined_reason"].str.contains("zero").all())

    def test_saved_chart_windows_do_not_reselect_by_error(self):
        starts = pd.date_range("2024-01-01", periods=200, freq="h", tz="UTC")
        frame = pd.DataFrame({"interval_start_utc": starts, "actual_kwh_per_m2": np.arange(200)})
        window = pd.Series(dict(building_id="L07_B01", start_utc=starts[4].isoformat(),
                                end_utc_exclusive=starts[172].isoformat(), rows=168))
        selected = followup.saved_week(frame, window)
        self.assertEqual(selected.actual_kwh_per_m2.iloc[0], 4)
        self.assertEqual(len(selected), 168)
        with self.assertRaisesRegex(followup.original.DataError, "not fully covered"):
            followup.saved_week(frame.drop(index=10), window)

    def test_output_directories_are_unique_and_original_paths_protected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            first, second = followup.new_run_directory(root), followup.new_run_directory(root)
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir() and second.is_dir())
        for path in (followup.BASE / "results", followup.BASE / "charts/new", followup.BASE / "Input Data/new"):
            with self.assertRaisesRegex(followup.original.DataError, "cannot be inside"):
                followup.new_run_directory(path)

    def test_feature_allowlist_and_settings_reuse_the_original(self):
        for features in followup.original.FEATURES.values():
            self.assertFalse({"electricity_kwh", "electricity_kwh_per_m2", "building_id", "location_id"}.intersection(features))
        original_manifest = json.loads((followup.BASE / "results/run_manifest.json").read_text())
        self.assertEqual(followup.original.FEATURES, original_manifest["input_predictors"])
        self.assertEqual(followup.original.SETTINGS, original_manifest["model_settings"])


if __name__ == "__main__":
    unittest.main()
