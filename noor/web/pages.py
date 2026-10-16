"""One function per page. Each takes the NoorService and the query parameters and returns HTML."""
from .. import settings
from ..allocation import STRATEGIES
from ..models import RESOURCE_CLASSES
from ..queries import QUERIES, run_query
from ..scenario import LIMITS
from .html import (category_badge, chart, esc, fmt, options, page, pct, severity_badge, stat, table, url)

TYPE_LABELS = {name: cls.label for name, cls in RESOURCE_CLASSES.items()}
KIND_CHOICES = list(settings.DATA_KINDS.items())


def _synthetic(svc):
    """True when every dataset in use is synthetic (drives the banner)."""
    return svc.status()["synthetic_only"]


def _layout(svc, title, active, body, q):
    """page() with the flash message from ?msg= / ?err= and the synthetic banner."""
    return page(title, active, body, q.get("msg"), q.get("err"), _synthetic(svc))


# ---------------------------------------------------------------------------- overview
def overview(svc, q):
    """Landing page: what NOOR is, the workflow, and a few live numbers."""
    latest = svc.db.latest_assessments()
    high = sum(1 for a in latest if a["category"] in ("High", "Severe", "Extreme"))
    active = len(svc.db.list_alerts(status="active"))
    plan = svc.plan("risk_first")
    cool = plan["by_type"]["cooling_centre"]
    steps = [("/explorer", "Climate data", "Daily temperature and humidity, gaps shown, CSV in and out."),
             ("/risk", "Risk analysis", "Hazard, exposure, vulnerability and capacity scored separately."),
             ("/map", "Vulnerability", "Where people are most exposed and least protected."),
             ("/alerts", "Early warnings", "Threshold rules that explain why they fired."),
             ("/plans", "Resource planning", "Cooling, water, medical and outreach matched to need."),
             ("/scenarios", "Scenario comparison", "What if it is 2 °C hotter, or we open five more centres?")]
    step_html = "".join(f'<li><a href="{href}">{esc(name)}</a><br><span class="small muted">{esc(text)}</span></li>'
                        for href, name, text in steps)
    body = f"""
<section class="hero">
  <p class="eyebrow">Climate Intelligence &amp; Resilience</p>
  <h1>NOOR</h1>
  <p class="tagline">See the risk. Save lives.</p>
  <p class="lead">NOOR helps communities and decision-makers understand heat risk, find the people most exposed,
  plan cooling, water and medical resources, and prepare for extreme heat — with methods you can read and change.</p>
  <p class="actions"><a class="button" href="/dashboard">Open the dashboard</a>
  <a class="button secondary" href="/methodology">How the scores work</a></p>
</section>
<h2>From data to decisions</h2>
<ol class="steps">{step_html}</ol>
<h2>Right now in the demo district</h2>
<div class="stats">
  {stat("Locations assessed", str(len(latest)))}
  {stat("High risk or worse", str(high), "Score 40 or more")}
  {stat("Active alerts", str(active), '<a href="/alerts">See alerts</a>')}
  {stat("Cooling demand met", pct(cool["coverage"]), f"{fmt(cool['unmet'], 0)} people/day short")}
</div>
<p class="muted small">Every number on this site comes from a calculation in the code, an identified source, or the
synthetic demonstration dataset — and says which. NOOR is not an official warning service.</p>"""
    return _layout(svc, "Overview", "/", body, q)


# ---------------------------------------------------------------------------- dashboard
def dashboard(svc, q):
    """Climate intelligence dashboard."""
    latest = svc.db.latest_assessments()
    scored = [a for a in latest if a["score"] is not None]
    status = svc.status()
    alerts = svc.db.list_alerts(status="active")
    plan = svc.plan("risk_first")
    by_sev = {s: sum(1 for a in alerts if a["severity"] == s) for s in ("emergency", "warning", "advisory", "info")}
    mean = sum(a["score"] for a in scored) / len(scored) if scored else None
    high = [a for a in latest if a["category"] in ("High", "Severe", "Extreme")]
    as_of = latest[0]["as_of_date"] if latest else "—"

    hot_rows = []
    for a in latest[:6]:
        reasons = a["reasons"].split(" | ")[1:3]
        hot_rows.append([f'<a href="/risk/{esc(a["code"])}">{esc(a["code"])} {esc(a["name"])}</a>',
                         fmt(a["score"]), category_badge(a["category"]), esc(a["confidence"]),
                         "<br>".join(esc(r) for r in reasons)])
    _title, regions = run_query(svc.db, "region_summary")
    region_rows = [[esc(r["region"]), str(r["locations"]), fmt(r["mean_score"]), fmt(r["max_score"]),
                    str(r["high_or_above"])] for r in regions]
    alert_rows = [[severity_badge(a["severity"]), esc(a["code"]), esc(a["message"]), esc(a["period"])]
                  for a in alerts[:6]]
    res_rows = []
    inventory = svc.db.list_resources()
    for rtype, label in TYPE_LABELS.items():
        items = [r for r in inventory if r["type"] == rtype]
        counts = {s: sum(1 for r in items if r["status"] == s) for s in ("available", "limited", "offline")}
        bt = plan["by_type"][rtype]
        res_rows.append([esc(label), str(counts["available"]), str(counts["limited"]), str(counts["offline"]),
                         fmt(bt["capacity"], 0), fmt(bt["demand"], 0), pct(bt["coverage"])])
    days = status["days_since_latest"]
    freshness = (f"Latest observation {esc(status['latest_observation'])} "
                 f"({days} days before today)." if days is not None else "No observations yet.")
    kinds = ", ".join(settings.DATA_KINDS[k] for k in status["data_kinds"])
    body = f"""
<p class="eyebrow">Dashboard · assessed as of {esc(as_of)}</p>
<h1>Heat risk at a glance</h1>
<div class="stats">
  {stat("Mean risk score", fmt(mean), "0 = no concern, 100 = worst")}
  {stat("High or worse", f"{len(high)} / {len(latest)}", "locations")}
  {stat("Active alerts", str(len(alerts)), f"{by_sev['emergency']} emergency · {by_sev['warning']} warning")}
  {stat("Cooling demand met", pct(plan['by_type']['cooling_centre']['coverage']), "risk-first plan")}
  {stat("Risk-weighted coverage", pct(plan['risk_weighted_coverage']), "all resource types")}
</div>
<div class="grid grid-2">
  <section class="panel"><h2>Where the risk is</h2>{chart("/chart/risk-map.png?layer=score", "Schematic map of risk score per ward")}
  <p class="small muted">Schematic grid, not to scale; not official boundaries. <a href="/map">Open the vulnerability map</a>.</p></section>
  <section class="panel"><h2>Score by location</h2>{chart("/chart/risk-bars.png", "Bar chart of risk score per location")}</section>
</div>
<h2>Highest-risk locations and why</h2>
{table(["Location", "Score", "Category", "Confidence", "Main reasons"], hot_rows)}
<div class="grid grid-2">
  <section class="panel"><h2>Active alerts</h2>{table(["Severity", "Location", "Alert", "Period"], alert_rows)}
  <p><a href="/alerts">All alerts</a></p></section>
  <section class="panel"><h2>Regional summary</h2>{table(["Region", "Locations", "Mean", "Max", "High+"], region_rows)}
  <h3>Forecast and trend</h3>{chart("/chart/heatmap.png", "Heatmap of daily maximum temperature per location")}</section>
</div>
<h2>Response readiness</h2>
{table(["Resource", "Available", "Limited", "Offline", "Capacity/day", "Demand/day", "Demand met"], res_rows)}
<section class="panel"><h2>Data freshness and limits</h2>
<p>{freshness} Data kinds in use: <strong>{esc(kinds)}</strong>. Each region is assessed as of its own latest observation;
the hazard uses the {settings.WINDOW_DAYS} days up to that date plus {settings.FORECAST_DAYS} forecast days.</p>
<p class="small muted">Scores rank relative priority under NOOR's documented assumptions; they are not health predictions.
Thresholds are NOOR defaults, not IMD criteria. See <a href="/methodology">Method</a> and <a href="/data">Data &amp; sources</a>.</p>
</section>"""
    return _layout(svc, "Dashboard", "/dashboard", body, q)


# ---------------------------------------------------------------------------- explorer
def explorer(svc, q):
    """Climate data explorer: one location's daily series, comparisons and CSV export."""
    from ..climate import explorer_table, location_comparison, monthly_means
    locations = svc.db.list_locations()
    frame = svc.db.observations_frame()
    if frame.empty:
        return _layout(svc, "Data explorer", "/explorer", "<h1>Data explorer</h1><p>No observations yet. "
                       '<a href="/data">Import a CSV</a>.</p>', q)
    observed = frame[frame["is_forecast"] == 0]
    code = q.get("location") or locations[0]["code"]
    if code not in {l["code"] for l in locations}:
        code = locations[0]["code"]
    last = observed["date"].max()
    end = q.get("end") or last
    start = q.get("start") or (_shift(last, -29))
    if start > end:
        start, end = end, start
    loc_frame = frame[frame["location"] == code]
    daily = explorer_table(loc_frame, start, end)
    missing = int(daily["missing"].sum())
    rows = []
    for day, r in daily.iloc[::-1].iterrows():
        rows.append([day.strftime("%Y-%m-%d"), fmt(r["t_max"]), fmt(r["t_min"]), fmt(r["humidity"], 0),
                     fmt(r["heat_index"]), "missing" if r["missing"] else f'<span class="kind">{esc(r["source_kind"])}</span>'])
    comp = location_comparison(observed[(observed["date"] >= start) & (observed["date"] <= end)])
    comp_rows = [[esc(r["location"]), esc(r["name"]), fmt(r["mean_tmax"]), fmt(r["max_tmax"]), fmt(r["mean_tmin"]),
                  fmt(r["mean_humidity"], 0), str(int(r["days_observed"])), str(int(r["days_missing"]))]
                 for _, r in comp.iterrows()]
    months = monthly_means(loc_frame)
    month_rows = [[esc(r["month"]), fmt(r["t_max"]), fmt(r["t_min"]), fmt(r["humidity"], 0)] for _, r in months.iterrows()]
    forecast = loc_frame[loc_frame["is_forecast"] == 1]
    fc_rows = [[esc(r["date"]), fmt(r["t_max"]), fmt(r["t_min"]), fmt(r["humidity"], 0), esc(r["source_kind"])]
               for _, r in forecast.iterrows()]
    loc_choices = [(l["code"], f"{l['code']} — {l['name']}") for l in locations]
    trend = url("/chart/trend.png", location=code, start=start, end=end)
    export = url("/export/observations.csv", location=code, start=start, end=end)
    body = f"""
<h1>Climate data explorer</h1>
<p class="lead">Daily maximum and minimum temperature, mean relative humidity and the derived heat index.
Days with no data are listed as <em>missing</em>, never filled in.</p>
<form class="inline panel" method="get" action="/explorer">
  <div class="field"><label for="location">Location</label><select id="location" name="location">{options(loc_choices, code)}</select></div>
  <div class="field"><label for="start">From</label><input id="start" type="date" name="start" value="{esc(start)}"></div>
  <div class="field"><label for="end">To</label><input id="end" type="date" name="end" value="{esc(end)}"></div>
  <button type="submit">Show</button>
  <a class="button secondary" href="{esc(export)}">Download CSV</a>
</form>
{chart(trend, f"Temperature and heat index trend for {code}")}
<p class="small muted">{missing} missing day(s) in this period. Heat index uses daily maximum temperature with daily
mean humidity, which can overstate the afternoon value.</p>
<div class="grid grid-2">
  <section><h2>Daily values</h2>{table(["Date", "Max °C", "Min °C", "Humidity %", "Heat index °C", "Source"], rows)}</section>
  <section><h2>Forecast days</h2>{table(["Date", "Max °C", "Min °C", "Humidity %", "Source"], fc_rows)}
  <h2>Monthly means ({esc(code)})</h2>{table(["Month", "Max °C", "Min °C", "Humidity %"], month_rows)}</section>
</div>
<h2>Compare locations ({esc(start)} to {esc(end)})</h2>
{table(["Code", "Name", "Mean max", "Highest max", "Mean min", "Humidity", "Days", "Missing"], comp_rows)}"""
    return _layout(svc, "Data explorer", "/explorer", body, q)


def _shift(day, days):
    """Add days to a YYYY-MM-DD string."""
    from datetime import date, timedelta
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------- risk
def risk(svc, q):
    """Risk table with filters, sorting and a what-if weights form."""
    weights = None
    custom = all(q.get("w_" + k) for k in settings.RISK_WEIGHTS)
    error = q.get("err")
    if custom:
        weights = {k: q.get("w_" + k) for k in settings.RISK_WEIGHTS}
        results = svc.assess(weights)
        rows_data = [{**r, "as_of_date": r["as_of"]} for r in results]
        rows_data.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    else:
        rows_data = svc.db.latest_assessments()
    category = q.get("category")
    if category:
        rows_data = [r for r in rows_data if r["category"] == category]
    sort = q.get("sort", "score")
    keys = {"score": lambda r: -(r["score"] or -1), "name": lambda r: r["name"], "hazard": lambda r: -(r["hazard"] or -1),
            "vulnerability": lambda r: -(r["vulnerability"] or -1), "confidence": lambda r: r["confidence"]}
    rows_data.sort(key=keys.get(sort, keys["score"]))
    rows = [[f'<a href="/risk/{esc(r["code"])}">{esc(r["code"])}</a>', esc(r["name"]), fmt(r["score"]),
             category_badge(r["category"]), fmt(r["hazard"], 2), fmt(r["exposure"], 2), fmt(r["vulnerability"], 2),
             fmt(r["capacity"], 2), esc(r["confidence"])] for r in rows_data]
    cat_choices = [("", "All categories")] + [(n, n) for _, n in settings.CATEGORIES] + [("Insufficient data", "Insufficient data")]
    sort_choices = [("score", "Score"), ("name", "Name"), ("hazard", "Hazard"), ("vulnerability", "Vulnerability"),
                    ("confidence", "Confidence")]
    current = weights or settings.RISK_WEIGHTS
    weight_fields = "".join(
        f'<div class="field"><label for="w_{k}">{esc(k.replace("_", " ").capitalize())}</label>'
        f'<input id="w_{k}" name="w_{k}" type="number" min="0" max="1" step="0.05" value="{esc(current[k])}"></div>'
        for k in settings.RISK_WEIGHTS)
    note = ("<p class='notice notice-info'>Showing a what-if ranking with your weights. Nothing was saved; the dashboard "
            "still uses the standard weights.</p>" if custom else "")
    body = f"""
<h1>Heat-risk assessment</h1>
<p class="lead">Each location gets four separate dimension scores (0–1) before they are combined into one
0–100 score. Click a code to see exactly why it scored what it did.</p>
{note}
<form class="inline panel" method="get" action="/risk">
  <div class="field"><label for="category">Category</label><select id="category" name="category">{options(cat_choices, category or "")}</select></div>
  <div class="field"><label for="sort">Sort by</label><select id="sort" name="sort">{options(sort_choices, sort)}</select></div>
  <button type="submit">Apply</button>
</form>
{table(["Code", "Location", "Score", "Category", "Hazard", "Exposure", "Vulnerability", "Capacity", "Confidence"], rows)}
<p class="small muted">Hazard, exposure and vulnerability: higher is worse. Capacity: higher is better.</p>
<div class="grid grid-2">
<section class="panel"><h2>Try different weights</h2>
<p class="small">The four weights must add up to 1. Hazard must stay above 0.</p>
<form method="get" action="/risk"><div class="form-grid">{weight_fields}</div>
<div class="actions"><button type="submit">Recalculate (not saved)</button><a class="button secondary" href="/risk">Reset</a></div></form>
</section>
<section class="panel"><h2>Score spread</h2>{chart("/chart/histogram.png", "Histogram of risk scores")}</section>
</div>"""
    return page("Risk", "/risk", body, q.get("msg"), error, _synthetic(svc))


def risk_detail(svc, q, code):
    """Why one location got its score."""
    r = svc.assessment(code)
    loc = svc.db.get_location(code)
    dim_tables = ""
    from ..risk import LABELS, format_value
    for dim, rows in r["details"].items():
        cells = []
        for row in rows:
            label, unit = LABELS[row["indicator"]]
            cells.append([esc(label), format_value(row["raw"], unit),
                          "missing" if row["normalised"] is None else fmt(row["normalised"], 2), fmt(row["weight"], 2)])
        value = r[dim]
        dim_tables += f"<h3>{esc(dim.capitalize())}: {'missing' if value is None else fmt(value, 2)}</h3>"
        dim_tables += table(["Indicator", "Raw value", "Normalised (0–1)", "Weight in dimension"], cells)
    daily_rows = []
    for day, d in r["daily"].iterrows():
        daily_rows.append([day.strftime("%Y-%m-%d"), "forecast" if d["is_forecast"] else "observed",
                           fmt(d["t_max"]), fmt(d["t_min"]), fmt(d["humidity"], 0), fmt(d["heat_index"])])
    w = settings.RISK_WEIGHTS
    formula = (f"100 × ({w['hazard']} × hazard + {w['exposure']} × exposure + {w['vulnerability']} × vulnerability "
               f"+ {w['lack_of_capacity']} × (1 − capacity))")
    body = f"""
<p class="eyebrow"><a href="/risk">Risk</a> · {esc(loc['region'])}</p>
<h1>{esc(r['code'])} — {esc(r['name'])}</h1>
<div class="stats">
  {stat("Score", fmt(r['score']), category_badge(r['category']))}
  {stat("Confidence", esc(r['confidence']), f"data completeness {pct(r['completeness'])}")}
  {stat("Data age", "—" if r['data_age_days'] is None else f"{r['data_age_days']} days", f"as of {esc(r['as_of'])}")}
  {stat("Population", fmt(loc['population'], 0), f'<span class="kind">{esc(loc["source_kind"])}</span>')}
</div>
<div class="grid grid-2">
<section class="panel"><h2>Why this score</h2><ul class="reasons">{''.join(f'<li>{esc(x)}</li>' for x in r['reasons'])}</ul>
<p class="small muted">Formula: score = {esc(formula)}. Missing dimensions use {settings.MISSING_DIMENSION_VALUE}, never 0.</p></section>
<section class="panel">{chart(f"/chart/dimensions/{esc(code)}.png", f"Dimension scores for {code}")}</section>
</div>
<h2>Inputs, step by step</h2>
{dim_tables}
<h2>Days used for the hazard</h2>
{table(["Date", "Type", "Max °C", "Min °C", "Humidity %", "Heat index °C"], daily_rows)}
<p><a href="{esc(url('/explorer', location=code))}">Open this location in the data explorer</a></p>"""
    return _layout(svc, f"Risk {code}", "/risk", body, q)


# ---------------------------------------------------------------------------- map
def vulnerability_map(svc, q):
    """Regional view with a layer switch."""
    layers = [("score", "Risk score"), ("hazard", "Hazard"), ("exposure", "Exposure"),
              ("vulnerability", "Vulnerability"), ("capacity", "Response capacity")]
    layer = q.get("layer", "score")
    if layer not in dict(layers):
        layer = "score"
    results = svc.assess()
    locations = {l["code"]: l for l in svc.db.list_locations()}
    rows = []
    for r in sorted(results, key=lambda x: -(x["vulnerability"] or 0)):
        loc = locations[r["code"]]
        top = "; ".join(r["reasons"][1:3])
        rows.append([f'<a href="/risk/{esc(r["code"])}">{esc(r["code"])}</a>', esc(r["name"]), fmt(loc["population"], 0),
                     fmt(r["exposure"], 2), fmt(r["vulnerability"], 2), category_badge(r["category"]),
                     esc(r["confidence"]), esc(top)])
    body = f"""
<h1>Vulnerability map</h1>
<p class="lead">A schematic grid of the demonstration district's wards. Positions are illustrative (3 km apart),
not real geography or official boundaries — a mapping library would add nothing honest here.</p>
<form class="inline panel" method="get" action="/map">
  <div class="field"><label for="layer">Layer</label><select id="layer" name="layer">{options(layers, layer)}</select></div>
  <button type="submit">Show layer</button>
</form>
{chart(url("/chart/risk-map.png", layer=layer), f"Schematic map of {layer} per ward")}
<p class="small muted">Cells show the value × 100. "n/a" means the input is missing. For capacity, higher is better.</p>
<h2>Exposure and vulnerability by location</h2>
{table(["Code", "Location", "Population", "Exposure", "Vulnerability", "Risk", "Confidence", "Top factors"], rows)}"""
    return _layout(svc, "Vulnerability map", "/map", body, q)


# ---------------------------------------------------------------------------- alerts
def alerts(svc, q):
    """Alert list with filters, run button and acknowledge/resolve actions."""
    status = q.get("status") or None
    severity = q.get("severity") or None
    items = svc.db.list_alerts(status, severity)
    from ..alerts import Alert
    cards = []
    for a in items:
        actions = "".join(f"<li>{esc(x)}</li>" for x in a["actions"].split(" | "))
        sms = Alert(a["rule"], a["severity"], a["message"], a["trigger_value"], a["threshold"], a["period"],
                    a["actions"].split(" | "), a["confidence"]).sms_preview()
        buttons = ""
        if a["status"] == "active":
            buttons += _status_button(a["id"], "acknowledged", "Acknowledge")
        if a["status"] != "resolved":
            buttons += _status_button(a["id"], "resolved", "Resolve")
        cards.append(f"""<article class="alert-card sev-border-{esc(a['severity'])}">
<div class="actions">{severity_badge(a['severity'])}<span class="kind">{esc(a['rule'])}</span>
<span class="small muted">status: <strong>{esc(a['status'])}</strong> · issued {esc(a['issued_at'])}</span></div>
<h3><a href="/risk/{esc(a['code'])}">{esc(a['code'])}</a> {esc(a['message'])}</h3>
<p class="small">Trigger: {fmt(a['trigger_value'])} against threshold {fmt(a['threshold'])} · period {esc(a['period'])}</p>
<ul>{actions}</ul>
<p class="small muted">{esc(a['confidence'])}</p>
<details><summary>Notification preview (local simulation — nothing is sent)</summary><pre>{esc(sms)}</pre></details>
<div class="actions">{buttons}</div></article>""")
    status_choices = [("", "Any status"), ("active", "Active"), ("acknowledged", "Acknowledged"), ("resolved", "Resolved")]
    sev_choices = [("", "Any severity"), ("emergency", "Emergency"), ("warning", "Warning"), ("advisory", "Advisory"),
                   ("info", "Info")]
    body = f"""
<h1>Early warnings</h1>
<p class="lead">Deterministic threshold rules (see <a href="/methodology#warnings">Method</a>). Each alert says what
fired, the value against its threshold, the period, and cautious preparedness actions.</p>
<p class="notice notice-info">NOOR does not replace official meteorological warnings or emergency authorities.
No SMS or e-mail is sent; the preview below each alert is a local simulation.</p>
<div class="actions">
<form method="post" action="/alerts/run"><button type="submit">Run the warning engine now</button></form>
<form class="inline" method="get" action="/alerts">
  <div class="field"><label for="status">Status</label><select id="status" name="status">{options(status_choices, status or "")}</select></div>
  <div class="field"><label for="severity">Severity</label><select id="severity" name="severity">{options(sev_choices, severity or "")}</select></div>
  <button type="submit" class="secondary">Filter</button>
</form>
<a class="button secondary" href="/export/alerts.csv">Download alert report (CSV)</a>
</div>
<p class="small muted">{len(items)} alert(s) shown.</p>
{''.join(cards) or '<p class="muted">No alerts match these filters.</p>'}"""
    return _layout(svc, "Alerts", "/alerts", body, q)


def _status_button(alert_id, new_status, label):
    """A one-button form that changes an alert's status."""
    return (f'<form method="post" action="/alerts/{int(alert_id)}/status"><input type="hidden" name="status" '
            f'value="{new_status}"><button class="secondary" type="submit">{label}</button></form>')


# ---------------------------------------------------------------------------- resources
def resources(svc, q):
    """Inventory with filters, inline status/amount edits, add and delete."""
    rtype = q.get("type") or ""
    rstatus = q.get("status") or ""
    objects = {r.code: r for r in svc.resources()}
    rows = []
    for r in svc.db.list_resources():
        if (rtype and r["type"] != rtype) or (rstatus and r["status"] != rstatus):
            continue
        obj = objects[r["code"]]
        edit = (f'<form class="inline" method="post" action="/resources/{esc(r["code"])}">'
                f'<label class="small" for="s-{esc(r["code"])}">Status</label>'
                f'<select id="s-{esc(r["code"])}" name="status">{options([(s, s) for s in settings.STATUS_FACTOR], r["status"])}</select>'
                f'<label class="small" for="a-{esc(r["code"])}">Amount</label>'
                f'<input id="a-{esc(r["code"])}" name="amount" type="number" min="1" step="any" value="{esc(r["amount"])}" class="narrow">'
                f'<button class="secondary" type="submit">Save</button></form>'
                f'<form method="post" action="/resources/{esc(r["code"])}/delete"><button class="secondary" type="submit">Delete</button></form>')
        rows.append([esc(r["code"]), esc(obj.describe()), esc(TYPE_LABELS[r["type"]]),
                     f'{esc(r["location_code"])} {esc(r["location_name"])}', f'{fmt(r["amount"], 0)} {esc(obj.unit)}',
                     fmt(obj.capacity(), 0), fmt(r["radius_km"]), str(r["staff"]), f'₹{r["daily_cost"]:,}',
                     f'<span class="kind">{esc(r["source_kind"])}</span>', edit])
    type_choices = [("", "All types")] + list(TYPE_LABELS.items())
    status_choices = [("", "Any status")] + [(s, s) for s in settings.STATUS_FACTOR]
    loc_choices = [(l["code"], f"{l['code']} — {l['name']}") for l in svc.db.list_locations()]
    units = "; ".join(f"{cls.label}: {cls.unit}" for cls in RESOURCE_CLASSES.values())
    body = f"""
<h1>Resources</h1>
<p class="lead">Cooling centres, drinking-water points, medical units, response teams and outreach teams. Each type
turns its size into people served per day in its own way (people per day column).</p>
<form class="inline panel" method="get" action="/resources">
  <div class="field"><label for="type">Type</label><select id="type" name="type">{options(type_choices, rtype)}</select></div>
  <div class="field"><label for="rstatus">Status</label><select id="rstatus" name="status">{options(status_choices, rstatus)}</select></div>
  <button type="submit">Filter</button>
</form>
{table(["Code", "Description", "Type", "Location", "Amount", "People/day", "Radius km", "Staff", "Cost/day", "Data", "Update"], rows)}
<p class="small muted">Units — {esc(units)}. Limited counts as 50%, offline as 0%. Changing a resource re-runs the risk assessment.</p>
<section class="panel"><h2>Add a resource</h2>
<form method="post" action="/resources/add"><div class="form-grid">
  <div class="field"><label for="n-code">Code</label><input id="n-code" name="code" required maxlength="20" placeholder="CC-08"></div>
  <div class="field"><label for="n-name">Name</label><input id="n-name" name="name" required maxlength="80"></div>
  <div class="field"><label for="n-type">Type</label><select id="n-type" name="type">{options(list(TYPE_LABELS.items()), "cooling_centre")}</select></div>
  <div class="field"><label for="n-loc">Location</label><select id="n-loc" name="location_code">{options(loc_choices, "")}</select></div>
  <div class="field"><label for="n-amount">Amount</label><input id="n-amount" name="amount" type="number" min="1" step="any" required><span class="hint">places, litres, patients, members or volunteers</span></div>
  <div class="field"><label for="n-status">Status</label><select id="n-status" name="status">{options([(s, s) for s in settings.STATUS_FACTOR], "available")}</select></div>
  <div class="field"><label for="n-radius">Service radius (km)</label><input id="n-radius" name="radius_km" type="number" min="0.1" max="100" step="0.1" value="3"></div>
  <div class="field"><label for="n-staff">Staff</label><input id="n-staff" name="staff" type="number" min="0" value="0"></div>
  <div class="field"><label for="n-cost">Daily cost (₹)</label><input id="n-cost" name="daily_cost" type="number" min="0" value="0"></div>
  <div class="field"><label for="n-kind">Data kind</label><select id="n-kind" name="kind">{options(KIND_CHOICES, "estimated")}</select></div>
</div><button type="submit">Add resource</button></form></section>"""
    return _layout(svc, "Resources", "/resources", body, q)


# ---------------------------------------------------------------------------- planning
def plans(svc, q):
    """Allocation plan, strategy comparison and saved plans."""
    strategy = q.get("strategy", "risk_first")
    if strategy not in STRATEGIES:
        strategy = "risk_first"
    plan = svc.plan(strategy)
    type_rows = [[esc(TYPE_LABELS[t]), fmt(v["demand"], 0), fmt(v["served"], 0), fmt(v["unmet"], 0), pct(v["coverage"]),
                  fmt(v["capacity"], 0), pct(v["utilisation"])] for t, v in plan["by_type"].items()]
    loc_rows = []
    for r in sorted(plan["locations"], key=lambda x: -(x["score"] or 0)):
        loc_rows.append([esc(r["code"]), esc(r["name"]), fmt(r["score"]), fmt(r["population"], 0),
                         pct(r["cooling_centre_coverage"]), pct(r["water_point_coverage"]),
                         pct(r["medical_unit_coverage"]), pct(r["response_team_coverage"]),
                         pct(r["outreach_team_coverage"])])
    res_rows = [[esc(r["code"]), esc(r["name"]), esc(r["status"]), fmt(r["capacity"], 0), fmt(r["used"], 0),
                 pct(r["utilisation"])] for r in plan["resources"]]
    cmp = svc.compare()
    cmp_rows = [[esc(TYPE_LABELS[r["type"]]), fmt(r["served_a"], 0), fmt(r["served_b"], 0), fmt(r["difference"], 0)]
                for r in cmp["rows"]]
    saved = [[esc(p["plan_name"]), esc(STRATEGIES.get(p["strategy"], p["strategy"])), esc(p["created_at"]),
              str(p["rows"]), fmt(p["people_per_day"], 0)] for p in svc.db.list_plans()]
    unknown = ", ".join(plan["unknown_demand"]) or "none"
    body = f"""
<h1>Resource allocation and emergency planning</h1>
<p class="lead">Demand per location = population × planning rate × risk score ÷ 100. A greedy loop serves locations in
priority order from the nearest resources that can reach them, until capacity runs out.</p>
<form class="inline panel" method="get" action="/plans">
  <div class="field"><label for="strategy">Strategy</label><select id="strategy" name="strategy">{options(list(STRATEGIES.items()), strategy)}</select></div>
  <button type="submit">Run plan</button>
  <a class="button secondary" href="{esc(url('/export/allocation.csv', strategy=strategy))}">Download plan (CSV)</a>
</form>
<div class="stats">
  {stat("Demand met", pct(plan['total_served'] / plan['total_demand'] if plan['total_demand'] else None), "all types, people/day")}
  {stat("Risk-weighted coverage", pct(plan['risk_weighted_coverage']), "need weighted by score")}
  {stat("High-risk with gaps", str(len(plan['high_risk_with_gaps'])), "locations")}
  {stat("Unknown demand", str(len(plan['unknown_demand'])), esc(unknown))}
</div>
{chart(url("/chart/allocation.png", strategy=strategy), "Demand versus capacity per resource type")}
{table(["Resource type", "Demand/day", "Served", "Unmet", "Demand met", "Capacity", "Utilisation"], type_rows)}
<h2>Coverage by location</h2>
{table(["Code", "Location", "Score", "Population", "Cooling", "Water", "Medical", "Response", "Outreach"], loc_rows)}
<h2>Resource utilisation</h2>
{table(["Code", "Resource", "Status", "Capacity/day", "Assigned", "Utilisation"], res_rows)}
<div class="grid grid-2">
<section class="panel"><h2>Compare strategies</h2>
{table(["Type", "Population-first served", "Risk-first served", "Difference"], cmp_rows)}
<p class="small">Risk-weighted coverage: population-first {pct(cmp['risk_weighted_a'])}, risk-first {pct(cmp['risk_weighted_b'])}.</p></section>
<section class="panel"><h2>Save this plan</h2>
<form method="post" action="/plans/save"><input type="hidden" name="strategy" value="{esc(strategy)}">
<div class="field"><label for="plan_name">Plan name</label><input id="plan_name" name="plan_name" required maxlength="60" value="{esc(STRATEGIES[strategy][:40])}"></div>
<p><button type="submit">Save plan</button></p></form>
{table(["Plan", "Strategy", "Saved", "Rows", "People/day"], saved)}</section>
</div>
<p class="small muted">Assumptions (settings.py): demand rates {esc(settings.DEMAND_RATES)}; {settings.LITRES_PER_PERSON} L water per person;
{settings.VISITS_PER_RESPONDER} visits per responder; {settings.CONTACTS_PER_VOLUNTEER} contacts per volunteer. These are planning
assumptions, not validated operational figures. A plan here is a starting point for people who know the ground.</p>"""
    return _layout(svc, "Planning", "/plans", body, q)


# ---------------------------------------------------------------------------- scenarios
SCENARIO_LABELS = {
    "temperature_increase": ("Temperature increase (°C)", "0.5"),
    "extra_hot_days": ("Longer heatwave (extra days)", "1"),
    "new_cooling_centres": ("New cooling centres", "1"),
    "water_capacity_pct": ("Water capacity (% of today)", "5"),
    "medical_capacity_pct": ("Medical capacity (% of today)", "5"),
    "budget_per_day": ("Extra budget per day (₹)", "5000"),
    "staff_available": ("Extra staff available", "1"),
}


def scenarios(svc, q):
    """Scenario Lab form and before/after results."""
    params = {k: q[k] for k in LIMITS if k in q and q[k] != ""}
    fields = ""
    for name, (low, high, default) in LIMITS.items():
        label, step = SCENARIO_LABELS[name]
        value = params.get(name, default)
        fields += (f'<div class="field"><label for="{name}">{esc(label)}</label><input id="{name}" name="{name}" '
                   f'type="number" min="{low}" max="{high}" step="{step}" value="{esc(value)}">'
                   f'<span class="hint">{low}–{high}</span></div>')
    result_html = ""
    if q.get("run"):
        result = svc.scenario(params)
        c = result["comparison"]
        type_rows = [[esc(TYPE_LABELS[r["type"]]), fmt(r["unmet_before"], 0), fmt(r["unmet_after"], 0),
                      pct(r["coverage_before"]), pct(r["coverage_after"]), pct(r["utilisation_before"]),
                      pct(r["utilisation_after"])] for r in c["by_type"]]
        loc_rows = [[esc(r["code"]), esc(r["name"]), fmt(r["score_before"]), fmt(r["score_after"]),
                     fmt(r["change"]), category_badge(r["category_before"]), category_badge(r["category_after"])]
                    for r in c["locations"]]
        still = ", ".join(f"{x['code']} {x['name']}" for x in c["still_needing_help"]) or "none"
        limited = (" Limited by " + " and ".join(result["limited_by"]) + ".") if result["limited_by"] else ""
        placed = ", ".join(result["placed_centres"]) or "none"
        query = {k: v for k, v in q.items() if k in LIMITS}
        result_html = f"""
<h2>Result</h2>
<div class="stats">
  {stat("Mean score", f"{fmt(c['mean_score_before'])} → {fmt(c['mean_score_after'])}")}
  {stat("High or worse", f"{c['high_before']} → {c['high_after']}", "locations")}
  {stat("Unmet demand", f"{fmt(c['unmet_before'], 0)} → {fmt(c['unmet_after'], 0)}", "people/day, all types")}
  {stat("New centres placed", str(len(result['placed_centres'])), f"₹{result['extra_cost_per_day']:,}/day")}
</div>
<p>New cooling centres placed at: <strong>{esc(placed)}</strong>.{esc(limited)}</p>
<p>Still needing intervention (High or worse with unmet demand): <strong>{esc(still)}</strong>.</p>
{chart(url("/chart/scenario.png", **query), "Risk score today versus scenario per location")}
{table(["Resource type", "Unmet before", "Unmet after", "Met before", "Met after", "Utilisation before", "Utilisation after"], type_rows)}
{table(["Code", "Location", "Score today", "Score in scenario", "Change", "Category today", "Category in scenario"], loc_rows)}
<p><a class="button secondary" href="{esc(url('/export/scenario.csv', **query))}">Download comparison (CSV)</a></p>"""
    body = f"""
<h1>Scenario lab</h1>
<p class="lead">Change the conditions and see how risk, coverage and unmet demand move. The same code that scores today
is rerun on the changed inputs.</p>
<p class="notice notice-info">A what-if comparison under NOOR's assumptions — not a forecast of real outcomes.</p>
<form class="panel" method="get" action="/scenarios"><input type="hidden" name="run" value="1">
<div class="form-grid">{fields}</div>
<div class="actions"><button type="submit">Run scenario</button><a class="button secondary" href="/scenarios">Reset to defaults</a></div>
<p class="small muted">A new centre: {settings.NEW_CENTRE['places']} places/day, ₹{settings.NEW_CENTRE['daily_cost']:,}/day,
{settings.NEW_CENTRE['staff']} staff, {settings.NEW_CENTRE['radius_km']} km radius. Centres go where risk-weighted unmet
cooling demand is highest. Humidity is held constant when temperature rises (a simplification).</p>
</form>
{result_html}"""
    return _layout(svc, "Scenario lab", "/scenarios", body, q)


# ---------------------------------------------------------------------------- reports
def reports(svc, q):
    """Downloadable reports and the SQL query viewer."""
    name = q.get("query", "region_summary")
    if name not in QUERIES:
        name = "region_summary"
    title, rows = run_query(svc.db, name)
    headers = list(rows[0].keys()) if rows else ["(no rows)"]
    cells = [[fmt(v) if isinstance(v, float) else esc(v) for v in r.values()] for r in rows]
    query_choices = [(k, v["title"]) for k, v in QUERIES.items()]
    downloads = [("/export/risk.csv", "Regional heat-risk summary"), ("/export/vulnerability.csv", "Vulnerability assessment"),
                 ("/export/alerts.csv", "Alert report"), ("/export/allocation.csv?strategy=risk_first", "Allocation plan (risk-first)"),
                 ("/export/scenario.csv?temperature_increase=2&new_cooling_centres=5", "Scenario comparison (+2 °C, 5 new centres)"),
                 ("/export/observations.csv", "All observations"), ("/export/template.csv", "Blank import template")]
    links = "".join(f'<li><a href="{esc(h)}">{esc(t)}</a></li>' for h, t in downloads)
    body = f"""
<h1>Reports and exports</h1>
<p class="lead">Every CSV starts with lines saying when it was generated, what data it used (and whether that data is
synthetic), the method, and its limitations.</p>
<section class="panel"><h2>Download</h2><ul>{links}</ul>
<p class="small">For a printable page, open any page and use your browser's print command; navigation is hidden in print.</p></section>
<h2>SQL summaries</h2>
<form class="inline panel" method="get" action="/reports">
  <div class="field"><label for="query">Query</label><select id="query" name="query">{options(query_choices, name)}</select></div>
  <button type="submit">Run</button>
</form>
<pre>{esc(QUERIES[name]['sql'].strip())}</pre>
<p class="small muted">Parameters: {esc(QUERIES[name]['params'])}</p>
{table(headers, cells, title)}"""
    return _layout(svc, "Reports", "/reports", body, q)


# ---------------------------------------------------------------------------- data & sources
def data_page(svc, q, import_report=None):
    """Sources, provenance, import form and add-location form."""
    status = svc.status()
    src_rows = [[esc(s["name"]), f'<span class="kind">{esc(s["kind"])}</span>', esc(s["provider"]), esc(s["licence"]),
                 str(s["observations"]), str(s["locations"]), str(s["resources"]), esc(s["notes"] or "")]
                for s in status["sources"]]
    count_rows = [[esc(k), str(v)] for k, v in status["counts"].items()]
    _t, missing = run_query(svc.db, "missing_days")
    miss_rows = [[esc(r["code"]), esc(r["name"]), esc(r["first_day"]), esc(r["last_day"]), str(r["days_missing"])]
                 for r in missing]
    report_html = ""
    if import_report:
        err_rows = [[str(e["line"]), esc(e["column"]), esc(e["message"])] for e in import_report["errors"]]
        more = f" ({import_report['more_errors']} more not shown)" if import_report["more_errors"] else ""
        report_html = f"""<section class="panel" aria-live="polite"><h2>Import result</h2>
<p>{import_report['rows']} row(s) read: <strong>{import_report['accepted']} accepted</strong>,
<strong>{import_report['rejected']} rejected</strong>{esc(more)}.
{('Saved under source “' + esc(import_report['source']) + '”; risk was recalculated.') if import_report.get('source') else 'Nothing was saved.'}</p>
{table(["Line", "Column", "Problem"], err_rows) if err_rows else ''}</section>"""
    region_choices = sorted({l["region"] for l in svc.db.list_locations()})
    body = f"""
<h1>Data and sources</h1>
<p class="lead">Where every number comes from, how far to trust it, and how to bring in your own data.</p>
<section class="panel"><h2>About the demonstration data</h2>
<p>The district “Saptapur”, its 16 wards, populations, vulnerability shares, resources and daily weather are
<strong>synthetic</strong>: generated by <code>noor/seed.py</code> with a fixed random seed so anyone gets the same numbers.
They are shaped like a hot pre-monsoon season in inland India, but no value is a measurement or an official statistic.
Two gaps are deliberate: Airport Road has no population figure and Outer Villages has no vulnerability survey, to show
how NOOR handles missing data. Lake View's readings stop four days early (stale data) and Mill Lines misses 2 June.</p>
<p><strong>Real data.</strong> NOOR is not connected to a live feed. IMD station data is not available through an open API
NOOR could rely on. <code>scripts/fetch_open_meteo.py</code> can download model-derived daily weather from Open-Meteo
(CC BY 4.0) into a CSV that you import below; it is labelled <em>model-derived</em>, never <em>measured</em>.</p></section>
{report_html}
<h2>Sources</h2>
{table(["Source", "Kind", "Provider", "Licence", "Observations", "Locations", "Resources", "Notes"], src_rows)}
<div class="grid grid-2">
<section class="panel"><h2>Import observations (CSV)</h2>
<p class="small">Columns: <code>location_code,date,t_max,t_min,humidity[,is_forecast]</code>. Dates YYYY-MM-DD, temperatures in °C,
humidity in %. Empty cells mean missing. Max 2 MB / 20,000 rows. <a href="/export/template.csv">Template</a>.</p>
<form method="post" action="/data/import" enctype="multipart/form-data"><div class="form-grid">
  <div class="field"><label for="file">CSV file</label><input id="file" name="file" type="file" accept=".csv,text/csv" required></div>
  <div class="field"><label for="source_name">Source name</label><input id="source_name" name="source_name" required maxlength="80" placeholder="e.g. Ward weather logger"></div>
  <div class="field"><label for="kind">Data kind</label><select id="kind" name="kind">{options(KIND_CHOICES, "measured")}</select></div>
  <div class="field"><label for="licence">Licence / terms</label><input id="licence" name="licence" required maxlength="120" placeholder="e.g. CC BY 4.0, or unknown"></div>
</div><button type="submit">Validate and import</button></form></section>
<section class="panel"><h2>Add a location</h2>
<form method="post" action="/data/location"><div class="form-grid">
  <div class="field"><label for="l-region">Region</label><input id="l-region" name="region" list="regions" required maxlength="80"><datalist id="regions">{''.join(f'<option value="{esc(r)}">' for r in region_choices)}</datalist></div>
  <div class="field"><label for="l-code">Code</label><input id="l-code" name="code" required maxlength="20"></div>
  <div class="field"><label for="l-name">Name</label><input id="l-name" name="name" required maxlength="80"></div>
  <div class="field"><label for="l-pop">Population</label><input id="l-pop" name="population" type="number" min="0"><span class="hint">leave empty if unknown</span></div>
  <div class="field"><label for="l-area">Area km²</label><input id="l-area" name="area_km2" type="number" min="0.01" step="any"></div>
  <div class="field"><label for="l-x">Grid x (km)</label><input id="l-x" name="grid_x" type="number" step="any"></div>
  <div class="field"><label for="l-y">Grid y (km)</label><input id="l-y" name="grid_y" type="number" step="any"></div>
  <div class="field"><label for="l-eld">Share aged 65+ (0–1)</label><input id="l-eld" name="elderly_share" type="number" min="0" max="1" step="0.01"></div>
  <div class="field"><label for="l-out">Outdoor workers (0–1)</label><input id="l-out" name="outdoor_worker_share" type="number" min="0" max="1" step="0.01"></div>
  <div class="field"><label for="l-house">Poor housing (0–1)</label><input id="l-house" name="poor_housing_share" type="number" min="0" max="1" step="0.01"></div>
  <div class="field"><label for="l-src">Where the numbers come from</label><input id="l-src" name="source" required maxlength="80"></div>
  <div class="field"><label for="l-kind">Data kind</label><select id="l-kind" name="kind">{options(KIND_CHOICES, "estimated")}</select></div>
</div><button type="submit">Add location</button></form></section>
</div>
<div class="grid grid-2">
<section><h2>Missing observation days</h2>{table(["Code", "Location", "First day", "Last day", "Missing"], miss_rows)}</section>
<section><h2>Database tables</h2>{table(["Table", "Rows"], count_rows)}
<p class="small muted">SQLite file: data stays on this machine. On the hosted demo the database lives in temporary storage
and is rebuilt from the seed when the server restarts.</p></section>
</div>"""
    return _layout(svc, "Data & sources", "/data", body, q)


# ---------------------------------------------------------------------------- methodology
def methodology(svc, q):
    """The method, rendered from settings.py so the page always matches the code."""
    def indicator_rows(indicators):
        return [[esc(k), fmt(lo, 2), fmt(hi, 2), fmt(w, 2)] for k, (lo, hi, w) in indicators.items()]
    w = settings.RISK_WEIGHTS
    cats = " · ".join(f"{name} ≥ {t:g}" for t, name in reversed(settings.CATEGORIES))
    bands = "; ".join(f"{sev} at {t} °C ({label})" for t, sev, label in settings.HEAT_INDEX_BANDS)
    body = f"""
<h1>Method</h1>
<p class="lead">Everything NOOR calculates, with the numbers it uses. These values are read from
<code>noor/settings.py</code>, so this page always matches the code.</p>
<h2>1. Heat index</h2>
<p>US National Weather Service heat index equation (Rothfusz regression with NWS adjustments), from daily maximum
temperature and daily mean humidity. Because humidity is usually lower at the hottest hour, this can overstate the
afternoon heat index. It is a screening indicator, not a medical measurement.</p>
<h2>2. Risk score</h2>
<p>Each raw indicator is min-max normalised with fixed bounds: <code>(x − low) ÷ (high − low)</code>, clipped to 0–1.
Fixed bounds keep scores comparable from day to day. Within a dimension, indicators are averaged with the weights below;
a missing indicator is left out and its weight shared by the others — it is never treated as 0.</p>
<p><code>score = 100 × ({w['hazard']} × hazard + {w['exposure']} × exposure + {w['vulnerability']} × vulnerability + {w['lack_of_capacity']} × (1 − capacity))</code></p>
<p>If a whole dimension has no data it gets {settings.MISSING_DIMENSION_VALUE} (precautionary, not 0) and confidence drops.
If fewer than {settings.MIN_OBSERVED_DAYS} of the {settings.WINDOW_DAYS} window days have a temperature, there is no score
(“Insufficient data”). If hazard is below 0.2 the score is capped at 39.9 so vulnerability alone never makes a cool week “High”.</p>
<p>Categories (lower bound inclusive): {esc(cats)}.</p>
<p>Confidence: <em>high</em> if ≥ 85% of indicators are present, data is ≤ 2 days old and nothing was imputed;
<em>medium</em> if ≥ 60% present and ≤ 7 days old; otherwise <em>low</em>.</p>
<div class="grid grid-2">
<section><h3>Hazard (window {settings.WINDOW_DAYS} days + {settings.FORECAST_DAYS} forecast days)</h3>{table(["Indicator", "Low", "High", "Weight"], indicator_rows(settings.HAZARD_INDICATORS))}
<p class="small">Hot day: Tmax ≥ {settings.HOT_DAY_C} °C. Warm night: Tmin ≥ {settings.WARM_NIGHT_C} °C. A missing day breaks a run.</p></section>
<section><h3>Exposure</h3>{table(["Indicator", "Low", "High", "Weight"], indicator_rows(settings.EXPOSURE_INDICATORS))}</section>
<section><h3>Vulnerability</h3>{table(["Indicator", "Low", "High", "Weight"], indicator_rows(settings.VULNERABILITY_INDICATORS))}</section>
<section><h3>Response capacity (higher is better)</h3>{table(["Indicator", "Low", "High", "Weight"], indicator_rows(settings.CAPACITY_INDICATORS))}
<p class="small">Per-1,000 values: each resource's people-per-day capacity is shared among the locations within its radius by population.</p></section>
</div>
<h2 id="warnings">3. Early warnings</h2>
<ul>
<li>Heat index (today and forecast days): {esc(bands)} — bands from the NWS heat index chart.</li>
<li>Hot spell still running or forecast: warning at {settings.HOT_SPELL_WARNING_DAYS}+ days ≥ {settings.HOT_DAY_C} °C, emergency at {settings.HOT_SPELL_EMERGENCY_DAYS}+.</li>
<li>Warm nights: advisory at {settings.WARM_NIGHTS_ADVISORY}+ consecutive nights ≥ {settings.WARM_NIGHT_C} °C.</li>
<li>Risk category: warning for Severe, emergency for Extreme.</li>
<li>Cooling gap: advisory if a High-or-worse location gets under {settings.COOLING_GAP_SHARE:.0%} of its cooling demand.</li>
<li>Stale data: info if the latest observation is more than {settings.STALE_DATA_DAYS} days old.</li>
</ul>
<p>These are NOOR defaults for demonstration, not IMD heat-wave criteria. For real decisions use official IMD and SDMA warnings.</p>
<h2>4. Allocation</h2>
<p>Demand = population × rate × score ÷ 100, rates {esc(settings.DEMAND_RATES)}. Greedy loop: sort locations by score × population
(or by population only, for comparison); for each, take capacity from the nearest resources of each type within their radius
until demand is met or capacity runs out. A heuristic, not an optimum, and not validated against real operations.</p>
<h2>5. Scenario lab</h2>
<p>Adds degrees to Tmax/Tmin, adds days to the hot spell, scales water and medical capacity, and places new cooling centres
one at a time where risk-weighted unmet cooling demand is highest (within budget and staff). Then reruns the same code.</p>
<h2>6. What NOOR does not claim</h2>
<p>No machine learning was trained; no accuracy figure exists because no held-out real outcome data was available. Scores are
relative priorities under stated assumptions, not predictions of illness or deaths.</p>"""
    return _layout(svc, "Method", "/methodology", body, q)


def error_page(status, message):
    """Friendly error page (no stack traces)."""
    body = f"""<h1>{status}</h1><p class="lead">{esc(message)}</p><p><a href="/dashboard">Back to the dashboard</a></p>"""
    return page(f"Error {status}", "", body, synthetic=False)
