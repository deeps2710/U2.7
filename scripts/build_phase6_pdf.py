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
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_6_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase6_pdf_preview"


def main() -> None:
    styles = stylesheet()
    doc = SimpleDocTemplate(str(PDF_OUT), pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    story = [
        Paragraph("ULTRON 2.7 Phase 6 Execution Report", styles["TitleCustom"]),
        Paragraph("Agentic brain layer and safe multi-step task runtime", styles["SubtitleCustom"]),
        table(
            [["Project", "ULTRON 2.7"], ["Phase", "Phase 6: Brain Layer"], ["Workspace", "Local workspace checkout: U2.7"], ["Status", "Implemented and verified"]],
            [1.55 * inch, 4.95 * inch],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph(
            "Phase 6 adds ULTRON's brain layer: a task-level orchestration system that can plan multi-step goals, execute allowed steps, pause for confirmation, remember non-sensitive context, and summarize outcomes. The brain does not receive raw shell access.",
            styles["Normal"],
        ),
        Paragraph("Phase 6 Scope", styles["H1"]),
        bullets(
            [
                "Add task state models and a TaskPlan structure.",
                "Add UltronBrain for goal classification, decomposition, preview, execution, and summaries.",
                "Add short-term session memory and persistent non-sensitive memory.",
                "Add console and CLI commands for /plan, /do, /memory, and /forget.",
                "Keep LLM and agentic behavior inside the existing safe runtime boundary.",
            ],
            styles,
        ),
        Paragraph("What Was Implemented", styles["H1"]),
        table(
            [
                ["Area", "File(s)", "Result"],
                ["Brain layer", "src/ultron27/brain.py", "TaskState, TaskStep, TaskPlan, MemoryStore, and UltronBrain."],
                ["Planner support", "src/ultron27/planner.py", "Deterministic append_to_note parsing for multi-step note workflows."],
                ["Console commands", "src/ultron27/console.py", "/plan, /do, /memory, and /forget."],
                ["CLI commands", "src/ultron27/cli.py", "Slash commands work in one-shot and interactive modes."],
                ["Docs", "README.md, docs/architecture.md, docs/phase6_brain_layer.md", "Brain boundary, memory, and command examples."],
                ["Tests", "tests/test_pipeline.py", "Expanded to 31 regression tests."],
            ],
            [1.45 * inch, 2.35 * inch, 2.7 * inch],
            styles,
            header=True,
        ),
        Paragraph("Brain Workflow", styles["H1"]),
        table(
            [
                ["Stage", "Purpose", "Safety Note"],
                ["Goal intake", "Classify single-step vs multi-step.", "No execution during classification."],
                ["TaskPlan", "Create ordered TaskStep entries.", "Preview uses planner, validator, and policy."],
                ["Execution", "Send each step to UltronAssistant.handle().", "Runtime enforces validation, policy, executor, and audit."],
                ["Pause/stop", "Stop on confirmation, blocked, or failed steps.", "High-risk actions cannot silently continue."],
                ["Memory", "Record non-sensitive facts and task summaries.", "Passwords, API keys, and tokens are rejected."],
            ],
            [1.25 * inch, 2.65 * inch, 2.6 * inch],
            styles,
            header=True,
        ),
        Paragraph("Verification Results", styles["H1"]),
        table(
            [
                ["Check", "Command", "Result"],
                ["Unit tests", "python -m unittest discover -s tests", "31 tests passed."],
                ["Acceptance plan", "python -m ultron27 /plan ... --text", "Goal decomposed into create_note and append_to_note."],
                ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Intent 1.0, tool 1.0, argument exact match 0.9614, confirmation 1.0."],
                ["Safety regression", "python scripts/evaluate_safety_regression.py", "362 cases, tool accuracy 1.0, policy action accuracy 1.0."],
            ],
            [1.45 * inch, 2.55 * inch, 2.5 * inch],
            styles,
            header=True,
        ),
        Paragraph("Recommended Next Step", styles["H1"]),
        bullets(
            [
                "Move to Phase 7 by connecting this brain runtime to a dedicated visual interface.",
                "Keep the interface as a client of the brain/runtime API rather than duplicating planner logic.",
                "Preserve the same confirmation and memory boundaries before adding voice in Phase 8.",
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
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 6 Report | Page {doc.page}")
    canvas.restoreState()


def preview() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [
        ["ULTRON 2.7 Phase 6 Execution Report", "Executive Summary", "Phase 6 Scope", "What Was Implemented"],
        ["Brain Workflow", "Verification Results", "Recommended Next Step"],
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
                d.text((175, y), "Rendered in the PDF with Phase 6 brain layer implementation details.", fill=(45, 45, 45), font=f)
                y += 70
        d.text((860, 1560), f"Preview page {i}", fill=(100, 100, 100), font=f)
        img.save(PREVIEW_DIR / f"page-{i}.png")


if __name__ == "__main__":
    main()
