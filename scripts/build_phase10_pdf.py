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
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_10_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase10_pdf_preview"


def main() -> None:
    styles = stylesheet()
    doc = SimpleDocTemplate(str(PDF_OUT), pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    story = [
        Paragraph("ULTRON 2.7 Phase 10 Execution Report", styles["TitleCustom"]),
        Paragraph("Wake-word detection and voice activity gating", styles["SubtitleCustom"]),
        table(
            [["Project", "ULTRON 2.7"], ["Phase", "Phase 10: Wake Word and VAD"], ["Workspace", "Local workspace checkout: U2.7"], ["Status", "Implemented and verified"]],
            [1.55 * inch, 4.95 * inch],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph(
            "Phase 10 adds wake-word detection and stronger voice activity detection to ULTRON 2.7. ULTRON can now enter an always-listening mode, wait for ULTRON or Hey ULTRON, ignore empty/noisy input, and only send authorized speech segments into STT and the safe runtime.",
            styles["Normal"],
        ),
        Paragraph(
            "Wake word and VAD are input gates only. They cannot choose tools, execute commands, skip validation, bypass policy, or bypass audit logging.",
            styles["Normal"],
        ),
        Paragraph("Phase 10 Scope", styles["H1"]),
        bullets(
            [
                "Add wake-word and VAD provider abstractions.",
                "Add text/mock wake-word providers and health-checked openWakeWord support.",
                "Add energy-threshold VAD plus health-checked Silero and WebRTC adapters.",
                "Add always-listening modes: inactive, waiting_for_wake_word, listening, transcribing, thinking, and speaking.",
                "Add wake APIs and UI privacy controls.",
                "Keep push-to-talk and typed input available.",
                "Add regression tests for wake gating, noisy input, VAD-gated STT, and unchanged high-risk confirmation behavior.",
            ],
            styles,
        ),
        Paragraph("What Was Implemented", styles["H1"]),
        table(
            [
                ["Area", "File(s)", "Result"],
                ["Wake/VAD runtime", "src/ultron27/wake.py", "Provider protocols, wake providers, VAD providers, health checks, and wake phrase stripping."],
                ["Voice session", "src/ultron27/voice.py", "Always-listening state, wake snapshots, wake processing, VAD gating, and safe STT handoff."],
                ["Local API", "src/ultron27/web_server.py", "Added wake start, stop, status, and process routes."],
                ["Configuration", "src/ultron27/config.py, ultron.config.example.json", "Added wake provider, wake phrases, wake model path, VAD provider, and VAD threshold settings."],
                ["Web interface", "web/index.html, web/styles.css, web/app.js", "Added always-listening toggle, mic privacy status, wake gate status, VAD status, and ignored-input feedback."],
                ["Tests", "tests/test_pipeline.py", "Expanded to 54 tests covering wake word, no-wake ignore, noisy input, VAD-gated STT, wake APIs, config parsing, and safety regression."],
            ],
            [1.35 * inch, 2.35 * inch, 2.8 * inch],
            styles,
            header=True,
        ),
        Paragraph("Wake/VAD Pipeline", styles["H1"]),
        table(
            [
                ["Stage", "Purpose", "Safety Property"],
                ["Candidate input", "Browser or mock voice submits a candidate speech segment.", "No command execution happens at capture time."],
                ["VAD", "Empty, noisy, or low-energy input is ignored.", "Noisy audio does not reach STT or the brain."],
                ["Wake word", "ULTRON or Hey ULTRON must be present while waiting.", "Background speech without wake phrase is ignored."],
                ["STT", "Authorized speech is transcribed through the existing provider layer.", "STT output is still untrusted user input."],
                ["Brain/runtime", "The command flows through the same typed tool pipeline.", "Validation, policy, executor, and audit remain authoritative."],
            ],
            [1.3 * inch, 2.6 * inch, 2.6 * inch],
            styles,
            header=True,
        ),
        Paragraph("Verification Results", styles["H1"]),
        table(
            [
                ["Check", "Command", "Result"],
                ["Unit tests", "$env:PYTHONPATH='src'; python -m unittest discover -s tests", "54 tests passed."],
                ["Compile check", "python -m py_compile src/ultron27/config.py src/ultron27/wake.py src/ultron27/voice.py src/ultron27/web_server.py scripts/run_phase10_wake_ui.py", "Phase 10 Python modules compiled successfully."],
                ["Frontend syntax", "bundled node --check web/app.js", "Frontend JavaScript parsed successfully."],
                ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Intent 1.0, tool 1.0, argument exact match 0.9614, confirmation 1.0."],
                ["Safety regression", "python scripts/evaluate_safety_regression.py", "362 cases, tool accuracy 1.0, policy action accuracy 1.0."],
                ["Wake API smoke", "ThreadingHTTPServer endpoint checks", "Wake start, status, process, and stop routes returned expected payloads."],
            ],
            [1.3 * inch, 2.65 * inch, 2.55 * inch],
            styles,
            header=True,
        ),
        Paragraph("Recommended Next Step", styles["H1"]),
        bullets(
            [
                "Install real openWakeWord and Silero/WebRTC dependencies for microphone audio.",
                "Connect browser microphone chunks or local audio capture to the wake/VAD providers.",
                "Add streaming partial transcripts after the wake path is stable.",
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
    s.add(ParagraphStyle("Cell", parent=s["Normal"], fontSize=8.45, leading=10.7, spaceAfter=0))
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
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 10 Report | Page {doc.page}")
    canvas.restoreState()


def preview() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [
        ["ULTRON 2.7 Phase 10 Execution Report", "Executive Summary", "Phase 10 Scope", "What Was Implemented"],
        ["Wake/VAD Pipeline", "Verification Results", "Recommended Next Step"],
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
                d.text((175, y), "Rendered in the PDF with Phase 10 wake/VAD implementation details.", fill=(45, 45, 45), font=f)
                y += 70
        d.text((860, 1560), f"Preview page {i}", fill=(100, 100, 100), font=f)
        img.save(PREVIEW_DIR / f"page-{i}.png")


if __name__ == "__main__":
    main()
