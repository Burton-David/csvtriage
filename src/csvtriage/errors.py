"""Exception hierarchy for csvtriage.

Every error carries an actionable message: what went wrong, and the concrete
parameter the caller can pass to get past it.
"""

from pathlib import Path

PathLike = str | Path


class CSVTriageError(Exception):
    """Base class for every error raised by csvtriage."""


class EncodingError(CSVTriageError):
    """The file's character encoding could not be detected or decoded."""

    def __init__(
        self,
        filepath: PathLike,
        detected_encoding: str | None = None,
        confidence: float | None = None,
    ) -> None:
        self.filepath = filepath
        self.detected_encoding = detected_encoding
        self.confidence = confidence

        if detected_encoding is not None:
            confidence_note = (
                f" (confidence: {confidence:.1%})" if confidence is not None else ""
            )
            message = (
                f"Failed to decode '{filepath}' with detected encoding "
                f"'{detected_encoding}'{confidence_note}. "
                f"Specify it explicitly, e.g. read('{filepath}', encoding='latin-1')."
            )
        else:
            message = (
                f"Could not detect the encoding of '{filepath}'. "
                f"Specify it explicitly, e.g. read('{filepath}', encoding='utf-8')."
            )
        super().__init__(message)


class DelimiterError(CSVTriageError):
    """No delimiter produced a consistent column structure."""

    def __init__(
        self,
        filepath: PathLike,
        attempted_delimiters: list[str] | None = None,
    ) -> None:
        self.filepath = filepath
        self.attempted_delimiters = attempted_delimiters or [",", "\t", ";", "|"]
        tried = ", ".join(repr(d) for d in self.attempted_delimiters)
        super().__init__(
            f"Could not detect a delimiter for '{filepath}' (tried {tried}). "
            f"Specify it explicitly, e.g. read('{filepath}', delimiter=',')."
        )


class FileTooLargeError(CSVTriageError):
    """The file is too large to load into memory; use streaming instead.

    Named to avoid shadowing the builtin ``MemoryError``.
    """

    def __init__(
        self,
        filepath: PathLike,
        file_size: int,
        available_memory: int | None = None,
    ) -> None:
        self.filepath = filepath
        self.file_size = file_size
        self.available_memory = available_memory
        size_gb = file_size / (1024**3)
        super().__init__(
            f"'{filepath}' is {size_gb:.1f} GB — too large to load into memory. "
            f"Stream it instead: for chunk in stream('{filepath}'): ..."
        )


class ParseError(CSVTriageError):
    """The CSV could not be parsed even after recovery."""

    def __init__(
        self,
        filepath: PathLike,
        row_number: int | None = None,
        error_detail: str | None = None,
    ) -> None:
        self.filepath = filepath
        self.row_number = row_number
        self.error_detail = error_detail

        if row_number is not None:
            super().__init__(
                f"Failed to parse row {row_number} of '{filepath}': {error_detail}. "
                f"Pass on_bad_lines='skip' to quarantine malformed rows instead."
            )
        else:
            super().__init__(
                f"Failed to parse '{filepath}': {error_detail}. "
                f"Try robust=True to recover what is parseable."
            )
