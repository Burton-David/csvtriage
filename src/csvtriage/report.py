"""The read report — a structured account of how a file was read.

Every ``read``/``peek``/``stream`` attaches a :class:`ReadReport`. It records what
was detected (encoding, delimiter, quoting, header, compression), how many rows
were read, what was repaired, and — crucially — every row that could not be parsed
and was quarantined rather than silently dropped.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class QuarantinedRow:
    """A source line that could not be parsed into the table.

    Attributes:
        line_number: 1-based line number in the source file.
        raw: The raw text of the line.
        reason: Why the line was quarantined.
    """

    line_number: int
    raw: str
    reason: str


@dataclass
class ReadReport:
    """What csvtriage detected, repaired, and could not parse.

    Attributes:
        encoding: The encoding used to decode the file.
        encoding_confidence: Detector confidence in ``encoding`` (0.0–1.0).
        delimiter: The field delimiter used.
        quote_char: The quote character used.
        has_header: Whether the first row was treated as a header.
        compression: Detected compression (``"gzip"``/``"zip"``/``"bz2"``/``"xz"``)
            or ``None``.
        rows_read: Number of data rows successfully read into the table.
        columns: Number of columns in the resulting table.
        repairs: Human-readable descriptions of repairs applied.
        quarantined: Rows that could not be parsed, with line number and reason.
    """

    encoding: str | None = None
    encoding_confidence: float | None = None
    delimiter: str | None = None
    quote_char: str | None = None
    has_header: bool | None = None
    compression: str | None = None
    rows_read: int = 0
    columns: int = 0
    repairs: list[str] = field(default_factory=list)
    quarantined: list[QuarantinedRow] = field(default_factory=list)

    @property
    def rows_quarantined(self) -> int:
        """Number of rows that were quarantined."""
        return len(self.quarantined)

    @property
    def is_clean(self) -> bool:
        """True when nothing needed repair and no rows were quarantined."""
        return not self.repairs and not self.quarantined

    def add_repair(self, description: str) -> None:
        """Record a repair that was applied to the data."""
        self.repairs.append(description)

    def quarantine(self, line_number: int, raw: str, reason: str) -> None:
        """Record a source line that could not be parsed.

        Args:
            line_number: 1-based line number in the source file.
            raw: The raw text of the line.
            reason: Why the line could not be parsed.
        """
        self.quarantined.append(QuarantinedRow(line_number, raw, reason))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of the report."""
        data = asdict(self)
        data["rows_quarantined"] = self.rows_quarantined
        data["is_clean"] = self.is_clean
        return data

    def to_json(self, *, indent: int | None = 2) -> str:
        """Return the report as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def explain(self) -> str:
        """Return a human-readable narrative of how the file was read."""
        lines = []
        if self.encoding is not None:
            confidence = (
                f" ({self.encoding_confidence:.0%} confidence)"
                if self.encoding_confidence is not None
                else ""
            )
            lines.append(f"Decoded as {self.encoding}{confidence}.")
        if self.compression:
            lines.append(f"Decompressed {self.compression} input.")
        if self.delimiter is not None:
            quote = self.quote_char or '"'
            lines.append(
                f"Parsed with delimiter {self.delimiter!r} and quote {quote!r}; "
                f"header {'present' if self.has_header else 'absent'}."
            )
        lines.append(f"Read {self.rows_read} rows across {self.columns} columns.")
        if self.repairs:
            lines.append(f"Applied {len(self.repairs)} repair(s):")
            lines.extend(f"  - {r}" for r in self.repairs)
        if self.quarantined:
            lines.append(
                f"Quarantined {self.rows_quarantined} unparseable row(s); "
                f"inspect report.quarantined for details."
            )
        if self.is_clean:
            lines.append("No repairs were needed.")
        return "\n".join(lines)

    def __str__(self) -> str:
        status = "clean" if self.is_clean else "with repairs"
        return (
            f"ReadReport({self.rows_read} rows x {self.columns} cols, {status}; "
            f"{len(self.repairs)} repair(s), "
            f"{self.rows_quarantined} quarantined)"
        )
