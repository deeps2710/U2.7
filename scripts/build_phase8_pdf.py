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
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_8_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase8_pdf_preview"


def main() -> None:
    styles = stylesheet()
    doc = SimpleDocTemplate(str(PDF_OUT), pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    story = [
        Paragraph("ULTRON 2.7 Phase 8 Execution Report", styles["TitleCustom"]),
        Paragraph("Voice interaction, transcript history, and speech response layer", styles["SubtitleCustom"]),
        table(
            [["Project", "ULTRON 2.7"], ["Phase", "Phase 8: Voice Mode"], ["Workspace", "Local workspace checkout: U2.7"], ["Status", "Implemented and verified"]],
            [1.55 * inch, 4.95 * inch],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph(
            "Phase 8 adds voice interaction to ULTRON 2.7. The interface can listen through browser speech recognition when available, send transcripts through the local API, process commands with the existing brain/runtime, and speak responses through browser speech synthesis.",
            styles["Normal"],
        ),
        Paragraph(
            "Voice mode remains an adapter around the safe runtime. It does not bypass typed tool calls, schema validation, policy gates, executor restrictions, audit logging, or confirmation requirements.",
            styles["Normal"],
        ),
        Paragraph("Phase 8 Scope", styles["H1"]),
        bullets(
            [
                "Add a backend voice module with STT/TTS provider abstractions.",
                "Add voice API endpoints for start, stop, transcribe, speak, and status.",
                "Add microphone, push-to-talk, mute, stop-speaking, confirmation, and mock voice controls.",
                "Use browser speech-recognition events plus empty-transcript rejection as the lightweight VAD path.",
                "Add transcript history covering user speech, understood command, selected tool, result, and spoken response.",
                "Keep typed commands and subtitles available as fallbacks.",
                "Add tests with mocked speech providers and safe confirmation behavior.",
            ],
            styles,
        ),
        Paragraph("What Was Implemented", styles["H1"]),
        table(
            [
                ["Area", "File(s)", "Result"],
                ["Voice runtime", "src/ultron27/voice.py", "VoiceSession, transcript records, provider protocols, confirmation phrase handling, browser TTS delegation, and mock TTS."],
                ["Local API", "src/ultron27/web_server.py", "Added voice start, stop, transcribe, speak, and status endpoints."],
                ["Web interface", "web/index.html, web/styles.css, web/app.js", "Added voice controls, transcript history, browser speech recognition, browser speech synthesis, mute, and stop voice."],
                ["Launcher", "scripts/run_phase8_voice_ui.py", "Adds a Phase 8-named launcher for the same local interface server."],
                ["Smoke check", "scripts/phase8_voice_smoke.mjs", "Adds browser smoke coverage when Playwright's browser binary is available."],
                ["Docs", "README.md, docs/architecture.md, docs/phase8_voice_mode.md", "Documents voice flow, endpoints, safety boundary, and run instructions."],
                ["Tests", "tests/test_pipeline.py", "Expanded to 42 tests including mocked STT/TTS and high-risk voice confirmation."],
            ],
            [1.35 * inch, 2.35 * inch, 2.8 * inch],
            styles,
            header=True,
        ),
        Paragraph("Voice Pipeline", styles["H1"]),
        table(
            [
                ["Stage", "Purpose", "Safety Property"],
                ["Capture", "Browser speech recognition or mock voice provides text.", "Capture does not execute actions; empty speech is ignored."],
                ["Transcription API", "POST /api/voice/transcribe accepts transcript payloads.", "Wake word is stripped and empty speech is rejected."],
                ["Brain/runtime", "Transcript is processed as a normal goal.", "Planner, validation, policy, executor, and audit remain authoritative."],
                ["Confirmation", "High-risk tasks pause for yes confirm or clicked confirmation.", "Destructive actions remain dry-run or not implemented."],
                ["Speech output", "Response text is sent to /api/speak and browser speech synthesis.", "Mute and stop-speaking controls remain available."],
            ],
            [1.25 * inch, 2.65 * inch, 2.6 * inch],
            styles,
            header=True,
        ),
        Paragraph("User Controls", styles["H1"]),
        table(
            [
                ["Control", "Behavior", "Fallback"],
                ["Mic On/Off", "Starts or stops browser speech recognition.", "Typed command input remains available."],
                ["Push-to-talk", "Switches between one-shot and continuous recognition behavior.", "Mock Voice can exercise the pipeline without a microphone."],
                ["Mute", "Prevents audible ULTRON responses.", "Subtitles still show the response."],
                ["Stop Voice", "Cancels browser speech synthesis and marks speaking stopped.", "The UI can return to listening or idle."],
                ["Confirm", "Sends yes confirm for pending high-risk tasks.", "Policy still controls whether execution is allowed."],
            ],
            [1.2 * inch, 2.85 * inch, 2.45 * inch],
            styles,
            header=True,
        ),
        Paragraph("Verification Results", styles["H1"]),
        table(
            [
                ["Check", "Command", "Result"],
                ["Unit tests", "$env:PYTHONPATH='src'; python -m unittest discover -s tests", "42 tests passed."],
                ["Compile check", "python -m py_compile src/ultron27/voice.py src/ultron27/web_server.py scripts/run_phase8_voice_ui.py", "Voice module, server, and launcher compiled successfully."],
                ["HTTP smoke", "local ThreadingHTTPServer endpoint check", "Voice controls served; start, transcribe, speak, and history endpoints worked."],
                ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Intent 1.0, tool 1.0, argument exact match 0.9614, confirmation 1.0."],
                ["Safety regression", "python scripts/evaluate_safety_regression.py", "362 cases, tool accuracy 1.0, policy action accuracy 1.0."],
                ["Browser smoke", "node scripts/phase8_voice_smoke.mjs", "Clean fallback when the Playwright browser binary is unavailable in the sandbox."],
            ],
            [1.3 * inch, 2.65 * inch, 2.55 * inch],
            styles,
            header=True,
        ),
        Paragraph("Recommended Next Step", styles["H1"]),
        bullets(
            [
                "Plug a local STT provider such as faster-whisper or whisper.cpp into the VoiceSession provider interface.",
                "Add a local TTS provider such as Piper or pyttsx3 for fully offline voice identity.",
                "Add wake-word and stronger VAD once the microphone path is stable across target machines.",
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
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 8 Report | Page {doc.page}")
    canvas.restoreState()


def preview() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [
        ["ULTRON 2.7 Phase 8 Execution Report", "Executive Summary", "Phase 8 Scope", "What Was Implemented"],
        ["Voice Pipeline", "User Controls", "Verification Results", "Recommended Next Step"],
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
                d.text((175, y), "Rendered in the PDF with Phase 8 voice-mode implementation details.", fill=(45, 45, 45), font=f)
                y += 70
        d.text((860, 1560), f"Preview page {i}", fill=(100, 100, 100), font=f)
        img.save(PREVIEW_DIR / f"page-{i}.png")


if __name__ == "__main__":
    main()
