"""Charts drawn with Matplotlib.

Every function returns a matplotlib Figure. The desktop app puts the Figure inside a
Tkinter window with FigureCanvasTkAgg; save_png() writes the same Figure to a PNG file.

Figures are made with matplotlib.figure.Figure (the object-oriented API), not pyplot, so no
global pyplot state is involved and every chart is an ordinary object.
"""
import matplotlib
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure

from . import settings

# Palette shared with the desktop interface (noor/gui/styles.py)
PAPER = "#FFFBF2"   # card background the charts sit on
INK = "#1F1A17"     # text
WINE = "#7F011F"    # main series
OCHRE = "#B07A1E"   # second series
OLIVE = "#55652E"   # third series
RULE = "#B9A67E"    # axis lines
MUTED = "#6B5E4B"
CATEGORY_COLOURS = {
    "Low": "#C9BE97",
    "Moderate": "#D9B45A",
    "High": "#A9481F",
    "Severe": "#7F011F",
    "Extreme": "#3E0010",
    "Insufficient data": "#9A9078",
}
CATEGORY_ORDER = ["Low", "Moderate", "High", "Severe", "Extreme", "Insufficient data"]
# sand -> ochre -> rust -> wine -> deep wine, for heatmaps
HEAT_CMAP = LinearSegmentedColormap.from_list("noor_heat", ["#F5EBD0", "#D9B45A", "#A9481F", "#7F011F", "#3E0010"])
HEAT_CMAP.set_bad("#A3A3A3")  # missing values (NaN) are drawn grey

# Theme settings applied once to every figure.
matplotlib.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "figure.facecolor": PAPER,
    "axes.facecolor": PAPER,
    "savefig.facecolor": PAPER,
    "text.color": INK,
    "axes.labelcolor": INK,
    "axes.edgecolor": RULE,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.grid": False,
    "legend.frameon": False,
})


def new_figure(width, height):
    """An empty Figure with constrained layout (labels never overlap the edge)."""
    return Figure(figsize=(width, height), dpi=100, facecolor=PAPER, layout="constrained")


def style_axes(ax, title):
    """The one shared chart style: bold wine title on the left, only left and bottom lines."""
    ax.set_title(title, loc="left", fontsize=10, color=WINE, fontweight="bold", pad=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(RULE)
    ax.tick_params(labelsize=8, length=3)


def save_png(fig, path):
    """Write a Figure to a PNG file."""
    fig.savefig(path, format="png", dpi=110, facecolor=fig.get_facecolor())


def empty_chart(message, width=6, height=1.6):
    """A small figure that says why there is no chart (instead of an empty box)."""
    fig = new_figure(width, height)
    ax = fig.add_subplot()
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center", color=MUTED, fontsize=10)
    return fig


def trend_chart(table, title):
    """Line chart of Tmax, Tmin and heat index per day; missing days marked along the bottom."""
    if table.empty or table["t_max"].notna().sum() == 0:
        return empty_chart("No observations in this period", 9, 3.4)
    fig = new_figure(9, 3.4)
    ax = fig.add_subplot()
    ax.plot(table.index, table["t_max"], color=WINE, linewidth=1.8, label="Max temperature")
    ax.plot(table.index, table["t_min"], color=OLIVE, linewidth=1.4, label="Min temperature")
    ax.plot(table.index, table["heat_index"], color=OCHRE, linewidth=1.2, linestyle="--", label="Heat index")
    ax.axhline(settings.HOT_DAY_C, color=WINE, linewidth=0.7, alpha=0.5)
    missing = table.index[table["t_max"].isna()]
    if len(missing):
        low = np.nanmin(table[["t_min", "t_max"]].to_numpy())
        ax.scatter(missing, [low - 1] * len(missing), marker="|", color=MUTED, s=60, label="Missing day")
    style_axes(ax, title)
    ax.set_ylabel("°C", color=MUTED)
    ax.legend(fontsize=8, ncol=4, loc="upper left")
    fig.autofmt_xdate()
    return fig


def risk_distribution(assessments):
    """Bar chart: how many locations fall in each risk category."""
    if not assessments:
        return empty_chart("No assessments yet", 5, 3)
    counts = {name: 0 for name in CATEGORY_ORDER}
    for a in assessments:
        counts[a["category"]] = counts.get(a["category"], 0) + 1
    names = [n for n in CATEGORY_ORDER if counts[n] or n != "Insufficient data"]
    fig = new_figure(5, 3)
    ax = fig.add_subplot()
    bars = ax.bar(names, [counts[n] for n in names], color=[CATEGORY_COLOURS[n] for n in names])
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1, f"{bar.get_height():.0f}",
                ha="center", va="bottom", fontsize=9, color=INK)
    style_axes(ax, "Locations per risk category")
    ax.set_ylabel("Locations", color=MUTED)
    ax.set_ylim(0, max(counts.values()) + 1.5)
    ax.tick_params(axis="x", labelsize=8)
    return fig


def risk_bars(assessments):
    """Horizontal bar chart of risk scores, coloured by category."""
    rows = [a for a in assessments if a["score"] is not None]
    if not rows:
        return empty_chart("No scored locations")
    rows = sorted(rows, key=lambda a: a["score"])
    fig = new_figure(7, 0.3 * len(rows) + 1.2)
    ax = fig.add_subplot()
    ax.barh([f"{a['code']} {a['name']}" for a in rows], [a["score"] for a in rows],
            color=[CATEGORY_COLOURS.get(a["category"], MUTED) for a in rows])
    for threshold, _name in settings.CATEGORIES[:-1]:
        ax.axvline(threshold, color=RULE, linewidth=0.5, linestyle=":", zorder=0)
    style_axes(ax, "Heat-risk score by location (0-100)")
    ax.set_xlim(0, 100)
    return fig


def score_histogram(assessments):
    """Histogram of scores with the category thresholds drawn in."""
    scores = [a["score"] for a in assessments if a["score"] is not None]
    if not scores:
        return empty_chart("No scored locations")
    fig = new_figure(6, 2.8)
    ax = fig.add_subplot()
    ax.hist(scores, bins=np.arange(0, 105, 5), color=WINE, edgecolor=PAPER)  # histogram
    for threshold, name in settings.CATEGORIES[:-1]:
        ax.axvline(threshold, color=MUTED, linewidth=0.8, linestyle=":")
        ax.text(threshold + 1, ax.get_ylim()[1] * 0.9, name, fontsize=7, color=MUTED)
    style_axes(ax, "How scores are spread")
    ax.set_xlabel("Score", color=MUTED)
    ax.set_ylabel("Locations", color=MUTED)
    return fig


def risk_map(assessments, value="score"):
    """Heatmap (imshow) of the schematic ward grid (not to scale, not official boundaries)."""
    cells = [a for a in assessments if a.get("grid_x") is not None and a.get("grid_y") is not None]
    if not cells:
        return empty_chart("No locations with a schematic position")
    cols = sorted({a["grid_x"] for a in cells})
    rows = sorted({a["grid_y"] for a in cells})
    grid = np.full((len(rows), len(cols)), np.nan)  # NaN = no ward in this cell
    fig = new_figure(7.5, 6)
    ax = fig.add_subplot()
    for a in cells:
        r, c = rows.index(a["grid_y"]), cols.index(a["grid_x"])
        v = a.get(value)
        grid[r, c] = np.nan if v is None else (v if value == "score" else v * 100)
        shown = "n/a" if v is None else f"{grid[r, c]:.0f}"
        dark = not np.isnan(grid[r, c]) and grid[r, c] > 45  # light text on dark cells
        ax.text(c, r, f"{a['code']}\n{a['name'][:14]}\n{shown}", ha="center", va="center", fontsize=8,
                color="white" if dark else INK)
    image = ax.imshow(np.ma.masked_invalid(grid), cmap=HEAT_CMAP, vmin=0, vmax=100)
    # white gaps between cells: minor grid lines on the cell borders
    ax.set_xticks(np.arange(len(cols) + 1) - 0.5, minor=True)
    ax.set_yticks(np.arange(len(rows) + 1) - 0.5, minor=True)
    ax.grid(which="minor", color=PAPER, linewidth=3)
    ax.tick_params(which="both", length=0)
    ax.set_xticks([])
    ax.set_yticks([])
    fig.colorbar(image, ax=ax, shrink=0.7, label=value.replace("_", " ") + " (0-100)")
    style_axes(ax, f"Schematic ward grid: {value.replace('_', ' ')} (not to scale)")
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    return fig


def temperature_heatmap(frame, days=30):
    """Heatmap (imshow) of daily maximum temperature: locations x the last `days` days."""
    observed = frame[frame["is_forecast"] == 0]
    if observed.empty:
        return empty_chart("No observations")
    last = pd.to_datetime(observed["date"]).max()
    recent = observed[pd.to_datetime(observed["date"]) > last - pd.Timedelta(days=days)]
    pivot = recent.pivot_table(index="location", columns="date", values="t_max")  # Pandas pivot table
    fig = new_figure(10, 0.32 * len(pivot) + 1.6)
    ax = fig.add_subplot()
    image = ax.imshow(np.ma.masked_invalid(pivot.to_numpy()), cmap=HEAT_CMAP, aspect="auto")
    step = max(1, len(pivot.columns) // 15)  # at most about 15 date labels
    ax.set_xticks(np.arange(0, len(pivot.columns), step), [c[5:] for c in pivot.columns[::step]], rotation=60)
    ax.set_yticks(np.arange(len(pivot.index)), pivot.index)
    fig.colorbar(image, ax=ax, label="Max temperature °C")
    style_axes(ax, f"Daily maximum temperature, last {days} days (grey = missing)")
    ax.tick_params(labelsize=7, colors=MUTED)
    return fig


def monthly_chart(table):
    """Monthly mean Tmax, Tmin and humidity (table from climate.monthly_means)."""
    if table.empty:
        return empty_chart("No observations")
    fig = new_figure(8, 3)
    ax = fig.add_subplot()
    ax.plot(table["month"], table["t_max"], color=WINE, marker="o", label="Mean max temperature (°C)")
    ax.plot(table["month"], table["t_min"], color=OLIVE, marker="o", label="Mean min temperature (°C)")
    ax2 = ax.twinx()  # humidity has its own scale on the right
    ax2.bar(table["month"], table["humidity"], color=OCHRE, alpha=0.25, label="Mean humidity (%)")
    ax2.set_ylim(0, 100)
    ax2.tick_params(labelsize=8, colors=MUTED)
    ax2.spines["top"].set_visible(False)
    ax.set_zorder(ax2.get_zorder() + 1)  # lines in front of the bars
    ax.patch.set_visible(False)
    style_axes(ax, "Monthly means across all locations")
    lines = ax.get_legend_handles_labels()
    bars = ax2.get_legend_handles_labels()
    ax.legend(lines[0] + bars[0], lines[1] + bars[1], fontsize=8, loc="upper left")
    return fig


def allocation_chart(plan):
    """Grouped bars: demand vs served per resource type."""
    types = list(plan["by_type"])
    demand = [plan["by_type"][t]["demand"] for t in types]
    served = [plan["by_type"][t]["served"] for t in types]
    labels = [t.replace("_", " ") for t in types]
    fig = new_figure(8, 3)
    ax = fig.add_subplot()
    x = np.arange(len(types))
    ax.bar(x - 0.2, demand, width=0.4, color=OCHRE, label="Estimated demand")
    ax.bar(x + 0.2, served, width=0.4, color=WINE, label="Can be served")
    ax.set_xticks(x, labels)
    ax.set_yscale("log")
    style_axes(ax, "Demand vs capacity per day (log scale)")
    ax.legend(fontsize=8)
    return fig


def scenario_chart(comparison):
    """Bars of each location's score before and after the scenario."""
    rows = [r for r in comparison["locations"] if r["score_before"] is not None and r["score_after"] is not None]
    if not rows:
        return empty_chart("No scored locations")
    fig = new_figure(9, 3.2)
    ax = fig.add_subplot()
    x = np.arange(len(rows))
    ax.bar(x - 0.2, [r["score_before"] for r in rows], width=0.4, color=OLIVE, label="Today")
    ax.bar(x + 0.2, [r["score_after"] for r in rows], width=0.4, color=WINE, label="Scenario")
    ax.set_xticks(x, [r["code"] for r in rows], rotation=60)
    ax.set_ylim(0, 100)
    style_axes(ax, "Risk score: today vs scenario")
    ax.legend(fontsize=8)
    return fig


def dimension_chart(result):
    """Four bars for one location's dimensions (capacity shown as lack of capacity)."""
    names = ["Hazard", "Exposure", "Vulnerability", "Lack of capacity"]
    capacity = result["capacity"]
    values = [result["hazard"], result["exposure"], result["vulnerability"],
              None if capacity is None else 1 - capacity]
    fig = new_figure(5.5, 2.5)
    ax = fig.add_subplot()
    heights = [0 if v is None else v for v in values]
    bars = ax.bar(names, heights, color=[WINE if v is not None else "#CFC6B0" for v in values])
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                "missing" if v is None else f"{v:.2f}", ha="center", fontsize=8, color=INK)
    ax.set_ylim(0, 1.15)
    style_axes(ax, f"{result['code']}: dimensions (0 = best, 1 = worst)")
    return fig
