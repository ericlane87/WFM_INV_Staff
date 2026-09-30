#!/usr/bin/env python3
"""Build the local Staffing and Inventory dashboard data file.

The source report is a wide, human-formatted tab-delimited export. This script
normalizes it into business-unit/work-category/month rows, builds connected
inventory and staffing features, generates early insight and forecast signals,
and writes a local JavaScript data file for dashboard.html.
"""

from __future__ import annotations

import datetime as dt
import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE_FILE = BASE_DIR / "Sample Report.txt"
INPUT_DIR = BASE_DIR / "input"
DATA_FILE = BASE_DIR / "data/dashboard-data.js"
SOURCE_STORE_FILE = BASE_DIR / "data/source-records.json"
DATA_HEADER = "// AUTO-GENERATED DASHBOARD DATA - DO NOT EDIT MANUALLY"
SLA_TARGET = 0.90
KNOWN_METRICS = {
    "Monthly Starting SLA %",
    "Starting Inventory",
    "In Standard",
    "Out of Standard",
    "Monthly Receipts",
    "Monthly Closures",
    "Monthly Receipt/Closure Variance",
    "Monthly Reroutes",
    "Average Daily Receipts",
    "Average Daily Production",
    "FTE's",
    "Hourly Goal",
}
SUPPORTED_SOURCE_SUFFIXES = {".txt", ".csv", ".xlsx", ".xlsm"}
DEFAULT_SOURCE_YEAR = 2026
MONTH_RE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:-(\d{2}|\d{4}))?$")
DAY_MONTH_RE = re.compile(r"^\d{1,2}-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:-(\d{2}|\d{4}))?$")
MONTH_ORDER = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def clean_cell(value: str) -> str:
    return value.replace("\u00a0", " ").strip()


def parse_number(value: str) -> float | None:
    text = clean_cell(value)
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "").replace("$", "")
    is_percent = text.endswith("%")
    text = text.rstrip("%").strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if negative:
        parsed *= -1
    if is_percent:
        parsed /= 100
    return parsed


def month_key(label: str, default_year: int = DEFAULT_SOURCE_YEAR) -> str:
    text = clean_cell(str(label))
    for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            parsed_date = dt.datetime.strptime(text, date_format)
            return f"{parsed_date.year}-{parsed_date.month:02d}"
        except ValueError:
            pass

    match = MONTH_RE.match(text)
    if match:
        month_name, year_text = match.groups()
    else:
        match = DAY_MONTH_RE.match(text)
        if not match:
            raise ValueError(f"Unsupported month label: {label}")
        month_name, year_text = match.groups()

    year = default_year if year_text is None else int(year_text)
    if year < 100:
        year += 2000
    return f"{year}-{MONTH_ORDER[month_name]:02d}"


def is_month_label(label: str) -> bool:
    try:
        month_key(label)
    except ValueError:
        return False
    return True


def month_sort_key(label: str, default_year: int = DEFAULT_SOURCE_YEAR) -> tuple[int, int]:
    year, month = month_key(label, default_year).split("-")
    return int(year), int(month)


def discover_blocks(cells: list[str], default_year: int = DEFAULT_SOURCE_YEAR) -> list[dict[str, Any]]:
    starts = [idx for idx, cell in enumerate(cells) if clean_cell(cell) in KNOWN_METRICS]
    blocks: list[dict[str, Any]] = []
    for pos, start in enumerate(starts):
        end = starts[pos + 1] if pos + 1 < len(starts) else len(cells)
        month_columns = [
            {"index": idx, "label": clean_cell(cells[idx]), "period": month_key(clean_cell(cells[idx]), default_year)}
            for idx in range(start + 1, end)
            if is_month_label(clean_cell(cells[idx]))
        ]
        if month_columns:
            blocks.append({"metric": clean_cell(cells[start]), "start": start, "months": month_columns})
    return blocks


def load_source_rows(path: Path, sheet_name: str | None = None) -> list[list[str]]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise SystemExit("Excel input requires openpyxl. Install it with: python3 -m pip install openpyxl") from exc

        workbook = load_workbook(path, data_only=True, read_only=True)
        if sheet_name:
            if sheet_name not in workbook.sheetnames:
                available = ", ".join(workbook.sheetnames)
                raise SystemExit(f"Worksheet not found: {sheet_name}. Available sheets: {available}")
            worksheet = workbook[sheet_name]
        else:
            worksheet = workbook.active

        rows: list[list[str]] = []
        for row in worksheet.iter_rows(values_only=True):
            cells = ["" if value is None else str(value) for value in row]
            if any(clean_cell(cell) for cell in cells):
                rows.append(cells)
        workbook.close()
        return rows

    if suffix == ".csv":
        import csv

        with path.open(newline="", encoding="utf-8-sig") as file:
            return [[cell for cell in row] for row in csv.reader(file)]

    return [line.split("\t") for line in path.read_text(encoding="utf-8-sig").splitlines()]


def infer_source_year(path: Path) -> int:
    for part in reversed(path.parts):
        if re.fullmatch(r"20\d{2}", part):
            return int(part)
    return DEFAULT_SOURCE_YEAR


def parse_source(path: Path, sheet_name: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_year = infer_source_year(path)
    rows = load_source_rows(path, sheet_name)
    normalized: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    active_blocks: list[dict[str, Any]] = []
    active_units: dict[int, str] = {}

    for row_number, raw_cells in enumerate(rows, start=1):
        cells = [clean_cell(cell) for cell in raw_cells]
        discovered = discover_blocks(cells, source_year)
        if discovered:
            active_blocks = discovered
            active_units = {}
            blocks.extend(
                {
                    "row": row_number,
                    "metric": block["metric"],
                    "monthLabels": [month["label"] for month in block["months"]],
                }
                for block in discovered
            )
            continue

        if not active_blocks:
            continue

        for block in active_blocks:
            start = block["start"]
            business_unit = cells[start] if start < len(cells) else ""
            work_category = cells[start + 1] if start + 1 < len(cells) else ""
            if business_unit:
                active_units[start] = business_unit
            else:
                business_unit = active_units.get(start, "")

            if not business_unit and not work_category:
                continue
            if business_unit == "Aggregated Total":
                work_category = "All Work Categories"
            if not work_category:
                continue

            for month in block["months"]:
                idx = month["index"]
                value = parse_number(cells[idx]) if idx < len(cells) else None
                if value is None:
                    continue
                normalized.append(
                    {
                        "businessUnit": business_unit,
                        "workCategory": work_category,
                        "period": month["period"],
                        "monthLabel": month["label"],
                        "metric": block["metric"],
                        "value": round(value, 4),
                    }
                )

    return normalized, blocks


def pivot_feature_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        key = (record["businessUnit"], record["workCategory"], record["period"])
        row = grouped.setdefault(
            key,
            {
                "businessUnit": record["businessUnit"],
                "workCategory": record["workCategory"],
                "period": record["period"],
                "monthLabel": record["monthLabel"],
            },
        )
        row[metric_key(record["metric"])] = record["value"]

    feature_rows = []
    for row in grouped.values():
        starting = row.get("startingInventory")
        out_standard = row.get("outOfStandard")
        in_standard = row.get("inStandard")
        receipts = row.get("monthlyReceipts")
        closures = row.get("monthlyClosures")
        ftes = row.get("ftes")
        production = row.get("averageDailyProduction")
        daily_receipts = row.get("averageDailyReceipts")
        hourly_goal = row.get("hourlyGoal")

        row["outOfStandardRate"] = safe_divide(out_standard, starting)
        row["calculatedSla"] = safe_divide(in_standard, starting)
        row["receiptClosureGap"] = None if receipts is None or closures is None else receipts - closures
        row["throughputBalance"] = None if receipts is None or closures is None else closures - receipts
        row["closuresPerFte"] = safe_divide(closures, ftes)
        row["receiptsPerFte"] = safe_divide(receipts, ftes)
        row["dailyProductionPerFte"] = safe_divide(production, ftes)
        row["dailyReceiptsPerFte"] = safe_divide(daily_receipts, ftes)
        row["productionToReceiptsRatio"] = safe_divide(production, daily_receipts)
        row["goalAttainmentProxy"] = safe_divide(row.get("dailyProductionPerFte"), hourly_goal)
        row["inventoryPressureScore"] = inventory_pressure(row)
        row["staffingPressureScore"] = staffing_pressure(row)
        feature_rows.append(row)

    feature_rows.sort(key=lambda item: (item["businessUnit"], item["workCategory"], item["period"]))
    add_change_features(feature_rows)
    add_history_features(feature_rows)
    add_status_features(feature_rows)
    return feature_rows


def metric_key(metric: str) -> str:
    return {
        "Monthly Starting SLA %": "monthlyStartingSla",
        "Starting Inventory": "startingInventory",
        "In Standard": "inStandard",
        "Out of Standard": "outOfStandard",
        "Monthly Receipts": "monthlyReceipts",
        "Monthly Closures": "monthlyClosures",
        "Monthly Receipt/Closure Variance": "receiptClosureVariance",
        "Monthly Reroutes": "monthlyReroutes",
        "Average Daily Receipts": "averageDailyReceipts",
        "Average Daily Production": "averageDailyProduction",
        "FTE's": "ftes",
        "Hourly Goal": "hourlyGoal",
    }[metric]


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator, 6)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def inventory_pressure(row: dict[str, Any]) -> float:
    out_rate = row.get("outOfStandardRate") or 0
    sla = row.get("monthlyStartingSla")
    gap = row.get("receiptClosureGap") or 0
    starting = row.get("startingInventory") or 0
    gap_pressure = max(0.0, safe_divide(gap, starting) or 0)
    sla_pressure = 0 if sla is None else max(0.0, 0.95 - sla)
    return round(clamp(out_rate * 0.55 + gap_pressure * 0.3 + sla_pressure * 0.8), 4)


def staffing_pressure(row: dict[str, Any]) -> float:
    ratio = row.get("productionToReceiptsRatio")
    gap = row.get("receiptClosureGap") or 0
    starting = row.get("startingInventory") or 0
    goal = row.get("goalAttainmentProxy")
    production_gap = 0 if ratio is None else max(0.0, 1 - ratio)
    backlog_gap = max(0.0, safe_divide(gap, starting) or 0)
    goal_gap = 0 if goal is None else max(0.0, 1 - goal)
    return round(clamp(production_gap * 0.45 + backlog_gap * 0.35 + goal_gap * 0.2), 4)


def add_change_features(rows: list[dict[str, Any]]) -> None:
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[(row["businessUnit"], row["workCategory"])].append(row)
    for group_rows in by_group.values():
        group_rows.sort(key=lambda item: item["period"])
        previous = None
        for row in group_rows:
            row["outOfStandardChange"] = diff(row.get("outOfStandard"), previous.get("outOfStandard") if previous else None)
            row["slaChange"] = diff(row.get("monthlyStartingSla"), previous.get("monthlyStartingSla") if previous else None)
            row["fteChange"] = diff(row.get("ftes"), previous.get("ftes") if previous else None)
            row["closureGapChange"] = diff(row.get("receiptClosureGap"), previous.get("receiptClosureGap") if previous else None)
            previous = row


def add_history_features(rows: list[dict[str, Any]]) -> None:
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[(row["businessUnit"], row["workCategory"])].append(row)

    lag_fields = {
        "monthlyReceipts": "receipts",
        "monthlyClosures": "closures",
        "ftes": "fte",
        "monthlyStartingSla": "sla",
        "outOfStandard": "outOfStandard",
        "averageDailyProduction": "production",
        "receiptClosureGap": "gap",
        "startingInventory": "inventory",
    }
    rolling_fields = {
        "monthlyReceipts": "receipts",
        "monthlyClosures": "closures",
        "monthlyStartingSla": "sla",
        "outOfStandard": "outOfStandard",
        "ftes": "fte",
        "averageDailyProduction": "production",
        "receiptClosureGap": "gap",
    }

    for group_rows in by_group.values():
        group_rows.sort(key=lambda item: item["period"])
        for index, row in enumerate(group_rows):
            history = group_rows[:index]
            for source_field, prefix in lag_fields.items():
                for lag in (1, 2, 3):
                    row[f"{prefix}Lag{lag}"] = group_rows[index - lag].get(source_field) if index >= lag else None
                row[f"{prefix}PctChange"] = pct_change(row.get(source_field), row.get(f"{prefix}Lag1"))
                row[f"{prefix}Change3Period"] = diff(row.get(source_field), row.get(f"{prefix}Lag3"))

            for source_field, prefix in rolling_fields.items():
                values3 = [item.get(source_field) for item in history[-3:] if item.get(source_field) is not None]
                values6 = [item.get(source_field) for item in history[-6:] if item.get(source_field) is not None]
                row[f"{prefix}Rolling3Avg"] = round(mean(values3), 4) if values3 else None
                row[f"{prefix}Rolling6Avg"] = round(mean(values6), 4) if values6 else None
                row[f"{prefix}Rolling3Std"] = round(stddev(values3), 4) if len(values3) >= 2 else None
                row[f"{prefix}VsRolling3Pct"] = pct_change(row.get(source_field), row.get(f"{prefix}Rolling3Avg"))

            row["consecutiveReceiptIncreasePeriods"] = streak(group_rows, index, "monthlyReceipts", "increase")
            row["consecutiveClosureDeclinePeriods"] = streak(group_rows, index, "monthlyClosures", "decline")
            row["consecutiveSlaDeclinePeriods"] = streak(group_rows, index, "monthlyStartingSla", "decline")
            row["consecutivePositiveGapPeriods"] = threshold_streak(group_rows, index, "receiptClosureGap", 0, "above")
            row["consecutiveOosIncreasePeriods"] = streak(group_rows, index, "outOfStandard", "increase")
            row["consecutiveProductionBelowReceiptsPeriods"] = threshold_streak(group_rows, index, "productionToReceiptsRatio", 1, "below")
            row["workloadGrowthVsFteGrowth"] = None
            if row.get("receiptsPctChange") is not None and row.get("ftePctChange") is not None:
                row["workloadGrowthVsFteGrowth"] = round(row["receiptsPctChange"] - row["ftePctChange"], 6)
            row["estimatedCapacityGap"] = estimated_capacity_gap(row)
            row["capacityStatus"] = capacity_status(row)
            row["capacityGapMagnitude"] = None if row.get("estimatedCapacityGap") is None else round(abs(row["estimatedCapacityGap"]), 2)
            row["capacityGrain"] = "WORK_CATEGORY_ESTIMATE"
            row["capacityUtilizationProxy"] = capacity_utilization(row)
            row["limitedHistory"] = len(history) < 6


def add_status_features(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        row["earlyWarning"] = build_early_warning(row)
        row["anomalySignals"] = detect_contextual_anomalies(row)
        status, reasons = classify_status(row)
        row["status"] = status
        row["statusReasons"] = reasons
        row["pressureTypes"] = classify_pressure_types(row)
        row["riskScore"] = risk_score(row)
        row["confidenceLabel"] = confidence_label(row)


def pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / abs(previous), 6)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def streak(rows: list[dict[str, Any]], index: int, field: str, direction: str) -> int:
    count = 0
    cursor = index
    while cursor > 0:
        current = rows[cursor].get(field)
        previous = rows[cursor - 1].get(field)
        if current is None or previous is None:
            break
        if direction == "increase" and current > previous:
            count += 1
        elif direction == "decline" and current < previous:
            count += 1
        else:
            break
        cursor -= 1
    return count


def threshold_streak(rows: list[dict[str, Any]], index: int, field: str, threshold: float, mode: str) -> int:
    count = 0
    cursor = index
    while cursor >= 0:
        value = rows[cursor].get(field)
        if value is None:
            break
        if mode == "above" and value > threshold:
            count += 1
        elif mode == "below" and value < threshold:
            count += 1
        else:
            break
        cursor -= 1
    return count


def estimated_capacity_gap(row: dict[str, Any]) -> float | None:
    receipts = row.get("monthlyReceipts")
    closures_per_fte = row.get("closuresPerFte")
    ftes = row.get("ftes")
    if receipts is None or closures_per_fte in (None, 0) or ftes is None:
        return None
    required = receipts / closures_per_fte
    return round(required - ftes, 2)


def capacity_status(row: dict[str, Any]) -> str:
    gap = row.get("estimatedCapacityGap")
    if gap is None:
        return "UNKNOWN"
    if gap > 0.25:
        return "SHORTFALL"
    if gap < -0.25:
        return "SURPLUS"
    return "SUFFICIENT"


def capacity_utilization(row: dict[str, Any]) -> float | None:
    receipts = row.get("monthlyReceipts")
    closures = row.get("monthlyClosures")
    if receipts is None or closures in (None, 0):
        return None
    return round(receipts / closures, 6)


def classify_status(row: dict[str, Any]) -> tuple[str, list[str]]:
    sla = row.get("monthlyStartingSla") or row.get("calculatedSla")
    reasons: list[str] = []
    if sla is None:
        return "NO_DATA", ["SLA is not available for this period."]
    gap = SLA_TARGET - sla
    if gap > 0:
        reasons.append(f"SLA is {format_percent(sla)}, {gap * 100:.0f} pts below target.")
    if (row.get("consecutiveSlaDeclinePeriods") or 0) >= 2:
        reasons.append(f"SLA declined for {row['consecutiveSlaDeclinePeriods']} consecutive periods.")
    if (row.get("consecutivePositiveGapPeriods") or 0) >= 2:
        reasons.append(f"Receipts exceeded closures for {row['consecutivePositiveGapPeriods']} consecutive periods.")
    if (row.get("outOfStandardChange") or 0) > 0:
        reasons.append(f"Out-of-standard inventory increased by {format_number(row.get('outOfStandardChange'))}.")

    if sla < 0.80 or (sla < SLA_TARGET and (row.get("inventoryPressureScore") or 0) >= 0.30):
        return "CRITICAL", reasons or ["SLA and inventory pressure are materially unfavorable."]
    if sla < SLA_TARGET:
        return "AT_RISK", reasons or ["SLA is below target."]
    if (row.get("earlyWarning", {}).get("active") if isinstance(row.get("earlyWarning"), dict) else False) or (
        row.get("inventoryPressureScore") or 0
    ) >= 0.18:
        return "WATCH", reasons or ["Leading indicators suggest pressure is forming."]
    return "MEETING_TARGET", reasons or ["SLA is meeting target."]


def classify_pressure_types(row: dict[str, Any]) -> list[str]:
    types: list[str] = []
    if (row.get("receiptsPctChange") or 0) >= 0.10 or (row.get("consecutiveReceiptIncreasePeriods") or 0) >= 2:
        types.append("DEMAND_PRESSURE")
    if (row.get("workloadGrowthVsFteGrowth") or 0) >= 0.10 or (row.get("estimatedCapacityGap") or 0) > 0.5:
        types.append("CAPACITY_PRESSURE")
    if (row.get("productionPctChange") or 0) <= -0.08 or (row.get("goalAttainmentProxy") or 1) < 0.90:
        types.append("PRODUCTIVITY_PRESSURE")
    if (row.get("receiptClosureGap") or 0) > 0 or (row.get("consecutivePositiveGapPeriods") or 0) >= 2:
        types.append("FLOW_IMBALANCE")
    if (row.get("outOfStandardChange") or 0) > 0 or (row.get("outOfStandardRate") or 0) >= 0.15:
        types.append("INVENTORY_PRESSURE")
    if (row.get("monthlyStartingSla") or 1) < SLA_TARGET or (row.get("consecutiveSlaDeclinePeriods") or 0) >= 2:
        types.append("SLA_PRESSURE")
    if abs(row.get("monthlyReroutes") or 0) > 0 and abs(row.get("monthlyReroutes") or 0) >= abs(row.get("receiptClosureGap") or 0) * 0.25:
        types.append("REROUTE_PRESSURE")
    if len(types) >= 3:
        types.insert(0, "MULTI_FACTOR_PRESSURE")
    return types[:5]


def build_early_warning(row: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    if (row.get("monthlyStartingSla") or 0) >= SLA_TARGET:
        if (row.get("consecutiveReceiptIncreasePeriods") or 0) >= 2:
            evidence.append(f"Receipts increased for {row['consecutiveReceiptIncreasePeriods']} consecutive periods.")
        if (row.get("consecutiveClosureDeclinePeriods") or 0) >= 2:
            evidence.append(f"Closures declined for {row['consecutiveClosureDeclinePeriods']} consecutive periods.")
        if (row.get("consecutivePositiveGapPeriods") or 0) >= 2:
            evidence.append(f"Receipt/closure gap was positive for {row['consecutivePositiveGapPeriods']} periods.")
        if (row.get("productionToReceiptsRatio") or 1) < 1:
            evidence.append(f"Production is {format_percent(row.get('productionToReceiptsRatio'))} of receipts.")
        if (row.get("outOfStandardChange") or 0) > 0:
            evidence.append(f"OOS inventory increased by {format_number(row.get('outOfStandardChange'))}.")
        if (row.get("workloadGrowthVsFteGrowth") or 0) > 0.10:
            evidence.append("Workload is growing faster than FTE.")
    active = len(evidence) >= 2
    return {
        "active": active,
        "type": "EMERGING_CAPACITY_PRESSURE" if active else "NONE",
        "label": "Early Warning" if active else "No early warning",
        "confidence": "LIMITED_DATA" if row.get("limitedHistory") else "MODERATE",
        "evidence": evidence[:5],
    }


def detect_contextual_anomalies(row: dict[str, Any]) -> list[dict[str, Any]]:
    signals = []
    checks = [
        ("monthlyReceipts", "Receipt volume"),
        ("monthlyClosures", "Closure volume"),
        ("outOfStandard", "Out-of-standard inventory"),
        ("ftes", "FTE"),
        ("monthlyStartingSla", "SLA"),
    ]
    for field, label in checks:
        rolling = row.get(f"{field_name_prefix(field)}Rolling3Avg")
        stdev = row.get(f"{field_name_prefix(field)}Rolling3Std")
        value = row.get(field)
        if value is None or rolling is None or stdev in (None, 0):
            continue
        z_score = (value - rolling) / stdev
        if abs(z_score) >= 2:
            signals.append(
                {
                    "metric": field,
                    "label": label,
                    "direction": "above normal" if z_score > 0 else "below normal",
                    "strength": round(abs(z_score), 2),
                    "summary": f"{label} is {abs(z_score):.1f} standard deviations {'above' if z_score > 0 else 'below'} its recent pattern.",
                }
            )
    return signals


def field_name_prefix(field: str) -> str:
    return {
        "monthlyReceipts": "receipts",
        "monthlyClosures": "closures",
        "outOfStandard": "outOfStandard",
        "ftes": "fte",
        "monthlyStartingSla": "sla",
    }.get(field, field)


def risk_score(row: dict[str, Any]) -> float:
    sla = row.get("monthlyStartingSla") or row.get("calculatedSla")
    sla_gap = max(0.0, SLA_TARGET - sla) if sla is not None else 0.0
    score = (
        sla_gap * 1.4
        + (row.get("inventoryPressureScore") or 0) * 0.9
        + (row.get("staffingPressureScore") or 0) * 0.7
        + min(0.25, max(0, (row.get("consecutivePositiveGapPeriods") or 0) * 0.06))
        + min(0.2, max(0, (row.get("consecutiveOosIncreasePeriods") or 0) * 0.05))
    )
    if row.get("earlyWarning", {}).get("active") if isinstance(row.get("earlyWarning"), dict) else False:
        score += 0.12
    return round(clamp(score), 4)


def confidence_label(row: dict[str, Any]) -> str:
    if row.get("limitedHistory"):
        return "LIMITED_DATA"
    if row.get("anomalySignals"):
        return "MODERATE"
    return "DIRECTIONAL"


def diff(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 4)


def latest_period(rows: list[dict[str, Any]]) -> str:
    return max(row["period"] for row in rows)


def latest_full_context_period(rows: list[dict[str, Any]]) -> str:
    full_context = [
        row["period"]
        for row in rows
        if row.get("ftes") is not None and row.get("monthlyReceipts") is not None and row.get("monthlyClosures") is not None
    ]
    return max(full_context) if full_context else latest_period(rows)


def aggregate_latest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    period = latest_period(rows)
    latest = [row for row in rows if row["period"] == period and row["businessUnit"] != "Aggregated Total"]
    return {
        "period": period,
        "startingInventory": sum_field(latest, "startingInventory"),
        "outOfStandard": sum_field(latest, "outOfStandard"),
        "inStandard": sum_field(latest, "inStandard"),
        "ftes": sum_field(latest, "ftes"),
        "receipts": sum_field(latest, "monthlyReceipts"),
        "closures": sum_field(latest, "monthlyClosures"),
        "receiptClosureGap": sum_field(latest, "receiptClosureGap"),
        "sla": safe_divide(sum_field(latest, "inStandard"), sum_field(latest, "startingInventory")),
    }


def aggregate_for_period(rows: list[dict[str, Any]], period: str, business_unit: str | None = None, work_category: str | None = None) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row["period"] == period
        and row["businessUnit"] != "Aggregated Total"
        and (business_unit is None or row["businessUnit"] == business_unit)
        and (work_category is None or row["workCategory"] == work_category)
    ]
    return {
        "period": period,
        "businessUnit": business_unit or "All",
        "workCategory": work_category or "All",
        "startingInventory": sum_field(selected, "startingInventory"),
        "inStandard": sum_field(selected, "inStandard"),
        "outOfStandard": sum_field(selected, "outOfStandard"),
        "monthlyReceipts": sum_field(selected, "monthlyReceipts"),
        "monthlyClosures": sum_field(selected, "monthlyClosures"),
        "receiptClosureGap": sum_field(selected, "receiptClosureGap"),
        "ftes": sum_field(selected, "ftes"),
        "averageDailyReceipts": sum_field(selected, "averageDailyReceipts"),
        "averageDailyProduction": sum_field(selected, "averageDailyProduction"),
        "sla": safe_divide(sum_field(selected, "inStandard"), sum_field(selected, "startingInventory")),
        "maxRiskScore": max([row.get("riskScore") or 0 for row in selected], default=0),
    }


def build_department_capacity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    business_units = sorted({row["businessUnit"] for row in rows if row["businessUnit"] != "Aggregated Total"})
    periods = sorted({row["period"] for row in rows})
    for period in periods:
        for business_unit in business_units:
            selected = [
                row
                for row in rows
                if row["period"] == period
                and row["businessUnit"] == business_unit
                and row["workCategory"] != "All Work Categories"
            ]
            if not selected:
                continue
            receipts = sum_optional_field(selected, "monthlyReceipts")
            closures = sum_optional_field(selected, "monthlyClosures")
            ftes = sum_optional_field(selected, "ftes")
            daily_receipts = sum_optional_field(selected, "averageDailyReceipts")
            daily_production = sum_optional_field(selected, "averageDailyProduction")
            closures_per_fte = safe_divide(closures, ftes)
            required_fte = safe_divide(receipts, closures_per_fte) if closures_per_fte else None
            gap = None if required_fte is None else round(required_fte - ftes, 2)
            ratio = safe_divide(daily_production, daily_receipts)
            throughput = None if receipts is None or closures is None else round(closures - receipts, 2)
            pressure_rows = sorted(selected, key=lambda row: row.get("riskScore") or 0, reverse=True)
            output.append(
                {
                    "businessUnit": business_unit,
                    "period": period,
                    "capacityGrain": "BUSINESS_UNIT_DEPARTMENT",
                    "fte": ftes,
                    "receipts": receipts,
                    "closures": closures,
                    "dailyReceipts": daily_receipts,
                    "dailyProduction": daily_production,
                    "productionToReceiptsRatio": ratio,
                    "closuresPerFte": closures_per_fte,
                    "requiredFteToKeepPace": None if required_fte is None else round(required_fte, 2),
                    "capacityGap": gap,
                    "capacityGapMagnitude": None if gap is None else round(abs(gap), 2),
                    "capacityStatus": capacity_status({"estimatedCapacityGap": gap}),
                    "throughputBalance": throughput,
                    "primaryWorkloadPressure": pressure_rows[0]["workCategory"] if pressure_rows else None,
                    "primaryWorkloadPressureStatus": pressure_rows[0].get("status") if pressure_rows else None,
                    "note": "Capacity is calculated at business-unit/department grain; work-category pressure remains operational workload context.",
                }
            )
    return output


def sum_field(rows: list[dict[str, Any]], field: str) -> float:
    return round(sum(float(row.get(field) or 0) for row in rows), 4)


def sum_optional_field(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    if not values:
        return None
    return round(sum(values), 4)


def generate_insights(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    period = latest_full_context_period(rows)
    latest = [row for row in rows if row["period"] == period and row["businessUnit"] != "Aggregated Total"]
    scored = sorted(latest, key=lambda row: row.get("riskScore") or 0, reverse=True)
    insights: list[dict[str, Any]] = []
    for row in scored[:10]:
        drivers = driver_list(row)
        insights.append(
            {
                "type": "operational_pressure",
                "priority": row.get("status", "WATCH"),
                "businessUnit": row["businessUnit"],
                "workCategory": row["workCategory"],
                "period": row["period"],
                "title": f"{row['businessUnit']} {row['workCategory']} needs attention",
                "summary": summarize_row(row, drivers),
                "drivers": drivers,
                "confidence": row.get("confidenceLabel", "DIRECTIONAL"),
                "pressureTypes": row.get("pressureTypes", []),
                "earlyWarning": row.get("earlyWarning", {}),
                "metrics": {
                    "sla": row.get("monthlyStartingSla"),
                    "startingInventory": row.get("startingInventory"),
                    "outOfStandard": row.get("outOfStandard"),
                    "receiptClosureGap": row.get("receiptClosureGap"),
                    "ftes": row.get("ftes"),
                    "staffingPressureScore": row.get("staffingPressureScore"),
                    "inventoryPressureScore": row.get("inventoryPressureScore"),
                    "riskScore": row.get("riskScore"),
                },
            }
        )
    return insights


def driver_list(row: dict[str, Any]) -> list[str]:
    drivers: list[str] = []
    if (row.get("monthlyStartingSla") or 1) < 0.9:
        drivers.append(f"SLA is {format_percent(row.get('monthlyStartingSla'))}")
    if (row.get("outOfStandardChange") or 0) > 0:
        drivers.append(f"out-of-standard inventory increased by {format_number(row.get('outOfStandardChange'))}")
    if (row.get("receiptClosureGap") or 0) > 0:
        drivers.append(f"receipts exceeded closures by {format_number(row.get('receiptClosureGap'))}")
    if (row.get("monthlyReroutes") or 0) > 0:
        drivers.append(f"reroutes added {format_number(row.get('monthlyReroutes'))} units of movement")
    if (row.get("productionToReceiptsRatio") or 1) < 1:
        drivers.append(f"daily production is {format_percent(row.get('productionToReceiptsRatio'))} of daily receipts")
    if not drivers:
        drivers.append("inventory, staffing, and production are connected but no single driver dominates")
    return drivers[:5]


def summarize_row(row: dict[str, Any], drivers: list[str]) -> str:
    return (
        f"{row['businessUnit']} {row['workCategory']} has {format_number(row.get('startingInventory'))} starting inventory, "
        f"and {format_number(row.get('outOfStandard'))} out of standard. "
        f"Key context: {', '.join(drivers[:3])}."
    )


def priority_label(score: float) -> str:
    if score >= 0.25:
        return "High"
    if score >= 0.12:
        return "Medium"
    return "Watch"


def confidence_score(row: dict[str, Any]) -> float:
    fields = ["startingInventory", "outOfStandard", "monthlyStartingSla", "ftes", "averageDailyProduction"]
    present = sum(1 for field in fields if row.get(field) is not None)
    return round(0.45 + present / len(fields) * 0.5, 2)


def generate_forecasts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["businessUnit"] != "Aggregated Total":
            by_group[(row["businessUnit"], row["workCategory"])].append(row)
    forecasts = []
    for (business_unit, work_category), group_rows in by_group.items():
        group_rows.sort(key=lambda item: item["period"])
        if len(group_rows) < 2:
            continue
        latest = group_rows[-1]
        prior = group_rows[-2]
        inventory_slope = (latest.get("startingInventory") or 0) - (prior.get("startingInventory") or 0)
        out_slope = (latest.get("outOfStandard") or 0) - (prior.get("outOfStandard") or 0)
        sla_slope = (latest.get("monthlyStartingSla") or latest.get("calculatedSla") or 0) - (
            prior.get("monthlyStartingSla") or prior.get("calculatedSla") or 0
        )
        forecasts.append(
            {
                "businessUnit": business_unit,
                "workCategory": work_category,
                "basePeriod": latest["period"],
                "forecastPeriod": next_month(latest["period"]),
                "startingInventory": max(0, round((latest.get("startingInventory") or 0) + inventory_slope, 2)),
                "outOfStandard": max(0, round((latest.get("outOfStandard") or 0) + out_slope, 2)),
                "sla": round(clamp((latest.get("monthlyStartingSla") or latest.get("calculatedSla") or 0) + sla_slope), 4),
                "method": "last-period trend",
            }
        )
    forecasts.sort(key=lambda item: item["outOfStandard"], reverse=True)
    return forecasts


def generate_forecast_engine(rows: list[dict[str, Any]], horizon: int = 3) -> dict[str, Any]:
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["businessUnit"] != "Aggregated Total":
            by_group[(row["businessUnit"], row["workCategory"])].append(row)

    contexts = []
    for (business_unit, work_category), group_rows in by_group.items():
        group_rows.sort(key=lambda item: item["period"])
        for index in range(len(group_rows)):
            base_history = group_rows[: index + 1]
            contexts.append(build_context_forecast(business_unit, work_category, base_history, horizon))

    min_history = min((context["historyPeriods"] for context in contexts), default=0)
    return {
        "method": "adaptive_directional_operational_forecast",
        "horizonPeriods": horizon,
        "historyAvailable": sorted({row["period"] for row in rows}),
        "maturity": forecast_maturity(min_history),
        "contexts": contexts,
        "notes": [
            "Uses observed operational history and rolling movement when limited history is available.",
            "Seasonality, backtesting, and statistical uncertainty become more meaningful as additional monthly periods are loaded.",
            "Scenario adjustments are temporary and do not modify source data.",
        ],
    }


def build_context_forecast(business_unit: str, work_category: str, history: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
    latest = history[-1]
    latest_operational = latest_operational_row(history) or latest
    history_periods = len(history)
    drivers = forecast_drivers(history)
    maturity = forecast_maturity(history_periods)
    confidence = forecast_confidence(history)
    projections = []
    current = {
        "period": latest["period"],
        "operationalBasePeriod": latest_operational["period"],
        "receipts": latest_operational.get("monthlyReceipts"),
        "closures": latest_operational.get("monthlyClosures"),
        "inventory": latest.get("startingInventory"),
        "outOfStandard": latest.get("outOfStandard"),
        "sla": latest.get("monthlyStartingSla") or latest.get("calculatedSla"),
        "fte": latest_operational.get("ftes"),
        "throughputBalance": latest_operational.get("throughputBalance"),
        "capacityStatus": latest.get("capacityStatus"),
    }

    base = dict(current)
    projections.append({"label": "Current", "horizon": 0, **base, "confidence": confidence, "drivers": drivers})

    receipt_slope = adaptive_slope(history, "monthlyReceipts")
    closure_slope = adaptive_slope(history, "monthlyClosures")
    oos_slope = adaptive_slope(history, "outOfStandard")
    fte_slope = adaptive_slope(history, "ftes")
    latest_period = latest["period"]
    prior_inventory = base.get("inventory")
    prior_oos = base.get("outOfStandard")

    for step in range(1, horizon + 1):
        period = add_months(latest_period, step)
        receipts = project_value(base.get("receipts"), receipt_slope, step)
        closures = project_value(base.get("closures"), closure_slope, step)
        throughput = None if receipts is None or closures is None else round(closures - receipts, 2)
        inventory = None
        if prior_inventory is not None and throughput is not None:
            inventory = round(max(0, prior_inventory - throughput), 2)
        out_standard = project_value(prior_oos, oos_slope, 1)
        fte = project_value(base.get("fte"), fte_slope, step)
        sla = None if inventory in (None, 0) or out_standard is None else round(clamp(1 - out_standard / inventory), 4)
        expected_range = forecast_range(sla, confidence, step)
        projections.append(
            {
                "label": f"Month +{step}",
                "period": period,
                "horizon": step,
                "receipts": receipts,
                "closures": closures,
                "inventory": inventory,
                "outOfStandard": out_standard,
                "sla": sla,
                "fte": fte,
                "throughputBalance": throughput,
                "capacityStatus": "SHORTFALL" if throughput is not None and throughput < 0 else "SUFFICIENT",
                "confidence": confidence_by_horizon(confidence, step),
                "expectedRange": expected_range,
                "drivers": drivers,
                "inventoryMethod": "Prior projected inventory + projected receipts - projected closures.",
            }
        )
        prior_inventory = inventory
        prior_oos = out_standard

    crossover = next((item["period"] for item in projections[1:] if (item.get("throughputBalance") or 0) > 0), None)
    target_inventory = operational_backlog_target(latest)
    clearance = next((item["period"] for item in projections[1:] if item.get("inventory") is not None and item["inventory"] <= target_inventory), None)
    return {
        "id": context_id(business_unit, work_category),
        "businessUnit": business_unit,
        "workCategory": work_category,
        "basePeriod": latest["period"],
        "operationalBasePeriod": latest_operational["period"],
        "historyPeriods": history_periods,
        "maturity": maturity,
        "confidence": confidence,
        "primaryDrivers": drivers,
        "operationalBacklogTarget": target_inventory,
        "crossoverPeriod": crossover,
        "clearancePeriod": clearance,
        "projection": projections,
    }


def latest_operational_row(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in reversed(history):
        if row.get("monthlyReceipts") is not None and row.get("monthlyClosures") is not None:
            return row
    return None


def adaptive_slope(history: list[dict[str, Any]], field: str) -> float:
    values = [row.get(field) for row in history if row.get(field) is not None]
    if len(values) < 2:
        return 0.0
    recent = values[-4:] if len(values) >= 4 else values
    pairwise = [recent[index] - recent[index - 1] for index in range(1, len(recent))]
    return round(mean(pairwise), 4) if pairwise else 0.0


def project_value(current: float | None, slope: float, step: int) -> float | None:
    if current is None:
        return None
    return round(max(0, current + slope * step), 2)


def forecast_maturity(history_periods: int) -> str:
    if history_periods >= 18:
        return "ADVANCED_HISTORY_READY"
    if history_periods >= 12:
        return "SEASONAL_HISTORY_READY"
    if history_periods >= 8:
        return "TREND_HISTORY_READY"
    return "LIMITED_HISTORY_DIRECTIONAL"


def forecast_confidence(history: list[dict[str, Any]]) -> dict[str, Any]:
    history_periods = len(history)
    missing_penalty = 0
    for field in ("monthlyReceipts", "monthlyClosures", "startingInventory", "outOfStandard", "monthlyStartingSla", "ftes"):
        if any(row.get(field) is None for row in history[-3:]):
            missing_penalty += 1
    volatility = volatility_score(history, "monthlyStartingSla")
    score = 0.35 + min(0.35, history_periods * 0.025) - missing_penalty * 0.04 - volatility * 0.25
    score = clamp(score)
    if score >= 0.68:
        label = "High"
    elif score >= 0.48:
        label = "Medium"
    else:
        label = "Low"
    return {
        "label": label,
        "score": round(score, 2),
        "rationale": confidence_rationale(history_periods, missing_penalty, volatility),
    }


def volatility_score(history: list[dict[str, Any]], field: str) -> float:
    values = [row.get(field) for row in history[-6:] if row.get(field) is not None]
    if len(values) < 3:
        return 0.25
    return clamp(stddev(values) / max(0.01, abs(mean(values))))


def confidence_rationale(history_periods: int, missing_penalty: int, volatility: float) -> str:
    parts = [f"{history_periods} historical periods available"]
    if missing_penalty:
        parts.append("recent fields are incomplete")
    if volatility > 0.12:
        parts.append("recent SLA is volatile")
    if history_periods < 8:
        parts.append("forecast is directional until more history is loaded")
    return "; ".join(parts) + "."


def confidence_by_horizon(confidence: dict[str, Any], step: int) -> dict[str, Any]:
    score = clamp((confidence.get("score") or 0) - step * 0.06)
    label = "High" if score >= 0.68 else "Medium" if score >= 0.48 else "Low"
    return {"label": label, "score": round(score, 2), "rationale": confidence.get("rationale")}


def forecast_range(sla: float | None, confidence: dict[str, Any], step: int) -> dict[str, float] | None:
    if sla is None:
        return None
    width = (0.025 + step * 0.015) * (1.4 - (confidence.get("score") or 0.4))
    return {"low": round(clamp(sla - width), 4), "high": round(clamp(sla + width), 4)}


def forecast_drivers(history: list[dict[str, Any]]) -> list[str]:
    latest = history[-1]
    drivers = []
    receipts_change = latest.get("receiptsPctChange")
    production_change = latest.get("productionPctChange")
    if receipts_change is not None and abs(receipts_change) >= 0.05:
        drivers.append(f"receipts trending {receipts_change:+.0%}")
    if production_change is not None and abs(production_change) >= 0.05:
        drivers.append(f"production trending {production_change:+.0%}")
    if (latest.get("fteChange") or 0) != 0:
        drivers.append(f"FTE changed by {format_number(latest.get('fteChange'))}")
    if (latest.get("outOfStandardChange") or 0) > 0:
        drivers.append(f"OOS inventory increased by {format_number(latest.get('outOfStandardChange'))}")
    if latest.get("throughputBalance") is not None:
        if latest["throughputBalance"] >= 0:
            drivers.append("closures are exceeding receipts")
        else:
            drivers.append("receipts are exceeding closures")
    if len(history) >= 12:
        drivers.append("enough history exists to begin seasonality checks")
    return drivers[:5] or ["limited movement detected in recent source data"]


def operational_backlog_target(row: dict[str, Any]) -> float:
    starting = row.get("startingInventory") or 0
    target = starting * 0.10
    return round(max(target, row.get("outOfStandard") or 0), 2)


def add_months(period: str, offset: int) -> str:
    year, month = [int(part) for part in period.split("-")]
    month += offset
    while month > 12:
        year += 1
        month -= 12
    return f"{year}-{month:02d}"


def build_contexts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contexts = [row for row in rows if row["businessUnit"] != "Aggregated Total"]
    output = []
    for row in contexts:
        output.append(
            {
                "id": context_id(row["businessUnit"], row["workCategory"]),
                "businessUnit": row["businessUnit"],
                "workCategory": row["workCategory"],
                "period": row["period"],
                "status": row.get("status"),
                "riskScore": row.get("riskScore"),
                "pressureTypes": row.get("pressureTypes", []),
                "earlyWarning": row.get("earlyWarning", {}),
                "confidence": row.get("confidenceLabel"),
                "brief": intelligence_brief(row),
                "driverBars": driver_bars(row),
                "metrics": compact_metrics(row),
                "whatWouldItTake": what_would_it_take(row),
                "ifNothingChanges": if_nothing_changes(row),
            }
        )
    return output


def context_id(business_unit: str, work_category: str) -> str:
    return f"{business_unit}::{work_category}"


def compact_metrics(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sla": row.get("monthlyStartingSla") or row.get("calculatedSla"),
        "sourceSla": row.get("monthlyStartingSla"),
        "calculatedSla": row.get("calculatedSla"),
        "targetSla": SLA_TARGET,
        "slaChange": row.get("slaChange"),
        "startingInventory": row.get("startingInventory"),
        "inventoryChange": row.get("inventoryPctChange"),
        "outOfStandard": row.get("outOfStandard"),
        "outOfStandardChange": row.get("outOfStandardChange"),
        "receipts": row.get("monthlyReceipts"),
        "receiptsChange": row.get("receiptsPctChange"),
        "closures": row.get("monthlyClosures"),
        "closuresChange": row.get("closuresPctChange"),
        "gap": row.get("receiptClosureGap"),
        "throughputBalance": row.get("throughputBalance"),
        "fte": row.get("ftes"),
        "fteChange": row.get("fteChange"),
        "productionToReceiptsRatio": row.get("productionToReceiptsRatio"),
        "capacityGap": row.get("estimatedCapacityGap"),
        "capacityStatus": row.get("capacityStatus"),
    }


def intelligence_brief(row: dict[str, Any]) -> dict[str, str]:
    drivers = driver_list(row)
    sla = row.get("monthlyStartingSla") or row.get("calculatedSla")
    return {
        "whatChanged": summarize_change(row),
        "whyItMatters": f"{row['businessUnit']} {row['workCategory']} is {status_label(row.get('status'))} with SLA at {format_percent(sla)}.",
        "staffing": staffing_sentence(row),
        "earlyWarning": "; ".join(row.get("earlyWarning", {}).get("evidence", [])[:2]) if row.get("earlyWarning", {}).get("active") else "No active early-warning signal in this period.",
        "outlook": if_nothing_changes(row)["summary"],
        "evidence": "; ".join(drivers[:4]),
    }


def summarize_change(row: dict[str, Any]) -> str:
    pieces = []
    if row.get("slaChange") is not None:
        pieces.append(f"SLA moved {row['slaChange'] * 100:+.0f} pts")
    if row.get("outOfStandardChange") is not None:
        pieces.append(f"OOS moved {format_number(row['outOfStandardChange'])}")
    if row.get("receiptClosureGap") is not None:
        pieces.append(f"gap is {format_number(row['receiptClosureGap'])}")
    return ", ".join(pieces) + "." if pieces else "Current period movement is limited by available history."


def staffing_sentence(row: dict[str, Any]) -> str:
    if row.get("ftes") is None:
        return "Staffing data is not available for this selected period."
    if row.get("productionToReceiptsRatio") is not None:
        return f"Production is {format_percent(row.get('productionToReceiptsRatio'))} of receipts for this workload bucket; FTE capacity actions should be interpreted at the department grain unless reliable bucket allocation is supplied."
    return "FTE is present in the source, but bucket-level staffing allocation should not be treated as precise unless the source explicitly supports it."


def status_label(status: str | None) -> str:
    return {
        "MEETING_TARGET": "meeting target",
        "WATCH": "on watch",
        "AT_RISK": "at risk",
        "CRITICAL": "critical",
        "NO_DATA": "missing SLA context",
    }.get(status or "", "under review")


def driver_bars(row: dict[str, Any]) -> list[dict[str, Any]]:
    drivers = [
        ("Receipt Growth", abs(row.get("receiptsPctChange") or 0), "Receipt movement is historically associated with workload pressure."),
        ("Closure Decline", abs(min(0, row.get("closuresPctChange") or 0)), "Closure deterioration can widen the flow gap."),
        ("Workload Pressure", max(0, row.get("receiptClosureGap") or 0) / max(1, row.get("startingInventory") or 1), "Workload bucket pressure based on receipts, closures, and inventory; not a bucket-level FTE allocation claim."),
        ("OOS Movement", abs(row.get("outOfStandardChange") or 0) / max(1, row.get("startingInventory") or 1), "Out-of-standard movement affects SLA risk."),
        ("Flow Gap", max(0, row.get("receiptClosureGap") or 0) / max(1, row.get("startingInventory") or 1), "Receipts above closures create inventory pressure."),
        ("Reroutes", abs(row.get("monthlyReroutes") or 0) / max(1, row.get("startingInventory") or 1), "Reroutes can affect operational flow."),
    ]
    max_value = max([value for _, value, _ in drivers], default=0) or 1
    return [
        {"label": label, "strength": round(clamp(value / max_value), 4), "rawValue": round(value, 6), "note": note}
        for label, value, note in sorted(drivers, key=lambda item: item[1], reverse=True)
        if value > 0
    ][:5]


def what_would_it_take(row: dict[str, Any]) -> dict[str, Any]:
    starting = row.get("startingInventory") or 0
    out_standard = row.get("outOfStandard") or 0
    current_sla = row.get("monthlyStartingSla") or row.get("calculatedSla")
    target_oos = max(0, starting * (1 - SLA_TARGET))
    oos_reduction_needed = max(0, out_standard - target_oos)
    closures_per_fte = row.get("closuresPerFte")
    estimated_fte = safe_divide(oos_reduction_needed, closures_per_fte) if closures_per_fte else None
    productivity_needed = safe_divide(oos_reduction_needed, row.get("monthlyClosures"))
    return {
        "target": "Reach 90% SLA",
        "currentSla": current_sla,
        "oosReductionNeeded": round(oos_reduction_needed, 2),
        "estimatedFteEquivalent": None if estimated_fte is None else round(estimated_fte, 2),
        "estimatedProductivityLift": productivity_needed,
        "assumption": "Directional estimate using current closures per FTE; not a causal staffing model.",
    }


def if_nothing_changes(row: dict[str, Any]) -> dict[str, Any]:
    oos = row.get("outOfStandard") or 0
    oos_change = row.get("outOfStandardChange") or 0
    inv = row.get("startingInventory") or 0
    inv_change = (row.get("inventoryPctChange") or 0) * inv
    projected_oos = max(0, oos + oos_change)
    projected_inventory = max(0, inv + inv_change)
    projected_sla = 1 - (projected_oos / projected_inventory) if projected_inventory else None
    return {
        "projectedInventory": round(projected_inventory, 2),
        "projectedOutOfStandard": round(projected_oos, 2),
        "projectedSla": None if projected_sla is None else round(clamp(projected_sla), 4),
        "summary": f"If current trends continue, next-period SLA trends near {format_percent(projected_sla)} with OOS around {format_number(projected_oos)}.",
        "method": "Directional continuation of recent inventory and OOS movement.",
    }


def build_heatmap(rows: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        if row["period"] == period and row["businessUnit"] != "Aggregated Total":
            output.append(
                {
                    "id": context_id(row["businessUnit"], row["workCategory"]),
                    "businessUnit": row["businessUnit"],
                    "workCategory": row["workCategory"],
                    "status": row.get("status"),
                    "riskScore": row.get("riskScore"),
                    "sla": row.get("monthlyStartingSla") or row.get("calculatedSla"),
                    "outOfStandard": row.get("outOfStandard"),
                    "pressureTypes": row.get("pressureTypes", []),
                    "earlyWarning": row.get("earlyWarning", {}).get("active", False),
                }
            )
    return sorted(output, key=lambda item: (item["businessUnit"], item["workCategory"]))


def build_biggest_movers(rows: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    latest = [row for row in rows if row["period"] == period and row["businessUnit"] != "Aggregated Total"]
    mover_specs = [
        ("SLA Deterioration", "slaChange", "asc", "SLA"),
        ("SLA Improvement", "slaChange", "desc", "SLA"),
        ("Inventory Increase", "inventoryPctChange", "desc", "Inventory"),
        ("Inventory Reduction", "inventoryPctChange", "asc", "Inventory"),
        ("Receipt Surge", "receiptsPctChange", "desc", "Receipts"),
        ("Closure Drop", "closuresPctChange", "asc", "Closures"),
        ("OOS Increase", "outOfStandardChange", "desc", "Out of Standard"),
        ("FTE Movement", "fteChange", "abs", "FTE"),
    ]
    movers = []
    for title, field, direction, metric in mover_specs:
        candidates = [row for row in latest if row.get(field) is not None]
        if not candidates:
            continue
        if direction == "asc":
            selected = min(candidates, key=lambda item: item.get(field) or 0)
        elif direction == "desc":
            selected = max(candidates, key=lambda item: item.get(field) or 0)
        else:
            selected = max(candidates, key=lambda item: abs(item.get(field) or 0))
        value = selected.get(field)
        unusual = bool(selected.get("anomalySignals"))
        movers.append(
            {
                "title": title,
                "metric": metric,
                "businessUnit": selected["businessUnit"],
                "workCategory": selected["workCategory"],
                "period": period,
                "value": value,
                "display": format_mover_value(field, value),
                "isUnusual": unusual,
                "context": "Unusual against recent pattern." if unusual else "Big movement; limited history for statistical unusualness.",
                "status": selected.get("status"),
            }
        )
    return movers


def format_mover_value(field: str, value: float | None) -> str:
    if value is None:
        return "n/a"
    if "Pct" in field or field == "slaChange":
        return f"{value * 100:+.1f} pts" if field == "slaChange" else f"{value:+.1%}"
    return f"{value:+,.0f}"


def build_workforce_pulse(rows: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    latest = [row for row in rows if row["period"] == period and row["businessUnit"] != "Aggregated Total"]
    weakest = max(latest, key=lambda row: row.get("riskScore") or 0)
    best_improvement = max([row for row in latest if row.get("slaChange") is not None], key=lambda row: row.get("slaChange") or 0, default=None)
    biggest_gap = max(latest, key=lambda row: row.get("receiptClosureGap") or 0)
    return [
        pulse_answer("Where should I look first?", weakest, "riskScore", "This is the highest combined risk context in the current period."),
        pulse_answer("What deteriorated most?", min(latest, key=lambda row: row.get("slaChange") if row.get("slaChange") is not None else 999), "slaChange", "This area had the largest SLA deterioration."),
        pulse_answer("Are receipts and closures balanced?", biggest_gap, "receiptClosureGap", "This area shows the largest positive receipt/closure gap."),
        pulse_answer("Where is staffing capacity tight?", max(latest, key=lambda row: row.get("estimatedCapacityGap") or 0), "estimatedCapacityGap", "This area has the largest estimated FTE-equivalent capacity gap."),
        pulse_answer("What improved?", best_improvement, "slaChange", "This area shows the strongest SLA improvement.") if best_improvement else {},
    ]


def pulse_answer(question: str, row: dict[str, Any] | None, metric: str, takeaway: str) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "question": question,
        "answer": f"{row['businessUnit']} {row['workCategory']}",
        "contextId": context_id(row["businessUnit"], row["workCategory"]),
        "takeaway": takeaway,
        "evidence": driver_list(row)[:4],
        "metric": metric,
        "value": row.get(metric),
        "status": row.get("status"),
    }


def build_correlation_explorer(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs = [
        ("FTE vs SLA", "ftes", "monthlyStartingSla"),
        ("FTE vs Closures", "ftes", "monthlyClosures"),
        ("Receipts vs Inventory", "monthlyReceipts", "startingInventory"),
        ("Receipts vs OOS", "monthlyReceipts", "outOfStandard"),
        ("Closures vs SLA", "monthlyClosures", "monthlyStartingSla"),
        ("Gap vs SLA", "receiptClosureGap", "monthlyStartingSla"),
        ("Inventory Pressure vs SLA", "inventoryPressureScore", "monthlyStartingSla"),
    ]
    output = []
    filtered = [row for row in rows if row["businessUnit"] != "Aggregated Total"]
    for label, x_field, y_field in pairs:
        points = [
            {
                "businessUnit": row["businessUnit"],
                "workCategory": row["workCategory"],
                "period": row["period"],
                "x": row.get(x_field),
                "y": row.get(y_field),
            }
            for row in filtered
            if row.get(x_field) is not None and row.get(y_field) is not None
        ]
        corr = correlation([point["x"] for point in points], [point["y"] for point in points])
        output.append(
            {
                "label": label,
                "xField": x_field,
                "yField": y_field,
                "correlation": corr,
                "observationCount": len(points),
                "interpretation": interpret_correlation(corr, len(points)),
                "points": points,
            }
        )
    return output


def correlation(x_values: list[float], y_values: list[float]) -> float | None:
    if len(x_values) < 3 or len(y_values) < 3 or len(x_values) != len(y_values):
        return None
    x_avg = mean(x_values)
    y_avg = mean(y_values)
    numerator = sum((x - x_avg) * (y - y_avg) for x, y in zip(x_values, y_values))
    x_den = math.sqrt(sum((x - x_avg) ** 2 for x in x_values))
    y_den = math.sqrt(sum((y - y_avg) ** 2 for y in y_values))
    if x_den == 0 or y_den == 0:
        return None
    return round(numerator / (x_den * y_den), 4)


def interpret_correlation(value: float | None, count: int) -> str:
    if value is None:
        return "Not enough varied observations to estimate a relationship."
    strength = "weak"
    if abs(value) >= 0.65:
        strength = "strong"
    elif abs(value) >= 0.35:
        strength = "moderate"
    direction = "positive" if value > 0 else "negative"
    caveat = " This is correlation, not causation."
    if count < 30:
        caveat += " History is limited, so treat this as directional."
    return f"{strength.capitalize()} {direction} association across {count} observations.{caveat}"


def build_meeting_mode(rows: list[dict[str, Any]], period: str) -> dict[str, Any]:
    latest = [row for row in rows if row["period"] == period and row["businessUnit"] != "Aggregated Total"]
    return {
        "period": period,
        "currentState": aggregate_for_period(rows, period),
        "topChange": mover_to_highlight(build_biggest_movers(rows, period), "OOS Increase"),
        "topImprovement": mover_to_highlight(build_biggest_movers(rows, period), "SLA Improvement"),
        "topDeterioration": mover_to_highlight(build_biggest_movers(rows, period), "SLA Deterioration"),
        "topEarlyWarning": row_highlight(max(latest, key=lambda row: 1 if row.get("earlyWarning", {}).get("active") else 0)),
        "topCapacityConcern": row_highlight(max(latest, key=lambda row: row.get("estimatedCapacityGap") or 0)),
        "outlook": row_highlight(max(latest, key=lambda row: row.get("riskScore") or 0)),
    }


def build_period_completeness(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required_operational = ("monthlyReceipts", "monthlyClosures", "ftes", "averageDailyReceipts", "averageDailyProduction")
    periods = sorted({row["period"] for row in rows})
    output = []
    for period in periods:
        period_rows = [row for row in rows if row["period"] == period and row["businessUnit"] != "Aggregated Total"]
        missing_fields = sorted({field for field in required_operational for row in period_rows if row.get(field) is None})
        output.append(
            {
                "period": period,
                "isFullOperationalPeriod": not missing_fields,
                "missingOperationalFields": missing_fields,
                "rowCount": len(period_rows),
            }
        )
    return output


def mover_to_highlight(movers: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    return next((item for item in movers if item["title"] == title), None)


def row_highlight(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "businessUnit": row["businessUnit"],
        "workCategory": row["workCategory"],
        "status": row.get("status"),
        "summary": intelligence_brief(row)["whyItMatters"],
        "evidence": driver_list(row)[:4],
    }


def validate_data(records: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    expected_units = {"CB", "GB", "CGS", "Aggregated Total"}
    expected_categories = {"Validation/Adjustments", "Disputes", "Correspondence", "Cash Posting", "Host", "All Work Categories"}
    units = {row["businessUnit"] for row in rows}
    categories = {row["workCategory"] for row in rows}
    if unexpected := sorted(units - expected_units):
        warnings.append({"severity": "warning", "type": "unexpected_business_unit", "summary": f"Unexpected business units: {', '.join(unexpected)}."})
    if unexpected := sorted(categories - expected_categories):
        warnings.append({"severity": "warning", "type": "unexpected_category", "summary": f"Unexpected work categories: {', '.join(unexpected)}."})
    for row in rows:
        if row.get("monthlyStartingSla") is not None and not 0 <= row["monthlyStartingSla"] <= 1:
            warnings.append({"severity": "error", "type": "impossible_sla", "summary": f"SLA outside 0-100% for {row['businessUnit']} {row['workCategory']} {row['period']}."})
        if row.get("ftes") == 0 and (row.get("monthlyClosures") or 0) > 0:
            warnings.append({"severity": "warning", "type": "zero_fte_with_closures", "summary": f"Closures exist with zero FTE for {row['businessUnit']} {row['workCategory']} {row['period']}."})
    periods_by_metric: dict[str, set[str]] = defaultdict(set)
    for record in records:
        periods_by_metric[record["metric"]].add(record["period"])
    for metric in KNOWN_METRICS:
        if metric not in periods_by_metric:
            warnings.append({"severity": "warning", "type": "missing_metric", "summary": f"{metric} was not found in the source report."})
    for item in build_period_completeness(rows):
        if not item["isFullOperationalPeriod"]:
            warnings.append(
                {
                    "severity": "warning",
                    "type": "incomplete_period",
                    "summary": f"{item['period']} is missing operational fields: {', '.join(item['missingOperationalFields'])}.",
                }
            )
    return warnings[:30]


def build_model_diagnostics(rows: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    periods = sorted({row["period"] for row in rows})
    observations_by_context = defaultdict(int)
    for row in rows:
        if row["businessUnit"] != "Aggregated Total":
            observations_by_context[context_id(row["businessUnit"], row["workCategory"])] += 1
    min_obs = min(observations_by_context.values()) if observations_by_context else 0
    return {
        "analyticalMaturity": "PHASE_1_LIMITED_HISTORY" if len(periods) < 8 or min_obs < 6 else "PHASE_2_READY",
        "historyPeriods": periods,
        "minimumObservationsPerContext": min_obs,
        "enabledMethods": ["descriptive", "diagnostic", "rule_based_early_warning", "directional_forecast", "correlation_scan"],
        "deferredMethods": ["robust_anomaly_detection", "model_backtesting", "learned_driver_importance", "seasonality", "change_point_detection"],
        "confidenceRationale": "Only five source periods are currently available, and operational metrics are missing for September. Outputs are directional until more history is loaded.",
        "dataQualityWarningCount": len(warnings),
    }


def next_month(period: str) -> str:
    year, month = [int(part) for part in period.split("-")]
    month += 1
    if month == 13:
        year += 1
        month = 1
    return f"{year}-{month:02d}"


def format_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0%}"


def build_payload(source_files: list[Path], sheet_name: str | None = None) -> dict[str, Any]:
    records, source_blocks, source_stats = merge_source_files(source_files, sheet_name)
    if not records:
        sources = "\n".join(f"  - {path}" for path in source_files)
        raise SystemExit(
            "No usable dashboard records were found in the source files.\n"
            "Check that the report has the expected Staffing and Inventory layout and includes metric headers such as "
            "'Monthly Starting SLA %', 'Starting Inventory', 'Monthly Receipts', and 'FTE''s'.\n"
            f"Source files checked:\n{sources}"
        )
    feature_rows = pivot_feature_rows(records)
    if not feature_rows:
        sources = "\n".join(f"  - {path}" for path in source_files)
        raise SystemExit(
            "The source files were read, but no feature rows could be built for the dashboard.\n"
            "Check that the report includes business units, work categories, month columns, and numeric values.\n"
            f"Source files checked:\n{sources}"
        )
    data_quality_warnings = validate_data(records, feature_rows)
    latest = latest_period(feature_rows)
    full_context = latest_full_context_period(feature_rows)
    return {
        "metadata": {
            "lastRefreshed": dt.datetime.now().replace(microsecond=0).isoformat(),
            "sourceFile": str(source_files[0]) if len(source_files) == 1 else "multiple input files",
            "sourceFiles": [str(path) for path in source_files],
            "sourceStoreFile": str(SOURCE_STORE_FILE),
            "sourceMerge": source_stats,
            "sourceSheet": sheet_name,
            "recordCount": len(records),
            "featureRows": len(feature_rows),
            "latestPeriod": latest,
            "latestFullContextPeriod": full_context,
            "periods": sorted({row["period"] for row in feature_rows}),
            "sourceBlocks": source_blocks,
            "periodCompleteness": build_period_completeness(feature_rows),
            "businessUnits": sorted({row["businessUnit"] for row in feature_rows if row["businessUnit"] != "Aggregated Total"}),
            "workCategories": sorted({row["workCategory"] for row in feature_rows if row["workCategory"] != "All Work Categories"}),
            "metrics": sorted(KNOWN_METRICS),
            "slaTarget": SLA_TARGET,
        },
        "records": records,
        "features": feature_rows,
        "summary": aggregate_latest(feature_rows),
        "operationalSummary": aggregate_for_period(feature_rows, full_context),
        "analytics": {
            "contexts": build_contexts(feature_rows),
            "heatmap": build_heatmap(feature_rows, full_context),
            "enterprisePulse": build_workforce_pulse(feature_rows, full_context),
            "biggestMovers": build_biggest_movers(feature_rows, full_context),
            "insights": generate_insights(feature_rows),
            "forecasts": generate_forecasts(feature_rows),
            "forecastEngine": generate_forecast_engine(feature_rows),
            "departmentCapacity": build_department_capacity(feature_rows),
            "correlationExplorer": build_correlation_explorer(feature_rows),
            "meetingMode": build_meeting_mode(feature_rows, full_context),
            "dataQuality": {"warnings": data_quality_warnings},
            "modelDiagnostics": build_model_diagnostics(feature_rows, data_quality_warnings),
            "modelContext": {
                "grain": "business_unit_work_category_month",
                "slaTarget": SLA_TARGET,
                "signals": [
                    "starting inventory",
                    "in standard",
                    "out of standard",
                    "SLA",
                    "receipts",
                    "closures",
                    "receipt/closure gap",
                    "reroutes",
                    "average daily receipts",
                    "average daily production",
                    "FTE",
                    "hourly goal",
                ],
            },
        },
    }


def input_source_files() -> list[Path]:
    if not INPUT_DIR.exists():
        return []
    candidates = [
        path
        for path in INPUT_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES
    ]
    for year_dir in sorted(path for path in INPUT_DIR.iterdir() if path.is_dir() and re.fullmatch(r"20\d{2}", path.name)):
        candidates.extend(
            path
            for path in year_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES
        )
    return sorted(candidates)


def default_source_files() -> list[Path]:
    input_files = input_source_files()
    return input_files if input_files else [DEFAULT_SOURCE_FILE]


def load_source_store() -> list[dict[str, Any]]:
    if not SOURCE_STORE_FILE.exists():
        return []
    document = json.loads(SOURCE_STORE_FILE.read_text(encoding="utf-8"))
    return document.get("records", [])


def write_source_store(records: list[dict[str, Any]]) -> None:
    SOURCE_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "updatedAt": dt.datetime.now().replace(microsecond=0).isoformat(),
        "periods": sorted({record["period"] for record in records}),
        "recordCount": len(records),
        "records": records,
    }
    SOURCE_STORE_FILE.write_text(json.dumps(document, indent=2), encoding="utf-8")


def merge_source_files(source_files: list[Path], sheet_name: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    stored_records = load_source_store()
    accepted_periods = {record["period"] for record in stored_records}
    packets = []
    for source_file in source_files:
        parsed_records, parsed_blocks = parse_source(source_file, sheet_name)
        periods = sorted({record["period"] for record in parsed_records})
        packets.append(
            {
                "sourceFile": source_file,
                "sourceYear": infer_source_year(source_file),
                "records": parsed_records,
                "blocks": parsed_blocks,
                "periods": periods,
            }
        )

    packets.sort(key=lambda packet: (packet["periods"][0] if packet["periods"] else "9999-99", str(packet["sourceFile"]).lower()))

    merged_records: list[dict[str, Any]] = list(stored_records)
    merged_blocks: list[dict[str, Any]] = []
    source_stats: list[dict[str, Any]] = [
        {
            "sourceFile": str(SOURCE_STORE_FILE),
            "acceptedPeriods": sorted(accepted_periods),
            "skippedDuplicatePeriods": [],
            "role": "existing source data before this run",
        }
    ] if stored_records else []

    for packet in packets:
        source_file = packet["sourceFile"]
        periods = packet["periods"]
        new_periods = [period for period in periods if period not in accepted_periods]
        skipped_periods = [period for period in periods if period in accepted_periods]
        new_period_set = set(new_periods)

        merged_records.extend(record for record in packet["records"] if record["period"] in new_period_set)
        for block in packet["blocks"]:
            month_labels = [label for label in block["monthLabels"] if month_key(label, packet["sourceYear"]) in new_period_set]
            if month_labels:
                merged_blocks.append({**block, "sourceFile": str(source_file), "monthLabels": month_labels})

        accepted_periods.update(new_period_set)
        source_stats.append(
            {
                "sourceFile": str(source_file),
                "acceptedPeriods": new_periods,
                "skippedDuplicatePeriods": skipped_periods,
            }
        )

    merged_records.sort(
        key=lambda record: (
            record["period"],
            record["businessUnit"],
            record["workCategory"],
            record["metric"],
        )
    )
    return merged_records, merged_blocks, source_stats


def write_dashboard_data(payload: dict[str, Any]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    document = f"{DATA_HEADER}\nwindow.DASHBOARD_DATA = {json.dumps(payload, indent=2)};\n"
    DATA_FILE.write_text(document, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Staffing and Inventory dashboard data file.")
    parser.add_argument(
        "source_file",
        nargs="?",
        help=(
            "Optional source report to read. If omitted, the updater reads all supported files directly "
            "inside input/, or falls back to Sample Report.txt. Supports .txt, .csv, .xlsx, and .xlsm files."
        ),
    )
    parser.add_argument(
        "--sheet",
        help="Worksheet name to read when the source file is Excel. Defaults to the active worksheet.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_files = [Path(args.source_file)] if args.source_file else default_source_files()
    source_files = [path if path.is_absolute() else BASE_DIR / path for path in source_files]
    missing_files = [path for path in source_files if not path.exists()]
    if missing_files:
        raise SystemExit(f"Source file not found: {missing_files[0]}")
    payload = build_payload(source_files, args.sheet)
    write_source_store(payload["records"])
    write_dashboard_data(payload)
    print(f"Wrote {DATA_FILE}")
    print(f"Updated source data: {SOURCE_STORE_FILE}")
    print(f"Source files: {len(source_files)}")
    for source_file in source_files:
        print(f"  - {source_file}")
    if args.sheet:
        print(f"Source sheet: {args.sheet}")
    print(f"Normalized records: {payload['metadata']['recordCount']}")
    print(f"Feature rows: {payload['metadata']['featureRows']}")
    print(f"Latest period: {payload['metadata']['latestPeriod']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
