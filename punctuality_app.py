"""
Public-Transport Punctuality Monitor - desktop app (Tkinter)

Run in IDLE with Run > Run Module (F5), or:  python punctuality_app.py

Uses the analysis functions in punctuality_monitor.py. Start-up loads the built-in
synthetic dataset; use "Open CSV" to analyse your own trips file.
"""

import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import punctuality_monitor as pm

HERE = os.path.dirname(os.path.abspath(__file__))


class PunctualityApp:
    def __init__(self, root):
        self.root = root
        root.title("Public-Transport Punctuality Monitor")
        root.geometry("1100x760")
        root.minsize(900, 640)

        self.routes = pm.default_routes()
        self.trips = []
        self.rejected = []
        self.df_all = None       # all valid trips
        self.df = None           # after filters
        self.source = ""
        self.canvases = {}

        self._build()
        self.use_sample()

    # ------------------------------------------------------------ layout
    def _build(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="Open CSV...", command=self.open_csv).pack(side="left")
        ttk.Button(top, text="Use sample data", command=self.use_sample).pack(side="left", padx=(6, 18))

        ttk.Label(top, text="Route:").pack(side="left")
        self.route_var = tk.StringVar(value="All")
        self.route_box = ttk.Combobox(top, textvariable=self.route_var, state="readonly", width=8,
                                      values=["All"] + list(self.routes))
        self.route_box.pack(side="left", padx=(4, 14))
        self.route_box.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Label(top, text="Period:").pack(side="left")
        self.period_var = tk.StringVar(value="All")
        box = ttk.Combobox(top, textvariable=self.period_var, state="readonly", width=10,
                           values=["All", "Peak", "Off-peak"])
        box.pack(side="left", padx=(4, 14))
        box.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Button(top, text="Export JSON...", command=self.export_json).pack(side="right")
        ttk.Button(top, text="Save charts...", command=self.save_charts).pack(side="right", padx=6)

        # metric cards
        cards = ttk.Frame(self.root, padding=(8, 0))
        cards.pack(fill="x")
        self.card_vars = {}
        for key, label in [("records", "Stop arrivals"), ("mean", "Mean delay (min)"),
                           ("median", "Median delay (min)"), ("ontime", "On time"),
                           ("severe", "Severely late")]:
            f = tk.Frame(cards, bd=1, relief="solid", padx=10, pady=6, bg="#f4f6fb")
            f.pack(side="left", expand=True, fill="x", padx=3, pady=6)
            v = tk.StringVar(value="-")
            tk.Label(f, textvariable=v, font=("Segoe UI", 16, "bold"), bg="#f4f6fb", fg="#1f3864").pack()
            tk.Label(f, text=label, font=("Segoe UI", 9), bg="#f4f6fb", fg="#444").pack()
            self.card_vars[key] = v

        # tabs
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.tabs = {}
        for key, title in [("routes", "Routes"), ("dist", "Delay distribution"), ("series", "Time series"),
                           ("hours", "By hour"), ("records", "Records & outliers"), ("summary", "Summary")]:
            frame = ttk.Frame(self.nb)
            self.nb.add(frame, text=title)
            self.tabs[key] = frame

        # records table
        cols = ("trip_id", "route_id", "service_date", "stop_name", "scheduled", "actual", "delay_min", "status")
        self.tree = ttk.Treeview(self.tabs["records"], columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=110, anchor="w")
        sb = ttk.Scrollbar(self.tabs["records"], orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("outlier", background="#fde7d3")

        # summary text
        self.text = tk.Text(self.tabs["summary"], wrap="word", font=("Consolas", 10), padx=10, pady=10)
        self.text.pack(fill="both", expand=True)

        self.status = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.status, anchor="w", padding=(8, 2)).pack(fill="x")

    # ------------------------------------------------------------ data
    def use_sample(self):
        routes_file = os.path.join(HERE, "data", "routes.csv")
        self.routes = pm.load_routes(routes_file) if os.path.exists(routes_file) else pm.default_routes()
        rows = pm.generate_sample_data(self.routes)
        self.load_rows(rows, "built-in synthetic sample (not real data)", popup=False)

    def open_csv(self):
        path = filedialog.askopenfilename(title="Open trips CSV", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            rows = pm.load_trips_csv(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot open file", str(exc))
            return
        sibling = os.path.join(os.path.dirname(path), "routes.csv")
        if os.path.exists(sibling):
            try:
                self.routes = pm.load_routes(sibling)
            except (KeyError, ValueError):
                pass
        self.load_rows(rows, os.path.basename(path))

    def load_rows(self, rows, source, popup=True):
        trips, rejected = pm.validate_rows(rows, self.routes)
        if not trips:
            messagebox.showwarning("No valid rows", "None of the %d rows passed validation." % len(rows))
            return
        self.trips, self.rejected, self.source = trips, rejected, source
        self.df_all = pm.build_dataframe(trips, self.routes)
        self.route_box.configure(values=["All"] + sorted(self.df_all["route_id"].unique()))
        self.route_var.set("All")
        self.period_var.set("All")
        self.refresh()
        msg = "%s: %d rows, %d valid, %d rejected" % (source, len(rows), len(trips), len(rejected))
        self.status.set(msg)
        if rejected and popup:
            shown = "\n".join("Row %d: %s" % r for r in rejected[:12])
            more = "\n... and %d more" % (len(rejected) - 12) if len(rejected) > 12 else ""
            messagebox.showinfo("Rejected rows", "%d rows were skipped:\n\n%s%s" % (len(rejected), shown, more))

    def filtered(self):
        df = self.df_all
        if self.route_var.get() != "All":
            df = df[df["route_id"] == self.route_var.get()]
        if self.period_var.get() != "All":
            df = df[df["period"] == self.period_var.get()]
        return df

    # ------------------------------------------------------------ display
    def refresh(self):
        df = self.filtered()
        self.df = df
        if df.empty:
            self.status.set("No records match the selected filters.")
            return
        st = pm.delay_stats(df["delay_min"].to_numpy())
        self.card_vars["records"].set("%d" % st["records"])
        self.card_vars["mean"].set("%.2f" % st["mean_delay"])
        self.card_vars["median"].set("%.1f" % st["median_delay"])
        self.card_vars["ontime"].set("%.1f%%" % st["on_time_pct"])
        self.card_vars["severe"].set("%d" % int((df["delay_min"] > pm.SEVERE_LIMIT).sum()))

        self._show("routes", pm.fig_route_bars(df))
        self._show("dist", pm.fig_distribution(df))
        self._show("series", pm.fig_time_series(df))
        self._show("hours", pm.fig_peak_hours(df))
        self._fill_table(df)
        self._fill_summary(df, st)
        if self.source:
            self.status.set("Source: %s | showing %d of %d valid arrivals" % (self.source, len(df), len(self.df_all)))

    def _show(self, key, fig):
        old = self.canvases.get(key)
        if old is not None:
            old.get_tk_widget().destroy()
        fig.set_size_inches(9, 4.6)
        canvas = FigureCanvasTkAgg(fig, master=self.tabs[key])
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvases[key] = canvas

    def _fill_table(self, df):
        self.tree.delete(*self.tree.get_children())
        *_, lo, hi = pm.iqr_bounds(df["delay_min"].to_numpy())
        # worst delays first, so outliers are visible at the top
        for _, r in df.sort_values("delay_min", ascending=False).head(500).iterrows():
            tag = ("outlier",) if (r["delay_min"] < lo or r["delay_min"] > hi) else ()
            self.tree.insert("", "end", tags=tag, values=(
                r["trip_id"], r["route_id"], r["service_date"].strftime("%Y-%m-%d"), r["stop_name"],
                r["scheduled"], r["actual"], r["delay_min"], r["status"]))

    def _fill_summary(self, df, st):
        q1, q3, iqr, lo, hi = pm.iqr_bounds(df["delay_min"].to_numpy())
        n_out = len(pm.outlier_table(df))
        lines = [
            "SUMMARY (%s | route: %s | period: %s)" % (self.source, self.route_var.get(), self.period_var.get()),
            "",
            "Stop arrivals: %d   Mean: %.2f min   Median: %.2f min   Std: %.2f   P90: %.1f min"
            % (st["records"], st["mean_delay"], st["median_delay"], st["std_delay"], st["p90_delay"]),
            "On time (-1 to +5 min): %.1f%%   Severely late (>15 min): %.1f%%" % (st["on_time_pct"], st["severe_pct"]),
            "IQR fences: %.1f to %.1f min   Outliers flagged: %d" % (lo, hi, n_out),
            "",
            "BY ROUTE", pm.route_summary(df).to_string(index=False),
            "",
            "BY PERIOD", pm.period_summary(df).to_string(index=False),
            "",
            "BY DAY", pm.day_summary(df).to_string(index=False),
            "",
            "Note: these figures are descriptive. They do not explain why delays occur.",
        ]
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", "\n".join(lines))
        self.text.configure(state="disabled")

    # ------------------------------------------------------------ export
    def export_json(self):
        if self.df is None or self.df.empty:
            return
        path = filedialog.asksaveasfilename(title="Export summary", defaultextension=".json",
                                            initialfile="summary.json", filetypes=[("JSON", "*.json")])
        if path:
            pm.export_json(self.df, self.rejected, path)
            self.status.set("Summary exported to " + path)

    def save_charts(self):
        if self.df is None or self.df.empty:
            return
        folder = filedialog.askdirectory(title="Choose a folder for the chart images")
        if folder:
            pm.plot_route_bars(self.df, os.path.join(folder, "fig_route_bars.png"))
            pm.plot_distribution(self.df, os.path.join(folder, "fig_distribution.png"))
            pm.plot_time_series(self.df, os.path.join(folder, "fig_time_series.png"))
            pm.plot_peak_hours(self.df, os.path.join(folder, "fig_peak_hours.png"))
            self.status.set("Charts saved in " + folder)


def main():
    root = tk.Tk()
    PunctualityApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
