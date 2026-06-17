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
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_11_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase11_pdf_preview"


def main() -> None:
    styles = stylesheet()
    doc = SimpleDocTemplate(str(PDF_OUT), pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    story = [
        Paragraph("ULTRON 2.7 Phase 11 Execution Report", styles["TitleCustom"]),
        Paragraph("Windows automation executor pack", styles["SubtitleCustom"]),
        table(
            [["Project", "ULTRON 2.7"], ["Phase", "Phase 11: Windows Automation Executor Pack"], ["Workspace", "Local workspace checkout: U2.7"], ["Status", "Implemented and verified"]],
            [1.55 * inch, 4.95 * inch],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph(
            "Phase 11 adds a real Windows automation executor pack while keeping ULTRON 2.7 inside the existing typed-tool safety architecture. The assistant can now front practical laptop actions such as app launch, safe-root file work, notes, reminders, clipboard, screenshots, and optional volume/brightness adapters.",
            styles["Normal"],
        ),
        Paragraph(
            "The LLM and planner still do not receive raw shell access. Every action remains user request -> brain/planner -> typed tool call -> schema validation -> policy gate -> executor adapter -> audit log -> response.",
            styles["Normal"],
        ),
        Paragraph("Phase 11 Scope", styles["H1"]),
        bullets(
            [
                "Add a Windows automation adapter module behind the executor.",
                "Restrict app launch to an approved alias registry.",
                "Block explicit file and folder paths outside configured safe roots.",
                "Require confirmation for medium-risk and high-risk actions.",
                "Keep destructive actions non-destructive and not implemented.",
                "Add a UI confirmation modal and confirmation-cancel API.",
                "Add a recent-audit endpoint for runtime inspection.",
                "Add tests and docs for the Windows pack.",
            ],
            styles,
        ),
        Paragraph("What Was Implemented", styles["H1"]),
        table(
            [
                ["Area", "File(s)", "Result"],
                ["Windows adapter", "src/ultron27/windows_executor.py", "Typed helpers for app aliases, path opening, clipboard, screenshots, optional volume, optional brightness, and safe target validation."],
                ["Executor", "src/ultron27/executor.py", "Routes Windows tasks through the adapter, blocks unsafe explicit paths, handles medium/destructive tools conservatively, and preserves dry-run behavior."],
                ["Policy", "src/ultron27/policy.py, src/ultron27/models.py", "Adds permission levels and requires confirmation for medium-risk and high-risk commands."],
                ["Planner", "src/ultron27/planner.py", "Routes terminal commands to the medium-risk terminal tool instead of generic app launch."],
                ["Audit API", "src/ultron27/audit.py, src/ultron27/web_server.py", "Adds recent audit reading plus GET /api/audit/recent."],
                ["Visual UI", "web/index.html, web/styles.css, web/app.js", "Adds a confirmation modal for risky typed and voice actions, plus cancellation that clears pending voice confirmation."],
                ["Tests", "tests/test_pipeline.py", "Expands to 60 tests covering safe roots, alias resolution, confirmation blocking, destructive non-execution, and audit endpoints."],
            ],
            [1.35 * inch, 2.35 * inch, 2.8 * inch],
            styles,
            header=True,
        ),
        Paragraph("Permission Behavior", styles["H1"]),
        table(
            [
                ["Level", "Meaning", "Phase 11 Handling"],
                ["low_risk_allowed", "Validated low-risk tool.", "Allowed after schema validation and policy approval."],
                ["medium_risk_confirmation", "Tool can affect local state or open powerful surfaces.", "Paused until explicit confirmation."],
                ["high_risk_confirmation", "Tool has elevated risk.", "Paused until explicit confirmation."],
                ["destructive_blocked_or_not_implemented", "Delete, move, rename, script, email, shutdown, restart.", "Confirmation-gated, then executor returns not_implemented rather than destructive behavior."],
                ["blocked", "Invalid, unsafe, or unknown execution request.", "Rejected before executor side effects."],
            ],
            [1.9 * inch, 2.1 * inch, 2.5 * inch],
            styles,
            header=True,
        ),
        Paragraph("Verification Results", styles["H1"]),
        table(
            [
                ["Check", "Command", "Result"],
                ["Unit tests", "$env:PYTHONPATH='src'; python -m unittest discover -s tests", "60 tests passed."],
                ["Compile check", "python -m py_compile src/ultron27/windows_executor.py src/ultron27/executor.py src/ultron27/policy.py src/ultron27/web_server.py scripts/run_phase11_windows_ui.py", "Phase 11 Python modules compiled successfully."],
                ["Frontend syntax", "bundled node --check web/app.js", "Frontend JavaScript parsed successfully."],
                ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Intent 0.9965, tool 0.9965, argument exact match 0.9579, confirmation 1.0. The intentional miss is Terminal now routing to the safer medium-risk terminal tool."],
                ["Safety regression", "python scripts/evaluate_safety_regression.py", "362 cases, tool accuracy 1.0, policy action accuracy 1.0."],
                ["API smoke", "Local HTTP checks", "Status, command confirmation, and audit recent routes returned expected payloads."],
            ],
            [1.3 * inch, 2.65 * inch, 2.55 * inch],
            styles,
            header=True,
        ),
        Paragraph("Recommended Next Step", styles["H1"]),
        bullets(
            [
                "Install optional Windows packages for real volume and brightness control if those features are needed on the target laptop.",
                "Add a small UI audit viewer panel on top of /api/audit/recent.",
                "Build a signed or user-reviewed app alias editor instead of editing JSON by hand.",
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
    s["Normal"].fontSize = 10.4
    s["Normal"].leading = 13
    s["Normal"].spaceAfter = 6
    s.add(ParagraphStyle("TitleCustom", parent=s["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=colors.HexColor("#0B2545"), alignment=TA_LEFT, spaceAfter=3))
    s.add(ParagraphStyle("SubtitleCustom", parent=s["Normal"], fontSize=12, leading=15, textColor=colors.HexColor("#555555"), spaceAfter=14))
    s.add(ParagraphStyle("H1", parent=s["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#2E74B5"), spaceBefore=16, spaceAfter=8))
    s.add(ParagraphStyle("Cell", parent=s["Normal"], fontSize=8.15, leading=10.5, spaceAfter=0))
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
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 11 Report | Page {doc.page}")
    canvas.restoreState()


def preview() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [
        ["ULTRON 2.7 Phase 11 Execution Report", "Executive Summary", "Phase 11 Scope", "What Was Implemented"],
        ["Permission Behavior", "Verification Results", "Recommended Next Step"],
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
                d.text((175, y), "Rendered in the PDF with Phase 11 Windows executor details.", fill=(45, 45, 45), font=f)
                y += 70
        d.text((860, 1560), f"Preview page {i}", fill=(100, 100, 100), font=f)
        img.save(PREVIEW_DIR / f"page-{i}.png")


if __name__ == "__main__":
    main()
