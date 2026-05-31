"""Preview and stream a file without loading it all into memory.

Run from anywhere:  python examples/streaming_example.py
"""

import tempfile
from pathlib import Path

import csvtriage as ct


def make_large_csv(path: Path, rows: int) -> None:
    lines = ["id,value"]
    lines.extend(f"{i},{i * 3}" for i in range(rows))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "large.csv"
        make_large_csv(path, 250_000)

        # Summarize without loading.
        summary = ct.info(path)
        print(f"Size: {summary['size_mb']} MB, ~{summary['estimated_rows']:,} rows")
        print(f"Encoding: {summary['encoding']}, delimiter: {summary['delimiter']!r}")

        # Preview the first handful of rows.
        preview = ct.peek(path, rows=5)
        print("\nPreview:")
        print(preview)

        # Stream in chunks; each chunk is a full Frame.
        total = 0
        chunks = 0
        for chunk in ct.stream(path, chunk_size=50_000):
            total += chunk.shape[0]
            chunks += 1
        print(f"\nStreamed {total:,} rows across {chunks} chunks")


if __name__ == "__main__":
    main()
