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
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_3_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase3_pdf_preview"


def main() -> None:
    styles = stylesheet()
    doc = SimpleDocTemplate(str(PDF_OUT), pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    story = [
        Paragraph("ULTRON 2.7 Phase 3 Execution Report", styles["TitleCustom"]),
        Paragraph("Dataset quality and safety regression layer", styles["SubtitleCustom"]),
        table([["Project", "ULTRON 2.7"], ["Phase", "Phase 3: Dataset Quality And Safety Evaluation"], ["Workspace", "Local workspace checkout: U2.7"], ["Status", "Implemented and verified"]], [1.55 * inch, 4.95 * inch], styles),
        Spacer(1, 8),
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph("Phase 3 adds dataset quality and safety evaluation tooling. ULTRON can now audit the supplied synthetic dataset, identify ambiguous duplicate labels, flag underspecified commands, extract safety regression cases, and evaluate planner/policy behavior against those cases.", styles["Normal"]),
        Paragraph("Phase 3 Scope", styles["H1"]),
        bullets(["Analyze the full 2,500-example dataset.", "Detect duplicate utterances with conflicting labels.", "Flag underspecified search/open-file examples.", "Extract high-risk and confirmation-gated safety cases.", "Evaluate policy behavior on the safety regression set."], styles),
        Paragraph("What Was Implemented", styles["H1"]),
        table([["Area", "File(s)", "Result"], ["Dataset quality module", "src/ultron27/dataset_quality.py", "Reusable analyzer and safety-case extraction."], ["Quality script", "scripts/analyze_dataset_quality.py", "Writes JSON report and safety regression JSONL."], ["Safety evaluator", "scripts/evaluate_safety_regression.py", "Checks expected tools and policy actions."], ["Generated artifacts", "docs/phase3_dataset_quality_report.json, data/regression/safety_cases.jsonl", "Concrete audit output."], ["Tests", "tests/test_pipeline.py", "Expanded to 17 regression tests."]], [1.55 * inch, 2.35 * inch, 2.6 * inch], styles, header=True),
        Paragraph("Audit Metrics", styles["H1"]),
        table([["Metric", "Value", "Meaning"], ["Total examples", "2500", "Full supplied synthetic dataset size."], ["Unique utterances", "2319", "Normalized utterances after duplicate grouping."], ["Duplicate groups", "101", "Utterances appearing more than once."], ["Conflicting duplicate groups", "101", "Duplicate groups with different labels or arguments."], ["Underspecified examples", "879", "Examples whose labels contain slots not explicit in the text."], ["Safety examples", "362", "High-risk, confirmation-gated, or unsupported examples."]], [2.0 * inch, 1.0 * inch, 3.5 * inch], styles, header=True),
        Paragraph("Verification Results", styles["H1"]),
        table([["Check", "Command", "Result"], ["Unit tests", "python -m unittest discover -s tests", "17 tests passed."], ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Intent 1.0, tool 1.0, argument exact match 0.9614, confirmation 1.0."], ["Quality audit", "python scripts/analyze_dataset_quality.py", "Report and safety cases generated."], ["Safety regression", "python scripts/evaluate_safety_regression.py", "362 cases, tool accuracy 1.0, policy action accuracy 1.0."]], [1.45 * inch, 2.55 * inch, 2.5 * inch], styles, header=True),
        Paragraph("Recommended Next Step", styles["H1"]),
        bullets(["Deduplicate conflicting synthetic rows.", "Convert underspecified file-search rows into clarification examples.", "Add real usage logs with corrected transcripts.", "Add Hinglish, Hindi, and STT-error variants.", "Keep safety cases as a permanent regression gate."], styles),
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
    cmd = [("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#B8C2CC")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
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
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 3 Report | Page {doc.page}")
    canvas.restoreState()


def preview() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [["ULTRON 2.7 Phase 3 Execution Report", "Executive Summary", "Phase 3 Scope", "What Was Implemented"], ["Audit Metrics", "Verification Results", "Recommended Next Step"]]
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
                d.text((175, y), "Rendered in the PDF with Phase 3 dataset and safety evaluation details.", fill=(45, 45, 45), font=f)
                y += 70
        d.text((860, 1560), f"Preview page {i}", fill=(100, 100, 100), font=f)
        img.save(PREVIEW_DIR / f"page-{i}.png")


if __name__ == "__main__":
    main()

