"""HTML building blocks that mirror the desktop widgets (noor/gui/widgets.py)."""
from html import escape
from urllib.parse import urlencode

# (key, label, URL) in the same order as the desktop sidebar
NAV = [
    ("overview", "Overview", "/"),
    ("monitoring", "Climate Monitoring", "/monitoring"),
    ("risk", "Risk Assessment", "/risk"),
    ("alerts", "Alerts", "/alerts"),
    ("resources", "Resource Allocation", "/resources"),
    ("scenario", "Scenario Lab", "/scenario"),
    ("reports", "Reports & Analytics", "/reports"),
    ("data", "Data Management", "/data"),
]


def esc(value):
    """Escape any value for HTML (None becomes an empty string)."""
    return "" if value is None else escape(str(value), quote=True)


def url(path, **params):
    """Path plus query string, skipping empty values."""
    clean = {k: v for k, v in params.items() if v not in (None, "")}
    return path + ("?" + urlencode(clean) if clean else "")


def page(active, title, subtitle, body, chrome, msg=None, err=None):
    """The whole page: sidebar, header, the screen, status bar.

    chrome: {"alerts": active alert count, "chip": header data chip, "notice": sidebar notice}"""
    nav = []
    for key, label, href in NAV:
        badge = f'<span class="badge">{chrome["alerts"]}</span>' if key == "alerts" and chrome["alerts"] else ""
        current = ' aria-current="page" class="active"' if key == active else ""
        nav.append(f'<a href="{href}"{current}><span>{esc(label)}</span>{badge}</a>')
    status = ""
    if err:
        status = f'<div class="status error" role="alert">{esc(err)}</div>'
    elif msg:
        status = f'<div class="status ok" role="status">{esc(msg)}</div>'
    else:
        status = '<div class="status">Ready.</div>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=1280">
<title>{esc(title)} · NOOR — Climate Intelligence</title>
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/style.css">
<script src="/static/app.js" defer></script>
</head><body>
<a class="skip" href="#main">Skip to content</a>
<aside class="sidebar">
  <div class="brand"><div class="wordmark">N O O R</div><div class="sub">Climate Intelligence</div>
  <div class="tag">See the risk. Save lives.</div></div>
  <nav aria-label="Screens">{''.join(nav)}</nav>
  <div class="foot"><p class="notice">{esc(chrome["notice"])}</p>
  <p>Python · SQLite · Pandas · NumPy · Matplotlib</p>
  <p>Desktop app: <a href="https://github.com/GlazyKahito/noor/archive/refs/heads/main.zip">download</a></p></div>
</aside>
<div class="main">
  <header class="head"><h1>{esc(title)}</h1><span class="chip">{esc(chrome["chip"])}</span></header>
  <p class="subtitle">{esc(subtitle)}</p>
  <main id="main" class="content">{body}</main>
  <footer>{status}</footer>
</div>
</body></html>"""


def card(body, title=None, subtitle=None, cls=""):
    """White panel with a thin border, like widgets.Card."""
    head = f"<h2>{esc(title)}</h2>" if title else ""
    sub = f'<p class="muted">{esc(subtitle)}</p>' if subtitle else ""
    return f'<section class="card {cls}">{head}{sub}{body}</section>'


def tiles(items):
    """Row of number tiles: [(label, value, note, accent)]."""
    cells = []
    for label, value, note, accent in items:
        cells.append(f'<div class="tile{" accent" if accent else ""}"><div class="caps">{esc(label)}</div>'
                     f'<div class="number">{esc(value)}</div><div class="muted">{esc(note)}</div></div>')
    return f'<div class="tiles">{"".join(cells)}</div>'


def table(columns, rows, formatters=None, tag=None, link=None, empty="No records to show.", selected=None,
          height=None):
    """A sortable table like widgets.DataTable (click a heading to sort).

    columns: [(key, heading, align)]; tag(row) -> CSS class for the row tint;
    link(row) -> URL opened when the row is clicked; selected(row) -> True to highlight."""
    formatters = formatters or {}
    head = "".join(f'<th class="{a}"><button type="button" data-sort="{i}">{esc(h)}</button></th>'
                   for i, (_k, h, a) in enumerate(columns))
    body = []
    for row in rows:
        classes = [tag(row) if tag else ""]
        if selected and selected(row):
            classes.append("selected")
        href = link(row) if link else None
        attr = f' data-href="{esc(href)}" tabindex="0"' if href else ""
        cells = []
        for i, (key, _h, align) in enumerate(columns):
            value = formatters[key](row.get(key)) if key in formatters else row.get(key)
            text = "—" if value is None else esc(value)
            if href and i == 0:
                text = f'<a href="{esc(href)}">{text}</a>'
            sort_value = row.get(key)
            sort_attr = f' data-v="{esc(sort_value)}"' if isinstance(sort_value, (int, float)) else ""
            cells.append(f'<td class="{align}"{sort_attr}>{text}</td>')
        body.append(f'<tr class="{" ".join(c for c in classes if c)}"{attr}>{"".join(cells)}</tr>')
    if not rows:
        body.append(f'<tr class="empty"><td colspan="{len(columns)}">{esc(empty)}</td></tr>')
    size = f" h-{height}" if height else ""
    return (f'<div class="table-wrap{size}"><table class="data"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def tabs(base, items, active, **keep):
    """Notebook-style tabs. items: [(key, label)]."""
    links = []
    for key, label in items:
        current = ' aria-current="page" class="active"' if key == active else ""
        links.append(f'<a href="{esc(url(base, tab=key, **keep))}"{current}>{esc(label)}</a>')
    return f'<nav class="tabs" aria-label="Tabs">{"".join(links)}</nav>'


def chart(src, alt, cls=""):
    """A Matplotlib chart drawn by /chart/... as a PNG."""
    return f'<img class="chart {cls}" src="{esc(src)}" alt="{esc(alt)}">'


def bullets(lines):
    """Bullet list like widgets.bullet_list."""
    return "<ul class='bullets'>" + "".join(f"<li>{esc(line)}</li>" for line in lines) + "</ul>"


def field(name, label, value="", kind="text", options=None, hint=None, width=None, step=None, minimum=None,
          maximum=None, required=False):
    """One labelled input. kind: text, number, select, file, datalist."""
    style = f' class="w-{width}"' if width else ""
    req = " required" if required else ""
    if kind == "select":
        opts = "".join(f'<option value="{esc(v)}"{" selected" if str(v) == str(value) else ""}>{esc(t)}</option>'
                       for v, t in options)
        control = f'<select id="f-{name}" name="{name}"{style}>{opts}</select>'
    elif kind == "datalist":
        opts = "".join(f'<option value="{esc(v)}">' for v, _t in options)
        control = (f'<input id="f-{name}" name="{name}" value="{esc(value)}" list="dl-{name}"{style}{req}>'
                   f'<datalist id="dl-{name}">{opts}</datalist>')
    elif kind == "file":
        control = f'<input id="f-{name}" name="{name}" type="file" accept=".csv,text/csv"{req}>'
    else:
        extra = "".join(f' {k}="{v}"' for k, v in (("step", step), ("min", minimum), ("max", maximum)) if v is not None)
        control = f'<input id="f-{name}" name="{name}" type="{kind}" value="{esc(value)}"{extra}{style}{req}>'
    note = f'<small class="muted">{esc(hint)}</small>' if hint else ""
    return f'<label class="field" for="f-{name}"><span>{esc(label)}</span>{control}{note}</label>'


def form(action, body, method="post", cls="", multipart=False):
    """A form; POST forms come back to the page with a message (post/redirect/get)."""
    enctype = ' enctype="multipart/form-data"' if multipart else ""
    return f'<form class="{cls}" method="{method}" action="{esc(action)}"{enctype}>{body}</form>'


def button(text, primary=False, name=None, value=None, confirm=None):
    """A submit button styled like the desktop ttk buttons."""
    attrs = f' name="{name}" value="{esc(value)}"' if name else ""
    if confirm:
        attrs += f' data-confirm="{esc(confirm)}"'
    return f'<button type="submit" class="btn{" primary" if primary else ""}"{attrs}>{esc(text)}</button>'


def link_button(text, href, primary=False):
    """A link that looks like a button (downloads, navigation)."""
    return f'<a class="btn{" primary" if primary else ""}" href="{esc(href)}">{esc(text)}</a>'


def caps(text):
    """Small capitals heading inside a card."""
    return f'<h3 class="caps">{esc(text)}</h3>'
