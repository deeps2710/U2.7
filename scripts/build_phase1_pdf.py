from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_1_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase1_pdf_preview"
WORKSPACE_LABEL = "Local workspace checkout: U2.7"

BLUE = colors.HexColor("#2E74B5")
DARK_BLUE = colors.HexColor("#1F4D78")
INK = colors.HexColor("#0B2545")
MUTED = colors.HexColor("#555555")
GRID = colors.HexColor("#B8C2CC")
HEADER_FILL = colors.HexColor("#F2F4F7")
CALLOUT_FILL = colors.HexColor("#F4F6F9")


def main() -> None:
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(PDF_OUT),
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
        title="ULTRON 2.7 Phase 1 Execution Report",
        author="deeps2710",
    )

    story = []
    story.extend(title_block(styles))
    story.extend(executive_summary(styles))
    story.extend(phase_scope(styles))
    story.extend(architecture(styles))
    story.extend(implementation(styles))
    story.extend(safety_model(styles))
    story.extend(verification(styles))
    story.extend(repository_map(styles))
    story.extend(handoff(styles))

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

    styles.add(
        ParagraphStyle(
            "TitleCustom",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=29,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            "SubtitleCustom",
            parent=styles["Normal"],
            fontSize=12,
            leading=15,
            textColor=MUTED,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            "H1",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=BLUE,
            spaceBefore=16,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "H2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=BLUE,
            spaceBefore=12,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "Cell",
            parent=styles["Normal"],
            fontSize=8.7,
            leading=11,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            "CellBold",
            parent=styles["Cell"],
            fontName="Helvetica-Bold",
            textColor=INK,
        )
    )
    styles.add(
        ParagraphStyle(
            "CodeBlock",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=9,
            leading=12,
            backColor=CALLOUT_FILL,
            leftIndent=12,
            rightIndent=12,
            borderPadding=8,
            spaceAfter=10,
        )
    )
    return styles


def title_block(styles):
    meta_rows = [
        ["Project", "ULTRON 2.7"],
        ["Phase", "Phase 1: Core Text Prototype"],
        ["Workspace", WORKSPACE_LABEL],
        ["Status", "Implemented and verified"],
    ]
    return [
        Paragraph("ULTRON 2.7 Phase 1 Execution Report", styles["TitleCustom"]),
        Paragraph("Basic text-first prototype for a safe Jarvis-style laptop assistant", styles["SubtitleCustom"]),
        styled_table(meta_rows, [1.55 * inch, 4.95 * inch], styles),
        Spacer(1, 8),
    ]


def executive_summary(styles):
    return [
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph(
            "Phase 1 has been executed as a safe text-first assistant prototype. "
            "The implementation converts a user command into a structured tool call, validates the call against an allowlisted schema, applies risk and confirmation policy, runs only through a controlled executor, and writes an audit record.",
            styles["Normal"],
        ),
        Paragraph(
            "The prototype intentionally defaults to dry-run execution. High-risk commands, such as deleting files, stop at a confirmation gate instead of executing directly.",
            styles["Normal"],
        ),
    ]


def phase_scope(styles):
    items = [
        "Build a command-line assistant entry point.",
        "Use the supplied dataset for exact and fuzzy command planning.",
        "Add deterministic regex fallbacks for common numeric commands.",
        "Define typed tool schemas and argument validation.",
        "Add policy gates for low, medium, high, and unsupported actions.",
        "Add a dry-run executor and audit log.",
        "Add tests and dataset evaluation for the basic prototype.",
    ]
    return [Paragraph("Phase 1 Scope", styles["H1"]), bullet_list(items, styles)]


def architecture(styles):
    return [
        Paragraph("Implemented Architecture", styles["H1"]),
        Paragraph("The current Phase 1 pipeline is:", styles["Normal"]),
        Paragraph("text command -> planner -> tool call -> validator -> policy -> executor -> audit log", styles["CodeBlock"]),
        Paragraph(
            "The design follows the research paper's recommendation that the LLM or planner should propose actions, while the application remains responsible for validation, permission checks, execution, and logging.",
            styles["Normal"],
        ),
    ]


def implementation(styles):
    rows = [
        ["Component", "File(s)", "Purpose"],
        ["CLI", "src/ultron27/cli.py", "Accepts a typed command, prints JSON output, and writes audit records."],
        ["Planner", "src/ultron27/planner.py", "Uses dataset matching plus deterministic fallbacks to produce a tool call."],
        ["Tool schemas", "src/ultron27/tools.py", "Defines allowed tools, required arguments, numeric ranges, and validation rules."],
        ["Policy", "src/ultron27/policy.py", "Allows safe commands, confirms risky commands, and blocks unsupported requests."],
        ["Executor", "src/ultron27/executor.py", "Runs dry-run actions by default and contains safe handlers for early tools."],
        ["Evaluation", "src/ultron27/evaluate.py, scripts/evaluate_dataset.py", "Measures planner quality against the supplied dataset splits."],
        ["Tests", "tests/test_pipeline.py", "Covers parsing, validation, policy, and dry-run execution behavior."],
        ["Docs", "README.md, docs/architecture.md, docs/evaluation.md", "Explains usage, architecture, evaluation, and next steps."],
    ]
    return [Paragraph("What Was Implemented", styles["H1"]), styled_table(rows, [1.4 * inch, 2.0 * inch, 3.1 * inch], styles, header=True)]


def safety_model(styles):
    rows = [
        ["Risk", "Examples", "Prototype behavior"],
        ["None", "clarification, unsupported request", "No OS action is executed."],
        ["Low", "open app, set volume, search files", "Allowed after schema validation."],
        ["Medium", "draft email, move file, calendar draft", "Confirmation when configured by the tool."],
        ["High", "delete file, send email, run script, shutdown", "Confirmation required; destructive execution is not implemented."],
    ]
    return [
        Paragraph("Safety Model", styles["H1"]),
        Paragraph("Phase 1 enforces a tool-based safety model instead of direct shell access.", styles["Normal"]),
        styled_table(rows, [1.05 * inch, 2.35 * inch, 3.1 * inch], styles, header=True),
    ]


def verification(styles):
    rows = [
        ["Check", "Command", "Result"],
        ["Unit tests", "python -m unittest discover -s tests", "6 tests passed."],
        ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Intent 1.0, tool 1.0, argument exact match 0.9614, confirmation 1.0."],
        ["High-risk command", 'python -m ultron27 "delete project_report.txt"', "Policy returned confirmation_required."],
    ]
    return [
        Paragraph("Verification Results", styles["H1"]),
        Paragraph("The Phase 1 prototype was verified with unit tests, dataset evaluation, and a high-risk CLI safety check.", styles["Normal"]),
        styled_table(rows, [1.45 * inch, 2.25 * inch, 2.8 * inch], styles, header=True),
        Paragraph(
            "The argument exact-match misses come from ambiguous synthetic dataset rows where similar or identical utterances have different generated file types, folders, or file names. That is documented in docs/evaluation.md.",
            styles["Normal"],
        ),
    ]


def repository_map(styles):
    items = [
        "src/ultron27: assistant package and core Phase 1 logic.",
        "scripts/evaluate_dataset.py: dataset evaluation entry point.",
        "tests/test_pipeline.py: regression tests for command planning and safety gates.",
        "data/jarvis_dataset_v2: supplied synthetic command dataset.",
        "docs/jarvis_research_paper.md: supplied research paper.",
        "docs/architecture.md: local-first architecture summary.",
        "docs/evaluation.md: baseline metrics and dataset notes.",
    ]
    return [Paragraph("Repository Map", styles["H1"]), bullet_list(items, styles)]


def handoff(styles):
    run_items = [
        "Set PYTHONPATH to src when running from the checkout, or install with pip install -e .",
        'Run a safe command: python -m ultron27 "set volume to 40 percent".',
        'Check a high-risk gate: python -m ultron27 "delete project_report.txt".',
        "Run tests: python -m unittest discover -s tests.",
        "Run evaluation: python scripts/evaluate_dataset.py --split test.",
    ]
    return [
        Paragraph("How To Run Phase 1", styles["H1"]),
        numbered_list(run_items, styles),
        Paragraph("Recommended Next Phase", styles["H1"]),
        Paragraph(
            "Phase 2 should focus on real low-risk laptop execution: app opening, file search, folder opening, note creation, reminders, clipboard, screenshot, volume, and brightness adapters. High-risk actions should remain preview-only until the confirmation UX is stronger.",
            styles["Normal"],
        ),
    ]


def styled_table(rows, widths, styles, header: bool = False):
    converted = []
    for row_index, row in enumerate(rows):
        converted.append([
            Paragraph(str(cell), styles["CellBold"] if header and row_index == 0 else styles["Cell"])
            for cell in row
        ])
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
    return ListFlowable(
        [ListItem(Paragraph(item, styles["Normal"]), leftIndent=18) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=18,
    )


def numbered_list(items, styles):
    return ListFlowable(
        [ListItem(Paragraph(item, styles["Normal"]), leftIndent=18) for item in items],
        bulletType="1",
        leftIndent=18,
    )


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 1 Report | Page {doc.page}")
    canvas.restoreState()


def write_preview_pngs() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [
        [
            "ULTRON 2.7 Phase 1 Execution Report",
            "Executive Summary",
            "Phase 1 Scope",
            "Implemented Architecture",
            "What Was Implemented",
        ],
        [
            "Safety Model",
            "Verification Results",
            "Repository Map",
        ],
        [
            "How To Run Phase 1",
            "Recommended Next Phase",
        ],
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
                draw.text((175, y), "Rendered in the PDF with prose, lists, tables, and verification details.", fill=(45, 45, 45), font=font)
                y += 70
        draw.text((860, 1560), f"Preview page {index}", fill=(100, 100, 100), font=font)
        img.save(PREVIEW_DIR / f"page-{index}.png")


if __name__ == "__main__":
    main()
