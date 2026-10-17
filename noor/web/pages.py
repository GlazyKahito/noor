"""The eight screens of the website, one function each, laid out like the desktop app.

Each function takes the NoorService and the query parameters and returns
(screen key, title, subtitle, body HTML). server.py wraps it in html.page().
"""
from datetime import date, timedelta

from .. import reports, settings
from ..alerts import DISCLAIMER
from ..climate import explorer_table, heat_index, location_comparison, summary_stats
from ..exceptions import ValidationError
from ..importer import REQUIRED
from ..models import RESOURCE_CLASSES, make_resource
from ..queries import QUERIES, run_query
from ..scenario import LIMITS
from ..summaries import (RULE_LABELS, STRATEGY_LABELS, TYPE_LABELS, WEIGHT_LABELS, data_note_for, fmt,
                         indicator_rows, limit_range, method_text, overview_numbers, pct, plan_location_rows,
                         recent_activity, recommended_actions, scenario_explanation, situation_summary, when, IST)
from .html import (bullets, button, caps, card, chart, esc, field, form, link_button, table, tabs, tiles, url)

MAX_ROWS_SHOWN = 3000
CATEGORY_NAMES = [name for _t, name in settings.CATEGORIES] + ["Insufficient data"]
KIND_OPTIONS = list(settings.DATA_KINDS.items())
SCENARIO_LABELS = {
    "temperature_increase": ("Temperature increase (°C)", 0.5),
    "extra_hot_days": ("Extra hot days in the spell", 1),
    "new_cooling_centres": ("New cooling centres requested", 1),
    "water_capacity_pct": ("Water-point capacity (% of today)", 5),
    "medical_capacity_pct": ("Medical capacity (% of today)", 5),
    "budget_per_day": ("Budget for new centres (₹ per day)", 15000),
    "staff_available": ("Staff available for new centres", 1),
}
# the same nine charts as Reports & Analytics → Charts in the desktop app
REPORT_CHARTS = [
    "Risk score by location", "Locations per risk category", "How risk scores are spread",
    "Schematic ward grid: risk score", "Schematic ward grid: hazard", "Schematic ward grid: vulnerability",
    "Daily max temperature heatmap (30 days)", "Monthly climate means", "Allocation: demand vs capacity (risk-first)",
]
EXPORTS = [
    ("risk", "Regional heat-risk summary", "Latest score, category, dimensions and reasons per location."),
    ("vulnerability", "Vulnerability assessment", "Indicator shares next to the vulnerability dimension."),
    ("alerts", "Alert report", "Every alert with severity, trigger, period, status and actions."),
    ("plan_risk", "Allocation plan (risk-first)", "Demand and served per location and resource type."),
    ("plan_population", "Allocation plan (population-first)", "The baseline plan for comparison."),
    ("observations", "Climate observations", "Every stored daily row."),
]


def f1(v):
    return fmt(v, 1)


def f2(v):
    return fmt(v, 2)


def ist(stamp):
    """Times on the website are shown in Indian Standard Time."""
    return when(stamp, IST)


def location_options(svc):
    return [(l["code"], f"{l['code']} — {l['name']}") for l in svc.db.list_locations()]


def check_date(text, label):
    """'' or a YYYY-MM-DD date; anything else is an input error."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValidationError(f"{label} must be a date written as YYYY-MM-DD") from None


def two(left, right, ratio="5fr 6fr"):
    """Two columns side by side; '5fr 6fr' becomes the CSS class cols-5-6 (see style.css)."""
    a, b = (part.replace("fr", "") for part in ratio.split())
    return f'<div class="row cols-{a}-{b}"><div>{left}</div><div>{right}</div></div>'


# ---------------------------------------------------------------------------- overview
def overview(svc, q):
    n = overview_numbers(svc)
    latest, status, severity, by_status = n["latest"], n["status"], n["severity"], n["by_status"]
    bar = (f'<div class="toolbar"><span class="muted">Last risk calculation: {esc(ist(n["assessed_at"]))} IST</span>'
           f'<span class="actions">{form("/actions/recalculate", button("Recalculate risk", True) + back("/"))}'
           f'{form("/actions/alerts", button("Run warning rules") + back("/"))}</span></div>')
    top = tiles([
        ("Monitored locations", len(n["locations"]), f"{n['regions']} region(s)", False),
        ("High risk or above", len(n["high"]), f"of {len(latest)} assessed locations", True),
        ("Active heatwave alerts", len(n["active"]), f"{severity['emergency']} emergency · {severity['warning']} "
                                                     f"warning · {severity['advisory']} advisory", True),
        ("Resources available", f"{by_status['available']} / {len(n['resources'])}",
         f"{by_status['limited']} limited · {by_status['offline']} offline", False),
        ("Latest observation", status["latest_observation"] or "—",
         "Synthetic demo data" if status["synthetic_only"] else ", ".join(status["data_kinds"]), False),
    ])
    middle = two(card(chart("/chart/distribution.png", "Bar chart: locations per risk category"), "Risk distribution",
                      "Number of locations in each category of the risk engine."),
                 card(bullets(situation_summary(svc, n)), "Situation summary",
                      "Written from the computed numbers on this screen."))
    locations = table([("code", "Code", "l"), ("name", "Location", "l"), ("score", "Score", "r"),
                       ("category", "Category", "l"), ("confidence", "Confidence", "l"), ("as_of_date", "As of", "l")],
                      latest, {"score": f1}, tag=lambda r: cat_class(r["category"]),
                      link=lambda r: url("/risk", code=r["code"]), height=330)
    activity = table([("time", "When (IST)", "l"), ("event", "Activity", "l")], recent_activity(svc.db),
                     {"time": ist}, height=330)
    bottom = two(card(locations, "Locations by current risk", "Click a location to see why it got its score."),
                 card(activity, "Recent monitoring activity", "Latest recalculations, alerts and saved plans."),
                 "6fr 5fr")
    return ("overview", "Overview",
            "Current heat-risk situation across all monitored locations, from the latest saved assessment.",
            bar + top + middle + bottom)


def back(path):
    """Hidden field telling the server where to return after a form post."""
    return f'<input type="hidden" name="back" value="{esc(path)}">'


def cat_class(category):
    return "cat-" + (category or "").lower().replace(" ", "-")


# ---------------------------------------------------------------------------- monitoring
MONITORING_TABS = [("observations", "Observations"), ("trend", "Daily trend"), ("heatmap", "All-location heatmap"),
                   ("comparison", "Location comparison"), ("import", "Import CSV")]


def filtered_observations(svc, q):
    """Observations matching the filter fields (same rules as the desktop screen)."""
    start = check_date(q.get("start"), "From")
    end = check_date(q.get("end"), "To")
    if start and end and start > end:
        raise ValidationError("'From' must be on or before 'To'")
    codes = [q["location"]] if q.get("location") else None
    frame = svc.db.observations_frame(codes, start, end)
    if not q.get("forecast"):
        frame = frame[frame["is_forecast"] == 0]
    text = (q.get("search") or "").strip().lower()
    if text:
        frame = frame[frame["name"].str.lower().str.contains(text, regex=False)
                      | frame["location"].str.lower().str.contains(text, regex=False)]
    return frame


def monitoring(svc, q, import_report=None):
    tab = q.get("tab", "observations") if not import_report else "import"
    body = tabs("/monitoring", MONITORING_TABS, tab)
    if tab == "trend":
        body += trend_tab(svc, q)
    elif tab == "heatmap":
        days = q.get("days", "30")
        try:
            days_n = int(days)
        except ValueError:
            raise ValidationError("Days to show must be a whole number") from None
        if not 7 <= days_n <= 90:
            raise ValidationError("Days to show must be between 7 and 90")
        controls = form("/monitoring", f'<input type="hidden" name="tab" value="heatmap">'
                        + field("days", "Days to show", days_n, "number", minimum=7, maximum=90, width=90)
                        + button("Draw heatmap", True), method="get", cls="inline")
        body += card(controls + chart(url("/chart/heatmap.png", days=days_n), "Heatmap of daily maximum temperature"),
                     "Daily maximum temperature, every location",
                     "Each row is a location and each column a day. Grey cells are days with no reading.")
    elif tab == "comparison":
        rows = location_comparison(svc.db.observations_frame()).to_dict("records")
        for r in rows:
            r["first_day"], r["last_day"] = str(r["first_day"])[:10], str(r["last_day"])[:10]
        t = table([("location", "Code", "l"), ("name", "Location", "l"), ("mean_tmax", "Mean max °C", "r"),
                   ("max_tmax", "Highest °C", "r"), ("mean_tmin", "Mean min °C", "r"),
                   ("mean_humidity", "Mean humidity %", "r"), ("days_observed", "Days observed", "r"),
                   ("days_missing", "Days missing", "r"), ("first_day", "First day", "l"), ("last_day", "Last day", "l")],
                  rows, {k: f1 for k in ("mean_tmax", "max_tmax", "mean_tmin", "mean_humidity")}, height=300)
        body += card(t, "Per-location summary of observed days", "Pandas groupby over all observed rows.")
        body += card(chart("/chart/monthly.png", "Monthly climate means"), "Monthly means")
    elif tab == "import":
        body += import_tab(svc, import_report)
    else:
        body += observations_tab(svc, q)
    return ("monitoring", "Climate Monitoring",
            "Daily observations per location: browse, filter, chart, compare and import new readings.", body)


def observations_tab(svc, q):
    all_frame = svc.db.observations_frame()
    if "start" not in q and not all_frame.empty:
        q = {**q, "start": all_frame["date"].min(), "end": all_frame["date"].max()}
    frame = filtered_observations(svc, q)
    frame = frame.assign(heat_index=[heat_index(t, h) for t, h in zip(frame["t_max"], frame["humidity"])],
                         type=["Forecast" if f else "Observed" for f in frame["is_forecast"]])
    stats = summary_stats(frame["t_max"])
    note = (f"{len(frame):,} rows. Max temperature: mean {fmt(stats['mean'], 1)} °C, lowest {fmt(stats['min'], 1)} °C, "
            f"highest {fmt(stats['max'], 1)} °C, standard deviation {fmt(stats['std'], 2)} °C "
            f"(NumPy, missing values ignored).")
    if len(frame) > MAX_ROWS_SHOWN:
        note += f" Showing the first {MAX_ROWS_SHOWN:,}; narrow the filters or export to see all."
    records = frame.head(MAX_ROWS_SHOWN).to_dict("records")
    for r in records:
        for key in ("t_max", "t_min", "humidity"):
            if r[key] != r[key]:
                r[key] = None
    keep = {k: q.get(k) for k in ("location", "start", "end", "search", "forecast")}
    filters = form("/monitoring",
                   field("location", "Location", q.get("location", ""), "select",
                         [("", "All locations")] + location_options(svc))
                   + field("start", "From (YYYY-MM-DD)", q.get("start", ""), width=130)
                   + field("end", "To", q.get("end", ""), width=130)
                   + field("search", "Search name or code", q.get("search", ""), width=160)
                   + f'<label class="check"><input type="checkbox" name="forecast" value="1"'
                     f'{" checked" if q.get("forecast") else ""}> Include forecast days</label>'
                   + '<input type="hidden" name="tab" value="observations">'
                   + button("Apply filters", True) + link_button("Reset", "/monitoring")
                   + link_button("Export shown rows (CSV)", url("/export/observations.csv", **keep)),
                   method="get", cls="filters")
    t = table([("location", "Code", "l"), ("name", "Location", "l"), ("date", "Date", "l"), ("type", "Type", "l"),
               ("t_max", "Max °C", "r"), ("t_min", "Min °C", "r"), ("humidity", "Humidity %", "r"),
               ("heat_index", "Heat index °C", "r"), ("source_kind", "Data kind", "l")],
              records, {k: f1 for k in ("t_max", "t_min", "humidity", "heat_index")},
              tag=lambda r: "muted" if r["is_forecast"] else "", empty="No observations match these filters.",
              height=520)
    return card(filters + f'<p class="muted">{esc(note)}</p>' + t)


def trend_tab(svc, q):
    options = location_options(svc)
    latest = svc.db.latest_assessments()
    code = q.get("code") or (latest[0]["code"] if latest else (options[0][0] if options else ""))
    observed = svc.db.observations_frame([code]) if code else None
    stats_line, img = "", chart("/chart/empty.png", "No observations")
    start, end = q.get("start", ""), q.get("end", "")
    if observed is not None:
        observed = observed[observed["is_forecast"] == 0]
    if observed is not None and not observed.empty:
        end = check_date(end, "To") or observed["date"].max()
        start = check_date(start, "From") or (date.fromisoformat(end) - timedelta(days=44)).isoformat()
        if start > end:
            raise ValidationError("'From' must be on or before 'To'")
        if (date.fromisoformat(end) - date.fromisoformat(start)).days > 400:
            raise ValidationError("Choose a period of at most 400 days")
        t = explorer_table(observed, start, end)
        s = summary_stats(t["t_max"])
        stats_line = (f"{s['count']} days with a reading, {int(t['missing'].sum())} missing; mean max "
                      f"{fmt(s['mean'], 1)} °C, highest {fmt(s['max'], 1)} °C")
        img = chart(url("/chart/trend.png", code=code, start=start, end=end), f"Daily temperatures for {code}")
    controls = form("/monitoring", '<input type="hidden" name="tab" value="trend">'
                    + field("code", "Location", code, "select", options)
                    + field("start", "From (YYYY-MM-DD)", start, width=130) + field("end", "To", end, width=130)
                    + button("Show trend", True), method="get", cls="filters")
    return card(controls + f'<p class="muted">{esc(stats_line)}</p>' + img, "Daily temperatures for one location",
                "Max and min temperature and the heat index (from temperature and humidity). Ticks along the "
                "bottom mark days with no reading.")


def import_tab(svc, report):
    upload = form("/monitoring/import",
                  field("file", "CSV file", kind="file", required=True)
                  + field("source", "Data source name", "", hint="Where the numbers come from, e.g. 'Ward weather "
                          "station log'", width=320)
                  + field("kind", "Kind of data", "measured", "select", KIND_OPTIONS)
                  + field("licence", "Licence or terms", "", hint="Write 'unknown' if you do not know", width=320)
                  + '<div class="buttons">' + button("Import valid rows", True, "action", "import")
                  + button("Check file only", False, "action", "check")
                  + link_button("Save empty template", "/export/template.csv") + "</div>",
                  multipart=True, cls="stack")
    left = card(upload, "Import climate observations",
                "Required columns: " + ", ".join(REQUIRED) + " (optional: is_forecast 0/1). Dates as YYYY-MM-DD, "
                "temperatures in °C, humidity in %. Bad rows are listed and skipped; good rows are saved. A row for a "
                "location and day that already exists replaces it.")
    if report is None:
        result = '<p>Choose a file and press Check file only or Import.</p>'
        errors = []
    else:
        result = f"<p>{esc(report['text'])}</p>"
        errors = report["errors"]
    right = card(result + table([("line", "Line", "r"), ("column", "Column", "l"), ("message", "Problem", "l")],
                                errors, empty="No problems found.", height=420), "Validation result")
    return two(left, right, "4fr 5fr")


# ---------------------------------------------------------------------------- risk
def risk(svc, q):
    weights = None
    if q.get("preview"):
        weights = {k: q.get(k, "") for k in WEIGHT_LABELS}
        rows = svc.assess(weights)  # RiskEngine.check_weights validates them
        weights = {k: float(v) for k, v in weights.items()}
        rows = sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0)))
        text = ", ".join(f"{WEIGHT_LABELS[k]} {v:.2f}" for k, v in weights.items())
        mode = f"PREVIEW with weights {text}. Not saved."
    else:
        rows = svc.db.latest_assessments()
        for r in rows:
            r["as_of"] = r["as_of_date"]
        mode = f"Saved assessment from {ist(rows[0]['assessed_at']) if rows else '—'} IST (standard weights from settings.py)."
    category, search = q.get("category", ""), (q.get("search") or "").strip().lower()
    shown = [r for r in rows if (not category or r["category"] == category)
             and (not search or search in r["code"].lower() or search in r["name"].lower())]
    code = q.get("code") or (rows[0]["code"] if rows else None)
    keep = {"category": category, "search": q.get("search")}
    if weights:
        keep.update({"preview": 1, **{k: v for k, v in weights.items()}})
    filters = form("/risk", field("category", "Category", category, "select",
                                  [("", "All categories")] + [(c, c) for c in CATEGORY_NAMES])
                   + field("search", "Search", q.get("search", ""), width=150)
                   + "".join(f'<input type="hidden" name="{k}" value="{esc(v)}">'
                             for k, v in keep.items() if k not in ("category", "search") and v not in (None, ""))
                   + button("Filter"), method="get", cls="filters")
    bar = (f'<div class="toolbar">{filters}<span class="actions">'
           f'{form("/actions/recalculate", button("Recalculate and save", True) + back("/risk"))}</span></div>')
    t = table([("code", "Code", "l"), ("name", "Location", "l"), ("score", "Score", "r"), ("category", "Category", "l"),
               ("confidence", "Confidence", "l"), ("hazard", "Hazard", "r"), ("exposure", "Exposure", "r"),
               ("vulnerability", "Vulner.", "r"), ("capacity", "Capacity", "r")],
              shown, {"score": f1, **{k: f2 for k in ("hazard", "exposure", "vulnerability", "capacity")}},
              tag=lambda r: cat_class(r["category"]), link=lambda r: url("/risk", code=r["code"], **keep),
              selected=lambda r: r["code"] == code, height=440)
    current = weights or settings.RISK_WEIGHTS
    wform = form("/risk", '<div class="grid4">' + "".join(field(k, label, current[k], "number", step="0.01",
                                                                minimum=0, maximum=1)
                                                          for k, label in WEIGHT_LABELS.items()) + "</div>"
                 + '<input type="hidden" name="preview" value="1">'
                 + (f'<input type="hidden" name="code" value="{esc(code)}">' if code else "")
                 + '<div class="buttons">' + button("Preview with these weights") + link_button("Back to saved results", "/risk")
                 + '<span class="muted">Weights must add up to 1.0. A preview is not saved.</span></div>',
                 method="get")
    left = card(bar + f'<p class="muted">{esc(mode)}</p>' + t) + card(wform, "Method and what-if weights", method_text())
    right = risk_detail(svc, code, weights) if code else card("<p>Select a location.</p>")
    return ("risk", "Risk Assessment", "Heat-risk score, category and the reasons behind it for every location.",
            two(left, right, "62fr 38fr"))


def risk_detail(svc, code, weights):
    result = svc.assessment(code, weights)
    loc = svc.db.get_location(code)
    score = "No score" if result["score"] is None else f"{result['score']:.1f}"
    params = {"code": code, **({k: v for k, v in weights.items()} if weights else {})}
    body = (f"<h2>{esc(result['name'])} ({esc(code)})</h2>"
            f"<p class='muted'>{esc(loc['region'])} · population {esc(fmt(loc['population']))} · data: "
            f"{esc(settings.DATA_KINDS.get(loc['source_kind'], loc['source_kind']))}</p>"
            f"<p class='big-number'>{esc(score)} &nbsp;{esc(result['category'])}</p>"
            f"<p class='muted'>Confidence: {esc(result['confidence'])} · as of {esc(result['as_of'])}</p>"
            + caps("Why this score") + bullets(result["reasons"])
            + caps("Recommended response") + bullets(recommended_actions(svc.db, code))
            + caps("Dimensions") + chart(url("/chart/dimensions.png", **params), f"Risk dimensions for {code}")
            + caps("Indicators used")
            + table([("dimension", "Dimension", "l"), ("indicator", "Indicator", "l"), ("value", "Value", "r"),
                     ("normalised", "0-1", "r"), ("weight", "Weight", "r")], indicator_rows(result),
                    {"normalised": f2, "weight": f2})
            + f"<p class='muted'>{esc(data_note_for(result))}{' Preview weights in use.' if weights else ''}</p>")
    return card(body, cls="detail")


# ---------------------------------------------------------------------------- alerts
def alerts(svc, q):
    counts = {r["k"]: r["n"] for r in svc.db.fetch_all(
        "SELECT CASE WHEN status = 'active' THEN severity ELSE status END AS k, COUNT(*) AS n FROM alerts GROUP BY k")}
    top = tiles([("Emergency (active)", counts.get("emergency", 0), "", True),
                 ("Warning (active)", counts.get("warning", 0), "", True),
                 ("Advisory (active)", counts.get("advisory", 0), "", False),
                 ("Acknowledged", counts.get("acknowledged", 0), "", False),
                 ("Resolved", counts.get("resolved", 0), "", False)])
    status = q.get("status", "active")
    severity = q.get("severity", "")
    rows = svc.db.list_alerts(None if status == "all" else status, severity or None)
    for a in rows:
        a["rule_label"] = RULE_LABELS.get(a["rule"], a["rule"])
    chosen = next((a for a in rows if str(a["id"]) == q.get("id", "")), None)
    if chosen is None and q.get("id"):
        chosen = next((a for a in svc.db.list_alerts() if str(a["id"]) == q["id"]), None)
    if chosen is None and rows:
        chosen = rows[0]
    filters = form("/alerts", field("status", "Status", status, "select",
                                    [("active", "Active"), ("acknowledged", "Acknowledged"), ("resolved", "Resolved"),
                                     ("all", "All")])
                   + field("severity", "Severity", severity, "select",
                           [("", "All"), ("emergency", "emergency"), ("warning", "warning"), ("advisory", "advisory"),
                            ("info", "info")]) + button("Filter"), method="get", cls="filters")
    bar = (f'<div class="toolbar">{filters}<span class="actions">'
           f'{form("/actions/alerts", button("Run warning rules", True) + back("/alerts"))}'
           f'{link_button("Export CSV", "/export/alerts.csv")}</span></div>')
    t = table([("id", "ID", "r"), ("severity", "Severity", "l"), ("name", "Location", "l"), ("rule_label", "Rule", "l"),
               ("issued_at", "Created (IST)", "l"), ("status", "Status", "l"), ("message", "Reason", "l")],
              rows, {"issued_at": ist}, tag=lambda a: ("sev-" + a["severity"]) if a["status"] == "active" else "muted",
              link=lambda a: url("/alerts", status=status, severity=severity, id=a["id"]),
              selected=lambda a: chosen is not None and a["id"] == chosen["id"],
              empty="No alerts match these filters.", height=520)
    left = card(bar + f'<p class="muted">{len(rows)} alert(s) shown. Most severe first.</p>' + t)
    if chosen is None:
        right = card("<p>Select an alert to see its details.</p>", "Alert details")
    else:
        a = chosen
        here = url("/alerts", status=status, severity=severity, id=a["id"])
        buttons = ""
        if a["status"] == "active":
            buttons += form(f"/alerts/{a['id']}/status", '<input type="hidden" name="status" value="acknowledged">'
                            + back(here) + button("Acknowledge"))
        if a["status"] != "resolved":
            buttons += form(f"/alerts/{a['id']}/status", '<input type="hidden" name="status" value="resolved">'
                            + back(here) + button("Mark resolved", True))
        right = card(f"<p class='strong'>{esc(a['message'])}</p>"
                     f"<p class='muted'>#{a['id']} · {esc(a['severity'].upper())} · {esc(a['name'])} ({esc(a['code'])}) · "
                     f"{esc(a['status'])} · created {esc(ist(a['issued_at']))} IST</p>"
                     + caps("Trigger")
                     + f"<p>{esc(RULE_LABELS.get(a['rule'], a['rule']))}: value {esc(fmt(a['trigger_value'], 1))} "
                       f"against threshold {esc(fmt(a['threshold'], 1))}; period {esc(a['period'])}.</p>"
                     + caps("Recommended action") + bullets([x for x in a["actions"].split(" | ") if x])
                     + caps("Confidence") + f"<p class='muted'>{esc(a['confidence'])}</p>"
                     + f'<div class="buttons">{buttons}</div>', "Alert details", cls="detail")
    return ("alerts", "Alerts", "Early warnings from fixed, documented threshold rules. " + DISCLAIMER,
            top + two(left, right, "66fr 34fr"))


# ---------------------------------------------------------------------------- resources
RESOURCE_TABS = [("inventory", "Inventory"), ("add", "Add resource"), ("plan", "Allocation plan"),
                 ("compare", "Compare strategies"), ("saved", "Saved plans")]


def resources(svc, q):
    tab = q.get("tab", "inventory")
    body = tabs("/resources", RESOURCE_TABS, tab)
    if tab == "add":
        body += add_resource_tab(svc)
    elif tab == "plan":
        body += plan_tab(svc, q)
    elif tab == "compare":
        result = svc.compare()
        t = table([("label", "Type", "l"), ("served_a", "Served (A)", "r"), ("served_b", "Served (B)", "r"),
                   ("difference", "B − A", "r"), ("unmet_a", "Unmet (A)", "r"), ("unmet_b", "Unmet (B)", "r")],
                  [{"label": TYPE_LABELS[r["type"]], **r} for r in result["rows"]],
                  {k: fmt for k in ("served_a", "served_b", "difference", "unmet_a", "unmet_b")})
        summary = (f"Risk-weighted coverage: A {pct(result['risk_weighted_a'])}, B {pct(result['risk_weighted_b'])}. "
                   f"High-risk locations still with gaps: A {', '.join(result['high_gaps_a']) or 'none'}; "
                   f"B {', '.join(result['high_gaps_b']) or 'none'}.")
        body += card(f"<p>{esc(summary)}</p>" + t, "Population-first (A) vs risk-first (B) on today's data",
                     "Same resources, same greedy loop; only the order in which locations are served changes.")
    elif tab == "saved":
        body += card(table([("plan_name", "Plan", "l"), ("strategy", "Strategy", "l"),
                            ("created_at", "Saved (IST)", "l"), ("rows", "Assignments", "r"),
                            ("people_per_day", "People / day", "r")], svc.db.list_plans(),
                           {"people_per_day": fmt, "created_at": ist}, empty="No plans saved yet."),
                     "Plans saved in the allocations table")
    else:
        body += inventory_tab(svc, q)
    return ("resources", "Resource Allocation",
            "Cooling centres, water points, medical units and teams: what exists, where, and how the greedy planner "
            "shares them out.", body)


def inventory_rows(svc, rtype="", status=""):
    rows = []
    for r in svc.db.list_resources():
        if rtype and r["type"] != rtype or status and r["status"] != status:
            continue
        obj = make_resource(r["type"], code=r["code"], name=r["name"], location_code=r["location_code"],
                            amount=r["amount"], status=r["status"], radius_km=r["radius_km"])
        rows.append({**r, "type_label": TYPE_LABELS[r["type"]], "location": f"{r['location_code']} {r['location_name']}",
                     "amount_text": f"{fmt(r['amount'])} {obj.unit}", "capacity": obj.capacity(),
                     "describe": obj.describe(), "unit": obj.unit})
    return rows


def inventory_tab(svc, q):
    rtype, status = q.get("type", ""), q.get("status", "")
    rows = inventory_rows(svc, rtype, status)
    total = len(svc.db.list_resources())
    chosen = next((r for r in rows if r["code"] == q.get("code")), rows[0] if rows else None)
    filters = form("/resources", '<input type="hidden" name="tab" value="inventory">'
                   + field("type", "Type", rtype, "select", [("", "All types")] + list(TYPE_LABELS.items()))
                   + field("status", "Status", status, "select", [("", "All")] + [(s, s) for s in settings.STATUS_FACTOR])
                   + button("Filter"), method="get", cls="filters")
    t = table([("code", "Code", "l"), ("name", "Name", "l"), ("type_label", "Type", "l"), ("location", "Location", "l"),
               ("amount_text", "Amount", "r"), ("capacity", "Serves / day", "r"), ("status", "Status", "l"),
               ("radius_km", "Radius km", "r"), ("staff", "Staff", "r"), ("daily_cost", "Cost ₹/day", "r")],
              rows, {"capacity": fmt, "daily_cost": fmt, "radius_km": f1},
              tag=lambda r: {"offline": "cat-extreme", "limited": "cat-high"}.get(r["status"], ""),
              link=lambda r: url("/resources", tab="inventory", type=rtype, status=status, code=r["code"]),
              selected=lambda r: chosen is not None and r["code"] == chosen["code"], height=560)
    left = card(filters + f'<p class="muted">{len(rows)} of {total} resources shown. \'Serves / day\' is the capacity '
                          f'after status (limited = half, offline = none).</p>' + t)
    if chosen is None:
        right = card("<p>Select a resource in the table.</p>", "Selected resource")
    else:
        r = chosen
        here = url("/resources", tab="inventory", type=rtype, status=status, code=r["code"])
        right = card(
            f"<p>{esc(r['code'])}: {esc(r['describe'])}. Based at {esc(r['location'])}, serves locations within "
            f"{r['radius_km']:.1f} km.</p>"
            + form(f"/resources/{r['code']}/update", field("status", "Status", r["status"], "select",
                                                           [(s, s) for s in settings.STATUS_FACTOR])
                   + field("amount", "Amount", f"{r['amount']:g}", hint=f"Amount is in {r['unit']}.")
                   + back(here) + button("Save status and amount", True), cls="stack")
            + form(f"/resources/{r['code']}/move", field("location", "Reassign to location", r["location_code"], "select",
                                                         location_options(svc))
                   + back(here) + button("Move resource here"), cls="stack")
            + form(f"/resources/{r['code']}/delete", back(url("/resources", tab="inventory"))
                   + button("Delete resource…", confirm=f"Delete {r['code']} ({r['name']})? Saved plan rows that use it "
                                                        f"are deleted too. This cannot be undone."), cls="stack")
            + "<p class='muted'>Every change is saved in SQLite and the risk scores are recalculated, because response "
              "capacity is part of the score.</p>", "Selected resource", cls="detail")
    return two(left, right, "74fr 26fr")


def add_resource_tab(svc):
    options = location_options(svc)
    body = form("/resources/add", '<div class="grid2">'
                + field("type", "Type", "cooling_centre", "select", list(TYPE_LABELS.items()))
                + field("location_code", "Located at", options[0][0] if options else "", "select", options)
                + field("code", "Code (2-20 characters)", required=True) + field("name", "Name", required=True)
                + field("amount", "Amount (in the unit above)", required=True)
                + field("radius_km", "Service radius (km)", "3") + field("staff", "Staff", "0")
                + field("daily_cost", "Daily cost (₹)", "0")
                + field("status", "Status", "available", "select", [(s, s) for s in settings.STATUS_FACTOR])
                + field("kind", "Kind of data", "estimated", "select", KIND_OPTIONS) + "</div>"
                + back("/resources?tab=add") + button("Add resource", True))
    return card(body, "Add a resource to the inventory",
                "Units: " + "; ".join(f"{cls.label}: {cls.unit}" for cls in RESOURCE_CLASSES.values()) + ".")


def plan_tab(svc, q):
    strategy = q.get("strategy", "risk_first")
    plan = svc.plan(strategy)
    controls = form("/resources", '<input type="hidden" name="tab" value="plan">'
                    + field("strategy", "Strategy", strategy, "select", list(STRATEGY_LABELS.items()))
                    + button("Run plan", True), method="get", cls="filters")
    save = form("/plans/save", field("name", "Save as (plan name)", width=220, required=True)
                + f'<input type="hidden" name="strategy" value="{esc(strategy)}">'
                + back(url("/resources", tab="plan", strategy=strategy)) + button("Save plan"), cls="filters")
    export_key = "plan_risk" if strategy == "risk_first" else "plan_population"
    top = card(f'<div class="toolbar">{controls}<span class="actions">{save}'
               f'{link_button("Export CSV", f"/export/{export_key}.csv")}</span></div>',
               "Run the allocation planner",
               reports.METHODS["allocation"] + " Demand rates are planning assumptions in settings.py, not measured needs.")
    coverage = plan["total_served"] / plan["total_demand"] if plan["total_demand"] else None
    gaps = plan["high_risk_with_gaps"]
    numbers = tiles([("Estimated demand / day", fmt(plan["total_demand"]), "people (or visits) per day", False),
                     ("Can be served / day", fmt(plan["total_served"]), f"{pct(coverage)} of demand", True),
                     ("Unmet / day", fmt(plan["total_unmet"]), "not reached by any resource", True),
                     ("Risk-weighted coverage", pct(plan["risk_weighted_coverage"]), "coverage weighted by risk score", False),
                     ("High-risk locations with gaps", len(gaps), ", ".join(gaps) if gaps else "none", False)])
    by_type = table([("label", "Type", "l"), ("demand", "Demand", "r"), ("served", "Served", "r"), ("unmet", "Unmet", "r"),
                     ("coverage", "Coverage", "r"), ("utilisation", "Use of capacity", "r")],
                    [{"label": TYPE_LABELS[t], **v} for t, v in plan["by_type"].items()],
                    {"demand": fmt, "served": fmt, "unmet": fmt, "coverage": pct, "utilisation": pct})
    cols = [("code", "Code", "l"), ("name", "Location", "l"), ("category", "Category", "l")]
    cols += [(t, TYPE_LABELS[t].split()[0], "r") for t in settings.DEMAND_RATES]
    by_loc = table(cols, plan_location_rows(plan), tag=lambda r: cat_class(r["category"]), height=430)
    return top + numbers + two(card(by_type + chart(url("/chart/allocation.png", strategy=strategy),
                                                    "Demand vs capacity per resource type"), "By resource type"),
                               card(by_loc, "By location (served / demand per day)"), "1fr 1fr")


# ---------------------------------------------------------------------------- scenario
def scenario_params(q):
    return {name: q.get(name, LIMITS[name][2]) for name in LIMITS}


def scenario(svc, q):
    params = scenario_params(q)
    result = svc.scenario(params)  # Scenario() validates every limit
    settings_form = form("/scenario", "".join(
        field(name, label, params[name], "number", step=step, minimum=LIMITS[name][0], maximum=LIMITS[name][1],
              hint=limit_range(*LIMITS[name][:2]), width=140)
        for name, (label, step) in SCENARIO_LABELS.items())
        + '<div class="buttons">' + button("Run scenario", True) + link_button("Reset", "/scenario")
        + link_button("Export CSV", url("/export/scenario.csv", **params)) + "</div>", method="get", cls="stack")
    nc = settings.NEW_CENTRE
    left = card(settings_form, "Scenario settings",
                f"Each new centre: {nc['places']} places/day, ₹{nc['daily_cost']:,}/day, {nc['staff']} staff, "
                f"{nc['radius_km']:g} km radius. Centres go where risk-weighted unmet cooling demand is largest.")
    c = result["comparison"]
    limited = " (limited by " + " and ".join(result["limited_by"]) + ")" if result["limited_by"] else ""
    numbers = tiles([("Mean risk score", f"{fmt(c['mean_score_before'], 1)} → {fmt(c['mean_score_after'], 1)}",
                      "average of all scored locations", True),
                     ("High risk or above", f"{c['high_before']} → {c['high_after']}", "locations High, Severe or Extreme", True),
                     ("Unmet demand / day", f"{fmt(c['unmet_before'])} → {fmt(c['unmet_after'])}", "people or visits per day", False),
                     ("New centres placed", len(result["placed_centres"]), f"₹{result['extra_cost_per_day']:,}/day extra{limited}", False)])
    types = table([("label", "Type", "l"), ("unmet_before", "Unmet before", "r"), ("unmet_after", "Unmet after", "r"),
                   ("coverage_before", "Coverage before", "r"), ("coverage_after", "Coverage after", "r"),
                   ("utilisation_after", "Use after", "r")],
                  [{"label": TYPE_LABELS[r["type"]], **r} for r in c["by_type"]],
                  {"unmet_before": fmt, "unmet_after": fmt, "coverage_before": pct, "coverage_after": pct,
                   "utilisation_after": pct})
    locs = sorted(c["locations"], key=lambda r: (r["change"] is None, -abs(r["change"] or 0)))
    loc_table = table([("code", "Code", "l"), ("name", "Location", "l"), ("score_before", "Before", "r"),
                       ("score_after", "After", "r"), ("change", "Change", "r"), ("category_before", "Category before", "l"),
                       ("category_after", "Category after", "l")], locs,
                      {"score_before": f1, "score_after": f1, "change": lambda v: "—" if v is None else f"{v:+.1f}"},
                      tag=lambda r: cat_class(r["category_after"]))
    right = (numbers + card(bullets(scenario_explanation(result)), "What changed")
             + card(chart(url("/chart/scenario.png", **params), "Risk score today vs scenario"))
             + card(caps("Resources by type: before → after") + types
                    + caps("Locations: score before → after (largest change first)") + loc_table, "Details"))
    return ("scenario", "Scenario Lab",
            "What-if analysis: the same risk and allocation code rerun on changed inputs. Not a prediction.",
            two(left, f"<div>{right}</div>", "31fr 69fr"))


# ---------------------------------------------------------------------------- reports
REPORT_TABS = [("summary", "Summary"), ("charts", "Charts"), ("sql", "SQL queries"), ("export", "Export")]


def reports_page(svc, q):
    tab = q.get("tab", "summary")
    body = tabs("/reports", REPORT_TABS, tab)
    if tab == "charts":
        try:
            index = int(q.get("chart", "0"))
        except ValueError:
            index = 0
        index = index if 0 <= index < len(REPORT_CHARTS) else 0
        active = ' class="active" aria-current="page"'
        menu = "".join(f'<a href="{esc(url("/reports", tab="charts", chart=i))}"{active if i == index else ""}>'
                       f'{esc(t)}</a>' for i, t in enumerate(REPORT_CHARTS))
        src = url("/chart/report.png", i=index)
        left = card(f'<nav class="chart-menu">{menu}</nav>'
                    + f'<a class="btn" href="{esc(src)}" download="noor_chart_{index + 1}.png">Save chart as PNG</a>',
                    "Choose a chart")
        body += two(left, card(chart(src, REPORT_CHARTS[index])), "3fr 7fr")
    elif tab == "sql":
        titles = [(k, v["title"]) for k, v in QUERIES.items()]
        key = q.get("query") if q.get("query") in QUERIES else "region_summary"
        query = QUERIES[key]
        param_text = q.get("param", ", ".join(str(p) for p in query["params"]))
        params = None
        if query["params"]:
            try:
                params = (int(param_text),)
            except ValueError:
                raise ValidationError("The parameter must be a whole number") from None
        _title, rows = run_query(svc.db, key, params)
        cols = [(c, c, "l") for c in (rows[0].keys() if rows else ["result"])]
        controls = form("/reports", '<input type="hidden" name="tab" value="sql">'
                        + field("query", "Query", key, "select", titles)
                        + field("param", "Parameter (?)", param_text if query["params"] else "", width=90)
                        + button("Run query", True), method="get", cls="filters")
        body += card(controls + f"<pre class='sql'>{esc(query['sql'].strip())}</pre>", "SQL examples from noor/queries.py",
                     "Each query runs on the live database with ? parameters (JOIN, GROUP BY, HAVING, sub-queries).")
        body += card(f"<p class='muted'>{len(rows)} row(s).</p>" + table(cols, rows, empty="The query returned no rows.",
                                                                          height=420), "Result")
    elif tab == "export":
        items = "".join(f"<tr><td class='strong'>{esc(t)}</td><td class='muted'>{esc(n)}</td>"
                        f"<td class='r'>{link_button('Save CSV', f'/export/{k}.csv')}</td></tr>" for k, t, n in EXPORTS)
        body += card(f"<table class='plain'>{items}</table>", "Download reports",
                     "Each CSV starts with lines beginning with # that say when it was made, from which data, by which "
                     "method, and its limitations.")
        body += card(link_button("Save all charts (ZIP of PNG files)", "/export/charts.zip"), "Charts",
                     "Every chart on the Charts tab as a PNG file.")
    else:
        body += summary_tab(svc)
    return ("reports", "Reports & Analytics",
            "Summary statistics, charts, the project's SQL queries and downloadable reports.", body)


def summary_tab(svc):
    frame = svc.db.observations_frame()
    observed = frame[frame["is_forecast"] == 0]
    stats = summary_stats(observed["t_max"])
    if stats["count"]:
        hottest = observed.loc[observed["t_max"].idxmax()]
        hot = (fmt(stats["max"], 1, "°C"), f"{hottest['name']}, {hottest['date']}")
    else:
        hot = ("—", "no readings")
    counts = svc.db.table_counts()
    open_alerts = svc.db.fetch_one("SELECT COUNT(*) AS n FROM alerts WHERE status <> 'resolved'")["n"]
    capacity = sum(r["capacity"] for r in svc.plan("risk_first")["resources"])
    numbers = tiles([("Observed days stored", fmt(len(observed)), f"{observed['location'].nunique()} locations", False),
                     ("Mean max temperature", fmt(stats["mean"], 1, "°C"), f"standard deviation {fmt(stats['std'], 1)} °C", False),
                     ("Hottest reading", hot[0], hot[1], True),
                     ("Alerts on record", counts["alerts"], f"{open_alerts} not yet resolved", False),
                     ("Resource capacity / day", fmt(capacity), f"{counts['resources']} resources, after status", False)])
    specs = [
        ("region_summary", [("region", "Region", "l"), ("locations", "Locations", "r"), ("mean_score", "Mean score", "r"),
                            ("max_score", "Max score", "r"), ("high_or_above", "High or above", "r")]),
        ("alerts_by_severity", [("severity", "Severity", "l"), ("status", "Status", "l"), ("alerts", "Alerts", "r")]),
        ("resources_by_type", [("type", "Type", "l"), ("status", "Status", "l"), ("resources", "Count", "r"),
                               ("total_amount", "Total amount", "r"), ("staff", "Staff", "r")]),
    ]
    cards = []
    for key, cols in specs:
        title, rows = run_query(svc.db, key)
        cards.append(card(table(cols, rows, {"total_amount": fmt}, height=230), title))
    comp = location_comparison(frame).to_dict("records")
    cards.append(card(table([("location", "Code", "l"), ("name", "Location", "l"), ("mean_tmax", "Mean max °C", "r"),
                             ("max_tmax", "Highest °C", "r"), ("mean_humidity", "Humidity %", "r"),
                             ("days_missing", "Missing days", "r")], comp,
                            {k: f1 for k in ("mean_tmax", "max_tmax", "mean_humidity")}, height=230),
                      "Location-wise climate comparison"))
    return numbers + two(cards[0], cards[1], "1fr 1fr") + two(cards[2], cards[3], "1fr 1fr")


# ---------------------------------------------------------------------------- data
DATA_TABS = [("database", "Database and sources"), ("locations", "Locations")]
SHARES = [("elderly_share", "Elderly (65+) share"), ("children_share", "Children (under 5) share"),
          ("outdoor_worker_share", "Outdoor worker share"), ("poor_housing_share", "Poor housing share"),
          ("low_income_share", "Low income share"), ("piped_water_share", "Piped water share")]


def data_page(svc, q):
    tab = q.get("tab", "database")
    body = tabs("/data", DATA_TABS, tab)
    status = svc.status()
    if tab == "locations":
        rows = []
        for loc in svc.db.list_locations():
            density = loc["population"] / loc["area_km2"] if loc["population"] and loc["area_km2"] else None
            rows.append({**loc, "density": density, "kind_label": settings.DATA_KINDS[loc["source_kind"]]})
        regions = sorted({r["region"] for r in rows})
        left = card(table([("code", "Code", "l"), ("name", "Name", "l"), ("region", "Region", "l"),
                           ("population", "Population", "r"), ("area_km2", "Area km²", "r"),
                           ("density", "People/km²", "r"), ("kind_label", "Data kind", "l")], rows,
                          {"population": fmt, "area_km2": f1, "density": fmt}, height=560), "Monitored locations")
        add = form("/data/locations", '<div class="grid2">'
                   + field("region", "Region", regions[0] if regions else "", "datalist", [(r, r) for r in regions])
                   + field("code", "Code", required=True) + field("name", "Name", required=True)
                   + field("population", "Population") + field("area_km2", "Area (km²)")
                   + field("grid_x", "Grid x (km)") + field("grid_y", "Grid y (km)")
                   + "".join(field(k, label) for k, label in SHARES)
                   + field("kind", "Kind of data", "estimated", "select", KIND_OPTIONS)
                   + field("source", "Source of the numbers", required=True) + "</div>"
                   + back("/data?tab=locations") + button("Add location", True))
        right = card(add, "Add a location", "Shares are fractions from 0 to 1 (0.12 = 12%). Leave a field empty when it "
                                            "is unknown: NOOR then treats it as missing, never as zero.")
        body += two(left, right, "3fr 2fr")
    else:
        kinds = ", ".join(settings.DATA_KINDS[k] for k in status["data_kinds"]) or "none"
        info = (f"<p>Latest observation: {esc(status['latest_observation'] or '—')}<br>Data kinds in use: {esc(kinds)}"
                + ("<br>All data is synthetic demonstration data." if status["synthetic_only"] else "") + "</p>"
                + "<p class='muted'>On the website the database lives in the server's temporary storage and is rebuilt "
                  "from the demo data when the server restarts. The desktop app keeps it in instance/noor.db.</p>")
        counts = table([("table", "Table", "l"), ("rows", "Rows", "r")],
                       [{"table": t, "rows": n} for t, n in status["counts"].items()], {"rows": fmt})
        sources = table([("id", "ID", "r"), ("name", "Name", "l"), ("kind_label", "Kind", "l"), ("provider", "Provider", "l"),
                         ("licence", "Licence", "l"), ("observations", "Observations", "r"), ("locations", "Locations", "r"),
                         ("resources", "Resources", "r"), ("notes", "Notes", "l")],
                        [{**s, "kind_label": settings.DATA_KINDS[s["kind"]]} for s in status["sources"]],
                        {"observations": fmt})
        body += two(card(info + counts, "SQLite database"),
                    card(sources, "Data sources", "Every location, observation and resource row points to a source. "
                                                  "Kind says how far to trust it: measured, model-derived, estimated, or "
                                                  "synthetic (made up for the demonstration)."), "2fr 5fr")
    return ("data", "Data Management", "The SQLite database, where every number comes from, and the monitored locations.",
            body)


def error_body(message):
    """Shown when a page cannot be built (bad filter value and so on)."""
    return card(f"<p>{esc(message)}</p><p>{link_button('Back to the Overview', '/', True)}</p>", "Please check")
