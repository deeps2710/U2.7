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
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_5_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase5_pdf_preview"


def main() -> None:
    styles = stylesheet()
    doc = SimpleDocTemplate(str(PDF_OUT), pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    story = [
        Paragraph("ULTRON 2.7 Phase 5 Execution Report", styles["TitleCustom"]),
        Paragraph("Interactive prototype and reusable assistant runtime", styles["SubtitleCustom"]),
        table(
            [["Project", "ULTRON 2.7"], ["Phase", "Phase 5: Interactive Prototype"], ["Workspace", "Local workspace checkout: U2.7"], ["Status", "Implemented and verified"]],
            [1.55 * inch, 4.95 * inch],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph(
            "Phase 5 completes the basic working prototype by adding an interactive assistant console on top of the existing ULTRON safety pipeline. The new console keeps the assistant text-first while making repeated commands, confirmation flows, and JSON inspection practical for demos and iterative testing.",
            styles["Normal"],
        ),
        Paragraph("Phase 5 Scope", styles["H1"]),
        bullets(
            [
                "Create a reusable runtime object for repeated assistant commands.",
                "Add an interactive console entry point with concise human-readable responses.",
                "Keep the same planner, validator, policy, executor, and audit path for one-shot and interactive usage.",
                "Add confirmation, JSON inspection, help, and exit commands inside the console.",
                "Document the final prototype workflow and provide a Windows convenience launcher.",
            ],
            styles,
        ),
        Paragraph("What Was Implemented", styles["H1"]),
        table(
            [
                ["Area", "File(s)", "Result"],
                ["Reusable runtime", "src/ultron27/runtime.py", "RuntimeSettings and UltronAssistant for repeated commands without reloading the dataset."],
                ["Interactive console", "src/ultron27/console.py", "/help, /json, /yes, /exit, and concise text response formatting."],
                ["CLI integration", "src/ultron27/cli.py", "--interactive/-i and --text while preserving JSON as the default."],
                ["Launcher", "scripts/run_ultron_console.ps1", "PowerShell helper to start the console from the repo root."],
                ["Docs", "README.md, docs/phase5_interactive_prototype.md", "Interactive prototype workflow and command examples."],
                ["Tests", "tests/test_pipeline.py", "Expanded to 24 regression tests."],
            ],
            [1.45 * inch, 2.35 * inch, 2.7 * inch],
            styles,
            header=True,
        ),
        Paragraph("Console Commands", styles["H1"]),
        table(
            [["Command", "Purpose"], ["/help", "Show available console commands."], ["/json <command>", "Run a command and print the full JSON payload."], ["/yes <command>", "Confirm a command that requires confirmation."], ["/exit", "Leave the interactive console."]],
            [1.6 * inch, 4.9 * inch],
            styles,
            header=True,
        ),
        Paragraph("Verification Results", styles["H1"]),
        table(
            [
                ["Check", "Command", "Result"],
                ["Unit tests", "python -m unittest discover -s tests", "24 tests passed."],
                ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Intent 1.0, tool 1.0, argument exact match 0.9614, confirmation 1.0."],
                ["Safety regression", "python scripts/evaluate_safety_regression.py", "362 cases, tool accuracy 1.0, policy action accuracy 1.0."],
                ["Text smoke test", "python -m ultron27 ... --text --no-audit", "High-risk command returned confirmation_required with /yes guidance."],
            ],
            [1.45 * inch, 2.55 * inch, 2.5 * inch],
            styles,
            header=True,
        ),
        Paragraph("Prototype Status", styles["H1"]),
        bullets(
            [
                "The project now has a working text-first assistant loop.",
                "The default behavior remains safe dry-run execution.",
                "Low-risk actions can be executed through the allowlisted executor when --execute is used.",
                "Destructive actions remain intentionally unimplemented in the MVP.",
                "The next major layer should be voice input and voice output on top of this stable console runtime.",
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
    s["Normal"].fontSize = 10.5
    s["Normal"].leading = 13.2
    s["Normal"].spaceAfter = 6
    s.add(ParagraphStyle("TitleCustom", parent=s["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=colors.HexColor("#0B2545"), alignment=TA_LEFT, spaceAfter=3))
    s.add(ParagraphStyle("SubtitleCustom", parent=s["Normal"], fontSize=12, leading=15, textColor=colors.HexColor("#555555"), spaceAfter=14))
    s.add(ParagraphStyle("H1", parent=s["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#2E74B5"), spaceBefore=16, spaceAfter=8))
    s.add(ParagraphStyle("Cell", parent=s["Normal"], fontSize=8.7, leading=11, spaceAfter=0))
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
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 5 Report | Page {doc.page}")
    canvas.restoreState()


def preview() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [
        ["ULTRON 2.7 Phase 5 Execution Report", "Executive Summary", "Phase 5 Scope", "What Was Implemented"],
        ["Console Commands", "Verification Results", "Prototype Status"],
    ]
    for i, lines in enumerate(pages, start=1):
        img = Image.new("RGB", (1275, 1650), "white")
        d = ImageDraw.Draw(img)
        ft = ImageFont.truetype("arial.ttf", 38)
        fh = ImageFont.truetype("arial.ttf", 27)
        f = ImageFont.truetype("arial.ttf", 22)
        d.rectangle((115, 110, 1160, 1540), outline=(230, 230, 230), width=2)
        y = 150
        for n, line in enumerate(lines):
            d.text((150, y), line, fill=(11, 37, 69) if n == 0 and i == 1 else (46, 116, 181), font=ft if n == 0 and i == 1 else fh)
            y += 55
            if n > 0 or i == 2:
                d.text((175, y), "Rendered in the PDF with Phase 5 interactive prototype details.", fill=(45, 45, 45), font=f)
                y += 70
        d.text((860, 1560), f"Preview page {i}", fill=(100, 100, 100), font=f)
        img.save(PREVIEW_DIR / f"page-{i}.png")


if __name__ == "__main__":
    main()
