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
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_9_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase9_pdf_preview"


def main() -> None:
    styles = stylesheet()
    doc = SimpleDocTemplate(str(PDF_OUT), pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    story = [
        Paragraph("ULTRON 2.7 Phase 9 Execution Report", styles["TitleCustom"]),
        Paragraph("Offline-first voice provider stack", styles["SubtitleCustom"]),
        table(
            [["Project", "ULTRON 2.7"], ["Phase", "Phase 9: Offline Voice Stack"], ["Workspace", "Local workspace checkout: U2.7"], ["Status", "Implemented and verified"]],
            [1.55 * inch, 4.95 * inch],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph(
            "Phase 9 upgrades ULTRON 2.7 from browser-only voice behavior to an offline-first provider stack. The system can now select local STT/TTS adapters, report provider health, fall back gracefully, and keep typed/browser operation available when local models are not installed.",
            styles["Normal"],
        ),
        Paragraph(
            "Voice still flows through STT, the brain/runtime, typed tool calls, schema validation, policy gates, the executor, audit logging, response text, and TTS. No voice provider receives raw shell authority or executor authority.",
            styles["Normal"],
        ),
        Paragraph("Phase 9 Scope", styles["H1"]),
        bullets(
            [
                "Add local STT provider adapters for faster-whisper and whisper.cpp.",
                "Add local TTS provider adapters for Piper and pyttsx3.",
                "Keep browser transcript and browser speech synthesis as fallbacks.",
                "Add voice provider config fields, environment overrides, and provider health checks.",
                "Expose provider status and provider test API endpoints.",
                "Update the web UI to display active STT/TTS providers and run provider tests.",
                "Add mocked provider-selection and health endpoint tests.",
            ],
            styles,
        ),
        Paragraph("What Was Implemented", styles["H1"]),
        table(
            [
                ["Area", "File(s)", "Result"],
                ["Configuration", "src/ultron27/config.py, ultron.config.example.json", "Added provider, model path, device, identity, rate, pitch, and volume settings."],
                ["Voice runtime", "src/ultron27/voice.py", "Added provider config, health model, local provider adapters, browser fallback, and mocks."],
                ["Local API", "src/ultron27/web_server.py", "Added provider health and test routes while preserving command and voice routes."],
                ["Web interface", "web/index.html, web/styles.css, web/app.js", "Added active provider display, refresh/test controls, and backend-aware browser speech fallback."],
                ["Launcher", "scripts/run_phase9_voice_ui.py", "Adds a Phase 9-named launcher for the local interface."],
                ["Docs", "README.md, docs/architecture.md, docs/phase9_offline_voice_stack.md", "Documents config, provider matrix, health checks, and fallback behavior."],
                ["Tests", "tests/test_pipeline.py", "Expanded to 47 tests covering provider selection, fallback, mocks, and API endpoints."],
            ],
            [1.35 * inch, 2.35 * inch, 2.8 * inch],
            styles,
            header=True,
        ),
        Paragraph("Provider Matrix", styles["H1"]),
        table(
            [
                ["Provider", "Type", "Behavior"],
                ["browser", "STT", "Browser recognition sends transcript text to the backend."],
                ["text_payload", "STT", "Accepts transcript/text JSON payloads."],
                ["faster_whisper", "STT", "Checks for package and model path before activation."],
                ["whisper_cpp", "STT", "Checks for executable and model path before activation."],
                ["browser_speech_synthesis", "TTS", "Delegates audio playback to the browser."],
                ["piper", "TTS", "Checks for Piper and local voice model before activation."],
                ["pyttsx3", "TTS", "Uses the local pyttsx3 package when available."],
                ["mock", "STT/TTS", "Deterministic tests and demos."],
            ],
            [1.65 * inch, 1.0 * inch, 3.85 * inch],
            styles,
            header=True,
        ),
        Paragraph("Safety Boundary", styles["H1"]),
        table(
            [
                ["Boundary", "Phase 9 Behavior", "Safety Property"],
                ["STT", "Transcribes or accepts text payloads.", "Output is treated as a user goal, not executable authority."],
                ["Brain/runtime", "Routes every goal through the existing system.", "Validation, policy, executor, and audit remain authoritative."],
                ["High-risk commands", "Pause for explicit confirmation.", "Destructive actions remain dry-run or not implemented."],
                ["TTS", "Speaks or delegates response text.", "Speech output cannot trigger tools."],
                ["Fallbacks", "Missing providers downgrade to browser/typed behavior.", "Unavailable local models do not crash the app."],
            ],
            [1.35 * inch, 2.6 * inch, 2.55 * inch],
            styles,
            header=True,
        ),
        Paragraph("Verification Results", styles["H1"]),
        table(
            [
                ["Check", "Command", "Result"],
                ["Unit tests", "$env:PYTHONPATH='src'; python -m unittest discover -s tests", "47 tests passed."],
                ["Compile check", "python -m py_compile src/ultron27/config.py src/ultron27/voice.py src/ultron27/web_server.py scripts/run_phase9_voice_ui.py", "Phase 9 Python modules compiled successfully."],
                ["Frontend syntax", "bundled node --check web/app.js", "Frontend JavaScript parsed successfully."],
                ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Intent 1.0, tool 1.0, argument exact match 0.9614, confirmation 1.0."],
                ["Safety regression", "python scripts/evaluate_safety_regression.py", "362 cases, tool accuracy 1.0, policy action accuracy 1.0."],
                ["Provider API", "ThreadingHTTPServer endpoint tests", "Provider status, test-STT, and test-TTS routes returned expected payloads."],
            ],
            [1.3 * inch, 2.65 * inch, 2.55 * inch],
            styles,
            header=True,
        ),
        Paragraph("Recommended Next Step", styles["H1"]),
        bullets(
            [
                "Install a real faster-whisper or whisper.cpp model and verify microphone audio capture end to end.",
                "Install a Piper voice model or pyttsx3 on the target Windows machine and tune ULTRON's voice identity.",
                "Add stronger wake-word and VAD layers after the offline providers are stable.",
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
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 9 Report | Page {doc.page}")
    canvas.restoreState()


def preview() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [
        ["ULTRON 2.7 Phase 9 Execution Report", "Executive Summary", "Phase 9 Scope", "What Was Implemented"],
        ["Provider Matrix", "Safety Boundary", "Verification Results", "Recommended Next Step"],
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
                d.text((175, y), "Rendered in the PDF with Phase 9 offline voice-provider details.", fill=(45, 45, 45), font=f)
                y += 70
        d.text((860, 1560), f"Preview page {i}", fill=(100, 100, 100), font=f)
        img.save(PREVIEW_DIR / f"page-{i}.png")


if __name__ == "__main__":
    main()
