"""Preview, inspect, and stream large files through the same engine as ``read``.

``peek`` and ``stream`` decode the file to UTF-8 once (using the detected encoding)
and parse with Polars, so a previewed or streamed chunk types identically to a
full ``read`` of the same file. ``info`` summarizes a file without loading it.
"""

import io
import logging
import os
import tempfile
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import polars as pl

from . import detect
from .frame import Frame
from .report import ReadReport

logger = logging.getLogger(__name__)

_DETECT_SAMPLE_BYTES = 256 * 1024
_UTF8_ENCODINGS = ("utf-8", "utf-8-sig", "ascii")
_PEEK_INITIAL_BYTES = 128 * 1024
_PEEK_MAX_BYTES = 64 * 1024 * 1024


@contextmanager
def _utf8_source(path: Path, encoding: str, compression: str | None) -> Iterator[str]:
    """Yield a path to UTF-8 CSV text, decoding to a temp file only when needed."""
    if compression is None and encoding.lower() in _UTF8_ENCODINGS:
        yield str(path)
        return

    text = detect.read_bytes(path).decode(encoding, errors="replace")
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    try:
        handle.write(text)
        handle.close()
        yield handle.name
    finally:
        os.unlink(handle.name)


def _detect_dialect(
    path: Path, encoding: str | None
) -> tuple[str, float, str, str, bool]:
    sample = detect.read_bytes(path, _DETECT_SAMPLE_BYTES)
    if encoding is None:
        encoding, confidence = detect.detect_encoding(sample)
    else:
        confidence = 1.0
    text = sample.decode(encoding, errors="replace")
    delimiter, _ = detect.detect_delimiter(text)
    quote_char = detect.detect_quote_char(text, delimiter)
    has_header = detect.detect_header(text, delimiter, quote_char)
    return encoding, confidence, delimiter, quote_char, has_header


def peek(
    file_path: str | Path,
    rows: int = 100,
    *,
    encoding: str | None = None,
) -> Frame:
    """Read the first ``rows`` data rows without loading the whole file.

    Works on compressed and non-UTF-8 files: the sample is decoded in Python and
    parsed by Polars, so messy encodings preview correctly.

    Args:
        file_path: Path to the CSV file.
        rows: Maximum number of data rows to return.
        encoding: Force an encoding; auto-detected when ``None``.

    Returns:
        A :class:`~csvtriage.frame.Frame` of up to ``rows`` rows.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    report = ReadReport()
    report.compression = detect.detect_compression(path)
    encoding, confidence, delimiter, quote_char, has_header = _detect_dialect(
        path, encoding
    )
    report.encoding = encoding
    report.encoding_confidence = confidence
    report.delimiter = delimiter
    report.quote_char = quote_char
    report.has_header = has_header

    table = _read_prefix(
        path,
        encoding=encoding,
        delimiter=delimiter,
        quote_char=quote_char,
        has_header=has_header,
        rows=rows,
    )
    report.rows_read = table.height
    report.columns = table.width
    return Frame(table, report)


def _read_prefix(
    path: Path,
    *,
    encoding: str,
    delimiter: str,
    quote_char: str,
    has_header: bool,
    rows: int,
) -> pl.DataFrame:
    """Parse the first ``rows`` rows from a bounded prefix of the file.

    Reads a growing byte window rather than the whole file, so previewing a
    multi-gigabyte file stays cheap. A partial trailing line is dropped unless the
    window has already reached end-of-file.
    """
    limit = _PEEK_INITIAL_BYTES
    while True:
        raw = detect.read_bytes(path, limit)
        at_eof = len(raw) < limit
        text = raw.decode(encoding, errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not at_eof:
            cut = text.rfind("\n")
            if cut != -1:
                text = text[: cut + 1]
        table = pl.read_csv(
            io.BytesIO(text.encode("utf-8")),
            separator=delimiter,
            quote_char=quote_char,
            has_header=has_header,
            n_rows=rows,
            truncate_ragged_lines=True,
            infer_schema_length=min(rows, 10000),
        )
        if at_eof or table.height >= rows or limit >= _PEEK_MAX_BYTES:
            return table
        limit *= 4


def info(file_path: str | Path) -> dict[str, Any]:
    """Summarize a CSV file without loading it into memory.

    Args:
        file_path: Path to the CSV file.

    Returns:
        A dict with ``size_bytes``, ``size_mb``, ``compression``, ``encoding``,
        ``encoding_confidence``, ``delimiter``, ``quote_char``, ``has_header``,
        ``columns``, and ``estimated_rows``.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    size_bytes = path.stat().st_size
    compression = detect.detect_compression(path)
    encoding, confidence, delimiter, quote_char, has_header = _detect_dialect(
        path, None
    )

    sample = detect.read_bytes(path, _DETECT_SAMPLE_BYTES)
    text = sample.decode(encoding, errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    columns = len(lines[0].split(delimiter)) if lines else 0
    estimated_rows = _estimate_rows(path, sample, compression, size_bytes, has_header)

    return {
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 3),
        "compression": compression,
        "encoding": encoding,
        "encoding_confidence": confidence,
        "delimiter": delimiter,
        "quote_char": quote_char,
        "has_header": has_header,
        "columns": columns,
        "estimated_rows": estimated_rows,
    }


def _estimate_rows(
    path: Path,
    sample: bytes,
    compression: str | None,
    size_bytes: int,
    has_header: bool,
) -> int:
    sample_lines = sample.count(b"\n")
    if sample_lines == 0:
        return 0
    if compression is None and len(sample) < size_bytes:
        avg_line_bytes = len(sample) / sample_lines
        estimate = int(size_bytes / avg_line_bytes)
    elif compression is None:
        estimate = sample_lines
    else:
        full = detect.read_bytes(path)
        estimate = full.count(b"\n")
    return max(estimate - (1 if has_header else 0), 0)


def stream(
    file_path: str | Path,
    *,
    chunk_size: int = 50000,
    encoding: str | None = None,
) -> Iterator[Frame]:
    """Yield the file in row-count chunks, parsed with the same engine as ``read``.

    Args:
        file_path: Path to the CSV file.
        chunk_size: Approximate number of rows per yielded chunk.
        encoding: Force an encoding; auto-detected when ``None``.

    Yields:
        :class:`~csvtriage.frame.Frame` chunks, each carrying its own report.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    encoding, confidence, delimiter, quote_char, has_header = _detect_dialect(
        path, encoding
    )
    compression = detect.detect_compression(path)

    with _utf8_source(path, encoding, compression) as csv_path:
        # read_csv_batched is the batched reader available across supported Polars
        # versions; its deprecation replacement (collect_batches) is not yet present
        # in the floor we target, so suppress the forward-looking warning here.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            reader = pl.read_csv_batched(
                csv_path,
                separator=delimiter,
                quote_char=quote_char,
                has_header=has_header,
                batch_size=chunk_size,
                truncate_ragged_lines=True,
                infer_schema_length=10000,
            )
        while True:
            batches = reader.next_batches(1)
            if not batches:
                break
            for batch in batches:
                report = ReadReport()
                report.encoding = encoding
                report.encoding_confidence = confidence
                report.delimiter = delimiter
                report.quote_char = quote_char
                report.has_header = has_header
                report.compression = compression
                report.rows_read = batch.height
                report.columns = batch.width
                yield Frame(batch, report)
