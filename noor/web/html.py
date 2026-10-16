"""Small helpers that build HTML strings. Every value shown to the user goes through esc()."""
from html import escape
from urllib.parse import urlencode

NAV = [
    ("/dashboard", "Dashboard"),
    ("/explorer", "Data explorer"),
    ("/risk", "Risk"),
    ("/map", "Vulnerability map"),
    ("/alerts", "Alerts"),
    ("/resources", "Resources"),
    ("/plans", "Planning"),
    ("/scenarios", "Scenario lab"),
    ("/reports", "Reports"),
    ("/data", "Data & sources"),
    ("/methodology", "Method"),
]

CATEGORY_CLASS = {"Low": "low", "Moderate": "moderate", "High": "high", "Severe": "severe",
                  "Extreme": "extreme", "Insufficient data": "none"}
SEVERITY_CLASS = {"info": "info", "advisory": "advisory", "warning": "warning", "emergency": "emergency"}


def esc(value):
    """HTML-escape any value (None becomes an empty string)."""
    return "" if value is None else escape(str(value), quote=True)


def fmt(value, digits=1, suffix=""):
    """Format a number for display; None -> an em dash."""
    if value is None or value != value:  # None or NaN
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:,.{digits}f}{suffix}"
    return esc(value)


def pct(value):
    """0.613 -> '61%'."""
    return "—" if value is None else f"{value * 100:.0f}%"


def url(path, **params):
    """Build a link with query parameters (None values are left out)."""
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    return path + ("?" + urlencode(clean) if clean else "")


def category_badge(category):
    """Coloured label for a risk category."""
    return f'<span class="badge cat-{CATEGORY_CLASS.get(category, "none")}">{esc(category)}</span>'


def severity_badge(severity):
    """Coloured label for an alert severity."""
    return f'<span class="badge sev-{SEVERITY_CLASS.get(severity, "info")}">{esc(severity)}</span>'


def table(headers, rows, caption=None):
    """A table inside a scroll wrapper. Cells in `rows` must already be safe HTML."""
    head = "".join(f'<th scope="col">{esc(h)}</th>' for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    if not rows:
        body = f'<tr><td colspan="{len(headers)}" class="empty">Nothing to show.</td></tr>'
    cap = f"<caption>{esc(caption)}</caption>" if caption else ""
    return f'<div class="table-wrap"><table>{cap}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def options(choices, selected):
    """<option> tags; choices is a list of (value, label)."""
    return "".join(
        f'<option value="{esc(v)}"{" selected" if str(v) == str(selected) else ""}>{esc(label)}</option>'
        for v, label in choices)


def stat(label, value, note=""):
    """A headline number."""
    return (f'<div class="stat"><div class="stat-label">{esc(label)}</div>'
            f'<div class="stat-value">{value}</div><div class="stat-note">{note}</div></div>')


def chart(src, alt):
    """An <img> for a server-drawn PNG chart."""
    return f'<figure class="chart"><img src="{esc(src)}" alt="{esc(alt)}" loading="lazy"></figure>'


def notice(message, kind="info"):
    """A message box (info / error / success)."""
    if not message:
        return ""
    role = "alert" if kind == "error" else "status"
    return f'<div class="notice notice-{kind}" role="{role}">{esc(message)}</div>'


def page(title, active, body, message=None, error=None, synthetic=True):
    """Wrap page content in the shared layout."""
    current = ' aria-current="page"'
    links = "".join(
        f'<a href="{href}"{current if href == active else ""}>{esc(label)}</a>'
        for href, label in NAV)
    banner = ""
    if synthetic:
        banner = ('<div class="demo-banner">Demonstration mode: all climate, population and resource figures '
                  'are <strong>synthetic</strong> (fictional district “Saptapur”). '
                  '<a href="/data">What does that mean?</a></div>')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · NOOR</title>
<meta name="description" content="NOOR — Climate Intelligence &amp; Resilience. See the risk. Save lives.">
<link rel="stylesheet" href="/static/style.css">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
{banner}
<header class="site-header">
  <a class="wordmark" href="/" aria-label="NOOR home"><span class="sun" aria-hidden="true"></span>NOOR</a>
  <nav aria-label="Main">{links}</nav>
</header>
<main id="main">
{notice(message, "success")}{notice(error, "error")}
{body}
</main>
<footer class="site-footer">
  <p><strong>NOOR</strong> — Climate Intelligence &amp; Resilience. See the risk. Save lives.</p>
  <p>NOOR supports preparedness planning. It does not replace warnings from the India Meteorological Department,
  State Disaster Management Authorities or local health officials.</p>
  <p><a href="/methodology">Method</a> · <a href="/data">Data &amp; sources</a> · <a href="/api/health">API status</a></p>
</footer>
</body>
</html>"""
