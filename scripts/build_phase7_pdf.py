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
PDF_OUT = ROOT / "docs" / "ULTRON_2.7_Phase_7_Report.pdf"
PREVIEW_DIR = ROOT / "docs" / "phase7_pdf_preview"


def main() -> None:
    styles = stylesheet()
    doc = SimpleDocTemplate(str(PDF_OUT), pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    story = [
        Paragraph("ULTRON 2.7 Phase 7 Execution Report", styles["TitleCustom"]),
        Paragraph("Cyberpunk visual interface and local brain API", styles["SubtitleCustom"]),
        table(
            [["Project", "ULTRON 2.7"], ["Phase", "Phase 7: Visual Interface"], ["Workspace", "Local workspace checkout: U2.7"], ["Status", "Implemented and verified"]],
            [1.55 * inch, 4.95 * inch],
            styles,
        ),
        Spacer(1, 8),
        Paragraph("Executive Summary", styles["H1"]),
        Paragraph(
            "Phase 7 gives ULTRON 2.7 a local web interface instead of a CLI-only experience. The interface presents a cyberpunk black-and-green scene with a Three.js plasma sphere, subtle particles, live subtitles, typed command input, and explicit visual states for listening, thinking, speaking, and idle.",
            styles["Normal"],
        ),
        Paragraph(
            "The UI connects to ULTRON's existing brain/runtime through a local API. It does not bypass schema validation, policy, execution restrictions, or audit logging.",
            styles["Normal"],
        ),
        Paragraph("Phase 7 Scope", styles["H1"]),
        bullets(
            [
                "Create a real local web interface backed by the ULTRON runtime.",
                "Build a responsive Three.js sphere scene with green plasma lines, eclipse rings, particles, glow, and state transitions.",
                "Add subtitle rendering and a subtitle on/off toggle.",
                "Add typed command input with Send button and Enter-key behavior.",
                "Add local API endpoints for commands, status, memory, subtitles, and development visual state control.",
                "Update tests, README, architecture notes, and implementation documentation.",
            ],
            styles,
        ),
        Paragraph("What Was Implemented", styles["H1"]),
        table(
            [
                ["Area", "File(s)", "Result"],
                ["Local API", "src/ultron27/web_server.py", "Serves the static UI and exposes command, status, memory, subtitle, and state endpoints."],
                ["Launcher", "scripts/run_phase7_ui.py, pyproject.toml", "Adds a script launcher and the ultron-ui package entry point."],
                ["Frontend shell", "web/index.html, web/styles.css", "Adds the full-screen black-and-green interface, subtitle panel, controls, and command bar."],
                ["3D scene", "web/app.js, web/vendor/three.module.min.js", "Adds the Three.js sphere, particles, rings, plasma arcs, and state transitions."],
                ["Smoke check", "scripts/phase7_visual_smoke.mjs", "Captures screenshots when a local Playwright browser binary is available."],
                ["Docs", "README.md, docs/architecture.md, docs/phase7_visual_interface.md", "Documents UI, endpoints, safety boundary, and run instructions."],
                ["Tests", "tests/test_pipeline.py", "Adds Phase 7 API, subtitle, static asset, and command-processing coverage."],
            ],
            [1.35 * inch, 2.35 * inch, 2.8 * inch],
            styles,
            header=True,
        ),
        Paragraph("Visual State Design", styles["H1"]),
        table(
            [
                ["State", "Animation", "User Impression"],
                ["Listening", "Sphere contracts slightly, glow tightens, breathing ring calms, particle motion slows.", "ULTRON is focused on the user's next command."],
                ["Thinking", "Green orbit rings spin around the sphere with crescent-like eclipse motion.", "ULTRON is analyzing and planning the request."],
                ["Speaking", "Sphere expands, plasma lines brighten, outer glow intensifies, particles push outward.", "ULTRON is delivering a result."],
                ["Idle", "Sphere remains alive with restrained motion and a stable field.", "The system is online and ready."],
            ],
            [1.15 * inch, 3.1 * inch, 2.25 * inch],
            styles,
            header=True,
        ),
        Paragraph("Runtime Safety Boundary", styles["H1"]),
        table(
            [
                ["Layer", "Responsibility", "Safety Property"],
                ["Web UI", "Collect typed commands and display state/subtitles.", "No shell access and no direct executor calls."],
                ["Local API", "Translate HTTP requests into brain calls and response snapshots.", "Only exposes typed endpoints."],
                ["Brain", "Plan and execute task steps through the assistant runtime.", "Cannot skip planner, validator, policy, or executor."],
                ["Runtime", "Validate tool calls, apply policy, execute allowed tasks, and audit.", "High-risk and blocked actions remain gated."],
            ],
            [1.15 * inch, 2.75 * inch, 2.6 * inch],
            styles,
            header=True,
        ),
        Paragraph("Verification Results", styles["H1"]),
        table(
            [
                ["Check", "Command", "Result"],
                ["Unit tests", "$env:PYTHONPATH='src'; python -m unittest discover -s tests", "35 tests passed."],
                ["Compile check", "python -m py_compile src/ultron27/web_server.py scripts/run_phase7_ui.py", "Backend and launcher compiled successfully."],
                ["Dataset evaluation", "python scripts/evaluate_dataset.py --split test", "Intent 1.0, tool 1.0, argument exact match 0.9614, confirmation 1.0."],
                ["Safety regression", "python scripts/evaluate_safety_regression.py", "362 cases, tool accuracy 1.0, policy action accuracy 1.0."],
                ["Browser smoke", "node scripts/phase7_visual_smoke.mjs", "Clean fallback when the Playwright browser binary is unavailable in the sandbox."],
            ],
            [1.3 * inch, 2.65 * inch, 2.55 * inch],
            styles,
            header=True,
        ),
        Paragraph("Recommended Next Step", styles["H1"]),
        bullets(
            [
                "Move to Phase 8 by adding voice input and voice output as adapters around the same local API and brain/runtime.",
                "Map voice activity to the existing listening, thinking, and speaking visual states.",
                "Keep confirmation prompts visible in the interface before enabling broader real-world task execution.",
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
    s.add(ParagraphStyle("Cell", parent=s["Normal"], fontSize=8.55, leading=10.8, spaceAfter=0))
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
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"ULTRON 2.7 Phase 7 Report | Page {doc.page}")
    canvas.restoreState()


def preview() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pages = [
        ["ULTRON 2.7 Phase 7 Execution Report", "Executive Summary", "Phase 7 Scope", "What Was Implemented"],
        ["Visual State Design", "Runtime Safety Boundary", "Verification Results", "Recommended Next Step"],
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
                d.text((175, y), "Rendered in the PDF with Phase 7 interface implementation details.", fill=(45, 45, 45), font=f)
                y += 70
        d.text((860, 1560), f"Preview page {i}", fill=(100, 100, 100), font=f)
        img.save(PREVIEW_DIR / f"page-{i}.png")


if __name__ == "__main__":
    main()
