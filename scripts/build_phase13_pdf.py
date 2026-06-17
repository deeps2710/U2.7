from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_13_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase13_pdf_preview"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    styles = stylesheet()
    doc = SimpleDocTemplate(str(PDF_OUT), pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    story = [
        Paragraph("ULTRON 2.7 Phase 13 Execution Report", styles["TitleCustom"]),
        Paragraph("Beta-ready local prototype", styles["SubtitleCustom"]),
        table(
            [["Project", "ULTRON 2.7"], ["Phase", "Phase 13: Beta-Ready Local Prototype"], ["Workspace", "Local workspace checkout: U2.7"], ["Status", "Implemented and verified"]],
            [1.55 * inch, 4.95 * inch],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph(
            "Phase 13 turns ULTRON 2.7 into a beta-ready local Windows prototype. The project now has setup scripts, dependency and provider checks, a config wizard, a one-command launcher, diagnostics, a no-microphone demo, and CI-style verification.",
            styles["Normal"],
        ),
        Paragraph(
            "The safety architecture is unchanged. Operator tooling does not grant raw shell access or bypass schema validation, policy gates, executor restrictions, or audit logging.",
            styles["Normal"],
        ),
        Paragraph("Phase 13 Scope", styles["H1"]),
        bullets(
            [
                "Add Windows setup and local dependency checks.",
                "Add STT/TTS/wake/VAD provider health checks.",
                "Add a config wizard for workspace, safe roots, app aliases, voice providers, and dry-run mode.",
                "Add a launcher that starts the backend and UI together and handles port conflicts.",
                "Add a diagnostics API and diagnostics page.",
                "Add a no-microphone demo flow using typed commands and mock voice.",
                "Add a CI-style verification script.",
                "Update README, architecture docs, install guide, run guide, troubleshooting guide, and safety guide.",
            ],
            styles,
        ),
        Paragraph("What Was Implemented", styles["H1"]),
        table(
            [
                ["Area", "File(s)", "Result"],
                ["Diagnostics", "src/ultron27/diagnostics.py, web_server.py", "Adds /api/diagnostics with backend, brain, runtime path, voice provider, safe-root, dependency, and recent-error readiness data."],
                ["Launcher", "scripts/launch_ultron.py", "Starts backend and UI together, chooses an open port, and prints URLs."],
                ["Setup", "setup_ultron_windows.ps1, check_dependencies.py", "Creates a Windows venv, installs the project, writes safe defaults, and reports missing dependencies."],
                ["Config", "scripts/config_wizard.py", "Generates ultron.config.json with workspace, safe roots, app aliases, voice providers, and dry-run defaults."],
                ["Demo", "scripts/demo_phase13.py", "Runs typed command, note creation, confirmation pause, and mock voice demos without a microphone."],
                ["Verification", "scripts/verify_phase13.py", "Runs tests, dataset evaluation, safety regression, and API smoke checks."],
                ["UI", "web/diagnostics.html, diagnostics.js", "Adds a readable diagnostics page linked from the main interface."],
            ],
            [1.35 * inch, 2.35 * inch, 2.8 * inch],
            styles,
            header=True,
        ),
        Paragraph("Beta Operator Workflow", styles["H1"]),
        table(
            [
                ["Need", "Command", "Expected Outcome"],
                ["Install", ".\\scripts\\setup_ultron_windows.ps1", "Creates .venv, installs package, writes config, checks dependencies."],
                ["Launch", "python scripts\\launch_ultron.py", "Starts backend and UI, then prints URLs."],
                ["Diagnose", "Open /diagnostics", "Shows backend, brain, voice, memory, audit, safe roots, and recent errors."],
                ["Demo", "python scripts\\demo_phase13.py", "Runs typed and mock voice demos without a microphone."],
                ["Verify", "python scripts\\verify_phase13.py", "Runs tests, dataset, safety, and API smoke checks."],
            ],
            [1.25 * inch, 2.5 * inch, 2.75 * inch],
            styles,
            header=True,
        ),
        Paragraph("Verification Results", styles["H1"]),
        table(
            [
                ["Check", "Command", "Result"],
                ["Unit tests", "python -m unittest discover -s tests", "71 tests passed."],
                ["Compile check", "python -m py_compile Phase 13 modules/scripts", "Python modules and scripts compiled successfully."],
                ["Frontend syntax", "node --check web/app.js and diagnostics.js", "Frontend JavaScript parsed successfully."],
                ["Dependency check", "python scripts/check_dependencies.py --json", "Required paths and packages were available."],
                ["Provider check", "python scripts/check_providers.py --json", "Text/browser providers active with no warnings."],
                ["Demo flow", "python scripts/demo_phase13.py", "Typed, note creation, confirmation, and mock voice demos completed."],
                ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Total 285; intent 0.9965; tool 0.9965; arguments 0.9579; confirmation 1.0."],
                ["Safety regression", "python scripts/evaluate_safety_regression.py", "362 cases; tool accuracy 1.0; policy action accuracy 1.0."],
                ["CI-style verifier", "python scripts/verify_phase13.py", "Passed tests, dataset, safety, and API smoke checks."],
            ],
            [1.25 * inch, 2.65 * inch, 2.6 * inch],
            styles,
            header=True,
        ),
        Paragraph("Safety Impact", styles["H1"]),
        Paragraph(
            "Phase 13 does not add a new execution authority. Diagnostics are read-only, the launcher only starts the existing local web server, the demo uses typed and mock voice inputs, and the verifier exercises public API routes.",
            styles["Normal"],
        ),
        Paragraph("Recommended Next Step", styles["H1"]),
        bullets(
            [
                "Package a signed Windows shortcut or small desktop launcher around scripts/launch_ultron.py.",
                "Add a first-run checklist in diagnostics for optional local voice model downloads.",
                "Add exportable demo logs for presentations and beta feedback.",
            ],
            styles,
        ),
    ]
    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    preview()
    print(PDF_OUT.name)


def stylesheet():
    s = getSampleStyleSheet()
    s["Normal"].fontName = "Helvetica"
    s["Normal"].fontSize = 10.2
    s["Normal"].leading = 12.8
    s["Normal"].spaceAfter = 6
    s.add(ParagraphStyle("TitleCustom", parent=s["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=colors.HexColor("#0B2545"), alignment=TA_LEFT, spaceAfter=3))
    s.add(ParagraphStyle("SubtitleCustom", parent=s["Normal"], fontSize=12, leading=15, textColor=colors.HexColor("#555555"), spaceAfter=14))
    s.add(ParagraphStyle("H1", parent=s["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#2E74B5"), spaceBefore=16, spaceAfter=8))
    s.add(ParagraphStyle("Cell", parent=s["Normal"], fontSize=7.95, leading=10.1, spaceAfter=0))
    s.add(ParagraphStyle("CellBold", parent=s["Cell"], fontName="Helvetica-Bold", textColor=colors.HexColor("#0B2545")))
    return s


def table(rows, widths, styles, header=False):
    converted = [[Paragraph(str(cell), styles["CellBold"] if header and r == 0 else styles["Cell"]) for cell in row] for r, row in enumerate(rows)]
    t = Table(converted, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
    cmd = [
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#B8C2CC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        cmd.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7")))
    t.setStyle(TableStyle(cmd))
    return t


def bullets(items, styles):
    return ListFlowable([ListItem(Paragraph(item, styles["Normal"]), leftIndent=18) for item in items], bulletType="bullet", start="circle", leftIndent=18)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 13 Report | Page {doc.page}")
    canvas.restoreState()


def preview() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [
        ["ULTRON 2.7 Phase 13 Execution Report", "Executive Summary", "Phase 13 Scope", "What Was Implemented"],
        ["Beta Operator Workflow", "Verification Results", "Safety Impact", "Recommended Next Step"],
    ]
    for i, lines in enumerate(pages, start=1):
        img = Image.new("RGB", (1275, 1650), "white")
        d = ImageDraw.Draw(img)
        try:
            ft = ImageFont.truetype("arial.ttf", 38)
            fh = ImageFont.truetype("arial.ttf", 27)
            f = ImageFont.truetype("arial.ttf", 22)
        except OSError:
            ft = fh = f = ImageFont.load_default()
        d.rectangle((115, 110, 1160, 1540), outline=(230, 230, 230), width=2)
        y = 150
        for n, line in enumerate(lines):
            d.text((150, y), line, fill=(11, 37, 69) if n == 0 and i == 1 else (46, 116, 181), font=ft if n == 0 and i == 1 else fh)
            y += 55
            if n > 0 or i == 2:
                d.text((175, y), "Rendered in the PDF with Phase 13 beta prototype details.", fill=(45, 45, 45), font=f)
                y += 70
        d.text((860, 1560), f"Preview page {i}", fill=(100, 100, 100), font=f)
        img.save(PREVIEW_DIR / f"page-{i}.png")


if __name__ == "__main__":
    main()
