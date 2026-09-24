# Staffing and Inventory Dashboard Project Memory

## Reference Project

Use `/Users/ericlane/Desktop/Work Projects/Antwon/Dashboard` as the workflow guide for this project.

The useful pattern from that dashboard is:

- Python reads local business report files.
- Python validates and normalizes the source data.
- Python creates an analysis-ready feature layer.
- Python writes a browser-readable generated data file.
- A standalone local `dashboard.html` opens directly in a browser without a server.
- Machine learning, forecasting, driver analysis, anomaly detection, and executive insights are generated from the normalized data.
- Dashboard UI code stays separate from generated data.

Do not copy the Antwon dashboard design. Reuse the automation architecture and local-file workflow.

## Current Source File

`Sample Report.txt` is the starting inventory and staffing report for a specific reporting period.

The file is a wide tab-delimited staffing model report titled `2026 Staffing Models`. It contains multiple repeated metric blocks across the same business dimensions.

Known business dimensions visible in the sample:

- Business segments: `CB`, `GB`, `CGS`
- Work categories: `Validation/Adjustments`, `Disputes`, `Correspondence`, `Cash Posting`, `Host`
- Aggregated total rows
- Monthly columns including `Jan-26`, `Jun-26`, `Jul-26`, `Aug-26`, and for some inventory/SLA sections `Sep-26`

Known metric groups visible in the sample:

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

## Intended Automation Shape

The Python job should convert the wide report into normalized rows before dashboarding or machine learning.

Target normalized grain should likely be:

```text
period, business_segment, work_category, metric_name, metric_value
```

Additional derived fields can be added after requirements are confirmed, such as:

- inventory health
- SLA risk
- staffing pressure
- production gap
- receipt/closure imbalance
- FTE productivity
- forecasted inventory
- likely drivers of out-of-standard work
- leadership insight priority

## Current Understanding

This project will become a local staffing and inventory intelligence dashboard.

The dashboard should help explain what is driving inventory, SLA performance, staffing pressure, production capacity, closure gaps, reroutes, and future risk. The exact measurements and business rules will be defined as the project continues.
