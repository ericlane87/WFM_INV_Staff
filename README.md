# Staffing and Inventory Intelligence Dashboard

This project builds a local dashboard from the staffing and inventory report in `Sample Report.txt`.

You can also put report files directly in the `input` folder beside the updater/batch file. The updater reads every supported file directly inside `input`, sorts the reports by their month periods, and keeps each period only once. If a later file repeats a period that was already loaded, that duplicate period is ignored.

Previously loaded source rows are stored in `data/source-records.json`. New runs keep those existing dates and add only new dates from the files in `input`.

Excel date headers such as `26-Jan`, `Jan-26`, `Aug`, and `2026-08-26` are supported. Month labels without a year default to 2026.

## Run

```bash
python3 update_dashboard.py
```

On Windows, double-click:

```text
run_dashboard_update.bat
```

You can also point the job directly at an Excel workbook that has the same staffing/inventory layout:

```bash
python3 update_dashboard.py "Your Report.xlsx"
python3 update_dashboard.py "Your Report.xlsx" --sheet "Sheet1"
```

Then open `dashboard.html` locally in a browser.

The Python job creates:

- `data/dashboard-data.js`
- `data/source-records.json`
- normalized records by business unit, work category, month, and metric
- feature rows connecting inventory, SLA, receipts, closures, reroutes, staffing, production, and hourly goals
- early driver insights
- simple trend forecasts
- scenario-builder inputs

## Reference Pattern

The automation pattern follows the Antwon Dashboard project:

- keep Python ingestion and analytics separate from dashboard UI
- write a generated browser-readable data file
- open the dashboard locally without a server
- build ML/forecasting context from a normalized feature layer

The design and business logic for this dashboard are specific to staffing and inventory.
