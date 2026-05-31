"""Read a CSV with automatic detection, then inspect the read report.

Run from anywhere:  python examples/basic_usage.py
"""

from pathlib import Path

import csvtriage as ct

DATA = Path(__file__).parent.parent / "test_data" / "messy_data.csv"


def main() -> None:
    frame = ct.read(DATA)

    print(f"Loaded {frame.shape[0]} rows x {frame.shape[1]} columns")
    print(f"Columns: {frame.columns}")
    print()

    # The report tells you exactly how the file was read.
    print(frame.report.explain())
    print()

    # Clean common messiness; the original frame is left untouched.
    cleaned = frame.clean()
    print(f"After cleaning: {cleaned.shape[0]} rows")
    for repair in cleaned.report.repairs:
        print(f"  - {repair}")


if __name__ == "__main__":
    main()
