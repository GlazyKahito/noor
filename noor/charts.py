"""Charts drawn with Matplotlib and Seaborn and returned as PNG bytes.

Matplotlib's pyplot keeps global state, so two threads drawing at once could mix their
figures. Every chart is therefore drawn while holding CHART_LOCK (threading.Lock).
"""
import io
import threading

import matplotlib

matplotlib.use("Agg")  # draw to memory, no window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

from . import settings  # noqa: E402

CHART_LOCK = threading.Lock()
INK = "#171719"
WINE = "#7F011F"
PAPER = "#FBF7EC"
GRID = "#E4DAC0"
MUTED = "#6B645A"
CATEGORY_COLOURS = {
    "Low": "#CFC5A5",
    "Moderate": "#E0A24A",
    "High": "#C4573A",
    "Severe": "#8E1630",
    "Extreme": "#4A0012",
    "Insufficient data": "#9A948A",
}


def _style(ax, title):
    """Shared look: paper background, light grid, no top/right frame."""
    ax.set_facecolor(PAPER)
    ax.figure.set_facecolor(PAPER)
    ax.set_title(title, loc="left", fontsize=11, color=INK, fontweight="bold", pad=10)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)


def _png(fig):
    """Save a figure to PNG bytes and close it."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buffer.getvalue()


def empty_chart(message):
    """A small PNG that says why there is no chart (instead of a broken image)."""
    with CHART_LOCK:
        fig, ax = plt.subplots(figsize=(6, 1.6))
        ax.axis("off")
        fig.set_facecolor(PAPER)
        ax.text(0.5, 0.5, message, ha="center", va="center", color=MUTED, fontsize=10)
        return _png(fig)


def trend_chart(table, title):
    """Line chart of Tmax, Tmin and heat index per day; missing days marked along the bottom."""
    if table.empty or table["t_max"].notna().sum() == 0:
        return empty_chart("No observations in this period")
    with CHART_LOCK:
        fig, ax = plt.subplots(figsize=(9, 3.6))
        ax.plot(table.index, table["t_max"], color=WINE, linewidth=1.8, label="Max temperature")
        ax.plot(table.index, table["t_min"], color="#B9A37A", linewidth=1.4, label="Min temperature")
        ax.plot(table.index, table["heat_index"], color=INK, linewidth=1, linestyle="--", label="Heat index")
        ax.axhline(settings.HOT_DAY_C, color=WINE, linewidth=0.7, alpha=0.5)
        missing = table.index[table["t_max"].isna()]
        if len(missing):
            low = np.nanmin(table[["t_min", "t_max"]].to_numpy())
            ax.scatter(missing, [low - 1] * len(missing), marker="|", color=MUTED, s=60, label="Missing day")
        _style(ax, title)
        ax.set_ylabel("°C", color=MUTED)
        ax.legend(fontsize=8, frameon=False, ncol=4, loc="upper left")
        fig.autofmt_xdate()
        return _png(fig)


def risk_bars(assessments):
    """Horizontal bar chart of risk scores, coloured by category."""
    rows = [a for a in assessments if a["score"] is not None]
    if not rows:
        return empty_chart("No scored locations")
    rows = sorted(rows, key=lambda a: a["score"])
    with CHART_LOCK:
        fig, ax = plt.subplots(figsize=(7, 0.32 * len(rows) + 1))
        ax.barh([f"{a['code']} {a['name']}" for a in rows], [a["score"] for a in rows],
                color=[CATEGORY_COLOURS.get(a["category"], MUTED) for a in rows])
        for threshold, _name in settings.CATEGORIES[:-1]:
            ax.axvline(threshold, color=GRID, linewidth=0.8, zorder=0)
        _style(ax, "Heat-risk score by location (0-100)")
        ax.grid(False)
        ax.set_xlim(0, 100)
        return _png(fig)


def score_histogram(assessments):
    """Histogram of scores with the category thresholds drawn in."""
    scores = [a["score"] for a in assessments if a["score"] is not None]
    if not scores:
        return empty_chart("No scored locations")
    with CHART_LOCK:
        fig, ax = plt.subplots(figsize=(6, 2.8))
        ax.hist(scores, bins=np.arange(0, 105, 5), color=WINE, edgecolor=PAPER)
        for threshold, name in settings.CATEGORIES[:-1]:
            ax.axvline(threshold, color=MUTED, linewidth=0.8, linestyle=":")
            ax.text(threshold + 1, ax.get_ylim()[1] * 0.9, name, fontsize=7, color=MUTED)
        _style(ax, "How scores are spread")
        ax.set_xlabel("Score", color=MUTED)
        ax.set_ylabel("Locations", color=MUTED)
        return _png(fig)


def risk_map(assessments, value="score"):
    """Seaborn heatmap of the schematic ward grid (not to scale, not official boundaries)."""
    cells = [a for a in assessments if a.get("grid_x") is not None and a.get("grid_y") is not None]
    if not cells:
        return empty_chart("No locations with a schematic position")
    cols = sorted({a["grid_x"] for a in cells})
    rows = sorted({a["grid_y"] for a in cells})
    grid = pd.DataFrame(np.nan, index=rows, columns=cols)
    labels = pd.DataFrame("", index=rows, columns=cols)
    for a in cells:
        v = a.get(value)
        grid.loc[a["grid_y"], a["grid_x"]] = np.nan if v is None else (v * 100 if value != "score" else v)
        shown = "n/a" if v is None else (f"{v:.0f}" if value == "score" else f"{v * 100:.0f}")
        labels.loc[a["grid_y"], a["grid_x"]] = f"{a['code']}\n{a['name'][:14]}\n{shown}"
    with CHART_LOCK:
        fig, ax = plt.subplots(figsize=(7.5, 6))
        cmap = sns.color_palette("blend:#F5EBD0,#C4573A,#7F011F,#2A000A", as_cmap=True)
        sns.heatmap(grid, annot=labels, fmt="", cmap=cmap, vmin=0, vmax=100, linewidths=3, linecolor=PAPER,
                    cbar_kws={"label": value.replace("_", " ") + " (0-100)", "shrink": 0.7}, ax=ax,
                    annot_kws={"fontsize": 8})
        for text in ax.texts:  # dark text on light cells, light text on dark cells
            x, y = text.get_position()
            cell = grid.iloc[int(y), int(x)]
            text.set_color("white" if (not np.isnan(cell) and cell > 55) else INK)
        ax.set_facecolor(PAPER)
        fig.set_facecolor(PAPER)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"Schematic ward grid — {value.replace('_', ' ')} (not to scale)", loc="left",
                     fontsize=11, color=INK, fontweight="bold")
        return _png(fig)


def temperature_heatmap(frame, days=30):
    """Seaborn heatmap of daily maximum temperature: locations x the last `days` days."""
    observed = frame[frame["is_forecast"] == 0]
    if observed.empty:
        return empty_chart("No observations")
    last = pd.to_datetime(observed["date"]).max()
    recent = observed[pd.to_datetime(observed["date"]) > last - pd.Timedelta(days=days)]
    pivot = recent.pivot_table(index="location", columns="date", values="t_max")
    pivot.columns = [c[5:] for c in pivot.columns]  # show MM-DD
    with CHART_LOCK:
        fig, ax = plt.subplots(figsize=(10, 0.35 * len(pivot) + 1.5))
        sns.heatmap(pivot, cmap="YlOrRd", cbar_kws={"label": "Max temperature °C"}, ax=ax, linewidths=0.3,
                    linecolor=PAPER)
        ax.set_facecolor("#D8D2C4")  # missing days show as grey
        fig.set_facecolor(PAPER)
        ax.set_title(f"Daily maximum temperature, last {days} days (grey = missing)", loc="left", fontsize=11,
                     color=INK, fontweight="bold")
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.tick_params(labelsize=7, colors=MUTED)
        return _png(fig)


def allocation_chart(plan):
    """Grouped bars: demand vs served per resource type."""
    types = list(plan["by_type"])
    demand = [plan["by_type"][t]["demand"] for t in types]
    served = [plan["by_type"][t]["served"] for t in types]
    labels = [t.replace("_", " ") for t in types]
    with CHART_LOCK:
        fig, ax = plt.subplots(figsize=(8, 3.2))
        x = np.arange(len(types))
        ax.bar(x - 0.2, demand, width=0.4, color="#D8C9A0", label="Estimated demand")
        ax.bar(x + 0.2, served, width=0.4, color=WINE, label="Can be served")
        ax.set_xticks(x, labels)
        ax.set_yscale("log")
        _style(ax, "Demand vs capacity per day (log scale)")
        ax.legend(fontsize=8, frameon=False)
        return _png(fig)


def scenario_chart(comparison):
    """Bars of each location's score before and after the scenario."""
    rows = [r for r in comparison["locations"] if r["score_before"] is not None and r["score_after"] is not None]
    if not rows:
        return empty_chart("No scored locations")
    with CHART_LOCK:
        fig, ax = plt.subplots(figsize=(9, 3.4))
        x = np.arange(len(rows))
        ax.bar(x - 0.2, [r["score_before"] for r in rows], width=0.4, color="#D8C9A0", label="Today")
        ax.bar(x + 0.2, [r["score_after"] for r in rows], width=0.4, color=WINE, label="Scenario")
        ax.set_xticks(x, [r["code"] for r in rows], rotation=60)
        ax.set_ylim(0, 100)
        _style(ax, "Risk score: today vs scenario")
        ax.legend(fontsize=8, frameon=False)
        return _png(fig)


def dimension_chart(result):
    """Four bars for one location's dimensions (capacity shown as lack of capacity)."""
    names = ["Hazard", "Exposure", "Vulnerability", "Lack of capacity"]
    capacity = result["capacity"]
    values = [result["hazard"], result["exposure"], result["vulnerability"],
              None if capacity is None else 1 - capacity]
    with CHART_LOCK:
        fig, ax = plt.subplots(figsize=(6, 2.6))
        heights = [0 if v is None else v for v in values]
        bars = ax.bar(names, heights, color=[WINE if v is not None else "#CFC8B8" for v in values])
        for bar, v in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                    "missing" if v is None else f"{v:.2f}", ha="center", fontsize=8, color=INK)
        ax.set_ylim(0, 1.1)
        _style(ax, f"{result['code']} — dimensions (0 = best, 1 = worst)")
        return _png(fig)
