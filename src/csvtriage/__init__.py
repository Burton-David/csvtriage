"""csvtriage — load messy CSVs, recover what you can, and report every decision.

The library never fails silently: every read returns a :class:`~csvtriage.frame.Frame`
whose :attr:`~csvtriage.frame.Frame.report` records the detected dialect, the
repairs applied, and any rows that had to be quarantined.
"""

from importlib.metadata import PackageNotFoundError, version

from .clean import quick_clean
from .errors import (
    CSVTriageError,
    DelimiterError,
    EncodingError,
    FileTooLargeError,
    ParseError,
)
from .frame import Frame
from .reader import read
from .report import QuarantinedRow, ReadReport
from .streaming import info, peek, stream

try:
    __version__ = version("csvtriage")
except PackageNotFoundError:  # pragma: no cover - only during local source runs
    __version__ = "0.0.0"

__all__ = [
    "CSVTriageError",
    "DelimiterError",
    "EncodingError",
    "FileTooLargeError",
    "Frame",
    "ParseError",
    "QuarantinedRow",
    "ReadReport",
    "info",
    "peek",
    "quick_clean",
    "read",
    "stream",
    "__version__",
]
