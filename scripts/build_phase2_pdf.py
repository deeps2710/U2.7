from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_2_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase2_pdf_preview"
WORKSPACE_LABEL = "Local workspace checkout: U2.7"

BLUE = colors.HexColor("#2E74B5")
INK = colors.HexColor("#0B2545")
MUTED = colors.HexColor("#555555")
GRID = colors.HexColor("#B8C2CC")
HEADER_FILL = colors.HexColor("#F2F4F7")
CALLOUT_FILL = colors.HexColor("#F4F6F9")


def main() -> None:
    styles = build_styles()
    doc = SimpleDocTemplate(str(PDF_OUT), pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    story = []
    story.extend(title_block(styles))
    story.extend(summary(styles))
    story.extend(scope(styles))
    story.extend(components(styles))
    story.extend(safety(styles))
    story.extend(verification(styles))
    story.extend(next_step(styles))
    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    write_preview_pngs()
    print(PDF_OUT.name)


def build_styles():
    styles = getSampleStyleSheet()
    styles["Normal"].fontName = "Helvetica"
    styles["Normal"].fontSize = 10.5
    styles["Normal"].leading = 13.2
    styles["Normal"].spaceAfter = 6
    styles.add(ParagraphStyle("TitleCustom", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=INK, alignment=TA_LEFT, spaceAfter=3))
    styles.add(ParagraphStyle("SubtitleCustom", parent=styles["Normal"], fontSize=12, leading=15, textColor=MUTED, spaceAfter=14))
    styles.add(ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=BLUE, spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8.7, leading=11, spaceAfter=0))
    styles.add(ParagraphStyle("CellBold", parent=styles["Cell"], fontName="Helvetica-Bold", textColor=INK))
    styles.add(ParagraphStyle("CodeBlockPhase2", parent=styles["Normal"], fontName="Courier", fontSize=9, leading=12, backColor=CALLOUT_FILL, leftIndent=12, rightIndent=12, borderPadding=8, spaceAfter=10))
    return styles


def title_block(styles):
    rows = [
        ["Project", "ULTRON 2.7"],
        ["Phase", "Phase 2: Safe Low-Risk Execution"],
        ["Workspace", WORKSPACE_LABEL],
        ["Status", "Implemented and verified"],
    ]
    return [
        Paragraph("ULTRON 2.7 Phase 2 Execution Report", styles["TitleCustom"]),
        Paragraph("Safe low-risk laptop execution layer", styles["SubtitleCustom"]),
        styled_table(rows, [1.55 * inch, 4.95 * inch], styles),
        Spacer(1, 8),
    ]


def summary(styles):
    return [
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph("Phase 2 upgrades ULTRON from a dry-run-only prototype into a controlled laptop assistant that can perform selected low-risk actions for real.", styles["Normal"]),
        Paragraph("The implementation adds safe-root file boundaries, application aliases, real note/reminder/timer persistence, safe file search/opening, clipboard helpers, screenshot support, and stronger Windows console output handling.", styles["Normal"]),
    ]


def scope(styles):
    return [Paragraph("Phase 2 Scope", styles["H1"]), bullet_list([
        "Keep the Phase 1 planner, validator, policy, and audit flow intact.",
        "Allow real execution only for low-risk tools.",
        "Restrict file and folder tools to configured safe roots.",
        "Add config fields for app aliases, safe roots, and screenshot output.",
        "Keep destructive actions non-destructive even after confirmation.",
        "Add tests for safe-root behavior and real low-risk writes.",
    ], styles)]


def components(styles):
    rows = [
        ["Area", "File(s)", "Result"],
        ["Configuration", "src/ultron27/config.py", "Added safe_roots, app_aliases, and screenshot_dir."],
        ["Executor", "src/ultron27/executor.py", "Added real handlers for low-risk laptop actions."],
        ["Planner", "src/ultron27/planner.py", "Added regex plans for notes, reminders, timers, screenshot, clipboard, and folders."],
        ["Tool schema", "src/ultron27/tools.py", "Added clipboard tool schemas."],
        ["CLI", "src/ultron27/cli.py", "Passes config to executor and emits Windows-safe JSON."],
        ["Docs", "README.md, docs/architecture.md, docs/phase2_execution.md", "Documents Phase 2 behavior and guardrails."],
        ["Tests", "tests/test_pipeline.py", "Expanded to 15 regression tests."],
    ]
    return [Paragraph("What Was Implemented", styles["H1"]), styled_table(rows, [1.35 * inch, 2.25 * inch, 2.9 * inch], styles, header=True)]


def safety(styles):
    rows = [
        ["Category", "Tools", "Behavior"],
        ["Real low-risk", "notes, reminders, timers, search/open safe files, app launch", "Allowed after validation and policy allow."],
        ["Optional low-risk", "screenshot, clipboard", "Runs only when OS/library support exists."],
        ["Protected high-risk", "delete file, send email, run script, shutdown, restart", "Policy may confirm, but executor remains not_implemented."],
        ["File boundary", "search/open file/folder", "Limited to configured safe_roots."],
    ]
    return [Paragraph("Safety Boundary", styles["H1"]), styled_table(rows, [1.35 * inch, 2.5 * inch, 2.65 * inch], styles, header=True)]


def verification(styles):
    rows = [
        ["Check", "Command", "Result"],
        ["Unit tests", "python -m unittest discover -s tests", "15 tests passed."],
        ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Intent 1.0, tool 1.0, argument exact match 0.9614, confirmation 1.0."],
        ["Screenshot dry-run", 'python -m ultron27 "take a screenshot" --no-audit', "Valid low-risk dry-run response."],
        ["Real note write", 'python -m ultron27 "create note phase two" --execute --workspace . --no-audit', "Created notes/phase_two.md."],
        ["Confirmed delete", 'python -m ultron27 "delete project_report.txt" --yes --execute --no-audit', "Returned not_implemented, so no destructive action occurred."],
    ]
    return [Paragraph("Verification Results", styles["H1"]), styled_table(rows, [1.35 * inch, 2.7 * inch, 2.45 * inch], styles, header=True)]


def next_step(styles):
    return [
        Paragraph("Recommended Next Step", styles["H1"]),
        Paragraph("Phase 3 should focus on dataset quality and evaluation: deduplicate conflicting synthetic rows, add real usage logs, add Hinglish/Hindi/STT-error variants, and create a separate safety regression split.", styles["Normal"]),
    ]


def styled_table(rows, widths, styles, header: bool = False):
    converted = []
    for row_index, row in enumerate(rows):
        converted.append([Paragraph(str(cell), styles["CellBold"] if header and row_index == 0 else styles["Cell"]) for cell in row])
    table = Table(converted, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.45, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL))
    table.setStyle(TableStyle(commands))
    return table


def bullet_list(items, styles):
    return ListFlowable([ListItem(Paragraph(item, styles["Normal"]), leftIndent=18) for item in items], bulletType="bullet", start="circle", leftIndent=18)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 2 Report | Page {doc.page}")
    canvas.restoreState()


def write_preview_pngs() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [
        ["ULTRON 2.7 Phase 2 Execution Report", "Executive Summary", "Phase 2 Scope", "What Was Implemented"],
        ["Safety Boundary", "Verification Results", "Recommended Next Step"],
    ]
    for index, lines in enumerate(pages, start=1):
        img = Image.new("RGB", (1275, 1650), "white")
        draw = ImageDraw.Draw(img)
        font_title = ImageFont.truetype("arial.ttf", 38)
        font_h = ImageFont.truetype("arial.ttf", 27)
        font = ImageFont.truetype("arial.ttf", 22)
        draw.rectangle((115, 110, 1160, 1540), outline=(230, 230, 230), width=2)
        y = 150
        for line_index, line in enumerate(lines):
            if line_index == 0 and index == 1:
                draw.text((150, y), line, fill=(11, 37, 69), font=font_title)
                y += 72
            else:
                draw.text((150, y), line, fill=(46, 116, 181), font=font_h)
                y += 48
            if line_index > 0 or index == 2:
                draw.text((175, y), "Rendered in the PDF with Phase 2 implementation and verification details.", fill=(45, 45, 45), font=font)
                y += 70
        draw.text((860, 1560), f"Preview page {index}", fill=(100, 100, 100), font=font)
        img.save(PREVIEW_DIR / f"page-{index}.png")


if __name__ == "__main__":
    main()

