# WorkforceIQ Dashboard Agent Handoff

This file describes the current WorkforceIQ dashboard after the enterprise intelligence / UX redesign pass.

## Project Purpose

WorkforceIQ is a local staffing, inventory, SLA, capacity, forecasting, and operational-intelligence dashboard. It is intended to help leadership answer:

- Are we healthy?
- Where are we falling behind?
- Why is it happening?
- Do we have enough capacity?
- What happens if current trends continue?
- What operational lever could improve the outcome?

The dashboard is static HTML. No web server is required.

## Main Files

- `update_dashboard.py`: source ingestion, normalization, calculations, analytics, forecasting payload, data-quality checks.
- `dashboard.html`: frontend UI, filters, executive cards, tabs, drill-downs, forecast scenario controls.
- `data/dashboard-data.js`: generated data payload consumed by `dashboard.html`.
- `Sample Report.txt`: current source report.

## Running The Job

Default source:

```bash
python3 update_dashboard.py
```

Excel source with the same wide report layout:

```bash
python3 update_dashboard.py "Report.xlsx"
python3 update_dashboard.py "Report.xlsx" --sheet "Sheet1"
```

CSV source:

```bash
python3 update_dashboard.py "Report.csv"
```

Then open `dashboard.html`.

## Source Grain

Preserved normalized grain:

```text
businessUnit + workCategory + period
```

Periods are converted from source labels such as `Jan-26` and `Sep-26` to sortable keys:

```text
2026-01
2026-09
```

The current sample has five monthly periods. The code is designed to use additional history dynamically if future files contain 12, 18, 24, or more months.

## Source Metrics

The parser detects known metric blocks:

- Monthly Starting SLA %
- Starting Inventory
- In Standard
- Out of Standard
- Monthly Receipts
- Monthly Closures
- Monthly Receipt/Closure Variance
- Monthly Reroutes
- Average Daily Receipts
- Average Daily Production
- FTE's
- Hourly Goal

## Generated Payload Shape

The generated `window.DASHBOARD_DATA` includes:

- `metadata`
- `records`
- `features`
- `summary`
- `operationalSummary`
- `analytics.contexts`
- `analytics.heatmap`
- `analytics.enterprisePulse`
- `analytics.biggestMovers`
- `analytics.insights`
- `analytics.forecasts`
- `analytics.forecastEngine`
- `analytics.correlationExplorer`
- `analytics.meetingMode`
- `analytics.dataQuality`
- `analytics.modelDiagnostics`
- `analytics.modelContext`

## Period Completeness

The dashboard distinguishes:

- `latestPeriod`: latest source period available.
- `latestFullContextPeriod`: latest period with operational/staffing context.

This matters because the sample has September inventory/SLA data but August is the latest fuller operational period.

`metadata.periodCompleteness` identifies partial periods and missing operational fields.

## Main Filters

The left Command Center has four filters:

- `Dashboard View`: Pulse, Flow, Staffing, Forecast, Intelligence, Detail.
- `Business Unit`: All or a specific BU.
- `Work Category`: All or a specific work category.
- `Period`: detected source period.

Filters propagate through KPI cards, tabs, detail modal, intelligence rail, and forecast context.

## Executive KPI Cards

The landing KPI row was redesigned into five interactive leadership cards.

### Capacity

Answers: Do we have enough productive capacity to keep up with incoming work?

Uses `estimatedCapacityGap` and `capacityStatus`.

Possible messages:

- `Sufficient`
- `2.4 FTE Shortfall`
- FTE equivalent surplus

Click navigates to Staffing.

### SLA Health

Shows selected-context SLA against the 90% target, plus subtle trend vs prior comparable period.

Uses source SLA where available and calculated SLA as supporting detail.

Click navigates to Detail.

### Backlog

Uses the user-facing `throughputBalance`:

```text
throughputBalance = closures - receipts
```

Positive is favorable. Negative means intake exceeded closures.

Examples:

- Down/burning down when balance is positive.
- Up/growing when balance is negative.

Click navigates to Flow.

### Operational Health

Counts state-aware issues. It does not force a fake “top focus” if everything is healthy.

If issues exist:

```text
3 Areas Need Attention
1 Critical • 2 At Risk • 0 Watch
```

If not:

```text
All Areas Healthy
```

Click navigates to Pulse.

### Outlook

Uses the new forecast engine. Labels include:

- Improving
- Stable
- Deteriorating
- Directional

Includes compact confidence label.

Click navigates to Forecast.

## Core Calculations

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

`receiptClosureGap` is preserved internally because existing risk logic uses receipts minus closures.

`throughputBalance` is used for presentation because positive is operationally favorable.

## Capacity Logic

Existing calculation:

```text
requiredFte = monthlyReceipts / closuresPerFte
estimatedCapacityGap = requiredFte - currentFte
```

Interpretation:

- Positive gap: staffing/productive-capacity shortfall.
- Negative gap: productive-capacity surplus.
- Near zero: sufficient.

New fields:

```text
capacityStatus = SHORTFALL | SUFFICIENT | SURPLUS | UNKNOWN
capacityGapMagnitude = abs(estimatedCapacityGap)
```

The UI never asks the user to interpret negative FTE.

## Production vs Receipts

The dashboard translates the ratio into plain English.

```text
productionToReceiptsRatio = averageDailyProduction / averageDailyReceipts
```

If ratio is `1.40`:

```text
Capacity Ahead: production is approximately 40% above incoming volume.
```

If ratio is `0.82`:

```text
Capacity Behind: production is approximately 18% below incoming volume.
```

## Pressure Scores

Inventory pressure:

```text
outRate = outOfStandard / startingInventory
gapPressure = max(0, receiptClosureGap / startingInventory)
slaPressure = max(0, 0.95 - monthlyStartingSla)

inventoryPressureScore =
  outRate * 0.55
  + gapPressure * 0.30
  + slaPressure * 0.80
```

Staffing pressure:

```text
productionGap = max(0, 1 - productionToReceiptsRatio)
backlogGap = max(0, receiptClosureGap / startingInventory)
goalGap = max(0, 1 - goalAttainmentProxy)

staffingPressureScore =
  productionGap * 0.45
  + backlogGap * 0.35
  + goalGap * 0.20
```

Both are clamped from 0 to 1.

## Risk Score

```text
slaGap = max(0, 0.90 - SLA)

riskScore =
  slaGap * 1.4
  + inventoryPressureScore * 0.9
  + staffingPressureScore * 0.7
  + min(0.25, consecutivePositiveGapPeriods * 0.06)
  + min(0.20, consecutiveOosIncreasePeriods * 0.05)
```

If early warning is active, add `0.12`.

Final score is clamped from 0 to 1.

## Status Classification

Statuses:

- NO_DATA
- MEETING_TARGET
- WATCH
- AT_RISK
- CRITICAL

Rules:

- `NO_DATA`: SLA missing.
- `CRITICAL`: SLA below 80%, or SLA below 90% with inventory pressure at least 0.30.
- `AT_RISK`: SLA below 90%.
- `WATCH`: SLA is okay, but early warning is active or inventory pressure is at least 0.18.
- `MEETING_TARGET`: SLA meeting target with no major warning.

## Tabs

### Pulse

Leadership triage. Shows affected areas first. If no affected areas exist, communicates healthy state instead of manufacturing a problem.

### Flow

Uses `throughputBalance` for presentation.

Shows:

- Receipts In
- Closures Out
- Throughput Balance
- Starting Inventory
- In Standard
- Out of Standard

Positive throughput balance means closures exceeded receipts.

### Staffing

Shows:

- Capacity action callout
- FTE
- Daily Receipts
- Daily Production
- Production / Receipts
- Top Capacity Concerns

Surplus-capacity areas are not listed as concerns.

If no shortfall:

```text
No current capacity shortfalls.
```

### Forecast

Major redesign.

Forecast now shows:

- If Current Trends Continue
- Current, Month +1, Month +2, Month +3
- receipts
- closures
- throughput balance
- inventory
- SLA
- confidence
- primary drivers
- backlog / burn-down outlook
- crossover period
- backlog target period

The old “If Nothing Changes” language was replaced with “If Current Trends Continue.”

Forecast scenario controls are integrated directly into the Forecast tab:

- FTE Change
- Productivity %
- Receipt %
- Backlog Target
- Reset To Baseline Forecast

Scenarios are temporary. Source data is not modified.

### Intelligence

Shows:

- Early Warnings
- Likely Drivers

Driver bars are explanatory rule-based signals, not learned feature importance.

### Detail

Now separates:

- Source SLA
- Calculated SLA

Also shows throughput balance rather than confusing gap sign.

## Forecast Engine

New payload:

```text
analytics.forecastEngine
```

It includes:

- `method`
- `horizonPeriods`
- `historyAvailable`
- `maturity`
- `contexts`
- `notes`

Each forecast context includes:

- BU
- work category
- history periods
- maturity
- confidence
- primary drivers
- operational backlog target
- crossover period
- clearance period
- projection array

Projection array includes:

- Current
- Month +1
- Month +2
- Month +3

Forecast maturity labels:

- LIMITED_HISTORY_DIRECTIONAL
- TREND_HISTORY_READY
- SEASONAL_HISTORY_READY
- ADVANCED_HISTORY_READY

The sample remains limited history, but the architecture is ready to use more history dynamically.

## Forecast Confidence

Confidence considers:

- number of historical periods
- missing recent fields
- recent SLA volatility
- forecast horizon

Labels:

- High
- Medium
- Low

No fake statistical confidence percentages are shown.

## Machine Learning Reality

The dashboard still does not use a trained ML model.

Current methods are:

```text
rule-based operational intelligence
directional forecasting
correlation scanning
adaptive history-aware forecast payload
```

True ML should only activate when enough history exists for:

- temporal validation
- backtesting
- useful driver selection
- seasonality
- uncertainty ranges
- forecast error comparison

## Intelligence Rail

The right-side rail now follows:

- Current State
- Why It Matters
- Primary Driver
- Early Warning
- Outlook
- Recommended Lever

Recommendations are modeled operational levers, not unsupported prescriptions.

## Data Quality

Validation checks:

- unexpected business units
- unexpected categories
- impossible SLA values
- zero FTE with closures
- missing metrics
- incomplete periods

Warnings appear in Source Notes.

## Important FTE Limitation

Do not invent staffing allocation that the source does not provide.

If future source data has reliable work-category FTE, the system can support granular analysis. If staffing is only reliable at department/business-unit level, FTE scenarios should operate at that grain.

The current implementation uses available feature-row FTE fields but should be further refined if future reports clarify staffing allocation grain.

## Current Limitations

- Current sample has limited monthly history.
- September has inventory/SLA but not full operational context.
- Forecast remains directional with limited history.
- No trained ML yet.
- Visuals are still HTML/CSS chart rows, not a full charting library.
- Forecast scenario is useful but still approximate.

## Good Next Improvements

- Add trend line charts over time.
- Visualize `correlationExplorer`.
- Add real charting for forecast/backlog trajectory.
- Add export to PDF or PowerPoint.
- Add upload/import UI.
- Add stronger business-unit-level FTE scenario handling.
- Add model backtesting when 12+ periods exist.
- Add seasonal pattern detection when 12+ months exist.
- Add explainability view for the risk score.
