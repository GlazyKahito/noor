# Methodology

Every number below is defined in `noor/settings.py`. The formula and category thresholds shown
on the Risk Assessment screen ("Method and what-if weights") are read from the same file, so
the app and the code cannot disagree.

None of the thresholds are official Indian warning criteria. The heat-index bands come from
the US National Weather Service (NWS) heat index chart; everything else is a NOOR default
chosen for the demonstration and meant to be replaced by people who know the local context.

---

## 1. Heat index — `noor/climate.py: heat_index()`

| | |
| --- | --- |
| Inputs | Daily maximum temperature (°C), daily mean relative humidity (%) |
| Formula | NWS heat index equation: Rothfusz regression in °F with the NWS low-humidity and high-humidity adjustments; the simple NWS formula when the result is below 80 °F |
| Output | Heat index (°C), rounded to 0.1 |
| Assumption | Daily mean humidity stands in for humidity at the hottest hour |
| Failure cases | Missing input → None. Humidity at the time of Tmax is usually lower than the daily mean, so the index can be **overstated** in humid places |
| Validation | Unit tests compare with NWS chart values (90 °F/50 % ≈ 95 °F; 100 °F/40 % ≈ 109 °F) |

## 2. Hazard indicators — `climate.py: hazard_inputs()`

Window: the 7 observed days ending on the as-of date plus 3 forecast days.

| Indicator | Definition |
| --- | --- |
| `peak_heat_index` | Highest daily heat index in the window |
| `peak_tmax` | Highest daily maximum temperature |
| `hot_days` | Longest run of consecutive days with Tmax ≥ 40 °C (a missing day breaks the run) |
| `warm_nights` | Number of nights with Tmin ≥ 28 °C |

If fewer than 3 of the 7 window days have a temperature, all four are None and the location
gets **no score** (“Insufficient data”) with low confidence. Missing days are listed, never filled.

Each region is assessed as of its own latest observed day. The dashboard shows how old that
day is compared with today.

## 3. Risk score — `noor/risk.py: RiskEngine`

### Step 1 — normalise each indicator (`normalise()`)

`n = (x − low) / (high − low)`, clipped to 0..1. The bounds are fixed in `settings.py` (not the
min/max of today's data) so a score means the same thing on every day.

| Dimension | Indicator | low | high | weight in dimension |
| --- | --- | --- | --- | --- |
| Hazard | peak heat index (°C) | 27 (NWS “caution”) | 52 (NWS “extreme danger”) | 0.40 |
| | peak Tmax (°C) | 35 | 47 | 0.25 |
| | consecutive hot days | 0 | 6 | 0.20 |
| | warm nights | 0 | 6 | 0.15 |
| Exposure | density (people/km²) | 1,000 | 40,000 | 0.6 |
| | population | 20,000 | 400,000 | 0.4 |
| Vulnerability | share aged 65+ | 0.03 | 0.15 | 0.25 |
| | share under 5 | 0.05 | 0.14 | 0.15 |
| | outdoor workers | 0.05 | 0.35 | 0.20 |
| | informal / heat-trapping housing | 0.00 | 0.60 | 0.25 |
| | low-income households | 0.05 | 0.50 | 0.15 |
| Capacity (higher = better) | cooling places per 1,000 | 0 | 5 | 0.35 |
| | water servings per 1,000 | 0 | 50 | 0.20 |
| | medical slots per 1,000 | 0 | 0.5 | 0.25 |
| | households with piped water | 0.30 | 1.00 | 0.20 |

The upper bounds of the per-1,000 capacity indicators equal the demand per 1,000 residents at
a score of 100 under the planning assumptions in section 5, so 1.0 means “enough for the worst case”.

### Step 2 — one value per dimension (`RiskEngine.dimension()`)

Weighted average of the indicators that exist: `np.average(values, weights=weights)` over the
present ones only. A missing indicator is **left out** and its weight shared by the others; it
is never counted as 0. `coverage` = share of the dimension's weight that was present.

### Step 3 — combine (`RiskEngine.assess()`)

```
score = 100 × (0.40 × hazard + 0.20 × exposure + 0.25 × vulnerability + 0.15 × (1 − capacity))
```

- The four dimensions stay separate until this line and are all stored and shown.
- If a whole dimension (exposure, vulnerability or capacity) has no data, it gets **0.5**
  (precautionary, mid-range) — never 0 — and the location is flagged “imputed”.
- If hazard < 0.2 (a cool week), the score is capped at 39.9 so vulnerability alone can never
  produce a “High” heat risk.
- Weights are configurable (`settings.RISK_WEIGHTS`, or the what-if weights preview on the Risk
  Assessment screen, which is not saved). They must be the four keys, each 0–1, summing to 1, with hazard > 0.

### Step 4 — category

Lower bound inclusive: Low 0–19.9 · Moderate 20–39.9 · High 40–59.9 · Severe 60–79.9 · Extreme 80–100.
No score → “Insufficient data”.

### Step 5 — confidence and explanation

- `completeness` = share of the 15 indicators that are present.
- `high` if completeness ≥ 0.85, data ≤ 2 days old and nothing imputed; `medium` if
  completeness ≥ 0.6 and data ≤ 7 days old; otherwise `low`. No score → `low`.
- `reasons()` lists the score, the three indicators pushing it up most
  (dimension weight × indicator weight share × normalised value, using 1 − value for capacity),
  any cap or imputation, the missing inputs and missing days.

### Input kinds

Every source row has a `kind`: `measured`, `model_derived`, `estimated` or `synthetic`. Locations,
observations and resources point at their source, so every screen and CSV can say what kind of
data it shows. The bundled data is all `synthetic`.

### Validation approach and limits

- Unit tests check normalisation boundaries, category boundaries, weight validation, the
  formula itself, missing-data handling, the low-hazard cap and the effect of capacity.
- There is **no validation against health outcomes**: no real outcome data was available, so
  NOOR reports no accuracy figure. Scores rank relative priority under stated assumptions.
- The weighted sum is compensatory: strong capacity can offset some hazard. The low-hazard cap
  limits the opposite case.

## 4. Early warnings — `noor/alerts.py`

One class per rule, each with a `check(context)` that returns an `Alert` or `None`.
`WarningEngine.run()` loops over every rule for every location. Generation is separate from
storage (`Database.save_alert`) and display (the Alerts screen, `noor/gui/alerts_view.py`).

| Rule class | Fires when | Severity |
| --- | --- | --- |
| `HeatIndexRule` | Heat index today or on a forecast day ≥ 32.2 / 39.4 / 51.7 °C (NWS “extreme caution” / “danger” / “extreme danger”) | advisory / warning / emergency |
| `HotSpellRule` | ≥ 3 / ≥ 5 consecutive days with Tmax ≥ 40 °C, still running or forecast | warning / emergency |
| `WarmNightsRule` | ≥ 2 consecutive nights with Tmin ≥ 28 °C, still running | advisory |
| `RiskCategoryRule` | Category Severe / Extreme | warning / emergency |
| `CoolingGapRule` | High-or-worse location gets < 50 % of its cooling demand | advisory |
| `StaleDataRule` | Latest observation > 3 days old, or none | info |

Each alert stores: rule, severity, message (with value and threshold), trigger value,
threshold, period, recommended preparedness actions, confidence note (including whether the
data is synthetic and the disclaimer), issue time, and status. The same rule does not fire
twice for the same location and period. Status only moves forward: active → acknowledged →
resolved (or active → resolved).

No SMS or e-mail is sent. The “notification preview” is a local simulation (`Alert.sms_preview`).

## 5. Resource allocation — `noor/allocation.py: AllocationPlanner`

### Capacity in people per day (polymorphism in `models.py`)

| Type | Stored amount | `capacity()` |
| --- | --- | --- |
| `CoolingCentre` | places/day | amount × status factor |
| `WaterPoint` | litres/day | amount ÷ 4 L per person × status factor |
| `MedicalUnit` | patients/day | amount × status factor |
| `ResponseTeam` | members | members × 6 visits × status factor |
| `OutreachTeam` | volunteers | volunteers × 40 contacts × status factor |

Status factor: available 1.0, limited 0.5, offline 0.

### Demand

`demand = population × rate × score / 100`, rates per type: cooling 0.005, water 0.05, medical
0.0005, response 0.0003, outreach 0.01 (planning assumptions). No score → 50 (precautionary).
No population → demand unknown; the location is listed, not dropped.

### Greedy loop

1. Sort locations: `risk_first` = score × population (default); `population_first` = population only.
2. For each location in order, for each resource type, take capacity from resources of that
   type whose service radius reaches it, nearest first, until demand is met or capacity runs out.

Outputs: demand, served, unmet and coverage per type and per location; utilisation per
resource; risk-weighted coverage (Σ score × served ÷ Σ score × demand); High-or-worse locations
with gaps; locations with unknown demand. Plans can be saved (`allocations` table) and the two
strategies compared.

**Trade-off and limits.** Greedy serves the top priority fully before the next one gets anything,
which favours the highest-risk wards but can leave a moderately-at-risk ward with nothing. It
is not an optimum and has not been validated against real operations; distances are on the
schematic grid.

## 6. Scenario Lab — `noor/scenario.py: Scenario`

| Parameter | Range | Effect |
| --- | --- | --- |
| `temperature_increase` | 0–6 °C | Added to every Tmax and Tmin (humidity held constant — a simplification) |
| `extra_hot_days` | 0–10 | Added to the current hot spell, if there is one |
| `new_cooling_centres` | 0–30 | Placed one at a time where score × unmet cooling demand is highest |
| `water_capacity_pct`, `medical_capacity_pct` | 25–300 % | Scale existing capacity |
| `budget_per_day`, `staff_available` | ₹0–5,000,000; 0–1000 | Limit how many centres are affordable (₹15,000 and 4 staff each) |

Then the same risk and allocation code runs on the changed inputs. Results: mean score, number
of High-or-worse locations, unmet demand, coverage and utilisation per type, before/after per
location, where centres were placed and what limited them, and locations still needing help.
It is a what-if under NOOR's assumptions, not a forecast.
