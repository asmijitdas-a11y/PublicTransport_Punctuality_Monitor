"""
Public-Transport Punctuality Monitor
Python Programming Laboratory - Project topic 4

Analyses scheduled versus actual arrival times for a small shuttle service.

  * Trip class .......... one scheduled stop call, with time validation and delay
  * stop/route records .. kept in files (routes.csv, trips.csv)
  * NumPy ............... delay distributions (mean, median, percentiles, histogram)
  * Pandas .............. route-wise and day-wise summaries
  * JSON export ......... summary.json
  * Matplotlib .......... delay bars and time-series plots (PNG files)

Run in IDLE with Run > Run Module (F5), or:  python punctuality_monitor.py [trips.csv]
With no argument a reproducible synthetic dataset is generated (NOT real data).
"""

import csv
import json
import os
import random
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
from matplotlib.figure import Figure  # no pyplot: works for PNG files and inside Tkinter

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
ON_TIME_EARLY_LIMIT = -1   # up to 1 minute early still counts as on time
ON_TIME_LATE_LIMIT = 5     # up to 5 minutes late still counts as on time
SEVERE_LIMIT = 15          # more than 15 minutes late = severely late
PEAK_HOURS = (7, 8, 9, 17, 18, 19)   # scheduled hour of day treated as peak
TRIP_FIELDS = ["trip_id", "route_id", "service_date", "stop_name", "scheduled", "actual"]
ROUTE_FIELDS = ["route_id", "route_name", "stop_order", "stop_name", "offset_min"]


# ----------------------------------------------------------------------------
# Time helpers and classification
# ----------------------------------------------------------------------------
def parse_time(text):
    """Convert 'HH:MM' (24-hour) to minutes after midnight; raise ValueError if invalid."""
    if not isinstance(text, str):
        raise ValueError("time must be text in HH:MM form")
    parts = text.strip().split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError("time must look like HH:MM, got %r" % text)
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("time out of range: %r" % text)
    return hh * 60 + mm


def format_time(minutes):
    return "%02d:%02d" % (minutes // 60, minutes % 60)


def compute_delay(scheduled_min, actual_min):
    """Delay in minutes (positive = late). Handles a service that crosses midnight."""
    delay = actual_min - scheduled_min
    if delay < -720:
        delay += 1440
    elif delay > 720:
        delay -= 1440
    return delay


def classify(delay):
    if delay < ON_TIME_EARLY_LIMIT:
        return "Early"
    if delay <= ON_TIME_LATE_LIMIT:
        return "On time"
    if delay <= SEVERE_LIMIT:
        return "Late"
    return "Severely late"


# ----------------------------------------------------------------------------
# Trip class
# ----------------------------------------------------------------------------
class Trip:
    """One scheduled stop call of a shuttle trip and when the vehicle actually arrived."""

    def __init__(self, trip_id, route_id, service_date, stop_name, scheduled, actual):
        self.trip_id = str(trip_id).strip()
        self.route_id = str(route_id).strip()
        self.service_date = str(service_date).strip()
        self.stop_name = str(stop_name).strip()
        if not (self.trip_id and self.route_id and self.stop_name):
            raise ValueError("trip_id, route_id and stop_name must not be empty")
        try:
            date.fromisoformat(self.service_date)
        except ValueError:
            raise ValueError("service_date must be YYYY-MM-DD, got %r" % service_date)
        self.scheduled_min = parse_time(scheduled)
        self.actual_min = parse_time(actual)

    @property
    def delay(self):
        return compute_delay(self.scheduled_min, self.actual_min)

    @property
    def status(self):
        return classify(self.delay)

    @property
    def is_peak(self):
        return self.scheduled_min // 60 in PEAK_HOURS

    @classmethod
    def from_dict(cls, row):
        return cls(row.get("trip_id", ""), row.get("route_id", ""), row.get("service_date", ""),
                   row.get("stop_name", ""), row.get("scheduled", ""), row.get("actual", ""))

    def to_dict(self):
        return {
            "trip_id": self.trip_id, "route_id": self.route_id,
            "service_date": self.service_date, "stop_name": self.stop_name,
            "scheduled": format_time(self.scheduled_min),
            "actual": format_time(self.actual_min),
            "delay_min": self.delay, "status": self.status, "peak": self.is_peak,
        }

    def __repr__(self):
        return "Trip(%s, %s, %s, sched=%s, actual=%s, delay=%+d)" % (
            self.trip_id, self.route_id, self.stop_name,
            format_time(self.scheduled_min), format_time(self.actual_min), self.delay)


# ----------------------------------------------------------------------------
# Route / stop records (dictionaries <-> CSV files)
# ----------------------------------------------------------------------------
def default_routes():
    """Route table as a dictionary: route_id -> {name, stops:[(stop, offset_min)]}."""
    return {
        "R1": {"name": "Campus - Sector V",
               "stops": [("Campus Gate", 0), ("Salt Lake Stadium", 12), ("City Centre", 22), ("Sector V", 35)]},
        "R2": {"name": "Campus - Esplanade",
               "stops": [("Campus Gate", 0), ("Ultadanga", 14), ("Sealdah", 26), ("Esplanade", 40)]},
        "R3": {"name": "Campus - Howrah",
               "stops": [("Campus Gate", 0), ("Park Circus", 15), ("Park Street", 28), ("Howrah Station", 48)]},
    }


def save_routes(routes, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(ROUTE_FIELDS)
        for rid, info in routes.items():
            for order, (stop, off) in enumerate(info["stops"], start=1):
                w.writerow([rid, info["name"], order, stop, off])


def load_routes(path):
    routes = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            r = routes.setdefault(row["route_id"], {"name": row["route_name"], "stops": []})
            r["stops"].append((row["stop_name"], int(row["offset_min"])))
    return routes


# ----------------------------------------------------------------------------
# Synthetic data (fixed seed) and CSV input / output
# ----------------------------------------------------------------------------
def generate_sample_data(routes, seed=2026, days=14, start=date(2026, 9, 7)):
    """Return a list of raw row dictionaries, including a few deliberately bad rows."""
    rng = random.Random(seed)
    base = {"R1": 1.5, "R2": 3.0, "R3": 5.0}       # typical late minutes by route
    rows = []
    n = 0
    for d in range(days):
        day = start + timedelta(days=d)
        weekend = day.weekday() >= 5
        trips_per_day = [9, 12, 17] if weekend else [7, 8, 9, 10, 12, 14, 16, 17, 18, 19]
        trips_per_day = [h for h in trips_per_day]
        for rid, info in routes.items():
            for hour in trips_per_day:
                n += 1
                trip_id = "T%04d" % n
                peak = hour in PEAK_HOURS and not weekend
                incident = rng.random() < 0.012          # rare breakdown or road closure
                carry = rng.gauss(base[rid] * (1.6 if peak else 0.8), 1.5)
                if incident:
                    carry += rng.uniform(25, 45)
                for stop, off in info["stops"]:
                    sched = hour * 60 + off
                    carry += rng.gauss(0.4 if peak else 0.1, 0.8) if off else 0
                    actual = sched + int(round(carry))
                    if stop == "Campus Gate":
                        actual = sched + int(round(rng.gauss(0.5, 0.8)))
                    rows.append({
                        "trip_id": trip_id, "route_id": rid, "service_date": day.isoformat(),
                        "stop_name": stop, "scheduled": format_time(sched % 1440),
                        "actual": format_time(actual % 1440)})
    # deliberately problematic rows to exercise validation
    rows += [
        {"trip_id": "T9001", "route_id": "R1", "service_date": "2026-09-10", "stop_name": "Sector V",
         "scheduled": "09:35", "actual": "25:61"},                 # impossible time
        {"trip_id": "T9002", "route_id": "R2", "service_date": "2026-09-10", "stop_name": "Esplanade",
         "scheduled": "08:40", "actual": ""},                      # blank actual time
        {"trip_id": "T9003", "route_id": "R9", "service_date": "2026-09-11", "stop_name": "Unknown",
         "scheduled": "10:00", "actual": "10:03"},                 # unknown route
        {"trip_id": "T9004", "route_id": "R3", "service_date": "11/09/2026", "stop_name": "Park Street",
         "scheduled": "12:28", "actual": "12:31"},                 # bad date format
        {"trip_id": "T9005", "route_id": "R1", "service_date": "2026-09-12", "stop_name": "City Centre",
         "scheduled": "9.30", "actual": "09:33"},                  # malformed scheduled time
    ]
    return rows


def save_trips_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRIP_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_trips_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in TRIP_FIELDS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("CSV is missing required columns: %s" % ", ".join(missing))
        return list(reader)


def validate_rows(rows, routes):
    """Return (list of Trip, list of (row number, reason)) for rejected rows."""
    trips, rejected = [], []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        try:
            t = Trip.from_dict(row)
            if t.route_id not in routes:
                raise ValueError("unknown route %r" % t.route_id)
            if t.stop_name not in [s for s, _ in routes[t.route_id]["stops"]]:
                raise ValueError("stop %r is not on route %s" % (t.stop_name, t.route_id))
            trips.append(t)
        except ValueError as exc:
            rejected.append((i, str(exc)))
    return trips, rejected


# ----------------------------------------------------------------------------
# NumPy statistics
# ----------------------------------------------------------------------------
def delay_stats(delays):
    d = np.asarray(delays, dtype=float)
    if d.size == 0:
        return {}
    on_time = (d >= ON_TIME_EARLY_LIMIT) & (d <= ON_TIME_LATE_LIMIT)
    return {
        "records": int(d.size),
        "mean_delay": round(float(d.mean()), 2),
        "median_delay": round(float(np.median(d)), 2),
        "std_delay": round(float(d.std(ddof=1)), 2) if d.size > 1 else 0.0,
        "p90_delay": round(float(np.percentile(d, 90)), 2),
        "max_delay": float(d.max()),
        "min_delay": float(d.min()),
        "on_time_pct": round(float(on_time.mean() * 100), 1),
        "severe_pct": round(float((d > SEVERE_LIMIT).mean() * 100), 1),
    }


def iqr_bounds(values, k=1.5):
    q1, q3 = np.percentile(values, [25, 75])
    iqr = q3 - q1
    return q1, q3, iqr, q1 - k * iqr, q3 + k * iqr


def delay_histogram(delays, bin_edges=(-10, -2, 0, 2, 5, 10, 15, 30, 60)):
    counts, edges = np.histogram(delays, bins=bin_edges)
    return counts, edges


# ----------------------------------------------------------------------------
# Pandas summaries
# ----------------------------------------------------------------------------
def build_dataframe(trips, routes):
    df = pd.DataFrame([t.to_dict() for t in trips])
    df["service_date"] = pd.to_datetime(df["service_date"])
    df["route_name"] = df["route_id"].map(lambda r: routes[r]["name"])
    df["hour"] = df["scheduled"].str.slice(0, 2).astype(int)
    df["on_time"] = df["delay_min"].between(ON_TIME_EARLY_LIMIT, ON_TIME_LATE_LIMIT)
    df["weekday"] = df["service_date"].dt.day_name()
    df["period"] = np.where(df["peak"], "Peak", "Off-peak")
    return df


def _summarise(group):
    return pd.Series({
        "records": len(group),
        "mean_delay": group["delay_min"].mean(),
        "median_delay": group["delay_min"].median(),
        "p90_delay": group["delay_min"].quantile(0.9),
        "max_delay": group["delay_min"].max(),
        "on_time_pct": group["on_time"].mean() * 100,
        "severe_pct": (group["delay_min"] > SEVERE_LIMIT).mean() * 100,
    })


def route_summary(df):
    return df.groupby(["route_id", "route_name"]).apply(_summarise, include_groups=False).round(2).reset_index()


def day_summary(df):
    out = df.groupby("service_date").apply(_summarise, include_groups=False).round(2).reset_index()
    out["weekday"] = out["service_date"].dt.day_name()
    return out


def route_day_summary(df):
    return df.pivot_table(index="service_date", columns="route_id", values="delay_min", aggfunc="mean").round(2)


def period_summary(df):
    return df.groupby("period").apply(_summarise, include_groups=False).round(2).reset_index()


def stop_summary(df):
    return (df.groupby(["route_id", "stop_name"], sort=False)["delay_min"]
              .agg(["count", "mean", "max"]).round(2).reset_index())


def outlier_table(df, k=1.5):
    *_, lo, hi = iqr_bounds(df["delay_min"].to_numpy(), k)
    return df[(df["delay_min"] < lo) | (df["delay_min"] > hi)]


# ----------------------------------------------------------------------------
# JSON export
# ----------------------------------------------------------------------------
def export_json(df, rejected, path):
    q1, q3, iqr, lo, hi = iqr_bounds(df["delay_min"].to_numpy())
    out = df.copy()
    summary = {
        "overall": delay_stats(df["delay_min"].to_numpy()),
        "rejected_rows": len(rejected),
        "iqr_rule": {"q1": q1, "q3": q3, "iqr": iqr, "upper_fence": hi, "lower_fence": lo},
        "by_route": json.loads(route_summary(out).to_json(orient="records")),
        "by_day": json.loads(day_summary(out).assign(
            service_date=lambda x: x["service_date"].dt.strftime("%Y-%m-%d")).to_json(orient="records")),
        "by_period": json.loads(period_summary(out).to_json(orient="records")),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    return summary


# ----------------------------------------------------------------------------
# Matplotlib charts
# ----------------------------------------------------------------------------
COLOURS = {"R1": "#1f5fa8", "R2": "#d9822b", "R3": "#3a8f5c"}


def fig_route_bars(df):
    rs = route_summary(df)
    fig = Figure(figsize=(9, 3.6))
    axes = fig.subplots(1, 2)
    cols = [COLOURS[r] for r in rs["route_id"]]
    axes[0].bar(rs["route_id"], rs["mean_delay"], color=cols)
    for x, v in zip(rs["route_id"], rs["mean_delay"]):
        axes[0].text(x, v + 0.1, "%.2f" % v, ha="center", fontsize=9)
    axes[0].set_ylabel("Mean delay (minutes)")
    axes[0].set_title("Mean delay by route")
    axes[1].bar(rs["route_id"], rs["on_time_pct"], color=cols)
    for x, v in zip(rs["route_id"], rs["on_time_pct"]):
        axes[1].text(x, v + 1, "%.1f%%" % v, ha="center", fontsize=9)
    axes[1].set_ylim(0, 105)
    axes[1].set_ylabel("On-time arrivals (%)")
    axes[1].set_title("On-time performance by route")
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def fig_distribution(df):
    delays = df["delay_min"].to_numpy()
    counts, edges = delay_histogram(delays)
    labels = []
    for a, b in zip(edges[:-1], edges[1:]):
        labels.append("%d to <%d" % (a, b))
    fig = Figure(figsize=(9, 3.6))
    axes = fig.subplots(1, 2)
    axes[0].bar(range(len(counts)), counts, color="#1f5fa8")
    axes[0].set_xticks(range(len(counts)))
    axes[0].set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    axes[0].set_xlabel("Delay band (minutes)")
    axes[0].set_ylabel("Number of stop arrivals")
    axes[0].set_title("Delay distribution")
    status = df["status"].value_counts().reindex(["Early", "On time", "Late", "Severely late"]).fillna(0)
    axes[1].bar(status.index, status.values, color=["#6fa8dc", "#3a8f5c", "#d9822b", "#b23a3a"])
    axes[1].set_title("Punctuality status counts")
    axes[1].set_ylabel("Number of stop arrivals")
    axes[1].tick_params(axis="x", labelsize=8)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def fig_time_series(df):
    pivot = route_day_summary(df)
    daily = day_summary(df).set_index("service_date")["mean_delay"]
    fig = Figure(figsize=(9, 3.8))
    ax = fig.subplots()
    for rid in pivot.columns:
        ax.plot(pivot.index, pivot[rid], marker="o", ms=3.5, lw=1.4, color=COLOURS[rid], label="Route " + rid)
    ax.plot(daily.index, daily.rolling(3, min_periods=1).mean(), color="black", lw=2, ls="--",
            label="All routes, 3-day rolling mean")
    ax.axhline(ON_TIME_LATE_LIMIT, color="grey", lw=0.8, ls=":")
    ax.text(pivot.index[0], ON_TIME_LATE_LIMIT + 0.15, "on-time limit (+5 min)", fontsize=8, color="grey")
    ax.set_ylabel("Mean delay (minutes)")
    ax.set_title("Daily mean delay by route")
    ax.legend(fontsize=8, ncol=2, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def fig_peak_hours(df):
    by_hour = df.groupby("hour")["delay_min"].mean()
    colours = ["#d9822b" if h in PEAK_HOURS else "#6fa8dc" for h in by_hour.index]
    fig = Figure(figsize=(9, 3.4))
    ax = fig.subplots()
    ax.bar([str(h) + ":00" for h in by_hour.index], by_hour.values, color=colours)
    ax.set_ylabel("Mean delay (minutes)")
    ax.set_xlabel("Scheduled hour (orange = peak)")
    ax.set_title("Mean delay by scheduled hour")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def _saver(make_fig):
    def save(df, path):
        make_fig(df).savefig(path, dpi=200)
    return save


plot_route_bars = _saver(fig_route_bars)
plot_distribution = _saver(fig_distribution)
plot_time_series = _saver(fig_time_series)
plot_peak_hours = _saver(fig_peak_hours)


# ----------------------------------------------------------------------------
# Main program
# ----------------------------------------------------------------------------
def run(csv_path=None, outdir="output"):
    os.makedirs(outdir, exist_ok=True)
    routes_file = os.path.join(outdir, "routes.csv")
    if os.path.exists(routes_file):
        routes = load_routes(routes_file)
    else:
        routes = default_routes()
        save_routes(routes, routes_file)

    if csv_path is None:
        raw = generate_sample_data(routes)
        csv_path = os.path.join(outdir, "trips.csv")
        save_trips_csv(raw, csv_path)
        print("Generated synthetic dataset ->", csv_path)
    rows = load_trips_csv(csv_path)
    trips, rejected = validate_rows(rows, routes)

    print("Input rows: %d | valid: %d | rejected: %d" % (len(rows), len(trips), len(rejected)))
    for rownum, reason in rejected:
        print("  rejected CSV row %d: %s" % (rownum, reason))

    df = build_dataframe(trips, routes)
    overall = delay_stats(df["delay_min"].to_numpy())
    print("\nOverall:", overall)
    print("\nBy route:\n", route_summary(df).to_string(index=False))
    print("\nBy period:\n", period_summary(df).to_string(index=False))
    print("\nBy day:\n", day_summary(df).to_string(index=False))
    out = outlier_table(df)
    print("\nIQR outliers (%d):\n%s" % (len(out), out[["trip_id", "route_id", "service_date", "stop_name",
                                                        "scheduled", "actual", "delay_min"]].to_string(index=False)))

    export_json(df, rejected, os.path.join(outdir, "summary.json"))
    df.drop(columns=["peak"]).to_csv(os.path.join(outdir, "trips_with_delays.csv"), index=False)
    plot_route_bars(df, os.path.join(outdir, "fig_route_bars.png"))
    plot_distribution(df, os.path.join(outdir, "fig_distribution.png"))
    plot_time_series(df, os.path.join(outdir, "fig_time_series.png"))
    plot_peak_hours(df, os.path.join(outdir, "fig_peak_hours.png"))
    print("\nSaved summary.json, trips_with_delays.csv and 4 figures in", os.path.abspath(outdir))
    return df, rejected


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
