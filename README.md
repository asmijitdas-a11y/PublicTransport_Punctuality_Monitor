# Public-Transport Punctuality Monitor

Python Programming Laboratory project (B.Tech, Electronics and Communication Engineering),
Institute of Engineering & Management, Kolkata. Section D1, session 2026-2027.
Submitted to Prof. Indranil Basu.

**Team:** Srinjay Mukherjee, Prithwish Chakraborty, Shankhanil Ghosh, Amit Majumder, Asmijit Das

The program analyses scheduled versus actual arrival times of a small shuttle service, computes
the delay at every stop, and reports how punctual each route, day and time of day is.

| Requirement | Where it is implemented |
|---|---|
| Compute delays and validate time inputs | `parse_time()`, `compute_delay()`, `Trip`, `validate_rows()` |
| NumPy for delay distributions | `delay_stats()`, `delay_histogram()`, `iqr_bounds()` |
| Stop/route records in files | `data/routes.csv`, `data/sample_trips.csv`, `load_routes()`, `load_trips_csv()` |
| `Trip` class | `Trip` in `punctuality_monitor.py` |
| Pandas route/day summaries and JSON export | `route_summary()`, `day_summary()`, `export_json()` |
| Delay bars and time-series plots | `fig_route_bars()`, `fig_time_series()` and two more charts |

![Desktop app](docs/screenshots/app_routes.png)

## Files

```
punctuality_monitor.py   analysis module and command-line run (Trip class, NumPy, Pandas, JSON, charts)
punctuality_app.py       Tkinter desktop dashboard
data/                    routes.csv and a synthetic sample_trips.csv
tests/                   unit tests (14)
docs/                    project report (PDF and Word), sample charts, app screenshots
requirements.txt
```

## Setup

Python 3.9 or newer. Tkinter ships with the standard Python installer (on some Linux systems install `python3-tk`).

```
pip install -r requirements.txt
```

## Run

Desktop app (or open the file in IDLE and press F5):

```
python punctuality_app.py
```

Use **Open CSV** to load your own trips file, filter by route and period, and use **Export JSON** or
**Save charts** to write results.

Analysis without a window. This writes `summary.json`, `trips_with_delays.csv` and four PNG charts to `output/`:

```
python punctuality_monitor.py                    # built-in synthetic dataset
python punctuality_monitor.py data/sample_trips.csv
```

## Input CSV format

Required headers (exact spelling): `trip_id, route_id, service_date, stop_name, scheduled, actual`.
Times are 24-hour `HH:MM`, dates are `YYYY-MM-DD`. Route and stop names must exist in `routes.csv`
(`route_id, route_name, stop_order, stop_name, offset_min`). Invalid rows are skipped and reported.

## Punctuality classes

Early: more than 1 minute early. On time: -1 to +5 minutes. Late: 6 to 15 minutes. Severely late: more than 15 minutes.

## Tests

```
python -m unittest discover -s tests -v
```

## Data note

The included dataset is synthetically generated with a fixed random seed (2026). It is not data from a real
transport operator, so the results describe the behaviour of the software and not of any real service.
The analysis is descriptive and does not explain the causes of delay.
