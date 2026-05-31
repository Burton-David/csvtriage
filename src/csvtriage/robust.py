"""Line-level recovery for files a strict parse rejects.

The recovery reader decodes each physical line independently — falling back
through a list of encodings and repairing mojibake — drops obvious non-data
contamination (HTML/error pages), normalizes every row to the header's width, and
hands the cleaned, uniform text to Polars for typing. Anything it cannot place is
quarantined in the :class:`~csvtriage.report.ReadReport`, never dropped silently.
"""

import csv
import io
import logging
import re
from collections import Counter
from pathlib import Path

import ftfy
import polars as pl

from . import detect
from .errors import ParseError
from .frame import Frame
from .report import ReadReport

logger = logging.getLogger(__name__)

_DECODE_ENCODINGS: tuple[str, ...] = ("utf-8", "cp1252", "latin-1")
_OVERFLOW_COLUMN = "_overflow"

_HTML_LINE = re.compile(
    r"""^\s*(
        <!doctype | <\?xml | </?(html|head|body|script|style|table|div|span|p|tr|td)\b
        | <!--
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def is_contamination(line: str) -> bool:
    """Return True if a line looks like HTML/markup rather than CSV data."""
    stripped = line.strip()
    if not stripped:
        return False
    if _HTML_LINE.match(stripped):
        return True
    # Several tags on one line is markup, not a stray ``<`` inside a cell.
    return len(re.findall(r"<[^>]+>", stripped)) > 2


def recover(
    file_path: Path,
    *,
    encoding: str | None,
    delimiter: str,
    has_header: bool,
    on_bad_lines: str,
    report: ReadReport,
) -> Frame:
    """Recover a table from a messy file, quarantining unparseable rows.

    Args:
        file_path: Path to the CSV file.
        encoding: Preferred encoding to try first; recovery still falls back
            through a standard list per line.
        delimiter: Field delimiter to parse with.
        has_header: Whether the first surviving row is the header.
        on_bad_lines: Unused distinction here (every bad row is quarantined), kept
            for signature parity with :func:`csvtriage.reader.read`.
        report: The report to annotate; returned on ``frame.report``.

    Returns:
        A :class:`~csvtriage.frame.Frame` of recovered rows.

    Raises:
        ParseError: If no data rows survive recovery.
    """
    raw = detect.read_bytes(file_path)
    # Normalize CRLF and lone-CR ("old Mac") endings before splitting so every
    # physical line is isolated. Otherwise a CR-only file is one giant "line" and
    # csv.reader raises on the embedded carriage returns.
    raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    physical_lines = raw.split(b"\n")

    decoded: list[tuple[int, str]] = []
    preferred = [encoding] if encoding else []
    encodings = preferred + [e for e in _DECODE_ENCODINGS if e != encoding]
    mojibake_fixes = 0

    for index, line_bytes in enumerate(physical_lines, start=1):
        if not line_bytes:
            continue

        text, used = _decode_line(line_bytes, encodings)
        if text is None:
            report.quarantine(index, repr(line_bytes), "undecodable bytes")
            continue
        if used not in ("utf-8", encoding):
            report.add_repair(f"line {index}: decoded with {used} fallback")

        repaired = ftfy.fix_text(text)
        if repaired != text:
            mojibake_fixes += 1
        text = repaired

        if is_contamination(text):
            report.quarantine(index, text, "HTML/markup contamination")
            continue

        decoded.append((index, text))

    if mojibake_fixes:
        report.add_repair(f"repaired mojibake on {mojibake_fixes} line(s)")

    if not decoded:
        raise ParseError(file_path, error_detail="no data rows survived recovery")

    header, rows, width = _structure_rows(decoded, delimiter, has_header, report)
    if not rows:
        raise ParseError(file_path, error_detail="no data rows survived recovery")

    clean_text = _reserialize(header, rows)
    table = pl.read_csv(
        io.BytesIO(clean_text.encode("utf-8")),
        separator=",",
        has_header=True,
        truncate_ragged_lines=True,
        infer_schema_length=10000,
    )

    report.rows_read = table.height
    report.columns = table.width
    if width > len(header) - (1 if _OVERFLOW_COLUMN in header else 0):
        report.add_repair("captured extra fields in '_overflow' column")
    return Frame(table, report)


def _decode_line(
    line_bytes: bytes, encodings: list[str]
) -> tuple[str | None, str | None]:
    for enc in encodings:
        if not enc:
            continue
        try:
            return line_bytes.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    try:
        return line_bytes.decode("utf-8", errors="replace"), "utf-8-replace"
    except UnicodeDecodeError:
        return None, None


def _structure_rows(
    decoded: list[tuple[int, str]],
    delimiter: str,
    has_header: bool,
    report: ReadReport,
) -> tuple[list[str], list[list[str]], int]:
    parsed: list[tuple[int, list[str]]] = []
    for line_no, text in decoded:
        fields = next(csv.reader([text], delimiter=delimiter), None)
        if fields is None:
            report.quarantine(line_no, text, "unparseable row")
            continue
        parsed.append((line_no, fields))

    if not parsed:
        return [], [], 0

    widths = Counter(len(fields) for _, fields in parsed)
    base_width = widths.most_common(1)[0][0]

    if has_header:
        header = parsed[0][1]
        base_width = max(base_width, len(header))
        data = parsed[1:]
    else:
        header = [f"column_{i + 1}" for i in range(base_width)]
        data = parsed

    has_overflow = any(len(fields) > base_width for _, fields in data)
    if has_overflow:
        header = header + [_OVERFLOW_COLUMN]

    rows: list[list[str]] = []
    for line_no, fields in data:
        if len(fields) < base_width:
            report.add_repair(f"line {line_no}: padded short row")
            fields = fields + [""] * (base_width - len(fields))
        if len(fields) > base_width:
            overflow = delimiter.join(fields[base_width:])
            fields = fields[:base_width] + [overflow]
        elif has_overflow:
            fields = fields + [""]
        rows.append(fields)

    return header, rows, max(widths) if widths else base_width


def _reserialize(header: list[str], rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()
