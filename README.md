# Staffing and Inventory Intelligence Dashboard

On Windows, double-click `run_dashboard_update.bat` to refresh the local dashboard and publish it to the WFM share. The shared root from `logs/log.txt` is

```text
\\va01pstodfs003.corp.agp.ads\Files\VA1\Private\ServiceOperations\Claims\CostContainmentTeam\Escalated Recoveries\Eric Lane\WFM
```

```text
WFM/
  Inputfile/                 Drop staffing and inventory reports here
  data/
    dashboard-data.js        Data that the dashboard displays
    source-records.json      Copy of the accumulated report records
  Dashboard/
    dashboard.html           Open this file to view the dashboard
```

Give viewers the `WFM\Dashboard` folder path. The HTML reads `../data/dashboard-data.js` directly in the browser, so viewers need read access to that file. Contributors can go up one level to `WFM\Inputfile`. The account running the updater needs write access to create the folders and publish the files.

The first run creates any missing folders and publishes the HTML. An empty input folder is fine. The updater publishes the local history if available, or shows “Waiting for the first report” on a fresh installation with no history. Later runs refresh the data and only replace the shared HTML if the local page has changed or the shared copy is missing. Viewers can use Refresh to load a new publication.

Each run reads reports from the shared `Inputfile` and local `input` folders, including four-digit year subfolders such as `2026`. Supported formats are `.txt`, `.csv`, `.xlsx` and `.xlsm`. The local `data/source-records.json` retains previously loaded months. Reports are processed by earliest period, with shared inputs first on a tie. Each new month is accepted once. The local dashboard and its data remain beside the updater. Windows batch logs stay in the local `logs` folder.

Excel date headers such as `26-Jan`, `Jan-26`, `Aug`, and `2026-08-26` are supported. Month labels without a year default to 2026.

## Run

```bash
python3 update_dashboard.py
```

To use a mounted share on macOS or another shared root on Windows, pass the parent directory containing `Inputfile`:

```bash
python3 update_dashboard.py --share-root "/Volumes/Files/path/to/WFM"
```

For a local-only run, use `python3 update_dashboard.py --local-only`. This is the default on macOS and Linux. Local-only runs fall back to `Sample Report.txt` if the local input folder has no reports.

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
