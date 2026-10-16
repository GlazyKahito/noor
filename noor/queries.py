"""Readable SQL examples used by the Reports page and the viva demo.

Each query is a plain string you can copy into any SQLite tool. Run them in Python with
run_query(db, name, params). They show JOIN, GROUP BY, HAVING, sub-queries and ? parameters.
"""

QUERIES = {
    # JOIN + GROUP BY: one summary row per region.
    "region_summary": {
        "title": "Risk by region (latest assessment of each location)",
        "sql": """
SELECT r.name AS region,
       COUNT(l.id) AS locations,
       ROUND(AVG(a.score), 1) AS mean_score,
       MAX(a.score) AS max_score,
       SUM(CASE WHEN a.category IN ('High', 'Severe', 'Extreme') THEN 1 ELSE 0 END) AS high_or_above
FROM regions r
JOIN locations l ON l.region_id = r.id
JOIN risk_assessments a ON a.location_id = l.id
WHERE a.id IN (SELECT MAX(id) FROM risk_assessments GROUP BY location_id)
GROUP BY r.id
ORDER BY mean_score DESC""",
        "params": (),
    },
    # GROUP BY + HAVING: only locations with more than a given number of hot days.
    "hot_locations": {
        "title": "Locations with more than ? days at or above 40 °C",
        "sql": """
SELECT l.code, l.name, COUNT(*) AS hot_days, MAX(o.t_max) AS hottest
FROM observations o
JOIN locations l ON l.id = o.location_id
WHERE o.t_max >= 40 AND o.is_forecast = 0
GROUP BY l.id
HAVING COUNT(*) > ?
ORDER BY hot_days DESC""",
        "params": (10,),
    },
    # Three-table JOIN: resources with their location and the kind of data behind them.
    "resources_by_type": {
        "title": "Resource inventory by type and status",
        "sql": """
SELECT res.type, res.status, COUNT(*) AS resources, SUM(res.amount) AS total_amount, SUM(res.staff) AS staff
FROM resources res
JOIN locations l ON l.id = res.location_id
JOIN data_sources s ON s.id = res.source_id
GROUP BY res.type, res.status
ORDER BY res.type, res.status""",
        "params": (),
    },
    # Monthly averages with strftime (SQLite date function).
    "monthly_climate": {
        "title": "Monthly mean maximum temperature and humidity",
        "sql": """
SELECT strftime('%Y-%m', obs_date) AS month,
       ROUND(AVG(t_max), 1) AS mean_t_max,
       ROUND(AVG(humidity), 1) AS mean_humidity,
       COUNT(*) AS readings
FROM observations
WHERE is_forecast = 0
GROUP BY month
ORDER BY month""",
        "params": (),
    },
    # LEFT JOIN: alerts per location, including locations with none.
    "alerts_per_location": {
        "title": "Open alerts per location (including locations with none)",
        "sql": """
SELECT l.code, l.name,
       COUNT(a.id) AS open_alerts,
       SUM(CASE WHEN a.severity = 'emergency' THEN 1 ELSE 0 END) AS emergencies
FROM locations l
LEFT JOIN alerts a ON a.location_id = l.id AND a.status <> 'resolved'
GROUP BY l.id
ORDER BY open_alerts DESC, l.code""",
        "params": (),
    },
    # Data provenance: how many rows each source contributed and of what kind.
    "provenance": {
        "title": "Rows per data source and kind",
        "sql": """
SELECT s.name, s.kind, s.licence, COUNT(o.id) AS observations
FROM data_sources s
LEFT JOIN observations o ON o.source_id = s.id
GROUP BY s.id
ORDER BY observations DESC""",
        "params": (),
    },
    # Missing data: days without an observation between each location's first and last day.
    "missing_days": {
        "title": "Missing observation days per location",
        "sql": """
SELECT l.code, l.name,
       MIN(o.obs_date) AS first_day, MAX(o.obs_date) AS last_day, COUNT(*) AS days_present,
       CAST(julianday(MAX(o.obs_date)) - julianday(MIN(o.obs_date)) + 1 AS INTEGER) - COUNT(*) AS days_missing
FROM locations l
JOIN observations o ON o.location_id = l.id AND o.is_forecast = 0
GROUP BY l.id
HAVING days_missing > 0
ORDER BY days_missing DESC""",
        "params": (),
    },
}


def run_query(db, name, params=None):
    """Run one named query and return (title, rows). Unknown names raise KeyError."""
    query = QUERIES[name]
    return query["title"], db.fetch_all(query["sql"], params if params is not None else query["params"])
