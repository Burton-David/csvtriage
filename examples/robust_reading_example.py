"""Recover data from a contaminated file and review what was quarantined.

Run from anywhere:  python examples/robust_reading_example.py
"""

import tempfile
from pathlib import Path

import csvtriage as ct

MESSY = """name,age,city
Alice,30,New York
<html><body>503 Service Unavailable</body></html>
Bob,25,Los Angeles
Carlos,,Madrid
<script>tracker()</script>
Diana,41,Toronto
"""


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "scraped.csv"
        path.write_text(MESSY, encoding="utf-8")

        frame = ct.read(path, robust=True)

        print(f"Recovered {frame.shape[0]} clean rows:")
        print(frame)
        print()

        report = frame.report
        print(f"Quarantined {report.rows_quarantined} row(s):")
        for row in report.quarantined:
            print(f"  line {row.line_number}: {row.reason}")
        print()
        print("Repairs applied:")
        for repair in report.repairs:
            print(f"  - {repair}")


if __name__ == "__main__":
    main()
