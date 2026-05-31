"""Detection of file properties: compression, encoding, delimiter, quoting, header.

These functions make the assumptions that the rest of the library acts on. They
never guess silently — every reader records what was detected (and the confidence)
in the :class:`~csvtriage.report.ReadReport`.
"""

import bz2
import csv
import gzip
import lzma
import zipfile
from collections import Counter
from pathlib import Path

import chardet

from .errors import PathLike

DELIMITER_CANDIDATES: tuple[str, ...] = (",", "\t", ";", "|", ":")
QUOTE_CANDIDATES: tuple[str, ...] = ('"', "'")

_BOMS: tuple[tuple[bytes, str], ...] = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)

_FALLBACK_ENCODINGS: tuple[str, ...] = ("utf-8", "cp1252", "latin-1")

# chardet labels normalized to the codec names Python's decoder expects. Only
# genuine aliases are mapped; distinct encodings (e.g. ISO-8859-2) are preserved
# rather than collapsed onto latin-1.
_ENCODING_ALIASES = {
    "ascii": "utf-8",
}


def detect_compression(filepath: PathLike) -> str | None:
    """Detect compression from the file's extension and magic bytes.

    Args:
        filepath: Path to the file.

    Returns:
        ``"gzip"``, ``"zip"``, ``"bz2"``, ``"xz"``, or ``None`` if uncompressed.
    """
    suffix = Path(filepath).suffix.lower()
    by_suffix = {".gz": "gzip", ".zip": "zip", ".bz2": "bz2", ".xz": "xz"}
    if suffix in by_suffix:
        return by_suffix[suffix]

    with open(filepath, "rb") as handle:
        magic = handle.read(6)
    if magic.startswith(b"\x1f\x8b"):
        return "gzip"
    if magic.startswith(b"PK\x03\x04"):
        return "zip"
    if magic.startswith(b"BZh"):
        return "bz2"
    if magic.startswith(b"\xfd7zXZ\x00"):
        return "xz"
    return None


def read_bytes(filepath: PathLike, limit: int | None = None) -> bytes:
    """Read decompressed bytes from a file, transparently handling compression.

    Args:
        filepath: Path to the file.
        limit: Maximum number of decompressed bytes to read; ``None`` reads all.

    Returns:
        The decompressed contents (or first ``limit`` bytes).
    """
    compression = detect_compression(filepath)
    amount = -1 if limit is None else limit

    if compression == "gzip":
        with gzip.open(filepath, "rb") as handle:
            return handle.read(amount)
    if compression == "bz2":
        with bz2.open(filepath, "rb") as handle:
            return handle.read(amount)
    if compression == "xz":
        with lzma.open(filepath, "rb") as handle:
            return handle.read(amount)
    if compression == "zip":
        with zipfile.ZipFile(filepath) as archive:
            members = [n for n in archive.namelist() if not n.endswith("/")]
            if not members:
                return b""
            with archive.open(members[0]) as handle:
                return handle.read(amount)
    with open(filepath, "rb") as handle:
        return handle.read(amount)


def detect_encoding(data: bytes) -> tuple[str, float]:
    """Detect the encoding of a byte sample.

    Order: byte-order mark, then chardet, then a decode-test fallback.

    Args:
        data: A sample of the file's raw (decompressed) bytes.

    Returns:
        A ``(encoding, confidence)`` pair where confidence is in ``[0.0, 1.0]``.
    """
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            return encoding, 1.0

    result = chardet.detect(data)
    detected = result.get("encoding")
    confidence = result.get("confidence") or 0.0

    if detected and confidence >= 0.7:
        return _normalize_encoding(detected), confidence

    for candidate in _FALLBACK_ENCODINGS:
        try:
            data.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
        return candidate, max(confidence, 0.5)

    if detected:
        return _normalize_encoding(detected), confidence
    return "utf-8", confidence


def _normalize_encoding(encoding: str) -> str:
    return _ENCODING_ALIASES.get(encoding.lower(), encoding.lower())


def _sample_lines(text: str, max_lines: int) -> list[str]:
    lines = []
    for line in text.splitlines():
        if line.strip():
            lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines


def detect_delimiter(
    text: str,
    candidates: tuple[str, ...] = DELIMITER_CANDIDATES,
    sample_lines: int = 100,
) -> tuple[str, float]:
    """Detect the field delimiter from decoded text.

    Scores each candidate by how consistently it yields the same field count
    across sample rows, weighted by the number of fields produced.

    Args:
        text: Decoded file contents (or a representative prefix).
        candidates: Delimiter characters to consider.
        sample_lines: Number of non-empty lines to sample.

    Returns:
        A ``(delimiter, confidence)`` pair. Confidence is the winning score's
        share of the top two scores; ``0.0`` when no candidate splits the text.
    """
    lines = _sample_lines(text, sample_lines)
    if not lines:
        return ",", 0.0

    scores: dict = {}
    for delimiter in candidates:
        field_counts = []
        for line in lines:
            row = next(csv.reader([line], delimiter=delimiter), [])
            field_counts.append(len(row))
        if not field_counts:
            continue
        most_common_count, occurrences = Counter(field_counts).most_common(1)[0]
        if most_common_count <= 1:
            continue
        consistency = occurrences / len(field_counts)
        scores[delimiter] = consistency * most_common_count

    if not scores:
        return ",", 0.0

    ranked = sorted(scores.values(), reverse=True)
    best_delimiter = max(scores, key=lambda d: scores[d])
    best = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else 0.0
    confidence = best / (best + runner_up) if (best + runner_up) else 1.0
    return best_delimiter, confidence


def detect_quote_char(text: str, delimiter: str, sample_lines: int = 100) -> str:
    """Detect the quote character used to wrap fields.

    Args:
        text: Decoded file contents (or a representative prefix).
        delimiter: The field delimiter already detected.
        sample_lines: Number of non-empty lines to sample.

    Returns:
        The most likely quote character; defaults to ``'"'``.
    """
    lines = _sample_lines(text, sample_lines)
    best_quote = '"'
    best_pairs = 0
    for quote in QUOTE_CANDIDATES:
        # A quoted field contributes a pair of quote characters, typically next to
        # a delimiter or a line boundary. Count balanced pairs as evidence.
        pairs = sum(line.count(quote) // 2 for line in lines if quote in line)
        adjacent = sum(
            1
            for line in lines
            if quote + delimiter in line or delimiter + quote in line
        )
        score = pairs + adjacent
        if score > best_pairs:
            best_pairs = score
            best_quote = quote
    return best_quote


def detect_header(
    text: str,
    delimiter: str,
    quote_char: str = '"',
) -> bool:
    """Decide whether the first row is a header.

    Headers are rarely numeric, so a first row whose cells are all non-numeric is
    treated as a header (the convention pandas and Polars default to). A numeric
    cell in the first row is strong evidence the row is data, not labels.

    Args:
        text: Decoded file contents (or a representative prefix).
        delimiter: The field delimiter.
        quote_char: The quote character.

    Returns:
        ``True`` if the first row looks like a header.
    """
    lines = _sample_lines(text, 5)
    if not lines:
        return True

    rows = list(csv.reader(lines, delimiter=delimiter, quotechar=quote_char))
    if not rows or not rows[0]:
        return True

    return not any(_is_number(cell) for cell in rows[0])


def _is_number(value: str) -> bool:
    try:
        float(value.strip())
    except ValueError:
        return False
    return True
