import json
import os
import tempfile
import unittest

import numpy as np

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import punctuality_monitor as pm


class TestTimeHelpers(unittest.TestCase):
    def test_parse_valid(self):
        self.assertEqual(pm.parse_time("08:05"), 485)
        self.assertEqual(pm.parse_time("23:59"), 1439)

    def test_parse_invalid(self):
        for bad in ["25:61", "", "9.30", "12:5x", "24:00", None]:
            with self.assertRaises(ValueError):
                pm.parse_time(bad)

    def test_delay_and_midnight(self):
        self.assertEqual(pm.compute_delay(600, 607), 7)
        self.assertEqual(pm.compute_delay(600, 598), -2)
        self.assertEqual(pm.compute_delay(pm.parse_time("23:55"), pm.parse_time("00:10")), 15)

    def test_classify(self):
        self.assertEqual(pm.classify(-3), "Early")
        self.assertEqual(pm.classify(0), "On time")
        self.assertEqual(pm.classify(5), "On time")
        self.assertEqual(pm.classify(6), "Late")
        self.assertEqual(pm.classify(16), "Severely late")


class TestTrip(unittest.TestCase):
    def test_trip_fields(self):
        t = pm.Trip("T1", "R1", "2026-09-07", "Sector V", "09:35", "09:42")
        self.assertEqual(t.delay, 7)
        self.assertEqual(t.status, "Late")
        self.assertTrue(t.is_peak)
        d = t.to_dict()
        self.assertEqual(d["delay_min"], 7)
        self.assertEqual(pm.Trip.from_dict({**d, "scheduled": d["scheduled"]}).delay, 7)

    def test_bad_date_and_empty(self):
        with self.assertRaises(ValueError):
            pm.Trip("T1", "R1", "07/09/2026", "A", "09:00", "09:01")
        with self.assertRaises(ValueError):
            pm.Trip("", "R1", "2026-09-07", "A", "09:00", "09:01")


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routes = pm.default_routes()
        cls.raw = pm.generate_sample_data(cls.routes)
        cls.trips, cls.rejected = pm.validate_rows(cls.raw, cls.routes)
        cls.df = pm.build_dataframe(cls.trips, cls.routes)

    def test_counts(self):
        self.assertEqual(len(self.raw), 1349)
        self.assertEqual(len(self.trips), 1344)
        self.assertEqual(len(self.rejected), 5)

    def test_reproducible(self):
        self.assertEqual(self.raw, pm.generate_sample_data(self.routes))

    def test_numpy_stats(self):
        s = pm.delay_stats(np.array([0, 2, 4, 6, 20]))
        self.assertEqual(s["mean_delay"], 6.4)
        self.assertEqual(s["median_delay"], 4.0)
        self.assertEqual(s["on_time_pct"], 60.0)

    def test_histogram_total(self):
        counts, _ = pm.delay_histogram(self.df["delay_min"].to_numpy())
        self.assertEqual(int(counts.sum()), len(self.df))

    def test_route_and_day_summary(self):
        self.assertEqual(len(pm.route_summary(self.df)), 3)
        self.assertEqual(len(pm.day_summary(self.df)), 14)
        self.assertEqual(int(pm.route_summary(self.df)["records"].sum()), len(self.df))

    def test_csv_and_routes_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "trips.csv")
            pm.save_trips_csv(self.raw, p)
            self.assertEqual(len(pm.load_trips_csv(p)), 1349)
            rp = os.path.join(d, "routes.csv")
            pm.save_routes(self.routes, rp)
            self.assertEqual(pm.load_routes(rp), self.routes)

    def test_missing_column(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.csv")
            with open(p, "w") as f:
                f.write("trip_id,route_id\nT1,R1\n")
            with self.assertRaises(ValueError):
                pm.load_trips_csv(p)

    def test_json_export(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "summary.json")
            pm.export_json(self.df, self.rejected, p)
            with open(p) as fh:
                data = json.load(fh)
            self.assertEqual(data["overall"]["records"], 1344)
            self.assertEqual(len(data["by_route"]), 3)
            self.assertEqual(data["rejected_rows"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
