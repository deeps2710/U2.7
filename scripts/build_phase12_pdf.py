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
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_12_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase12_pdf_preview"


def main() -> None:
    styles = stylesheet()
    doc = SimpleDocTemplate(str(PDF_OUT), pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    story = [
        Paragraph("ULTRON 2.7 Phase 12 Execution Report", styles["TitleCustom"]),
        Paragraph("Skills and local knowledge base", styles["SubtitleCustom"]),
        table(
            [["Project", "ULTRON 2.7"], ["Phase", "Phase 12: Skills and Local Knowledge"], ["Workspace", "Local workspace checkout: U2.7"], ["Status", "Implemented and verified"]],
            [1.55 * inch, 4.95 * inch],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph(
            "Phase 12 adds a reusable skill registry and local knowledge base to ULTRON 2.7. ULTRON can now list and run built-in skills, ingest safe local documents, search project knowledge, and expose skills, sources, and recent tasks through the web interface.",
            styles["Normal"],
        ),
        Paragraph(
            "Skills and knowledge do not bypass safety. Skills validate their own schemas, pass through skill policy, and use the typed tool runtime for OS-facing actions. Knowledge retrieval provides context only; it never becomes execution authority.",
            styles["Normal"],
        ),
        Paragraph("Phase 12 Scope", styles["H1"]),
        bullets(
            [
                "Add a skill registry with names, descriptions, schemas, risk levels, handlers, and examples.",
                "Add built-in notes, reminders, file search, project summary, and daily planning skills.",
                "Add a local knowledge base with safe-root enforcement, extraction, chunking, metadata, keyword search, and keyword-only embedding fallback.",
                "Reject obvious secrets during skill input validation and knowledge ingestion.",
                "Add skills and knowledge APIs.",
                "Add UI panels for skills, memory/knowledge, knowledge search, and recent task history.",
                "Add regression tests and architecture documentation.",
            ],
            styles,
        ),
        Paragraph("What Was Implemented", styles["H1"]),
        table(
            [
                ["Area", "File(s)", "Result"],
                ["Skill registry", "src/ultron27/skills.py", "Schema validation, privacy checks, skill-level policy, built-in skills, examples, and skill-run audit records."],
                ["Knowledge base", "src/ultron27/knowledge.py", "Safe-root ingestion, Markdown/TXT/PDF/DOCX extraction where available, chunking, metadata, keyword search, and secret rejection."],
                ["Runtime support", "src/ultron27/runtime.py", "Adds handle_tool_call() so skills can submit typed tool calls through validation, policy, executor, and audit."],
                ["Local API", "src/ultron27/web_server.py", "Adds skills and knowledge endpoints."],
                ["Interface", "web/index.html, web/styles.css, web/app.js", "Adds skills, memory/knowledge, local search, and recent-task panels."],
                ["Tests", "tests/test_pipeline.py", "Expands to 67 tests covering skills, knowledge, privacy, policy, and endpoints."],
            ],
            [1.35 * inch, 2.35 * inch, 2.8 * inch],
            styles,
            header=True,
        ),
        Paragraph("Safety Boundary", styles["H1"]),
        table(
            [
                ["Boundary", "Rule", "Why It Matters"],
                ["Skill schema", "Inputs must match each skill schema.", "Prevents ambiguous or unexpected skill payloads."],
                ["Skill policy", "Medium and high-risk skills require confirmation.", "Keeps reusable skills under the same permission model."],
                ["Tool runtime", "OS-facing skills call handle_tool_call().", "Preserves validation, policy, executor restrictions, and audit logging."],
                ["Knowledge paths", "Ingested files must stay inside safe roots.", "Prevents accidental indexing of private filesystem areas."],
                ["Knowledge content", "Obvious secrets are rejected.", "Prevents storing passwords, tokens, API keys, and credentials."],
                ["Retrieval", "Search results are context only.", "Knowledge cannot command ULTRON to execute tasks."],
            ],
            [1.35 * inch, 2.35 * inch, 2.8 * inch],
            styles,
            header=True,
        ),
        Paragraph("Verification Results", styles["H1"]),
        table(
            [
                ["Check", "Command", "Result"],
                ["Unit tests", "$env:PYTHONPATH='src'; python -m unittest discover -s tests", "67 tests passed."],
                ["Compile check", "python -m py_compile Phase 12 modules and scripts", "Phase 12 Python modules compiled successfully."],
                ["Frontend syntax", "bundled node --check web/app.js", "Frontend JavaScript parsed successfully."],
                ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Intent 0.9965, tool 0.9965, argument exact match 0.9579, confirmation 1.0."],
                ["Safety regression", "python scripts/evaluate_safety_regression.py", "362 cases, tool accuracy 1.0, policy action accuracy 1.0."],
                ["API smoke", "Local HTTP checks", "Skills, knowledge ingest/search, and status panels returned expected payloads."],
            ],
            [1.3 * inch, 2.65 * inch, 2.55 * inch],
            styles,
            header=True,
        ),
        Paragraph("Recommended Next Step", styles["H1"]),
        bullets(
            [
                "Add optional embeddings with a local provider and keep keyword search as fallback.",
                "Add source-linked answer generation that cites local chunks.",
                "Add a user-reviewed knowledge source manager for deleting and re-ingesting documents.",
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
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 12 Report | Page {doc.page}")
    canvas.restoreState()


def preview() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [
        ["ULTRON 2.7 Phase 12 Execution Report", "Executive Summary", "Phase 12 Scope", "What Was Implemented"],
        ["Safety Boundary", "Verification Results", "Recommended Next Step"],
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
                d.text((175, y), "Rendered in the PDF with Phase 12 skill and knowledge details.", fill=(45, 45, 45), font=f)
                y += 70
        d.text((860, 1560), f"Preview page {i}", fill=(100, 100, 100), font=f)
        img.save(PREVIEW_DIR / f"page-{i}.png")


if __name__ == "__main__":
    main()
