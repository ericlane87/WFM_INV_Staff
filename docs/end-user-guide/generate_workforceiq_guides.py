#!/usr/bin/env python3
"""Generate WorkforceIQ end-user guide deliverables.

The script intentionally reads the current local dashboard and generated data,
captures real screenshots, annotates them, and creates user-facing PDF/DOCX
training materials without modifying application files.
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as RLImage,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parents[1]
ASSETS_DIR = SCRIPT_DIR / "assets"
DASHBOARD_HTML = PROJECT_DIR / "dashboard.html"
DATA_JS = PROJECT_DIR / "data" / "dashboard-data.js"
COMPLETE_PDF = SCRIPT_DIR / "WorkforceIQ - Complete End-User Guide.pdf"
COMPLETE_DOCX = SCRIPT_DIR / "WorkforceIQ - Complete End-User Guide.docx"
QUICK_PDF = SCRIPT_DIR / "WorkforceIQ - Quick Start Guide.pdf"
HTML_SOURCE = SCRIPT_DIR / "WorkforceIQ - Complete End-User Guide.html"

BLUE = colors.HexColor("#123a66")
NAVY = colors.HexColor("#102642")
TEAL = colors.HexColor("#0d7f86")
GREEN = colors.HexColor("#177245")
YELLOW = colors.HexColor("#b77916")
RED = colors.HexColor("#bc3434")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#66758b")
LIGHT = colors.HexColor("#f3f5f8")
LINE = colors.HexColor("#d8e0ea")


@dataclass
class Section:
    title: str
    body: list


def load_data() -> dict:
    text = DATA_JS.read_text(encoding="utf-8")
    match = re.search(r"window\.DASHBOARD_DATA\s*=\s*(\{.*\});\s*$", text, re.S)
    if not match:
        raise RuntimeError("Could not parse data/dashboard-data.js")
    return json.loads(match.group(1))


def capture_screenshots() -> dict[str, Path]:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    raw_overview = ASSETS_DIR / "dashboard_overview_raw.png"
    raw_forecast = ASSETS_DIR / "dashboard_forecast_raw.png"
    raw_flow = ASSETS_DIR / "dashboard_flow_raw.png"
    overview = ASSETS_DIR / "dashboard_overview_annotated.png"
    forecast = ASSETS_DIR / "dashboard_forecast_annotated.png"
    flow = ASSETS_DIR / "dashboard_flow_annotated.png"

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
            page.goto(DASHBOARD_HTML.resolve().as_uri(), wait_until="load")
            page.wait_for_timeout(3600)
            page.screenshot(path=str(raw_overview), full_page=False)

            page.select_option("#businessFilter", "GB")
            page.select_option("#categoryFilter", "Disputes")
            page.select_option("#viewModeFilter", "forecast")
            page.wait_for_timeout(700)
            page.screenshot(path=str(raw_forecast), full_page=False)

            page.select_option("#businessFilter", "All")
            page.select_option("#categoryFilter", "All")
            page.select_option("#viewModeFilter", "flow")
            page.wait_for_timeout(700)
            page.screenshot(path=str(raw_flow), full_page=False)
            browser.close()
    except Exception as exc:
        print(f"Screenshot capture warning: {exc}")
        make_placeholder(raw_overview, "Dashboard screenshot unavailable")
        make_placeholder(raw_forecast, "Forecast screenshot unavailable")
        make_placeholder(raw_flow, "Flow screenshot unavailable")

    annotate(
        raw_overview,
        overview,
        [
            (1, 1220, 44, "data freshness"),
            (2, 80, 150, "executive KPI cards"),
            (3, 95, 640, "filters"),
            (4, 410, 420, "dashboard tabs"),
            (5, 1120, 540, "intelligence rail"),
        ],
    )
    annotate(
        raw_forecast,
        forecast,
        [
            (1, 80, 640, "specific BU/category filters"),
            (2, 430, 385, "scenario controls"),
            (3, 410, 610, "forecast chart"),
            (4, 1030, 610, "crossover and goal tiles"),
            (5, 525, 842, "forecast table"),
        ],
    )
    annotate(
        raw_flow,
        flow,
        [
            (1, 430, 360, "throughput balance"),
            (2, 440, 600, "burn-down runway"),
            (3, 1045, 615, "run-rate timing"),
            (4, 470, 875, "receipts vs closures"),
        ],
    )
    return {"overview": overview, "forecast": forecast, "flow": flow}


def make_placeholder(path: Path, title: str) -> None:
    image = Image.new("RGB", (1440, 1050), "#f3f5f8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 100, 1360, 950), outline="#123a66", width=3)
    draw.text((140, 170), title, fill="#123a66")
    image.save(path)


def font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                pass
    return ImageFont.load_default()


def annotate(source: Path, target: Path, callouts: list[tuple[int, int, int, str]]) -> None:
    image = Image.open(source).convert("RGB")
    draw = ImageDraw.Draw(image)
    f_num = font(22, True)
    f_label = font(16, True)
    for number, x, y, label_text in callouts:
        r = 20
        draw.ellipse((x - r, y - r, x + r, y + r), fill="#bc3434", outline="white", width=3)
        label_number = str(number)
        bbox = draw.textbbox((0, 0), label_number, font=f_num)
        draw.text((x - (bbox[2] - bbox[0]) / 2, y - (bbox[3] - bbox[1]) / 2 - 1), label_number, fill="white", font=f_num)
        text = f"{number}. {label_text}"
        tb = draw.textbbox((0, 0), text, font=f_label)
        tx = min(max(12, x + 28), image.width - (tb[2] - tb[0]) - 24)
        ty = min(max(12, y - 18), image.height - 42)
        draw.rounded_rectangle((tx - 8, ty - 6, tx + (tb[2] - tb[0]) + 8, ty + 28), radius=7, fill="white", outline="#123a66", width=2)
        draw.text((tx, ty), text, fill="#123a66", font=f_label)
    image.save(target)


def styles():
    sample = getSampleStyleSheet()
    out = {
        "Title": ParagraphStyle(
            "GuideTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=34,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "Subtitle": ParagraphStyle(
            "Subtitle",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=13,
            leading=18,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "H1": ParagraphStyle(
            "H1",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=23,
            textColor=BLUE,
            spaceBefore=14,
            spaceAfter=8,
        ),
        "H2": ParagraphStyle(
            "H2",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=TEAL,
            spaceBefore=10,
            spaceAfter=5,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.2,
            textColor=INK,
            spaceAfter=6,
        ),
        "Small": ParagraphStyle(
            "Small",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=10.5,
            textColor=INK,
        ),
        "Callout": ParagraphStyle(
            "Callout",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=13,
            textColor=NAVY,
            backColor=colors.HexColor("#eef4fa"),
            borderColor=colors.HexColor("#c8d5e4"),
            borderWidth=0.8,
            borderPadding=7,
            spaceBefore=5,
            spaceAfter=8,
        ),
        "TOC": ParagraphStyle(
            "TOC",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=BLUE,
            leftIndent=12,
            spaceAfter=3,
        ),
    }
    return out


class Bookmark(Paragraph):
    def __init__(self, text: str, style: ParagraphStyle, key: str, level: int = 0):
        super().__init__(text, style)
        self.key = key
        self.level = level
        self.clean_text = re.sub("<[^>]+>", "", text)

    def draw(self):
        self.canv.bookmarkPage(self.key)
        self.canv.addOutlineEntry(self.clean_text, self.key, level=self.level, closed=False)
        super().draw()


def P(text: str, style: ParagraphStyle | None = None) -> Paragraph:
    return Paragraph(text, style or ST["Body"])


def bullets(items: Iterable[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(P(item, ST["Body"]), bulletColor=BLUE) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=16,
        bulletFontName="Helvetica",
        bulletFontSize=6,
    )


def nums(items: Iterable[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(P(item, ST["Body"])) for item in items],
        bulletType="1",
        leftIndent=20,
    )


def guide_table(rows: list[list[str]], widths: list[float] | None = None) -> Table:
    data = [[P(cell, ST["Small"]) for cell in row] for row in rows]
    table = Table(data, colWidths=widths, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def image_flowable(path: Path, width: float = 7.2 * inch) -> RLImage:
    with Image.open(path) as img:
        ratio = img.height / img.width
    return RLImage(str(path), width=width, height=width * ratio)


def callout(text: str) -> Paragraph:
    return P(text, ST["Callout"])


def chapter(title: str, anchor: str):
    return [Bookmark(title, ST["H1"], anchor, 0)]


def build_sections(data: dict, shots: dict[str, Path]) -> list:
    latest = data["metadata"].get("latestPeriod", "latest period")
    full = data["metadata"].get("latestFullContextPeriod", latest)
    refreshed = data["metadata"].get("lastRefreshed", "available refresh time")
    periods = ", ".join(data["metadata"].get("periods", []))
    story: list = []

    story += [
        Spacer(1, 1.2 * inch),
        P("WorkforceIQ", ST["Title"]),
        P("Complete End-User Guide", ST["Title"]),
        P("Training and reference manual for operational leaders, WFM teams, analysts, managers, and executive stakeholders.", ST["Subtitle"]),
        Spacer(1, 0.2 * inch),
        guide_table(
            [
                ["Document", "Details"],
                ["Application", "WorkforceIQ Staffing and Inventory Intelligence Dashboard"],
                ["Generated From", "Current local dashboard.html and generated dashboard data"],
                ["Last Dashboard Refresh", refreshed],
                ["Latest Source Period", latest],
                ["Latest Full Operational Period", full],
            ],
            [2.1 * inch, 4.7 * inch],
        ),
        Spacer(1, 0.5 * inch),
        callout("This guide explains what users can see and do in the current WorkforceIQ dashboard. Forecasts and intelligence signals are directional planning aids, not guaranteed outcomes or trained machine-learning predictions."),
        PageBreak(),
        Bookmark("Table of Contents", ST["H1"], "toc", 0),
    ]
    toc = [
        ("Chapter 1 - Welcome to WorkforceIQ", "ch1"),
        ("Chapter 2 - Getting Started and Navigation", "ch2"),
        ("Chapter 3 - Understanding the Executive KPI Cards", "ch3"),
        ("Chapter 4 - Workforce Pulse", "ch4"),
        ("Chapter 5 - Flow: Understanding Workload Movement", "ch5"),
        ("Chapter 6 - Staffing and Productive Capacity", "ch6"),
        ("Chapter 7 - Forecast: Understanding What May Happen Next", "ch7"),
        ("Chapter 8 - Interactive What-If Forecasting", "ch8"),
        ("Chapter 9 - Intelligence: Understanding Operational Drivers", "ch9"),
        ("Chapter 10 - Detail: Reviewing Actual Operational Information", "ch10"),
        ("Chapter 11 - Understanding the Intelligence Rail", "ch11"),
        ("Chapter 12 - Practical WorkforceIQ Walkthroughs", "ch12"),
        ("Chapter 13 - WorkforceIQ Metric Glossary", "ch13"),
        ("Chapter 14 - Frequently Asked Questions and Troubleshooting", "ch14"),
    ]
    for label, anchor in toc:
        story.append(P(f'<a href="#{anchor}">{label}</a>', ST["TOC"]))
    story.append(PageBreak())

    story += chapter("Chapter 1 - Welcome to WorkforceIQ", "ch1")
    story += [
        P("WorkforceIQ is a local operational intelligence dashboard that turns staffing, inventory, receipts, closures, SLA, production, and FTE information into practical decision support. Instead of asking users to scan a wide spreadsheet and infer the story manually, WorkforceIQ organizes the same operational information into health indicators, drill-down views, and short-range directional forecasts."),
        P("The dashboard is designed for operational leadership, department managers, Workforce Management personnel, business analysts, operational associates, and executive stakeholders. It helps these users quickly understand where work is moving, where service-level pressure exists, whether productive capacity appears sufficient, and which areas may need further investigation."),
        callout("WorkforceIQ does not replace operational judgment. It helps focus attention by translating reporting data into clear signals, explanations, and planning scenarios."),
        P("The primary business questions WorkforceIQ helps answer are:"),
        bullets(
            [
                "Are we meeting operational expectations?",
                "Is backlog increasing or decreasing?",
                "Are receipts and closures balanced?",
                "Do we have sufficient productive capacity to keep pace with incoming work?",
                "Which business units or work categories need attention?",
                "What operational signals may be contributing to pressure?",
                "What could happen if current trends continue?",
            ]
        ),
        P("The dashboard has six main sections:"),
        guide_table(
            [
                ["Section", "Purpose"],
                ["Pulse", "Executive landing page for overall health, ranked attention areas, and business-unit status."],
                ["Flow", "Shows how incoming work, completed work, and inventory/backlog are moving."],
                ["Staffing", "Explains department capacity, FTE, productivity, and workload pressure areas."],
                ["Forecast", "Projects receipts, closures, inventory, out-of-standard work, SLA, and scenario impacts."],
                ["Intelligence", "Shows early warnings and likely operational drivers for the selected context."],
                ["Detail", "Displays the underlying operational actuals by business unit and work category."],
            ],
            [1.3 * inch, 5.5 * inch],
        ),
    ]

    story += chapter("Chapter 2 - Getting Started and Navigation", "ch2")
    story += [
        P("Open WorkforceIQ by opening `dashboard.html` in the WorkforceIQ project folder. The dashboard reads the generated local data file, `data/dashboard-data.js`. No server is required."),
        P("When the dashboard first loads, users see a short loading screen, then the Pulse view. The default reporting period is usually the latest full operational period. This matters because a newer reporting period can exist with inventory or SLA data but without complete receipts, closures, production, and FTE information."),
        image_flowable(shots["overview"], 7.1 * inch),
        P("Annotated overview: 1 data freshness, 2 executive KPI cards, 3 filters, 4 dashboard tabs, 5 intelligence rail.", ST["Small"]),
        guide_table(
            [
                ["Control", "How to use it"],
                ["Dashboard View", "Changes the primary section: Pulse, Flow, Staffing, Forecast, Intelligence, or Detail."],
                ["Business Unit", "Filters the dashboard to All business units or a selected unit such as CB, CGS, or GB."],
                ["Work Category", "Filters to All work categories or a specific work type such as Disputes or Correspondence."],
                ["Period", "Changes the reporting month displayed in the dashboard."],
                ["Reset", "Returns the dashboard to Pulse, All business units, All work categories, and the default full operational period."],
                ["Refresh", "Rerenders the currently loaded local dashboard data. It does not import a new source report."],
                ["Guide Me", "Opens a question-based navigation helper."],
                ["Presentation Mode", "Changes the display style for meeting use. It does not change data."],
            ],
            [1.45 * inch, 5.35 * inch],
        ),
        P("<b>Last Refreshed</b> is when the dashboard data file was generated. <b>Latest Source Period</b> is the most recent reporting period available in the source data. <b>Latest Full Operational Period</b> is the most recent period with the operational fields needed for flow, staffing, and capacity analysis."),
        callout(f"In the current data, the latest source period is {latest}, while the latest full operational period is {full}. That is why the dashboard may default to {full} for operational analysis."),
        P("Many dashboard elements are clickable. KPI cards navigate to related sections. Bar rows and table rows open detail views. Information icons show short explanations when hovered. Forecast rows and tiles open a calculation explanation modal."),
    ]

    story += chapter("Chapter 3 - Understanding the Executive KPI Cards", "ch3")
    story += [
        P("The five cards across the top summarize the selected operational context. They update whenever filters change."),
        guide_table(
            [
                ["Card", "What it means", "Click behavior"],
                ["Capacity", "Shows whether department-level productive capacity appears sufficient, short, or surplus based on receipts, closures, and FTE.", "Opens Staffing."],
                ["SLA Health", "Shows selected-context SLA against the 90% target. The dashboard recalculates aggregate SLA from in-standard work divided by starting inventory.", "Opens Detail."],
                ["Backlog", "Shows whether closures exceeded receipts. Positive throughput means the operation may burn down backlog; negative throughput means backlog pressure is growing.", "Opens Flow."],
                ["Operational Health", "Counts critical, at-risk, and watch areas in the selected context. If none are flagged, it reports that all areas are healthy.", "Opens Pulse."],
                ["Outlook", "Summarizes the next forecast direction as Improving, Stable, Deteriorating, or Directional with a confidence label.", "Opens Forecast."],
            ],
            [1.05 * inch, 4.45 * inch, 1.3 * inch],
        ),
        P("Example: if the Backlog card shows an upward value labeled Growing, incoming work exceeded completed work. A manager should open Flow to compare receipts and closures, then open Staffing to see whether department capacity is contributing to the pressure."),
        P("Example: if Capacity shows a shortfall, that estimate answers whether the operation appears to have enough productive capacity to keep pace with incoming receipts. It does not automatically mean the same amount of staffing would eliminate all accumulated backlog."),
    ]

    story += chapter("Chapter 4 - Workforce Pulse", "ch4")
    story += [
        P("Pulse is the primary landing page. It is built for the question, <b>Where should I focus my attention today?</b>"),
        P("Pulse shows selected-context SLA, starting inventory, a count of flagged areas, a ranked attention list, and enterprise health by business unit. Rows marked Critical, At Risk, or Watch are shown first. If nothing is flagged, Pulse says the selected context is healthy instead of inventing a problem."),
        bullets(
            [
                "Use Pulse before meetings to identify the highest-risk business unit or work category.",
                "Click an attention row to open the detail modal and review source SLA, calculated SLA, inventory, out-of-standard work, and throughput balance.",
                "Use the Business Unit health bars to move quickly from an enterprise view into a specific unit.",
            ]
        ),
        P("Practical example: a department manager preparing for a leadership meeting starts in Pulse with Business Unit set to All and Work Category set to All. If GB Disputes appears as the highest-risk area, the manager clicks it, reviews the operational snapshot, then checks Flow and Staffing to determine whether pressure is related to incoming demand, output, inventory, or capacity."),
    ]

    story += chapter("Chapter 5 - Flow: Understanding Workload Movement", "ch5")
    story += [
        P("Flow explains the relationship between incoming work, completed work, and existing inventory. It is the best section for understanding whether the operation is keeping pace with demand."),
        guide_table(
            [
                ["Term", "Plain-English meaning"],
                ["Receipts", "Incoming work received during the reporting period."],
                ["Closures", "Work completed or closed during the reporting period."],
                ["Starting Inventory", "Work/backlog present at the start of the reporting period."],
                ["Throughput Balance", "Closures minus receipts. Positive is favorable; negative means incoming work exceeded completed work."],
                ["Backlog Growth", "Occurs when receipts are greater than closures."],
                ["Backlog Burn-Down", "Occurs when closures are greater than receipts."],
                ["Burn-Down Runway", "A run-rate estimate showing where inventory may go if the current throughput rate continues."],
            ],
            [1.55 * inch, 5.25 * inch],
        ),
        callout("Throughput Balance = Closures - Receipts. A positive result means closures exceeded incoming work. A negative result means incoming work exceeded closures."),
        P("Numerical example: if a team receives 1,000 items and closes 1,200 items, throughput balance is +200. Existing backlog has an opportunity to decline. If the team receives 1,200 items and closes 1,000 items, throughput balance is -200. Backlog pressure is increasing."),
        image_flowable(shots["flow"], 7.1 * inch),
        P("The Flow tab includes a throughput callout, an inventory burn-down runway chart, timing estimates for 10% and 25% inventory reduction, a receipts-versus-closures comparison, and an inventory position view.", ST["Small"]),
    ]

    story += chapter("Chapter 6 - Staffing and Productive Capacity", "ch6")
    story += [
        P("The Staffing section helps users evaluate whether available productive capacity appears sufficient to keep pace with incoming workload. It uses available department-level staffing information and observed productivity."),
        guide_table(
            [
                ["Metric", "How to read it"],
                ["Department FTE", "Available staffing capacity for the department/business unit in the selected period."],
                ["Average Daily Receipts", "Average amount of incoming work per day."],
                ["Average Daily Production", "Average amount of completed production per day."],
                ["Production-to-Receipts Ratio", "Daily production divided by daily receipts. Above 100% means production is ahead of incoming volume."],
                ["Closures per FTE", "Monthly closures divided by FTE. Used to estimate productive capacity."],
                ["Capacity Shortfall", "Estimated additional FTE-equivalent productive capacity needed to keep pace with current receipts."],
                ["Capacity Surplus", "Estimated FTE-equivalent capacity above what is needed to keep pace with current receipts."],
                ["Workload Pressure Areas", "Specific work categories ranked by operational risk; these provide workload context, not exact staffing allocation proof."],
            ],
            [1.75 * inch, 5.05 * inch],
        ),
        callout("Important: WorkforceIQ does not assume exact FTE allocation by work category unless the source data explicitly supports it. Staffing scenarios should be read at the department/business-unit level."),
        P("Capacity to keep pace and capacity to reduce backlog are different questions. A department may have enough capacity to close the same amount of work it receives this month, while still carrying old backlog. Reducing accumulated backlog requires closures to exceed receipts for a sustained period."),
        P("Practical example: if Staffing shows a 2.5 FTE-equivalent shortfall, the manager should read that as a keep-pace signal. It means observed productivity suggests more capacity would be needed to match incoming receipts. The manager should then look at Flow to see whether backlog is growing and Forecast to test whether additional FTE could improve future inventory and SLA."),
    ]

    story += chapter("Chapter 7 - Forecast: Understanding What May Happen Next", "ch7")
    story += [
        P("Forecast is a directional planning view. It projects what may happen to receipts, closures, inventory, out-of-standard work, and SLA if recent operational trends continue. It is designed to support planning conversations, not to guarantee outcomes."),
        image_flowable(shots["forecast"], 7.1 * inch),
        P("Annotated forecast view: 1 select a specific business unit and work category, 2 adjust temporary scenario controls, 3 read receipts/closures/inventory lines, 4 review crossover and goal timing, 5 inspect the forecast table.", ST["Small"]),
        P("<b>Receipts</b> are projected incoming work during each future period. <b>Closures</b> are projected completed work during each future period. <b>Inventory</b> is the projected backlog level after receipts and closures interact."),
        callout("Next Inventory = Current Inventory + Receipts - Closures. If closures exceed receipts, inventory can decline. If receipts exceed closures, inventory can increase."),
        P("Crossover means projected closures begin exceeding projected receipts. The dashboard distinguishes three conditions:"),
        bullets(
            [
                "Positive throughput now: closures already exceed receipts in the current or baseline context.",
                "Future crossover: closures are projected to exceed receipts in a future displayed month.",
                "No Crossover Expected: projected closures remain below projected receipts throughout the forecast horizon.",
            ]
        ),
        P("The Forecast table displays Current, Month +1, Month +2, and Month +3. Each row includes projected receipts, closures, balance, inventory, out-of-standard work, expected SLA, and confidence. Clicking a row opens a modal explaining the math for projected balance, inventory roll-forward, and expected SLA."),
        P("Forecast confidence considers available history, missing recent fields, recent SLA volatility, and forecast horizon. Current forecasts are directional because the available history is limited. The dashboard does not present these outputs as trained machine-learning predictions."),
        P("Numerical example: if current inventory is 5,000, projected receipts are 1,200, and projected closures are 1,500, next inventory is 4,700. Because closures exceed receipts by 300, backlog declines. If projected receipts are 1,500 and closures are 1,200, next inventory is 5,300 and backlog grows."),
    ]

    story += chapter("Chapter 8 - Interactive What-If Forecasting", "ch8")
    story += [
        P("The Forecast tab includes temporary scenario controls. These controls let users test planning assumptions without changing historical data or the generated dashboard data file."),
        nums(
            [
                "Select a specific Business Unit and Work Category. Forecast scenarios do not run from an All/All context.",
                "Open the Forecast view.",
                "Use the Staffing control to increase or decrease department FTE.",
                "Use the Workload buttons to model incoming receipts at -10%, current, or +10%.",
                "Use the Productivity buttons to model closures at -5%, current, or +5%.",
                "Optionally enter a Backlog Goal to test when inventory might reach a target level.",
                "Review changes to projected receipts, closures, throughput balance, inventory, and expected SLA.",
                "Use Reset To Baseline Forecast to return to the original forecast assumptions.",
            ]
        ),
        P("A baseline forecast is the dashboard's current projection before the user changes scenario controls. A what-if scenario applies temporary planning assumptions on top of that baseline."),
        P("Worked example: leadership asks what could happen if incoming workload increases by 10% while department staffing increases by three FTE. Select the department and work category, open Forecast, increase the Staffing input by 3, choose +10% under Workload, and keep Productivity at Current unless a productivity change is also expected. Then compare projected closures, throughput balance, ending inventory, and expected SLA against the baseline. If throughput remains negative, additional staffing may not be enough by itself. If throughput turns positive, the forecast may show crossover or a clearer backlog burn-down path."),
        callout("Scenario adjustments are temporary. They do not update historical actuals, source reports, source-records.json, or dashboard-data.js."),
    ]

    story += chapter("Chapter 9 - Intelligence: Understanding Operational Drivers", "ch9")
    story += [
        P("The Intelligence section helps users understand why an area may be under pressure. It displays early-warning indicators and likely drivers for the selected context."),
        P("Early Warnings appear when SLA may still be meeting target but multiple leading indicators suggest pressure is forming. Examples include rising receipts, declining closures, positive receipt/closure gaps, production below receipts, increasing out-of-standard work, or workload growing faster than FTE."),
        P("Primary Drivers are formula-based operational signals. They may include receipt growth, closure decline, workload pressure, out-of-standard movement, flow gap, and reroutes. Clicking a driver opens a modal that explains the definition, formula, raw value, normalized displayed score, and source inputs."),
        callout("A driver is a signal, not proof of root cause. Use Intelligence to focus investigation, then confirm causes with operational context, staffing knowledge, process details, and source-system review."),
        P("Example: if Intelligence shows Receipt Growth and Flow Gap as the strongest signals, a manager might investigate volume spikes, upstream routing, work mix, and whether staffing or productivity changes are needed. If OOS Movement dominates, the investigation may focus on aging inventory and SLA recovery actions."),
    ]

    story += chapter("Chapter 10 - Detail: Reviewing Actual Operational Information", "ch10")
    story += [
        P("Detail shows the actual operational rows for the selected reporting period and filters. It is the best place to inspect the underlying metrics behind the higher-level cards and charts."),
        guide_table(
            [
                ["Displayed field", "Meaning"],
                ["Business Unit", "Operational unit such as CB, CGS, or GB."],
                ["Work Category", "Type of work such as Disputes, Correspondence, Cash Posting, Host, or Validation/Adjustments."],
                ["Operational Status", "Current health classification: Meeting Target, Watch, At Risk, Critical, or No Data."],
                ["Source SLA", "SLA value supplied by the source report."],
                ["Calculated SLA", "In-standard inventory divided by starting inventory."],
                ["Inventory", "Starting inventory/backlog for the period."],
                ["Out of Standard", "Inventory that is outside standard."],
                ["Receipts", "Incoming work for the period."],
                ["Closures", "Completed work for the period."],
                ["Balance", "Throughput balance: closures minus receipts."],
                ["FTE", "Available staffing information from the source."],
            ],
            [1.55 * inch, 5.25 * inch],
        ),
        callout("Detail contains historical actuals for the selected period. Forecast contains future directional estimates. Do not compare a forecasted future value as if it were an actual source result."),
        P("Clicking a Detail row opens an operational snapshot and intelligence brief for that business unit/work category."),
    ]

    story += chapter("Chapter 11 - Understanding the Intelligence Rail", "ch11")
    story += [
        P("The Intelligence Rail is the right-side contextual panel. It updates based on the selected Business Unit, Work Category, Period, and dashboard context."),
        guide_table(
            [
                ["Rail section", "How to use it"],
                ["Current State", "Summarizes the selected context and its status."],
                ["Why It Matters", "Lists the evidence supporting the current operational interpretation."],
                ["Primary Driver", "Calls out the most direct signal, such as incoming work exceeding closures."],
                ["Early Warning", "Shows whether leading indicators are active."],
                ["Outlook", "Shows the next projected SLA when forecast data is available, otherwise the simple trend continuation summary."],
                ["Recommended Lever", "Suggests the type of operational lever to consider, such as capacity, throughput, or backlog reduction."],
            ],
            [1.5 * inch, 5.3 * inch],
        ),
        P("Use the rail as a companion to the main chart. For example, Flow may show backlog growing, while the rail explains the primary driver and whether the selected area also has a capacity shortfall or early warning signal."),
    ]

    story += chapter("Chapter 12 - Practical WorkforceIQ Walkthroughs", "ch12")
    scenario_rows = [
        ["A. My department's SLA is declining.", "Open Pulse, filter to the department, review attention rows, then open Detail for Source SLA and Calculated SLA. Check Intelligence for likely drivers and Flow for backlog direction."],
        ["B. Incoming work is exceeding closures.", "Open Flow. Review Throughput Balance, Receipts In, Closures Out, and burn-down runway. A negative balance means backlog pressure is increasing."],
        ["C. I need to understand whether staffing is sufficient.", "Open Staffing. Review department FTE, production-to-receipts ratio, and capacity shortfall/surplus. Then compare Flow to see whether backlog is actually burning down."],
        ["D. I want to identify which area requires attention.", "Start in Pulse with All filters. Review Attention Required and Enterprise Health. Click the highest-risk row for a detail modal."],
        ["E. I want projected backlog for the next three months.", "Select a specific Business Unit and Work Category, then open Forecast. Review inventory line, forecast table, crossover, and backlog goal tile."],
        ["F. Leadership asks what additional staffing could change.", "Open Forecast for a specific context. Increase Staffing/FTE, then compare projected closures, balance, inventory, and expected SLA against baseline."],
        ["G. I need a meeting summary.", "Use Pulse for health, Flow for backlog direction, Staffing for capacity, Forecast for outlook, and the Intelligence Rail for a concise explanation."],
    ]
    story += [
        P("Use these task-based walkthroughs as training exercises or daily operating routines."),
        guide_table([["Business question", "Recommended workflow"], *scenario_rows], [2.4 * inch, 4.4 * inch]),
        P("For every walkthrough, pay attention to whether you are viewing all business units or a filtered context. Filters change the meaning of every card, chart, table, and rail statement."),
    ]

    story += chapter("Chapter 13 - WorkforceIQ Metric Glossary", "ch13")
    glossary = [
        ["Backlog", "Work still present in inventory.", "Often represented by Starting Inventory or projected Inventory.", "A backlog can exist even when capacity is currently sufficient."],
        ["Backlog Burn-Down", "A condition where closures exceed receipts.", "Closures - Receipts is positive.", "Must persist to reduce accumulated inventory."],
        ["Calculated SLA", "SLA calculated by WorkforceIQ from source counts.", "In Standard / Starting Inventory.", "May differ from Source SLA if source definitions differ."],
        ["Capacity Shortfall", "Estimated FTE-equivalent productive capacity needed to keep pace.", "Required FTE - Current FTE.", "Directional, department-level estimate."],
        ["Capacity Surplus", "Estimated productive capacity above what is needed to keep pace.", "Negative capacity gap shown as surplus.", "Does not automatically mean backlog is eliminated."],
        ["Closures", "Work completed during the period.", "Source metric.", "Compared with receipts to determine flow."],
        ["Crossover", "Future point where projected closures exceed receipts.", "First forecast period with positive throughput balance.", "No crossover means closures stay below receipts within the horizon."],
        ["Expected SLA", "Forecasted future SLA.", "1 - projected OOS / projected inventory.", "Directional estimate."],
        ["Forecast Confidence", "Label describing how much support the forecast has.", "Considers history, missing data, volatility, and horizon.", "Low confidence does not mean useless; it means treat as directional."],
        ["FTE", "Staffing level from the source data.", "Source metric.", "Read as department-level unless source proves finer allocation."],
        ["Inventory", "Work/backlog count.", "Source actual or forecast projection.", "In Forecast, inventory is rolled forward from receipts and closures."],
        ["OOS / Out of Standard", "Inventory outside standard.", "Source metric.", "Higher OOS usually increases SLA pressure."],
        ["Production-to-Receipts Ratio", "Daily production compared with incoming daily receipts.", "Average Daily Production / Average Daily Receipts.", "Above 100% means production is ahead of incoming volume."],
        ["Receipts", "Incoming work during the period.", "Source metric.", "When receipts exceed closures, pressure grows."],
        ["SLA", "Service-level performance.", "Source SLA or calculated SLA.", "Dashboard target is 90%."],
        ["Throughput Balance", "Whether the operation completed more work than it received.", "Closures - Receipts.", "Positive is favorable; negative means incoming work exceeded closures."],
    ]
    story += [guide_table([["Metric", "Definition", "Calculation", "Interpretation / limitation"], *glossary], [1.35 * inch, 2.0 * inch, 1.65 * inch, 1.8 * inch])]

    story += chapter("Chapter 14 - Frequently Asked Questions and Troubleshooting", "ch14")
    faq = [
        ["Why am I seeing N/A?", "The selected period or context does not have the source fields needed for that metric, or the calculation would require division by zero."],
        ["Why does the dashboard show an earlier reporting month?", f"The latest source period is {latest}, but the latest full operational period is {full}. WorkforceIQ defaults to the complete operational period for views that require receipts, closures, production, or FTE."],
        ["What does partial data mean?", "A period has some source information but is missing operational fields such as receipts, closures, FTE, average daily receipts, or average daily production."],
        ["Why do Forecast and Detail display different numbers?", "Detail shows actual historical values for the selected period. Forecast shows directional projected future values and scenario outputs."],
        ["What does limited forecast confidence mean?", "The dashboard has limited history, missing recent fields, or volatility. Treat the forecast as a planning signal, not a guaranteed result."],
        ["Why is no crossover expected?", "Projected closures do not exceed projected receipts within the displayed forecast horizon."],
        ["What does a negative Throughput Balance mean?", "Incoming work exceeded completed work. Backlog pressure is increasing unless throughput improves."],
        ["Why can capacity appear sufficient while backlog still exists?", "Capacity may be enough to keep pace with current receipts, but reducing existing backlog requires closures to exceed receipts."],
        ["Are what-if changes permanent?", "No. Scenario changes are temporary browser-side assumptions and do not modify source data."],
        ["Does Refresh retrieve new source data?", "No. The Refresh button rerenders the currently loaded dashboard data. To load new source data, run the dashboard update script."],
        ["How do I return to the original forecast?", "Use Reset To Baseline Forecast in the Forecast tab."],
    ]
    story += [guide_table([["Question", "Answer"], *faq], [2.15 * inch, 4.65 * inch])]
    return story


def build_pdf(story: list, output: Path) -> None:
    doc = BaseDocTemplate(
        str(output),
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.62 * inch,
        bottomMargin=0.58 * inch,
        title="WorkforceIQ - Complete End-User Guide",
        author="WorkforceIQ Documentation",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="guide", frames=[frame], onPage=draw_page)])
    doc.build(story)


def draw_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 10.72 * inch, 8.5 * inch, 0.28 * inch, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(0.55 * inch, 10.82 * inch, "WorkforceIQ End-User Guide")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(7.95 * inch, 0.32 * inch, f"Page {doc.page}")
    canvas.restoreState()


def quick_start(shots: dict[str, Path], data: dict) -> None:
    c = __import__("reportlab.pdfgen.canvas", fromlist=["Canvas"]).Canvas(str(QUICK_PDF), pagesize=landscape(letter))
    width, height = landscape(letter)

    def header(title: str):
        c.setFillColor(NAVY)
        c.rect(0, height - 0.45 * inch, width, 0.45 * inch, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(0.45 * inch, height - 0.3 * inch, title)

    def box(x, y, w, h, title, lines, accent=BLUE):
        c.setStrokeColor(LINE)
        c.setFillColor(colors.white)
        c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
        c.setFillColor(accent)
        c.rect(x, y + h - 0.22 * inch, w, 0.22 * inch, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(x + 0.08 * inch, y + h - 0.16 * inch, title)
        c.setFillColor(INK)
        c.setFont("Helvetica", 7.6)
        cursor = y + h - 0.36 * inch
        for line in lines:
            wrapped = textwrap.wrap(line, 43)
            for piece in wrapped:
                c.drawString(x + 0.08 * inch, cursor, piece)
                cursor -= 0.13 * inch
            cursor -= 0.03 * inch

    header("WorkforceIQ Quick Start Guide")
    c.setFillColor(INK)
    c.setFont("Helvetica", 9)
    c.drawString(0.45 * inch, height - 0.68 * inch, "Use this two-page guide to get productive quickly. Filters change every card, chart, table, and explanation.")
    c.drawImage(str(shots["overview"]), 0.45 * inch, 2.85 * inch, width=5.25 * inch, height=3.82 * inch, preserveAspectRatio=True, mask="auto")
    box(5.95 * inch, 5.58 * inch, 4.6 * inch, 1.1 * inch, "Six Dashboard Sections", [
        "Pulse: where to focus first.",
        "Flow: receipts, closures, throughput, and backlog.",
        "Staffing: FTE, production, and capacity.",
        "Forecast: directional outlook and scenarios.",
        "Intelligence: early warnings and drivers.",
        "Detail: actual operational rows."
    ], BLUE)
    box(5.95 * inch, 4.05 * inch, 4.6 * inch, 1.32 * inch, "Executive KPI Cards", [
        "Capacity: shortfall, sufficient, or surplus.",
        "SLA Health: selected-context SLA vs 90% target.",
        "Backlog: positive means closures exceeded receipts.",
        "Operational Health: count of areas needing attention.",
        "Outlook: projected direction and confidence."
    ], TEAL)
    box(5.95 * inch, 2.55 * inch, 4.6 * inch, 1.3 * inch, "Basic Filter Pattern", [
        "1. Choose Dashboard View.",
        "2. Select Business Unit.",
        "3. Select Work Category.",
        "4. Select Period.",
        "5. Click rows/cards for detail."
    ], GREEN)
    box(0.45 * inch, 0.62 * inch, 10.1 * inch, 1.55 * inch, "Throughput Balance", [
        "Throughput Balance = Closures - Receipts. Positive is favorable because completed work exceeded incoming work. Negative means incoming work exceeded completed work, so backlog pressure is growing. A department can have enough capacity to keep pace with receipts and still have backlog if prior inventory has not been burned down."
    ], RED)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawRightString(width - 0.45 * inch, 0.25 * inch, "Page 1")
    c.showPage()

    header("Which Dashboard View Should I Use?")
    questions = [
        ("Are we healthy?", "Pulse", "Review attention rows, business-unit health, and KPI cards."),
        ("Is backlog growing?", "Flow", "Check Throughput Balance and burn-down runway."),
        ("Do we have capacity?", "Staffing", "Review department FTE, production/receipts, and capacity gap."),
        ("What happens next?", "Forecast", "Select one BU and work category; review chart, table, crossover, and SLA."),
        ("What if work or staffing changes?", "Forecast", "Use FTE, workload, productivity, and backlog target scenario controls."),
        ("Why is pressure forming?", "Intelligence", "Review early warnings and driver explanations."),
        ("What are the actual source values?", "Detail", "Review Source SLA, Calculated SLA, inventory, OOS, receipts, closures, balance, and FTE."),
        ("How do I brief leadership?", "Pulse + Rail", "Use Pulse for status and the Intelligence Rail for why it matters and recommended lever."),
    ]
    y = 6.75 * inch
    for idx, (q, view, action) in enumerate(questions):
        x = 0.45 * inch if idx < 4 else 5.55 * inch
        row_y = y - (idx % 4) * 1.28 * inch
        box(x, row_y - 0.95 * inch, 4.7 * inch, 1.02 * inch, q, [f"Use {view}.", action], BLUE if idx % 2 == 0 else TEAL)

    metric_rows = [
        ("SLA", "Service-level performance; target is 90%."),
        ("OOS", "Out-of-standard inventory."),
        ("Receipts", "Incoming work."),
        ("Closures", "Completed work."),
        ("Inventory", "Backlog/work on hand."),
        ("Crossover", "Projected closures begin exceeding receipts."),
        ("N/A", "Needed source data is unavailable for the selected context."),
    ]
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.45 * inch, 1.45 * inch, "Compact Metric Reference")
    c.setFillColor(INK)
    c.setFont("Helvetica", 8)
    col_w = 1.55 * inch
    for i, (name, desc) in enumerate(metric_rows):
        x = 0.45 * inch + (i % 4) * 2.55 * inch
        y2 = 1.13 * inch - (i // 4) * 0.42 * inch
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x, y2, name)
        c.setFont("Helvetica", 7.4)
        for line in textwrap.wrap(desc, 28):
            c.drawString(x + 0.52 * inch, y2, line)
            y2 -= 0.11 * inch
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(0.45 * inch, 0.25 * inch, f"Latest source period: {data['metadata'].get('latestPeriod')} | Latest full operational period: {data['metadata'].get('latestFullContextPeriod')}")
    c.drawRightString(width - 0.45 * inch, 0.25 * inch, "Page 2")
    c.save()


def html_document(data: dict, shots: dict[str, Path]) -> str:
    latest = html.escape(data["metadata"].get("latestPeriod", "latest"))
    full = html.escape(data["metadata"].get("latestFullContextPeriod", "latest full"))
    refreshed = html.escape(data["metadata"].get("lastRefreshed", ""))
    overview = html.escape(str(shots["overview"].resolve()))
    forecast = html.escape(str(shots["forecast"].resolve()))
    flow = html.escape(str(shots["flow"].resolve()))
    periods = html.escape(", ".join(data["metadata"].get("periods", [])))
    body = f"""
    <h1>WorkforceIQ - Complete End-User Guide</h1>
    <p><b>Purpose:</b> This editable document explains the current WorkforceIQ dashboard for end users. It is generated from the same reviewed content as the PDF manual and is intended for operational leaders, department managers, WFM personnel, analysts, associates, and executive stakeholders.</p>
    <p><b>Last Dashboard Refresh:</b> {refreshed}<br><b>Latest Source Period:</b> {latest}<br><b>Latest Full Operational Period:</b> {full}<br><b>Available Periods:</b> {periods}</p>
    <p><b>Important:</b> WorkforceIQ uses transparent operational calculations, rule-based intelligence, and directional forecasts. It does not currently use a trained machine-learning model, and forecasts are not guaranteed outcomes.</p>

    <h2>Table of Contents</h2>
    <ol>
      <li>Welcome to WorkforceIQ</li>
      <li>Getting Started and Navigation</li>
      <li>Understanding the Executive KPI Cards</li>
      <li>Workforce Pulse</li>
      <li>Flow: Understanding Workload Movement</li>
      <li>Staffing and Productive Capacity</li>
      <li>Forecast: Understanding What May Happen Next</li>
      <li>Interactive What-If Forecasting</li>
      <li>Intelligence: Understanding Operational Drivers</li>
      <li>Detail: Reviewing Actual Operational Information</li>
      <li>Understanding the Intelligence Rail</li>
      <li>Practical WorkforceIQ Walkthroughs</li>
      <li>WorkforceIQ Metric Glossary</li>
      <li>Frequently Asked Questions and Troubleshooting</li>
    </ol>

    <h2>1. Welcome to WorkforceIQ</h2>
    <p>WorkforceIQ converts staffing, inventory, SLA, receipts, closures, production, and FTE reporting into a local operational intelligence dashboard. It helps users answer practical operating questions: Are we meeting expectations? Is backlog increasing or decreasing? Are receipts and closures balanced? Do we have sufficient productive capacity? Which areas need attention? What may happen if current trends continue?</p>
    <p>The dashboard is designed to reduce the amount of manual interpretation required from wide operational reports. It organizes actual source information into executive KPI cards, visual workflow views, drill-down tables, contextual explanations, and directional forecasts.</p>
    <table><tr><th>Section</th><th>Purpose</th></tr>
      <tr><td>Pulse</td><td>Executive health, ranked attention areas, and business-unit status.</td></tr>
      <tr><td>Flow</td><td>Receipts, closures, throughput balance, inventory, and burn-down runway.</td></tr>
      <tr><td>Staffing</td><td>Department-level capacity, FTE, productivity, and workload pressure.</td></tr>
      <tr><td>Forecast</td><td>Directional projections, crossover, backlog goals, and temporary scenarios.</td></tr>
      <tr><td>Intelligence</td><td>Early warnings and likely operational driver signals.</td></tr>
      <tr><td>Detail</td><td>Underlying operational actuals for the selected period.</td></tr>
    </table>

    <h2>2. Getting Started and Navigation</h2>
    <p>Open <code>dashboard.html</code> in the WorkforceIQ folder. The dashboard loads the generated local data file, <code>data/dashboard-data.js</code>. No web server is required.</p>
    <p>When the dashboard opens, it displays the Pulse view by default. The dashboard may default to the latest complete operational period instead of the latest source period when the newest month has only partial information. In the current data, the latest source period is {latest}, while the latest full operational period is {full}.</p>
    <img src="file://{overview}" width="680">
    <p><b>Annotated overview:</b> 1 data freshness, 2 executive KPI cards, 3 filters, 4 dashboard tabs, 5 intelligence rail.</p>
    <table><tr><th>Control</th><th>How to use it</th></tr>
      <tr><td>Dashboard View</td><td>Switches among Pulse, Flow, Staffing, Forecast, Intelligence, and Detail.</td></tr>
      <tr><td>Business Unit</td><td>Filters the dashboard to All or a specific business unit.</td></tr>
      <tr><td>Work Category</td><td>Filters the dashboard to All or a specific work category.</td></tr>
      <tr><td>Period</td><td>Changes the reporting month.</td></tr>
      <tr><td>Reset View</td><td>Returns to Pulse, All business units, All work categories, and the default full operational period.</td></tr>
      <tr><td>Refresh</td><td>Rerenders the already-loaded local data. It does not import a new source report.</td></tr>
      <tr><td>Guide Me</td><td>Opens a question-based navigation helper.</td></tr>
      <tr><td>Presentation Mode</td><td>Changes display style for meeting use. It does not alter data.</td></tr>
    </table>
    <p><b>Last Refreshed</b> means when the dashboard data file was generated. <b>Latest Source Period</b> means the newest period present in the source data. <b>Latest Full Operational Period</b> means the newest period with enough operational fields for flow, staffing, and capacity analysis.</p>

    <h2>3. Executive KPI Cards</h2>
    <p>The five KPI cards update whenever filters change. Clicking a card opens the dashboard section most closely related to that card.</p>
    <table><tr><th>Card</th><th>What it measures</th><th>Click opens</th></tr>
      <tr><td>Capacity</td><td>Whether department-level productive capacity appears sufficient, short, or surplus based on receipts, closures, and FTE.</td><td>Staffing</td></tr>
      <tr><td>SLA Health</td><td>Selected-context SLA compared with the 90% target. Aggregate SLA is calculated from in-standard work divided by starting inventory.</td><td>Detail</td></tr>
      <tr><td>Backlog</td><td>Whether closures exceeded receipts. Positive throughput is favorable; negative throughput means incoming work exceeded completed work.</td><td>Flow</td></tr>
      <tr><td>Operational Health</td><td>Count of Critical, At Risk, and Watch areas. If none are present, the card reports that all areas are healthy.</td><td>Pulse</td></tr>
      <tr><td>Outlook</td><td>Next forecast direction: Improving, Stable, Deteriorating, or Directional, with confidence label.</td><td>Forecast</td></tr>
    </table>
    <p>Example: if Backlog shows a growing value, open Flow to compare receipts and closures, then open Staffing to see whether capacity may be contributing to the issue.</p>

    <h2>4. Workforce Pulse</h2>
    <p>Pulse answers: <b>Where should I focus my attention today?</b> It shows selected-context SLA, starting inventory, count of flagged areas, ranked attention rows, and enterprise health by business unit.</p>
    <p>Rows classified as Critical, At Risk, or Watch appear first. If no areas are flagged, Pulse communicates that the selected context is healthy instead of forcing a false problem statement.</p>
    <p>Practical use: before a leadership meeting, start in Pulse with Business Unit set to All and Work Category set to All. Review the highest-risk area, click it for a detail snapshot, and use the rail to prepare a concise explanation.</p>

    <h2>5. Flow</h2>
    <p>Flow explains workload movement. It connects incoming work, completed work, and starting inventory so users can determine whether the operation is keeping pace with demand.</p>
    <p><b>Throughput Balance = Closures - Receipts.</b> A positive value means closures exceeded incoming work, creating an opportunity to reduce backlog. A negative value means incoming work exceeded completed work, increasing backlog pressure.</p>
    <p>Example: if receipts are 1,000 and closures are 1,200, throughput balance is +200. If receipts are 1,200 and closures are 1,000, throughput balance is -200.</p>
    <img src="file://{flow}" width="680">
    <p>The Flow tab shows a throughput callout, inventory burn-down runway, run-rate timing for 10% and 25% inventory reduction, receipts versus closures, and inventory position.</p>

    <h2>6. Staffing and Productive Capacity</h2>
    <p>Staffing evaluates whether productive capacity appears sufficient to keep pace with incoming receipts. It uses available department-level staffing information and observed productivity.</p>
    <table><tr><th>Metric</th><th>Business meaning</th></tr>
      <tr><td>Department FTE</td><td>Available staffing capacity for the department/business unit.</td></tr>
      <tr><td>Average Daily Receipts</td><td>Average incoming work per day.</td></tr>
      <tr><td>Average Daily Production</td><td>Average completed production per day.</td></tr>
      <tr><td>Production-to-Receipts Ratio</td><td>Daily production divided by daily receipts. Above 100% means production is ahead of incoming volume.</td></tr>
      <tr><td>Closures per FTE</td><td>Monthly closures divided by FTE. Used in capacity estimates.</td></tr>
      <tr><td>Capacity Shortfall</td><td>Estimated additional FTE-equivalent productive capacity needed to keep pace with receipts.</td></tr>
      <tr><td>Capacity Surplus</td><td>Estimated productive capacity above what is needed to keep pace.</td></tr>
    </table>
    <p><b>Important:</b> WorkforceIQ does not claim exact FTE allocation by individual work category unless the source data explicitly supports that level. Staffing scenarios should be interpreted at the department/business-unit level.</p>
    <p>Capacity to keep pace and capacity to reduce accumulated backlog are different questions. A department may have enough capacity to match current receipts while still carrying prior backlog. Backlog decreases only when closures exceed receipts.</p>

    <h2>7. Forecast</h2>
    <p>Forecast is a directional planning view. It projects receipts, closures, inventory, out-of-standard work, and expected SLA over the displayed horizon using recent operational movement.</p>
    <img src="file://{forecast}" width="680">
    <p><b>Receipts</b> are projected incoming work. <b>Closures</b> are projected completed work. <b>Inventory</b> is the projected backlog after receipts and closures interact. Receipts and closures are period activity; inventory is the resulting backlog level.</p>
    <p><b>Next Inventory = Current Inventory + Receipts - Closures.</b> If projected closures exceed projected receipts, inventory can decline. If projected receipts exceed closures, inventory can increase.</p>
    <p><b>Crossover</b> is the first future period where projected closures exceed projected receipts. If the tile says No Crossover Expected, closures are not projected to exceed receipts within the displayed horizon.</p>
    <p>The forecast table includes Current, Month +1, Month +2, and Month +3. Rows show projected receipts, closures, balance, inventory, out-of-standard work, expected SLA, and confidence. Clicking forecast rows or tiles opens a formula explanation.</p>
    <p>Forecast confidence considers available history, missing recent fields, volatility, and horizon. Low confidence means the projection should be treated as directional.</p>

    <h2>8. Interactive What-If Forecasting</h2>
    <p>Forecast scenario controls are temporary planning assumptions. Users can adjust Staffing/FTE, incoming workload, productivity, and backlog target, then return to the original baseline forecast.</p>
    <ol>
      <li>Select a specific Business Unit and Work Category.</li>
      <li>Open Forecast.</li>
      <li>Adjust Staffing/FTE using the stepper or number input.</li>
      <li>Choose Workload at -10%, Current, or +10%.</li>
      <li>Choose Productivity at -5%, Current, or +5%.</li>
      <li>Optionally enter a Backlog Goal.</li>
      <li>Review projected receipts, closures, balance, inventory, and expected SLA.</li>
      <li>Click Reset To Baseline Forecast to return to original assumptions.</li>
    </ol>
    <p>Worked example: to test incoming workload increasing by 10% while staffing increases by three FTE, select the department and work category, open Forecast, increase the FTE control by 3, choose +10% under Workload, and compare ending inventory and expected SLA against the baseline. If throughput remains negative, staffing may not be enough by itself. If throughput turns positive, the forecast may show crossover or a stronger burn-down path.</p>

    <h2>9. Intelligence</h2>
    <p>Intelligence explains why a selected area may be under pressure. It shows Early Warnings and Likely Drivers. Early warnings appear when multiple leading indicators suggest pressure is forming, even if SLA has not fully broken yet.</p>
    <p>Driver signals can include receipt growth, closure decline, workload pressure, out-of-standard movement, flow gap, and reroutes. Clicking a driver opens a modal with its definition, formula, raw value, normalized displayed score, and source inputs.</p>
    <p><b>Important:</b> driver indicators are analytical signals, not proof of causation. Use them to focus investigation, then confirm root cause with operational context.</p>

    <h2>10. Detail</h2>
    <p>Detail displays actual operational rows for the selected reporting period. It includes Business Unit, Work Category, Operational Status, Source SLA, Calculated SLA, Inventory, Out of Standard, Receipts, Closures, Throughput Balance, and FTE.</p>
    <p>Clicking a Detail row opens an operational snapshot and intelligence brief. Detail is historical actual information; Forecast is future directional estimates.</p>

    <h2>11. Intelligence Rail</h2>
    <p>The right-side Intelligence Rail changes with the selected context. It includes Current State, Why It Matters, Primary Driver, Early Warning, Outlook, and Recommended Lever.</p>
    <p>Use the rail next to the main visualization. For example, Flow may show backlog growing while the rail explains the primary driver and whether the selected area also has a capacity shortfall or early warning signal.</p>

    <h2>12. Practical Walkthroughs</h2>
    <table><tr><th>Scenario</th><th>Workflow</th></tr>
      <tr><td>My department's SLA is declining.</td><td>Open Pulse, filter to the department, review attention rows, then open Detail for Source SLA and Calculated SLA. Check Intelligence for drivers and Flow for backlog direction.</td></tr>
      <tr><td>Incoming work is exceeding closures.</td><td>Open Flow. Review Throughput Balance, Receipts In, Closures Out, and burn-down runway. Negative balance means backlog pressure is increasing.</td></tr>
      <tr><td>I need to know whether staffing is sufficient.</td><td>Open Staffing. Review FTE, production-to-receipts ratio, and capacity shortfall/surplus. Then compare Flow to see whether backlog is burning down.</td></tr>
      <tr><td>I need to identify the area requiring attention.</td><td>Start in Pulse with All filters. Review Attention Required and Enterprise Health. Click the highest-risk row.</td></tr>
      <tr><td>I want projected backlog over the next three months.</td><td>Select one Business Unit and Work Category, then open Forecast. Review inventory line, forecast table, crossover, and backlog goal tile.</td></tr>
      <tr><td>Leadership asks what staffing could change.</td><td>Open Forecast, increase Staffing/FTE, and compare projected closures, balance, inventory, and expected SLA against baseline.</td></tr>
      <tr><td>I need a meeting summary.</td><td>Use Pulse for status, Flow for backlog direction, Staffing for capacity, Forecast for outlook, and the Intelligence Rail for narrative.</td></tr>
    </table>

    <h2>13. Metric Glossary</h2>
    <table><tr><th>Metric</th><th>Definition</th><th>Calculation / interpretation</th></tr>
      <tr><td>Backlog</td><td>Work still present in inventory.</td><td>Often represented by Starting Inventory or projected Inventory.</td></tr>
      <tr><td>Backlog Burn-Down</td><td>Closures exceed receipts.</td><td>Positive throughput must persist to reduce accumulated inventory.</td></tr>
      <tr><td>Calculated SLA</td><td>Dashboard-calculated SLA.</td><td>In Standard / Starting Inventory.</td></tr>
      <tr><td>Capacity Shortfall</td><td>Estimated productive capacity needed to keep pace.</td><td>Required FTE minus current FTE.</td></tr>
      <tr><td>Capacity Surplus</td><td>Estimated capacity above keep-pace need.</td><td>Negative capacity gap shown in user-friendly language.</td></tr>
      <tr><td>Closures</td><td>Work completed during the period.</td><td>Compared with receipts to determine flow.</td></tr>
      <tr><td>Crossover</td><td>Forecast period where closures begin exceeding receipts.</td><td>First future period with positive throughput balance.</td></tr>
      <tr><td>Expected SLA</td><td>Forecasted future SLA.</td><td>1 - projected OOS / projected inventory.</td></tr>
      <tr><td>Forecast Confidence</td><td>Support level for forecast output.</td><td>Considers history, missing data, volatility, and horizon.</td></tr>
      <tr><td>FTE</td><td>Staffing level from source data.</td><td>Read as department-level unless source proves finer allocation.</td></tr>
      <tr><td>Inventory</td><td>Work/backlog count.</td><td>In Forecast, rolled forward using receipts and closures.</td></tr>
      <tr><td>OOS / Out of Standard</td><td>Inventory outside standard.</td><td>Higher OOS usually increases SLA pressure.</td></tr>
      <tr><td>Production-to-Receipts Ratio</td><td>Daily production compared with incoming daily receipts.</td><td>Average Daily Production / Average Daily Receipts.</td></tr>
      <tr><td>Receipts</td><td>Incoming work during the period.</td><td>If receipts exceed closures, pressure grows.</td></tr>
      <tr><td>SLA</td><td>Service-level performance.</td><td>Dashboard target is 90%.</td></tr>
      <tr><td>Throughput Balance</td><td>Whether completed work exceeded incoming work.</td><td>Closures - Receipts. Positive is favorable; negative means incoming work exceeded closures.</td></tr>
    </table>

    <h2>14. FAQ</h2>
    <table><tr><th>Question</th><th>Answer</th></tr>
      <tr><td>Why am I seeing N/A?</td><td>The selected period or context does not have the fields needed for that metric, or the calculation would require division by zero.</td></tr>
      <tr><td>Why does the dashboard show an earlier reporting month?</td><td>The latest source period is {latest}, but the latest full operational period is {full}. Views needing receipts, closures, production, and FTE use the complete period.</td></tr>
      <tr><td>What does partial data mean?</td><td>A period has some information but is missing operational fields such as receipts, closures, FTE, average daily receipts, or average daily production.</td></tr>
      <tr><td>Why do Forecast and Detail show different numbers?</td><td>Detail shows historical actuals. Forecast shows future directional estimates and scenario outputs.</td></tr>
      <tr><td>What does limited forecast confidence mean?</td><td>There is limited history, missing recent data, volatility, or horizon uncertainty. Treat the output as directional.</td></tr>
      <tr><td>Why is no crossover expected?</td><td>Projected closures do not exceed projected receipts within the displayed forecast horizon.</td></tr>
      <tr><td>What does a negative Throughput Balance mean?</td><td>Incoming work exceeded completed work, so backlog pressure is increasing unless throughput improves.</td></tr>
      <tr><td>Why can capacity appear sufficient while backlog still exists?</td><td>Capacity may be sufficient to keep pace with current receipts, but reducing old backlog requires closures to exceed receipts.</td></tr>
      <tr><td>Are what-if changes permanent?</td><td>No. Scenario changes are temporary browser-side assumptions and do not modify source data.</td></tr>
      <tr><td>Does Refresh retrieve new source data?</td><td>No. Refresh rerenders the current local data. New source data requires running the update script.</td></tr>
      <tr><td>How do I return to the original forecast?</td><td>Click Reset To Baseline Forecast in the Forecast tab.</td></tr>
    </table>
    """
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>WorkforceIQ - Complete End-User Guide</title>
    <style>body{{font-family:Arial,Helvetica,sans-serif;color:#172033;line-height:1.45;max-width:840px;margin:40px auto}}h1{{color:#102642;font-size:30px}}h2{{color:#123a66;page-break-before:always;border-bottom:2px solid #d8e0ea;padding-bottom:5px}}h3{{color:#0d7f86}}img{{border:1px solid #d8e0ea;margin:10px 0}}table{{border-collapse:collapse;width:100%;margin:12px 0}}th{{background:#123a66;color:white;text-align:left}}td,th{{border:1px solid #d8e0ea;padding:7px;vertical-align:top}}code{{background:#eef4fa;padding:2px 4px}}</style></head><body>{body}</body></html>"""


def build_docx(data: dict, shots: dict[str, Path]) -> None:
    HTML_SOURCE.write_text(html_document(data, shots), encoding="utf-8")
    try:
        subprocess.run(["textutil", "-convert", "docx", "-output", str(COMPLETE_DOCX), str(HTML_SOURCE)], check=True, capture_output=True)
    except Exception as exc:
        print(f"DOCX conversion warning: {exc}")
        COMPLETE_DOCX.write_bytes(b"")


def main() -> int:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    shots = capture_screenshots()
    global ST
    ST = styles()
    story = build_sections(data, shots)
    build_pdf(story, COMPLETE_PDF)
    quick_start(shots, data)
    build_docx(data, shots)
    print(f"Wrote {COMPLETE_PDF}")
    print(f"Wrote {COMPLETE_DOCX}")
    print(f"Wrote {QUICK_PDF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
