# Staffing and Inventory Intelligence Dashboard

On Windows, double-click `run_dashboard_update.bat` to build the dashboard data on the WFM share. After publication, the updater copies both generated data files back to the computer that ran it. The shared root from `logs/log.txt` is

```text
\\va01pstodfs003.corp.agp.ads\Files\VA1\Private\ServiceOperations\Claims\CostContainmentTeam\Escalated Recoveries\Eric Lane\WFM
```

```text
WFM/
  Inputfile/                 Drop staffing and inventory reports here
  data/
    dashboard-data.js        Data that the dashboard displays
    source-records.json      History imported from shared reports
  Dashboard/
    dashboard.html           Open this file to view the dashboard
```

Give viewers the `WFM\Dashboard` folder path. The HTML reads `../data/dashboard-data.js` directly in the browser, so viewers need read access to that file. Contributors can go up one level to `WFM\Inputfile`. The account running the updater needs write access to create the folders and publish the files.

The first run creates the folders, both data files, and the HTML. If you used the earlier publisher, the first corrected run rebuilds the shared history using the reports currently in `WFM\Inputfile`. With an empty folder, it replaces the old copied data and the dashboard shows “Waiting for the first report”. Put any historical reports you want to import in `Inputfile` or one of its four-digit year subfolders.

Each shared run reads new reports exclusively from `WFM\Inputfile`. Supported formats are `.txt`, `.csv`, `.xlsx` and `.xlsm`. Reports are processed by earliest period and each new month is accepted once. Months imported by the corrected updater stay in `WFM\data\source-records.json` if you later remove a report from `Inputfile`.

After the shared data and HTML are published, the updater overwrites the two files in its local `data` folder with the published copies. Open the local `dashboard.html` to view that snapshot. The shared HTML is replaced only when its template changes or the file is missing. Viewers can use Refresh to load the latest publication. Windows batch logs stay in the local `logs` folder.

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

To select one workbook for a shared run, use its path relative to the shared `Inputfile` folder. To select a workbook on the launching computer, use `--local-only`.

```bash
python3 update_dashboard.py --share-root "/Volumes/Files/path/to/WFM" "Your Report.xlsx"
python3 update_dashboard.py --local-only "Your Report.xlsx" --sheet "Sheet1"
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
