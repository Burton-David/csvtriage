"""The single front door: ``read``.

Every read goes through one engine. Bytes are decompressed, decoded to UTF-8 in
Python using the detected (or supplied) encoding, then parsed by Polars. When the
strict parse fails — or ``robust=True`` is requested — control passes to the
line-level recovery path in :mod:`csvtriage.robust`, which still parses fields
through Polars and quarantines whatever it cannot place.
"""

import io
import logging
from pathlib import Path

import polars as pl

from . import detect
from .errors import ParseError, PathLike
from .frame import Frame
from .report import ReadReport

logger = logging.getLogger(__name__)

_DETECT_SAMPLE_BYTES = 256 * 1024


def read(
    file_path: str | Path,
    *,
    encoding: str | None = None,
    delimiter: str | None = None,
    has_header: bool | None = None,
    columns_as_string: list[str] | None = None,
    on_bad_lines: str = "error",
    robust: bool = False,
) -> Frame:
    """Read a CSV file, auto-detecting encoding, delimiter, quoting, and header.

    Args:
        file_path: Path to the CSV file (optionally compressed: .gz/.zip/.bz2/.xz).
        encoding: Force a character encoding; auto-detected when ``None``.
        delimiter: Force a field delimiter; auto-detected when ``None``.
        has_header: Force header presence; auto-detected when ``None``.
        columns_as_string: Column names to read as strings rather than inferring.
        on_bad_lines: Behavior when the strict parse hits malformed rows. Both
            modes first attempt line-level recovery, so ragged rows are repaired
            and recorded rather than silently truncated. ``"error"`` then raises a
            :class:`ParseError` if any row still could not be recovered (was
            quarantined); ``"skip"`` returns the recovered table and records each
            quarantined row in the report.
        robust: Force the line-level recovery path even if the strict parse would
            succeed. Slower, but handles mixed encodings and ragged structure.

    Returns:
        A :class:`~csvtriage.frame.Frame` wrapping the parsed table, with a
        :class:`~csvtriage.report.ReadReport` describing what was detected and
        repaired (``frame.report``).

    Raises:
        FileNotFoundError: If ``file_path`` does not exist.
        ParseError: If the file cannot be parsed even after recovery.
        EncodingError: If no encoding can decode the file.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if on_bad_lines not in ("error", "skip"):
        raise ValueError("on_bad_lines must be 'error' or 'skip'")

    report = ReadReport()
    report.compression = detect.detect_compression(path)

    sample_bytes = detect.read_bytes(path, _DETECT_SAMPLE_BYTES)
    if encoding is None:
        encoding, confidence = detect.detect_encoding(sample_bytes)
        report.encoding_confidence = confidence
    else:
        report.encoding_confidence = 1.0
    report.encoding = encoding

    sample_text = _decode_sample(sample_bytes, encoding, path)

    if delimiter is None:
        delimiter, _ = detect.detect_delimiter(sample_text)
    quote_char = detect.detect_quote_char(sample_text, delimiter)
    if has_header is None:
        has_header = detect.detect_header(sample_text, delimiter, quote_char)

    report.delimiter = delimiter
    report.quote_char = quote_char
    report.has_header = has_header

    if robust:
        from .robust import recover

        return recover(
            path,
            encoding=encoding,
            delimiter=delimiter,
            has_header=has_header,
            on_bad_lines=on_bad_lines,
            report=report,
        )

    try:
        return _strict_read(
            path,
            encoding=encoding,
            delimiter=delimiter,
            quote_char=quote_char,
            has_header=has_header,
            columns_as_string=columns_as_string,
            report=report,
        )
    except (pl.exceptions.PolarsError, UnicodeDecodeError) as exc:
        logger.info("Strict parse failed (%s); recovering line-by-line", exc)
        from .robust import recover

        reason = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        report.add_repair(f"strict parse failed, recovered line-by-line: {reason}")
        frame = recover(
            path,
            encoding=encoding,
            delimiter=delimiter,
            has_header=has_header,
            on_bad_lines="skip",
            report=report,
        )
        if on_bad_lines == "error" and frame.report.quarantined:
            raise ParseError(
                path,
                error_detail=(
                    f"{len(frame.report.quarantined)} row(s) could not be "
                    f"recovered. Pass on_bad_lines='skip' to load the rest and "
                    f"inspect report.quarantined"
                ),
            ) from exc
        return frame


def _decode_sample(data: bytes, encoding: str, path: PathLike) -> str:
    from .errors import EncodingError

    try:
        decoded: str = data.decode(encoding, errors="replace")
    except LookupError as exc:
        raise EncodingError(path, encoding) from exc
    return decoded


def _strict_read(
    path: Path,
    *,
    encoding: str,
    delimiter: str,
    quote_char: str,
    has_header: bool,
    columns_as_string: list[str] | None,
    report: ReadReport,
) -> Frame:
    raw = detect.read_bytes(path)
    # Strict decode (no errors="replace"): a byte the detected encoding cannot
    # handle raises UnicodeDecodeError here, and read() recovers line-by-line with
    # per-line encoding fallback rather than silently substituting U+FFFD.
    text = _normalize_newlines(raw.decode(encoding))
    if encoding not in ("utf-8", "utf-8-sig", "ascii"):
        report.add_repair(f"re-encoded from {encoding} to utf-8")

    schema_overrides = (
        dict.fromkeys(columns_as_string, pl.String) if columns_as_string else None
    )
    # truncate_ragged_lines stays False so an over-long row raises instead of being
    # silently trimmed; read() then routes it to recovery, which records the repair
    # and captures the extra fields rather than dropping them.
    table = pl.read_csv(
        io.BytesIO(text.encode("utf-8")),
        separator=delimiter,
        quote_char=quote_char,
        has_header=has_header,
        schema_overrides=schema_overrides,
        truncate_ragged_lines=False,
        infer_schema_length=10000,
    )

    if not has_header:
        report.add_repair("no header detected; generated column names")

    report.rows_read = table.height
    report.columns = table.width
    return Frame(table, report)


def _normalize_newlines(text: str) -> str:
    r"""Normalize CRLF and lone-CR ("old Mac") line endings to ``\n``."""
    return text.replace("\r\n", "\n").replace("\r", "\n")
