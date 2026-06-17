from __future__ import annotations

from phase_report_common import ROOT, build_pdf
from build_phase14_report import REPORT


if __name__ == "__main__":
    build_pdf(REPORT, ROOT / "docs" / "ULTRON_2.7_Phase_14_Report.pdf")
