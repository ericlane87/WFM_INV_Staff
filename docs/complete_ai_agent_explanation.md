# WorkforceIQ Complete AI Agent Explanation

This document is written for another AI agent that needs to understand the whole WorkforceIQ staffing and inventory dashboard: what files matter, how data moves through the system, every major calculation, how health is classified, how forecasting and scenarios work, what is real analytics versus directional intelligence, and where the current limitations are.

## Plain-English Purpose

WorkforceIQ turns a local staffing and inventory report into a standalone executive dashboard. It answers questions like:

- Are we healthy?
- Where should leadership look first?
- Is backlog growing or burning down?
- Are receipts and closures balanced?
- Do we have enough productive capacity?
- What is driving pressure?
- What happens if current trends continue?
- What would change if staffing, productivity, or incoming work changed?

The dashboard is intentionally local. It does not require a server, database, cloud service, API key, or trained machine learning model. The Python script generates a browser-readable JavaScript data file, and `dashboard.html` renders the dashboard directly from that generated payload.

## Main Files

- `update_dashboard.py`: the complete ingestion, normalization, feature engineering, health classification, forecasting, analytics, and data-quality pipeline.
- `dashboard.html`: the standalone dashboard UI. It loads `data/dashboard-data.js`, keeps filter state in the browser, renders KPI cards/tabs/modals/scenario controls, and performs temporary scenario math.
- `data/dashboard-data.js`: generated output from Python. It defines `window.DASHBOARD_DATA = {...}`. Do not edit it by hand.
- `data/source-records.json`: persistent normalized source record store. It lets the updater keep old periods and add only new periods from future report files.
- `Sample Report.txt`: fallback source report used when no input file is supplied and no supported files exist in `input/`.
- `run_dashboard_update.bat`: Windows convenience runner.
- `README.md`: short run instructions.
- `docs/dashboard_agent_handoff.md`: shorter summary handoff.

The project folder name currently appears as `Saffing and Inventoryy `, including a trailing space in the path. Be careful when scripting paths.

## How To Run

Default:

```bash
python3 update_dashboard.py
```

With an explicit report:

```bash
python3 update_dashboard.py "Your Report.xlsx"
python3 update_dashboard.py "Your Report.xlsx" --sheet "Sheet1"
python3 update_dashboard.py "Your Report.csv"
python3 update_dashboard.py "Your Report.txt"
```

Then open:

```text
dashboard.html
```

No dev server is required.

## Source Input Rules

The source report is a wide, human-formatted staffing/inventory export. It is not already normalized. The parser expects repeated metric blocks across business-unit/work-category rows and month columns.

Supported file types:

- `.txt`
- `.csv`
- `.xlsx`
- `.xlsm`

Default source behavior:

- If `input/` exists and has supported files directly inside it, those files are read.
- If `input/` contains year-named subfolders like `2026`, supported files inside those year folders are also read.
- If no input files are found, `Sample Report.txt` is used.
- If a source file path is passed on the command line, only that file is used.

Excel behavior:

- The script uses `openpyxl`.
- It reads formulas as values with `data_only=True`.
- If `--sheet` is supplied, that worksheet is required.
- If `--sheet` is omitted, the active worksheet is used.

CSV behavior:

- The script uses Python's `csv.reader`.
- UTF-8 with BOM is supported.

Text behavior:

- The script splits lines by tabs.
- UTF-8 with BOM is supported.

## Recognized Metrics

The parser only treats these exact labels as metric block starts:

- `Monthly Starting SLA %`
- `Starting Inventory`
- `In Standard`
- `Out of Standard`
- `Monthly Receipts`
- `Monthly Closures`
- `Monthly Receipt/Closure Variance`
- `Monthly Reroutes`
- `Average Daily Receipts`
- `Average Daily Production`
- `FTE's`
- `Hourly Goal`

If a report uses different labels, those sections will not parse unless `KNOWN_METRICS` and `metric_key()` are updated.

## Month Parsing

The source can contain multiple date header shapes:

- `Jan-26`
- `Jan`
- `26-Jan`
- `26-Jan-26`
- `2026-08-26`
- `08/26/2026`
- `08/26/26`

All are normalized to a sortable period key:

```text
YYYY-MM
```

Examples:

```text
Jan-26 -> 2026-01
Aug -> 2026-08
2026-08-26 -> 2026-08
```

Month labels without a year default to `2026`, unless the source file lives under a year-named path like `input/2027/...`; in that case the year is inferred from the folder path.

## Source Merge And Duplicate Period Logic

The updater is append-oriented by period.

1. It loads existing records from `data/source-records.json`.
2. It parses the current source file(s).
3. It finds periods already accepted from the stored records.
4. It adds only records from periods that are not already accepted.
5. It skips duplicate periods from later files.
6. It writes the merged result back to `data/source-records.json`.
7. It writes the full dashboard payload to `data/dashboard-data.js`.

This means rerunning the updater against the same report should not duplicate the same month. It also means that if a period needs to be corrected, the store may need to be intentionally reset or edited through a deliberate maintenance step.

## Normalized Record Grain

The first output layer is `records`, with this grain:

```text
businessUnit + workCategory + period + metric
```

Each normalized record contains:

- `businessUnit`
- `workCategory`
- `period`
- `monthLabel`
- `metric`
- `value`

The source report often shows a business unit once and leaves following rows blank until the next unit. The parser carries the last seen business unit forward inside each metric block. If the business unit is `Aggregated Total`, the work category is forced to `All Work Categories`.

## Feature Row Grain

The second output layer is `features`, with this grain:

```text
businessUnit + workCategory + period
```

The feature layer pivots normalized metric rows into one operational row per business unit, work category, and period. Source metric names are converted into JavaScript-friendly field names:

```text
Monthly Starting SLA %              -> monthlyStartingSla
Starting Inventory                  -> startingInventory
In Standard                         -> inStandard
Out of Standard                     -> outOfStandard
Monthly Receipts                    -> monthlyReceipts
Monthly Closures                    -> monthlyClosures
Monthly Receipt/Closure Variance    -> receiptClosureVariance
Monthly Reroutes                    -> monthlyReroutes
Average Daily Receipts              -> averageDailyReceipts
Average Daily Production            -> averageDailyProduction
FTE's                               -> ftes
Hourly Goal                         -> hourlyGoal
```

## Core Calculations

All divisions are safe divisions: if the numerator is missing, or the denominator is missing or zero, the output is `null`.

```text
outOfStandardRate = outOfStandard / startingInventory
calculatedSla = inStandard / startingInventory
receiptClosureGap = monthlyReceipts - monthlyClosures
throughputBalance = monthlyClosures - monthlyReceipts
closuresPerFte = monthlyClosures / ftes
receiptsPerFte = monthlyReceipts / ftes
dailyProductionPerFte = averageDailyProduction / ftes
dailyReceiptsPerFte = averageDailyReceipts / ftes
productionToReceiptsRatio = averageDailyProduction / averageDailyReceipts
goalAttainmentProxy = dailyProductionPerFte / hourlyGoal
```

Two flow signs matter:

- `receiptClosureGap` is receipts minus closures. Positive means incoming work exceeded closures. This is internally useful for risk logic.
- `throughputBalance` is closures minus receipts. Positive means closures exceeded incoming work. This is used in the UI because positive is healthy.

## Inventory Pressure Score

Inventory pressure combines out-of-standard rate, backlog/flow pressure, and SLA pressure.

```text
outRate = outOfStandard / startingInventory
gapPressure = max(0, receiptClosureGap / startingInventory)
slaPressure = max(0, 0.95 - monthlyStartingSla)

inventoryPressureScore =
  outRate * 0.55
  + gapPressure * 0.30
  + slaPressure * 0.80
```

The result is clamped from `0` to `1`.

Important interpretation:

- Higher means inventory/SLA conditions are more pressured.
- It is a rule-based pressure proxy.
- It is not a trained model score.

## Staffing Pressure Score

Staffing pressure combines production falling behind receipts, unfavorable receipt/closure gap, and goal attainment pressure.

```text
productionGap = max(0, 1 - productionToReceiptsRatio)
backlogGap = max(0, receiptClosureGap / startingInventory)
goalGap = max(0, 1 - goalAttainmentProxy)

staffingPressureScore =
  productionGap * 0.45
  + backlogGap * 0.35
  + goalGap * 0.20
```

The result is clamped from `0` to `1`.

## Change Features

For each `businessUnit + workCategory`, rows are sorted by period. The script calculates one-period differences:

```text
outOfStandardChange = current outOfStandard - prior outOfStandard
slaChange = current monthlyStartingSla - prior monthlyStartingSla
fteChange = current ftes - prior ftes
closureGapChange = current receiptClosureGap - prior receiptClosureGap
```

If prior data is missing, the change is `null`.

## Lag, Rolling, And History Features

For each `businessUnit + workCategory`, the system creates lag fields for these source fields:

- receipts
- closures
- FTE
- SLA
- out-of-standard
- production
- receipt/closure gap
- inventory

For lags:

```text
receiptsLag1, receiptsLag2, receiptsLag3
closuresLag1, closuresLag2, closuresLag3
...
```

Percent changes:

```text
fieldPctChange = (current - lag1) / abs(lag1)
```

Three-period change:

```text
fieldChange3Period = current - lag3
```

Rolling features use prior history only, not the current row:

```text
fieldRolling3Avg = average of previous 3 available values
fieldRolling6Avg = average of previous 6 available values
fieldRolling3Std = sample standard deviation of previous 3 available values
fieldVsRolling3Pct = (current - rolling3Avg) / abs(rolling3Avg)
```

The standard deviation function uses sample standard deviation:

```text
sqrt(sum((value - average)^2) / (n - 1))
```

## Streak Features

The feature layer also calculates consecutive streaks:

```text
consecutiveReceiptIncreasePeriods
consecutiveClosureDeclinePeriods
consecutiveSlaDeclinePeriods
consecutivePositiveGapPeriods
consecutiveOosIncreasePeriods
consecutiveProductionBelowReceiptsPeriods
```

Increase/decline streaks compare current to prior period and walk backward until the pattern breaks.

Threshold streaks count current and prior periods while a value stays above or below a threshold. For example:

```text
consecutivePositiveGapPeriods = count of consecutive periods where receiptClosureGap > 0
consecutiveProductionBelowReceiptsPeriods = count of consecutive periods where productionToReceiptsRatio < 1
```

## Capacity Calculations

Work-category feature rows include a capacity estimate:

```text
requiredFte = monthlyReceipts / closuresPerFte
estimatedCapacityGap = requiredFte - ftes
capacityGapMagnitude = abs(estimatedCapacityGap)
```

Status:

```text
if estimatedCapacityGap is null -> UNKNOWN
if estimatedCapacityGap > 0.25 -> SHORTFALL
if estimatedCapacityGap < -0.25 -> SURPLUS
otherwise -> SUFFICIENT
```

Interpretation:

- Positive gap means estimated productive capacity shortfall.
- Negative gap means estimated productive capacity surplus.
- Near zero means sufficient.

There is also a department-level capacity layer, `analytics.departmentCapacity`, built by summing all non-total work categories for each business unit and period. That layer contains:

- `fte`
- `receipts`
- `closures`
- `dailyReceipts`
- `dailyProduction`
- `productionToReceiptsRatio`
- `closuresPerFte`
- `requiredFteToKeepPace`
- `capacityGap`
- `capacityGapMagnitude`
- `capacityStatus`
- `throughputBalance`
- `primaryWorkloadPressure`
- `primaryWorkloadPressureStatus`

Important limitation: the UI treats FTE scenario work as department-level. It does not claim precise work-category staffing allocation unless the source truly supports that grain.

## Capacity Utilization Proxy

```text
capacityUtilizationProxy = monthlyReceipts / monthlyClosures
```

Higher than `1` means receipts are higher than closures. Lower than `1` means closures are higher than receipts.

## Health Status Classification

The target SLA is:

```text
SLA_TARGET = 0.90
```

Status values:

- `NO_DATA`
- `MEETING_TARGET`
- `WATCH`
- `AT_RISK`
- `CRITICAL`

Rules:

```text
sla = monthlyStartingSla, falling back to calculatedSla

if sla is missing:
  NO_DATA

if sla < 0.80:
  CRITICAL

if sla < 0.90 and inventoryPressureScore >= 0.30:
  CRITICAL

if sla < 0.90:
  AT_RISK

if earlyWarning is active or inventoryPressureScore >= 0.18:
  WATCH

otherwise:
  MEETING_TARGET
```

Status reasons are collected along the way. Reasons may include:

- SLA below target.
- SLA declined for multiple consecutive periods.
- Receipts exceeded closures for multiple periods.
- Out-of-standard inventory increased.

## Early Warning Logic

Early warning only evaluates when current SLA is at or above target. It looks for pressure before the SLA breaks.

Evidence items may include:

- Receipts increased for at least two consecutive periods.
- Closures declined for at least two consecutive periods.
- Receipt/closure gap was positive for at least two periods.
- Production is below receipts.
- Out-of-standard inventory increased.
- Workload is growing faster than FTE.

If at least two evidence items are present:

```text
earlyWarning.active = true
earlyWarning.type = EMERGING_CAPACITY_PRESSURE
earlyWarning.label = Early Warning
```

Confidence:

- `LIMITED_DATA` when fewer than six prior periods exist.
- `MODERATE` otherwise.

## Pressure Type Classification

Each feature row can receive pressure type labels:

- `DEMAND_PRESSURE`: receipts grew at least 10% or receipts increased for at least two periods.
- `CAPACITY_PRESSURE`: workload growth exceeds FTE growth by at least 10 percentage points, or estimated capacity gap is above `0.5`.
- `PRODUCTIVITY_PRESSURE`: production declined by at least 8%, or goal attainment proxy is below `0.90`.
- `FLOW_IMBALANCE`: receipt/closure gap is positive, or it has been positive for at least two periods.
- `INVENTORY_PRESSURE`: out-of-standard inventory increased, or out-of-standard rate is at least `0.15`.
- `SLA_PRESSURE`: SLA is below target, or SLA declined for at least two periods.
- `REROUTE_PRESSURE`: reroutes are non-zero and at least 25% of the absolute receipt/closure gap.
- `MULTI_FACTOR_PRESSURE`: inserted at the front when at least three pressure types are present.

Only the first five labels are kept.

## Risk Score

Risk score is a rule-based combined risk measure clamped from `0` to `1`.

```text
slaGap = max(0, 0.90 - sla)

riskScore =
  slaGap * 1.4
  + inventoryPressureScore * 0.9
  + staffingPressureScore * 0.7
  + min(0.25, consecutivePositiveGapPeriods * 0.06)
  + min(0.20, consecutiveOosIncreasePeriods * 0.05)

if earlyWarning.active:
  riskScore += 0.12
```

Interpretation:

- Higher score means the row should be ranked higher for leadership attention.
- This is not a probability.
- This is not a model prediction.
- It is a transparent weighted operational score.

## Anomaly Signals

For each row, the system checks these metrics:

- monthly receipts
- monthly closures
- out-of-standard inventory
- FTE
- monthly starting SLA

For each metric, it compares the current value to the rolling three-period average and rolling three-period standard deviation:

```text
zScore = (current - rolling3Avg) / rolling3Std
```

If:

```text
abs(zScore) >= 2
```

an anomaly signal is emitted with:

- metric
- label
- direction: above normal or below normal
- strength
- summary

Because current history is limited, these are contextual signals, not robust statistical anomaly detection.

## Confidence Labels

For feature rows:

```text
if limitedHistory:
  LIMITED_DATA
elif anomalySignals exist:
  MODERATE
else:
  DIRECTIONAL
```

`limitedHistory` is true when fewer than six prior periods exist for the row's business-unit/work-category context.

## Aggregations

`summary` is an aggregate for the latest available period. It excludes `Aggregated Total` rows and sums fields such as inventory, in-standard, out-of-standard, FTE, receipts, closures, and receipt/closure gap. SLA is recalculated as:

```text
sum(inStandard) / sum(startingInventory)
```

`operationalSummary` is the same style of aggregate for `latestFullContextPeriod`, because the latest source period may have inventory/SLA but lack staffing and flow fields.

`aggregate_for_period()` can also aggregate a period with optional business-unit and work-category filters.

## Period Completeness

The dashboard distinguishes:

- `latestPeriod`: latest source period with any data.
- `latestFullContextPeriod`: latest period that has receipts, closures, and FTE.

Period completeness checks these operational fields:

- `monthlyReceipts`
- `monthlyClosures`
- `ftes`
- `averageDailyReceipts`
- `averageDailyProduction`

If any selected period rows are missing these, the period is marked partial.

Current generated data has:

- latest available source period: `2026-09`
- latest full operational period: `2026-08`

That is why the default dashboard view uses August for operational context even though September exists.

## Generated Payload Shape

`window.DASHBOARD_DATA` contains:

- `metadata`
- `records`
- `features`
- `summary`
- `operationalSummary`
- `analytics`

`metadata` contains:

- refresh timestamp
- source file(s)
- source store path
- merge stats
- record counts
- feature row count
- latest periods
- period completeness
- business units
- work categories
- metric names
- SLA target

`analytics` contains:

- `contexts`
- `heatmap`
- `enterprisePulse`
- `biggestMovers`
- `insights`
- `forecasts`
- `forecastEngine`
- `departmentCapacity`
- `correlationExplorer`
- `meetingMode`
- `dataQuality`
- `modelDiagnostics`
- `modelContext`

## Context Objects

`analytics.contexts` is the detail/intelligence layer for each non-total feature row. Each context includes:

- `id`: `businessUnit::workCategory`
- business unit
- work category
- period
- status
- risk score
- pressure types
- early warning object
- confidence
- `brief`
- `driverBars`
- compact metrics
- `whatWouldItTake`
- `ifNothingChanges`

The brief explains:

- what changed
- why it matters
- staffing interpretation
- early warning
- outlook
- evidence

## Driver Bars

Driver bars are rule-based explanatory signals. They are not learned model feature importance.

Raw drivers:

```text
Receipt Growth = abs(receiptsPctChange)
Closure Decline = abs(min(0, closuresPctChange))
Workload Pressure = max(0, receiptClosureGap) / startingInventory
OOS Movement = abs(outOfStandardChange) / startingInventory
Flow Gap = max(0, receiptClosureGap) / startingInventory
Reroutes = abs(monthlyReroutes) / startingInventory
```

Then the dashboard normalizes each raw value against the largest raw driver in that same context:

```text
displayed strength = raw driver / max raw driver
```

Only drivers with positive raw values are shown, up to five.

## What Would It Take

This estimates what it would take to reach 90% SLA:

```text
targetOos = startingInventory * (1 - 0.90)
oosReductionNeeded = max(0, outOfStandard - targetOos)
estimatedFteEquivalent = oosReductionNeeded / closuresPerFte
estimatedProductivityLift = oosReductionNeeded / monthlyClosures
```

This is directional. It assumes current closures per FTE and does not prove causality.

## If Current Trends Continue

The context object still uses the key `ifNothingChanges`, but the UI language says "If current trends continue."

Calculation:

```text
projectedOos = max(0, current outOfStandard + outOfStandardChange)
projectedInventory = max(0, current inventory + inventoryPctChange * current inventory)
projectedSla = 1 - projectedOos / projectedInventory
```

It is a simple continuation of recent movement.

## Insights

`analytics.insights` uses the latest full operational period, excludes `Aggregated Total`, sorts rows by `riskScore`, and returns the top ten operational pressure insights.

Each insight includes:

- priority/status
- business unit
- work category
- period
- title
- summary
- drivers
- confidence
- pressure types
- early warning
- key metrics

Driver text may include:

- SLA level
- out-of-standard increase
- receipts exceeding closures
- reroutes
- production below receipts

## Heatmap

`analytics.heatmap` is built for the latest full operational period. It gives one row per non-total business-unit/work-category with:

- id
- business unit
- work category
- status
- risk score
- SLA
- out-of-standard
- pressure types
- early warning boolean

It is sorted by business unit and work category.

## Biggest Movers

`analytics.biggestMovers` is built from the latest full operational period. It identifies one strongest row for each mover type:

- SLA Deterioration
- SLA Improvement
- Inventory Increase
- Inventory Reduction
- Receipt Surge
- Closure Drop
- OOS Increase
- FTE Movement

Each mover includes:

- title
- metric
- business unit
- work category
- period
- value
- display string
- unusual flag
- context
- status

`isUnusual` is true when the selected row has anomaly signals. Otherwise the context says it is a big movement with limited history.

## Enterprise Pulse

`analytics.enterprisePulse` creates leadership Q&A style answers for the latest full operational period:

- Where should I look first?
- What deteriorated most?
- Are receipts and closures balanced?
- Where is staffing capacity tight?
- What improved?

Each answer points to a business-unit/work-category row, metric, value, status, and evidence.

## Correlation Explorer

`analytics.correlationExplorer` scans simple Pearson correlations across non-total feature rows.

Pairs:

- FTE vs SLA
- FTE vs Closures
- Receipts vs Inventory
- Receipts vs OOS
- Closures vs SLA
- Gap vs SLA
- Inventory Pressure vs SLA

Formula:

```text
correlation = covariance(x, y) / (stddev(x) * stddev(y))
```

The implementation requires at least three paired observations and non-zero variance. Interpretation labels:

- strong if absolute correlation is at least `0.65`
- moderate if absolute correlation is at least `0.35`
- weak otherwise

Every interpretation explicitly treats correlation as non-causal, especially with limited history.

## Meeting Mode

`analytics.meetingMode` prepares a concise executive briefing for the latest full operational period:

- current state aggregate
- top OOS increase
- top SLA improvement
- top SLA deterioration
- top early warning
- top capacity concern
- outlook/highest risk context

The dashboard has a Presentation Mode button that changes the UI display mode, not the data.

## Forecasts: Legacy Simple Forecast

`analytics.forecasts` is an older simple forecast layer.

For each non-total business-unit/work-category with at least two periods:

```text
inventorySlope = latest startingInventory - prior startingInventory
outSlope = latest outOfStandard - prior outOfStandard
slaSlope = latest SLA - prior SLA

next startingInventory = max(0, latest startingInventory + inventorySlope)
next outOfStandard = max(0, latest outOfStandard + outSlope)
next sla = clamp(latest SLA + slaSlope)
```

Method label:

```text
last-period trend
```

The dashboard's more important forecast system is `analytics.forecastEngine`.

## Forecast Engine

`analytics.forecastEngine` is the newer adaptive directional forecast layer. It generates a forecast context for every business-unit/work-category and for every possible base point in the available history.

High-level payload:

- `method`: `adaptive_directional_operational_forecast`
- `horizonPeriods`: currently `3`
- `historyAvailable`
- `maturity`
- `contexts`
- `notes`

Forecast maturity labels:

```text
if historyPeriods >= 18 -> ADVANCED_HISTORY_READY
if historyPeriods >= 12 -> SEASONAL_HISTORY_READY
if historyPeriods >= 8  -> TREND_HISTORY_READY
else                    -> LIMITED_HISTORY_DIRECTIONAL
```

## Forecast Context Selection

In the UI, forecast scenarios require a specific business unit and work category. If filters are `All`, the Forecast tab asks the user to select one department and one work bucket.

When selected, the UI chooses a forecast context in this order:

1. Same business unit, work category, and selected `basePeriod`.
2. Same business unit, work category, with selected `operationalBasePeriod`.
3. Latest forecast context for that business unit/work category.
4. Any context matching selected business unit.
5. First forecast context.

## Forecast Base Values

For a forecast context:

- `latest` is the latest row in the selected history.
- `latestOperational` is the latest row in the history with receipts and closures.
- Inventory, out-of-standard, and SLA use the latest row.
- Receipts, closures, FTE, and throughput use the latest operational row when the latest period is partial.

This is how the system can use September inventory/SLA while still falling back to August operational values when September lacks receipts/closures/FTE.

## Forecast Slopes

For each forecast field, the system uses an adaptive slope:

```text
values = all non-null historical values for the field
if fewer than 2 values:
  slope = 0
else:
  recent = last 4 values if available, otherwise all values
  slope = average pairwise difference across recent values
```

Fields with slopes:

- monthly receipts
- monthly closures
- out-of-standard
- FTE

## Forecast Projection Math

Each forecast starts with a current row:

```text
horizon = 0
period = latest period
receipts = latest operational receipts
closures = latest operational closures
inventory = latest inventory
outOfStandard = latest outOfStandard
sla = latest SLA
fte = latest operational FTE
throughputBalance = latest operational throughputBalance
```

Then for each future month:

```text
receipts = max(0, base receipts + receiptSlope * step)
closures = max(0, base closures + closureSlope * step)
throughputBalance = closures - receipts
inventory = max(0, prior projected inventory - throughputBalance)
outOfStandard = max(0, prior outOfStandard + oosSlope)
fte = max(0, base fte + fteSlope * step)
sla = 1 - outOfStandard / inventory
```

Because `throughputBalance = closures - receipts`, inventory roll-forward can also be read as:

```text
inventory = prior inventory + receipts - closures
```

Forecast capacity status:

```text
if throughputBalance < 0 -> SHORTFALL
else -> SUFFICIENT
```

## Forecast Confidence

Forecast confidence considers:

- number of history periods
- missing recent fields
- recent SLA volatility

Score:

```text
score =
  0.35
  + min(0.35, historyPeriods * 0.025)
  - missingPenalty * 0.04
  - volatility * 0.25

score is clamped from 0 to 1
```

Missing penalty:

- For each of these fields, if any of the last three rows are missing it, add `1`:
  - monthly receipts
  - monthly closures
  - starting inventory
  - out-of-standard
  - monthly starting SLA
  - FTE

Volatility:

```text
values = last 6 non-null SLA values
if fewer than 3 values:
  volatility = 0.25
else:
  volatility = stddev(values) / max(0.01, abs(mean(values)))
```

Labels:

```text
score >= 0.68 -> High
score >= 0.48 -> Medium
else          -> Low
```

Confidence declines by forecast horizon:

```text
horizonScore = baseConfidenceScore - step * 0.06
```

The expected SLA range is directional:

```text
width = (0.025 + step * 0.015) * (1.4 - confidenceScore)
low = sla - width
high = sla + width
```

Both low and high are clamped from `0` to `1`.

## Forecast Drivers

Forecast driver text can include:

- receipts trending by at least 5%
- production trending by at least 5%
- FTE change
- OOS inventory increase
- closures exceeding receipts
- receipts exceeding closures
- enough history exists to begin seasonality checks

If none are detected:

```text
limited movement detected in recent source data
```

## Forecast Crossover And Clearance

Crossover period:

```text
first future period where throughputBalance > 0
```

That means closures exceed receipts.

Operational backlog target:

```text
target = max(startingInventory * 0.10, outOfStandard)
```

Clearance period:

```text
first future period where projected inventory <= operationalBacklogTarget
```

In the UI, the user can also enter a custom backlog target. The custom target is temporary and recalculated in the browser.

## Browser Scenario Controls

The Forecast tab has temporary controls:

- Staffing/FTE stepper and number input.
- Workload receipt scenario: `-10%`, current, `+10%`.
- Productivity/closure scenario: `-5%`, current, `+5%`.
- Backlog target input.
- Reset to baseline forecast.

These do not modify source data, `source-records.json`, or `dashboard-data.js`.

Scenario math happens in `dashboard.html` inside `scenarioProjection()`.

For future rows only:

```text
receipts = baseline receipts * (1 + receiptChange)
closures = baseline closures * (1 + productivityChange) + fteChange * closuresPerFte
throughputBalance = closures - receipts
inventory = prior scenario inventory + receipts - closures
outRate = current outOfStandard / current inventory
outOfStandard =
  baseline outOfStandard
  + max(0, -throughputBalance) * outRate
  - max(0, throughputBalance) * 0.15
sla = 1 - outOfStandard / inventory
```

Interpretation:

- More FTE increases projected closures using observed department closures per FTE.
- Receipt scenario changes incoming workload.
- Productivity scenario changes closures.
- If throughput is unfavorable, OOS increases proportionally to the current OOS rate.
- If throughput is favorable, OOS is reduced by 15% of positive throughput.
- This is an approximate operational what-if, not a staffing optimization model.

## Dashboard UI State

The browser keeps a `state` object:

```text
view
tab
businessUnit
workCategory
period
forecastKey
```

Default state:

```text
view = pulse
tab = pulse
businessUnit = All
workCategory = All
period = latestFullContextPeriod or latestPeriod
```

Filter selections update state and rerender the dashboard.

## Dashboard Filters

Left command center filters:

- Dashboard View
- Business Unit
- Work Category
- Period

Business units and work categories come from generated metadata.

Rows shown in most views exclude `Aggregated Total` and then apply current filters:

```text
row.period == selected period
row.businessUnit != Aggregated Total
business unit matches unless All
work category matches unless All
```

## KPI Cards

There are five executive KPI cards.

### Capacity

Uses department capacity summary for the selected context.

If shortfalls exist:

```text
total shortfall FTE
number of areas needing capacity
```

If no shortfalls and surplus exists:

```text
Sufficient
FTE-equivalent surplus
```

Otherwise:

```text
Sufficient
No current shortfalls
```

Clicking navigates to Staffing.

### SLA Health

Uses aggregate selected-context SLA:

```text
sum(inStandard) / sum(startingInventory)
```

It compares against the 90% SLA target and shows average SLA trend if row-level `slaChange` values exist.

Clicking navigates to Detail.

### Backlog

Uses:

```text
throughput = -aggregate(receiptClosureGap)
```

That equals closures minus receipts.

Display:

- positive: burning down
- negative: growing

Clicking navigates to Flow.

### Operational Health

Counts rows with statuses:

- `CRITICAL`
- `AT_RISK`
- `WATCH`

If none exist, it says:

```text
All Areas Healthy
```

Clicking navigates to Pulse.

### Outlook

Uses selected forecast context. It compares next projected SLA to current projected SLA:

```text
outlookDelta = next.sla - current.sla
```

Labels:

- `Improving` if delta is greater than `0.005`
- `Deteriorating` if delta is less than `-0.005`
- `Stable` otherwise
- `Directional` when no comparison is possible

Clicking navigates to Forecast.

## Pulse Tab

Purpose: leadership triage.

Shows:

- selected SLA
- selected inventory
- count of attention areas
- attention required or all healthy list
- enterprise health by business unit

Attention rows are `CRITICAL`, `AT_RISK`, or `WATCH`, sorted by risk score. If no rows are flagged, it still shows the current rows sorted by risk score, but labels the section healthy.

Clicking a row opens a detail modal.

## Flow Tab

Purpose: explain receipts, closures, throughput, and inventory pressure.

Main calculation:

```text
throughputBalance = closures - receipts
```

Positive is favorable. Negative is unfavorable.

The burn-down runway uses the current selected aggregate inventory and assumes current throughput repeats:

```text
futureInventory = currentInventory - throughput * monthIndex
```

If throughput is positive, the UI estimates months to:

```text
10% inventory reduction target = inventory * 0.90
25% inventory reduction target = inventory * 0.75
```

If throughput is zero or negative, reduction targets are marked not possible at current rate.

## Staffing Tab

Purpose: explain department capacity and work-category pressure.

Uses `analytics.departmentCapacity`, not only the selected feature row.

It shows a callout:

- capacity cannot be calculated if receipts, closures, or FTE are missing
- FTE-equivalent shortfall if capacity gap is above `0.25`
- FTE-equivalent surplus if capacity gap is below `-0.25`
- no current shortfall if within the threshold

It also shows:

- department FTE
- daily receipts
- daily production
- production/receipts ratio
- workload pressure areas sorted by risk

Production meaning:

```text
if productionToReceiptsRatio >= 1:
  Capacity Ahead: production is approximately X% above incoming volume
else:
  Capacity Behind: production is approximately X% below incoming volume
```

## Forecast Tab

Purpose: show projected receipts, closures, inventory, OOS, SLA, crossover, backlog target timing, and scenario effects.

Requirements:

- A specific business unit must be selected.
- A specific work category must be selected.

Displays:

- forecast callout with outlook label and confidence rationale
- scenario controls
- interactive line chart for receipts, closures, inventory, and optional target
- crossover tile
- backlog goal tile
- expected SLA tile
- forecast table
- backlog/burn-down outlook
- burn-down math explanation
- primary drivers

Clicking forecast rows or tiles opens a forecast explanation modal with formulas:

```text
Projected balance = closures - receipts
Inventory roll-forward = prior inventory + receipts - closures
Expected SLA = 1 - out of standard / inventory
```

## Intelligence Tab

Purpose: explain why something is happening.

Shows:

- active early warnings
- likely drivers for the selected context

Clicking a driver opens an explanation modal that gives:

- definition
- formula
- raw value
- displayed normalized score
- source inputs
- caveat that it is formula-based, not causal proof

## Detail Tab

Purpose: row-level table and modal drill-down.

Columns:

- BU
- Category
- Status
- Source SLA
- Calculated SLA
- Inventory
- OOS
- Receipts
- Closures
- Balance
- FTE

Clicking a row opens an operational snapshot and intelligence brief.

## Intelligence Rail

The right rail changes with filters and selected context. It shows:

- Current State
- Why It Matters
- Primary Driver
- Early Warning
- Outlook
- Recommended Lever

Recommended lever logic:

- If department capacity status is `SHORTFALL`, mention estimated FTE-equivalent shortfall and warn that the selected work category is context, not a staffing allocation claim.
- Else if throughput balance is negative, recommend improving closures or reducing receipts enough to turn throughput positive.
- Else if department capacity status is `SURPLUS`, mention surplus productive capacity may support backlog reduction.
- Else say capacity appears sufficient from available department-level staffing data.

## Guide Modal

The "Guide Me" modal maps user questions to views:

- Are we healthy? -> Pulse
- Is backlog growing? -> Flow
- Do we have capacity? -> Staffing
- What happens next? -> Forecast
- Why is it happening? -> Intelligence
- Prepare for a meeting -> Pulse plus Presentation Mode

## Presentation Mode

Presentation Mode toggles a CSS class on `body` and changes the button text between:

- `Presentation Mode`
- `Exit Presentation`

It does not modify data.

## Loading Behavior

If `data/dashboard-data.js` is missing, the dashboard displays a data-not-found loading/error screen and throws an error.

Normal initial navigation shows the loading screen briefly. A URL parameter can force loading preview mode:

```text
?loading-preview
```

The Refresh button rerenders from the already-loaded local data. It does not rerun Python.

## Data Quality Checks

Validation emits warnings for:

- unexpected business units
- unexpected work categories
- SLA outside 0% to 100%
- zero FTE with closures
- missing recognized metrics
- incomplete operational periods

Expected business units:

```text
CB
GB
CGS
Aggregated Total
```

Expected work categories:

```text
Validation/Adjustments
Disputes
Correspondence
Cash Posting
Host
All Work Categories
```

Warnings are included in:

```text
analytics.dataQuality.warnings
```

The UI shows them in Source Notes.

## Model Diagnostics

`analytics.modelDiagnostics` describes analytical maturity and what methods are enabled.

Current enabled methods:

- descriptive
- diagnostic
- rule-based early warning
- directional forecast
- correlation scan

Deferred methods:

- robust anomaly detection
- model backtesting
- learned driver importance
- seasonality
- change point detection

The current generated data has limited history, so diagnostics identify the system as phase 1 / limited history.

## Machine Learning Reality

This dashboard does not currently train or run a machine learning model.

It uses:

- deterministic parsing
- feature engineering
- weighted rule-based scoring
- simple trend continuation
- adaptive directional forecasting
- Pearson correlation scanning
- contextual z-score anomaly hints
- browser-side scenario simulation

Do not describe driver bars as learned feature importance. Do not describe risk score as probability. Do not describe forecasts as statistically validated predictions. The honest language is:

```text
rule-based operational intelligence
directional forecasting
limited-history signal detection
scenario planning
```

True ML would need more history and validation, especially:

- 12+ months for seasonality checks
- enough observations per business-unit/work-category
- backtesting
- forecast error measurement
- temporal validation
- change-point detection
- learned driver importance only after enough data exists

## Healthy Versus Unhealthy Language

Healthy means the selected context has no rows classified as `CRITICAL`, `AT_RISK`, or `WATCH`, and the selected aggregate SLA is meeting target with no active pressure flags.

Unhealthy/attention language comes from:

- status classification
- risk score ranking
- early warning activation
- negative throughput balance
- capacity shortfall
- below-target SLA
- rising out-of-standard inventory

The UI tries not to manufacture a problem. If all rows are healthy, it says so directly.

## Key Sign Conventions

This is one of the most important things for another agent to preserve:

```text
receiptClosureGap = receipts - closures
throughputBalance = closures - receipts
```

Use `receiptClosureGap` for internal pressure/risk logic where positive means pressure.

Use `throughputBalance` for executive UI language where positive means favorable.

## Current Data Snapshot

The generated payload currently shows:

- `recordCount`: 700
- `featureRows`: 70
- periods: `2026-01`, `2026-06`, `2026-07`, `2026-08`, `2026-09`
- latest source period: `2026-09`
- latest full operational period: `2026-08`
- September is partial because it lacks:
  - average daily production
  - average daily receipts
  - FTE
  - monthly closures
  - monthly receipts

Because September is partial, operational analytics default to August.

## Common Extension Points

To add a new source metric:

1. Add the exact source label to `KNOWN_METRICS`.
2. Add it to `metric_key()`.
3. Add derived calculations in `pivot_feature_rows()` if needed.
4. Add validation or UI fields if needed.

To add a new risk driver:

1. Add raw driver math in `driver_bars()`.
2. Add explanation text in `driverDefinition()` inside `dashboard.html`.
3. Decide whether it should affect `risk_score()` or only be explanatory.

To change health rules:

1. Update `classify_status()`.
2. Update status reasons if the user-facing language changes.
3. Check KPI health counts and Pulse behavior.

To change forecast behavior:

1. Update `build_context_forecast()` and helper functions in Python for baseline generated forecasts.
2. Update `scenarioProjection()` in `dashboard.html` if browser what-if behavior should match the new model.
3. Update forecast explanation modal formulas so users see the same math being used.

To support real ML:

1. Preserve the `features` layer as the training table.
2. Add a temporal train/test split.
3. Backtest forecasts by period.
4. Store model diagnostics and error metrics in `analytics.modelDiagnostics`.
5. Keep rule-based fallbacks for limited-history contexts.

## Do Not Break These Contracts

- `dashboard.html` expects `window.DASHBOARD_DATA`.
- `data/dashboard-data.js` must remain valid JavaScript, not raw JSON.
- `features` must contain `businessUnit`, `workCategory`, and `period`.
- Periods should remain sortable `YYYY-MM` strings.
- Positive `throughputBalance` must remain favorable.
- `Aggregated Total` rows should not be counted as regular BU rows in most analytics.
- Scenario controls are temporary and must not mutate source data.
- FTE recommendations should not overclaim work-category precision.
- Driver bars are explanatory formulas, not learned model importance.

## One-Sentence System Summary

WorkforceIQ is a local, file-based operational intelligence dashboard that parses wide staffing/inventory reports, normalizes them into monthly business-unit/work-category rows, calculates transparent health/capacity/flow/risk/forecast signals, and renders an executive UI for triage, explanation, and temporary scenario planning without claiming unsupported machine learning precision.
