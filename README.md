# Staffing and Inventory Intelligence Dashboard

This project builds a local dashboard from the staffing and inventory report in `Sample Report.txt`.

## Run

```bash
python3 update_dashboard.py
```

Then open `dashboard.html` locally in a browser.

The Python job creates:

- `data/dashboard-data.js`
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
