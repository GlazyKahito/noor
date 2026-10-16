# Deployment

## Live

- App: **https://noor-climate.vercel.app** (also https://noor-two-ruddy.vercel.app)
- Repository: https://github.com/GlazyKahito/noor
- Host: Vercel, team `krut1`, project `noor`, connected to the repository's `main` branch:
  every push to `main` deploys to production.

## How it runs on Vercel

```
request ─► vercel.json rewrite ─► api/index.py  (class handler(NoorHandler))
           /risk/SPR-01  →  /api/index?__path=risk/SPR-01
```

- `api/index.py` is a Vercel Python function. Vercel's runtime calls the class named `handler`,
  which subclasses `BaseHTTPRequestHandler` — the same `NoorHandler` the local server uses.
  `restore_path()` turns the rewritten URL back into the original one before routing.
- `requirements.txt` (numpy, pandas, matplotlib, seaborn) is installed at build time; the
  function bundle is about 75 MB. `.python-version` asks for Python 3.12.
- `vercel.json` gives the function 1024 MB memory and 30 s maximum duration, and includes the
  `noor/` package files (schema, CSS).
- `MPLCONFIGDIR=/tmp/matplotlib` because Matplotlib needs a writable cache folder.
- No environment variables or secrets are needed. If you add any later, set them in the Vercel
  project settings, never in the repository.

## What works differently from local mode

| | Local (`python run.py`) | Vercel |
| --- | --- | --- |
| Database file | `instance/noor.db`, permanent | `/tmp/noor.db`, rebuilt from the seed on every cold start |
| Writes (alerts acknowledged, resources edited, CSV imports, saved plans) | Kept | Kept only while that server instance stays warm; another instance may not see them; lost on the next cold start |
| Concurrency | `ThreadingHTTPServer`, threads share one file | One request per instance at a time; instances do not share `/tmp` |
| First request | Instant after start | A cold start seeds the database and imports NumPy/Pandas/Matplotlib (a few seconds) |

So the hosted site is a **demonstration**: it always shows the synthetic district, and anything
a visitor changes is temporary. For permanent shared data, run NOOR on a machine or VM with a
persistent disk (for example `python run.py --host 0.0.0.0 --port 3060` behind a reverse proxy
with HTTPS and a login), or move the database to a hosted relational database.

## Redeploying by hand

```bash
npx vercel link --yes --project noor --scope krut1     # once per checkout
npx vercel deploy --prod --yes --scope krut1
```

Pushing to `main` on GitHub does the same automatically.

## Checks after a deploy

```bash
curl https://noor-climate.vercel.app/api/health
curl -I https://noor-climate.vercel.app/dashboard
curl -o map.png https://noor-climate.vercel.app/chart/risk-map.png
```

The `*-krut1.vercel.app` deployment URLs are protected by Vercel login; use the public aliases above.

## Security notes for any public deployment

- There is no authentication. On the public demo this is acceptable because the data is
  synthetic and resets; do not load real or personal data into it.
- Security headers (CSP with no scripts, frame denial, nosniff) are sent by the app itself.
- Upload and request size limits are enforced in code (2 MB CSV, 2.5 MB request body).

## Last verification of the live site (2026-10-16)

Run headless against https://noor-climate.vercel.app after the Git-triggered deploy:

- 17/17 API checks passed: health (16 locations), status (`synthetic_only: true`), risk list,
  precautionary vulnerability for SPR-16, alerts, plan and strategy comparison (risk-weighted
  coverage 0.746 population-first vs 0.758 risk-first), scenario (+2 °C and 5 new centres: mean
  score 56.2 → 59.6, 5 centres placed), SQL query, 400 for invalid scenario and weights, 404 for
  an unknown location, POST alert run and what-if weights, CSV provenance header, PNG chart,
  cross-site form POST refused (403).
- 13 pages × 4 desktop windows (1280×800, 1366×768, 1440×900, 1920×1080): all HTTP 200, no
  horizontal overflow, all chart images valid, no console errors; 19 dashboard links all working.
- Landing intro: shown on first visit and gone after about 3.5 s, not repeated in the same visit,
  skippable with Enter and the Skip button, absent with reduced motion and with JavaScript off;
  Google Fonts load under the Content-Security-Policy; no console errors.
