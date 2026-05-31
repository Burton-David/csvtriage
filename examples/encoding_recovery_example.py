"""Read files in non-UTF-8 encodings without specifying the encoding by hand.

Run from the repo root:  python examples/encoding_recovery_example.py
"""

import tempfile
from pathlib import Path

import csvtriage as ct


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # A file saved as Latin-1 (common from European spreadsheet exports).
        latin1 = Path(tmp) / "european.csv"
        latin1.write_bytes("name,city\nJosé,São Paulo\nFrançois,Genève\n".encode("latin-1"))

        frame = ct.read(latin1)
        print(f"Detected encoding: {frame.report.encoding} "
              f"({frame.report.encoding_confidence:.0%} confidence)")
        print(frame)
        print()
        for repair in frame.report.repairs:
            print(f"  - {repair}")


if __name__ == "__main__":
    main()
