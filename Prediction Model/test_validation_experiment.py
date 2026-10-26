"""Checks for chronological isolation and the predefined shared selector."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import run_validation_experiment as validation

original, shared = validation.original, validation.shared
np, pd = validation.np, validation.pd


class ValidationTests(unittest.TestCase):
    def item(self, hours, building="L03_B01"):
        stamps = pd.Series(pd.Timestamp("2024-01-01T00:00:00Z") + pd.to_timedelta(hours, unit="h"))
        tracking = pd.DataFrame(dict(building_id=building, location_id=building[:3],
                                     source_data_row=np.arange(1, len(hours) + 1),
                                     interval_start_utc=stamps,
                                     interval_end_utc=stamps + pd.Timedelta(hours=1)))
        return original.BuildingData(building, pd.DataFrame({"marker": hours}),
                                     pd.Series(np.arange(len(hours), dtype=float)), tracking, {})

    def test_duplicates_stay_together_without_reordering_input(self):
        item = self.item([9, 0, 8, 1, 9, 2, 7, 3, 6, 4, 5, 8])
        fit, val, boundary, membership = validation.chronological_split(item)
        self.assertEqual(boundary["fit_unique_timestamps"], 8)
        self.assertEqual(fit.features.marker.tolist(), [0, 1, 2, 7, 3, 6, 4, 5])
        self.assertEqual(val.features.marker.tolist(), [9, 8, 9, 8])
        self.assertEqual(fit.tracking.source_data_row.tolist(), [2, 4, 6, 7, 8, 9, 10, 11])
        self.assertEqual(val.target.tolist(), [0., 2., 4., 11.])
        self.assertEqual(membership.groupby("interval_start_utc").role.nunique().max(), 1)
        self.assertLess(fit.tracking.interval_start_utc.max(), val.tracking.interval_start_utc.min())

    def test_cutoffs_are_per_building_with_explicit_rounding(self):
        first = self.item(list(range(11)))
        second = self.item(list(range(100, 125)), "L14_B04")
        a = validation.chronological_split(first)[2]
        b = validation.chronological_split(second)[2]
        self.assertEqual((a["fit_unique_timestamps"], a["validation_unique_timestamps"]), (8, 3))
        self.assertEqual((b["fit_unique_timestamps"], b["validation_unique_timestamps"]), (20, 5))
        self.assertNotEqual(a["validation_start_utc"], b["validation_start_utc"])
        with self.assertRaisesRegex(original.DataError, "two unique"):
            validation.chronological_split(self.item([0, 0]))

    def test_missing_targets_do_not_move_the_timestamp_cutoff(self):
        item = self.item(list(range(10)))
        item.target.iloc[[0, 9]] = np.nan
        fit, val, boundary, _ = validation.chronological_split(item)
        self.assertEqual((len(fit.target), len(val.target)), (8, 2))
        self.assertEqual((boundary["fit_eligible_rows"], boundary["validation_eligible_rows"]), (7, 1))

    def metrics(self, errors):
        return pd.DataFrame([dict(candidate=c, scope="equal_weight_buildings", model=m, rmse_kwh_per_m2=v)
                             for c, pair in errors.items() for m, v in zip(("A", "B"), pair)])

    def test_shared_selection_uses_both_models_and_ignores_test_rows(self):
        metrics = self.metrics({"candidate_1": (1., 9.), "candidate_2": (3., 3.), "candidate_3": (5., 2.)})
        # Extreme test values cannot affect the validation-only criterion.
        test = metrics.assign(scope="location", rmse_kwh_per_m2=-100000.)
        selected, _ = validation.select_configuration(pd.concat([metrics, test]), validation.candidate_settings())
        self.assertEqual(selected, "candidate_2")

    def test_ties_prefer_fewer_leaves_then_larger_minimum_leaf(self):
        metrics = self.metrics({c: (1., 1.) for c in validation.candidate_settings()})
        selected, _ = validation.select_configuration(metrics, validation.candidate_settings())
        self.assertEqual(selected, "candidate_3")
        candidates = validation.candidate_settings()
        candidates["candidate_2"]["max_leaf_nodes"] = 7
        selected, _ = validation.select_configuration(metrics, candidates)
        self.assertEqual(selected, "candidate_3")
        with self.assertRaisesRegex(original.DataError, "one finite"):
            validation.select_configuration(metrics.iloc[1:], candidates)

    def test_predefined_candidates_keep_other_settings_fixed(self):
        for name, settings in validation.candidate_settings().items():
            changed = {k for k in settings if settings[k] != original.SETTINGS[k]}
            self.assertEqual(changed, set() if name == "candidate_1" else {"max_leaf_nodes", "min_samples_leaf"})
            self.assertFalse(settings["early_stopping"])
            self.assertEqual(settings["random_state"], 42)

    def test_validation_averages_buildings_equally_and_preserves_undefined_reasons(self):
        frame = pd.DataFrame(dict(building_id=["L03_B01"] * 10 + ["L14_B04", "L14_B05"],
                                  actual_kwh_per_m2=[1.] * 12))
        for method in shared.METHODS:
            frame[f"predicted_{method}_kwh_per_m2"] = [2.] * 10 + [3., 4.]
        metrics = validation.evaluate_validation(frame)
        row = metrics[(metrics.scope == "equal_weight_buildings") & (metrics.model == "A")].iloc[0]
        self.assertEqual(row.rmse_kwh_per_m2, 2.)
        self.assertEqual(row.nrmse_pct, 200.)
        frame.loc[frame.building_id == "L14_B05", "actual_kwh_per_m2"] = 0.
        row = validation.evaluate_validation(frame).query("scope == 'equal_weight_buildings' and model == 'A'").iloc[0]
        self.assertTrue(np.isnan(row.nrmse_pct))
        self.assertIn("L14_B05", row.nrmse_undefined_reason)

    def test_training_only_statistics_and_heldout_fit_guard(self):
        n = 90
        features = pd.DataFrame({c: np.arange(n, dtype=float) for c in original.NUMERIC_METADATA + original.CALENDAR + original.WEATHER})
        features["building_use"], features["climate_zone"] = "fit_category", "fit_climate"
        targets = pd.Series(np.linspace(1., 2., n))
        stamps = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
        tracking = pd.DataFrame({"building_id": np.repeat(validation.DEVELOPMENT, 30), "interval_start_utc": stamps})
        with TemporaryDirectory() as directory:
            models = validation.fit_models(features, targets, tracking, validation.candidate_settings()["candidate_3"],
                                            Path(directory) / "models", 1)
            baseline = validation.fit_baselines(features, targets, tracking)
            self.assertEqual(baseline[1].training_rows, n)
            self.assertAlmostEqual(baseline[0].constant_.item(), 1.5)
            future = features.iloc[:2].copy()
            future[original.NUMERIC_METADATA] = 1e8
            future["building_use"] = "validation_only_category"
            before = models["A"].named_steps["preprocessing"].named_transformers_["numeric"].statistics_.copy()
            with original.threadpool_limits(limits=1):
                self.assertTrue(np.isfinite(models["A"].predict(future[original.FEATURES["A"]])).all())
            np.testing.assert_array_equal(before, np.repeat(44.5, len(before)))
            shared.preprocessing_audit(models["A"], "A", features, validation.DEVELOPMENT)
            bad_tracking = tracking.copy()
            bad_tracking.loc[0, "building_id"] = "L07_B01"
            with self.assertRaisesRegex(original.DataError, "test building"):
                validation.fit_baselines(features, targets, bad_tracking)
            with self.assertRaisesRegex(original.DataError, "test building"):
                validation.fit_models(features, targets, bad_tracking, original.SETTINGS, Path(directory) / "bad", 1)


if __name__ == "__main__":
    unittest.main()
