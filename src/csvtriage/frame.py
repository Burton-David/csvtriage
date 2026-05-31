"""The Frame: a thin handle over a Polars table plus its read report.

The wrapper deliberately exposes only a small, explicit surface. It does not proxy
arbitrary Polars methods via ``__getattr__`` — that silently returns raw Polars
objects and loses the report. Call :meth:`to_polars` to drop into Polars when you
want the full dataframe API.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import polars as pl

from .report import ReadReport

if TYPE_CHECKING:
    import pandas
    import pyarrow

ParquetCompression = Literal["lz4", "uncompressed", "snappy", "gzip", "brotli", "zstd"]


class Frame:
    """A parsed table and the report describing how it was read.

    Attributes:
        report: The :class:`~csvtriage.report.ReadReport` for this read.
    """

    def __init__(self, table: pl.DataFrame, report: ReadReport | None = None):
        self._table = table
        self.report = report if report is not None else ReadReport()

    @property
    def shape(self) -> tuple[int, int]:
        """The ``(rows, columns)`` shape of the table."""
        rows, cols = self._table.shape
        return (int(rows), int(cols))

    @property
    def columns(self) -> list[str]:
        """The column names."""
        return list(self._table.columns)

    def __len__(self) -> int:
        return self._table.height

    def __getitem__(self, key: Any) -> Any:
        return self._table[key]

    def __repr__(self) -> str:
        return f"Frame(shape={self.shape}, {self.report})"

    def __str__(self) -> str:
        return str(self._table)

    def to_polars(self) -> pl.DataFrame:
        """Return the underlying Polars DataFrame."""
        return self._table

    def to_pandas(self) -> "pandas.DataFrame":
        """Return the table as a pandas DataFrame (requires pandas)."""
        return self._table.to_pandas()

    def to_arrow(self) -> "pyarrow.Table":
        """Return the table as a PyArrow Table."""
        return self._table.to_arrow()

    def clean(self, **options: Any) -> "Frame":
        """Apply cleaning transforms, returning a new Frame.

        Accepts the same keyword options as :func:`csvtriage.clean.quick_clean`.
        Repairs are appended to a copy of this frame's report.

        Returns:
            A new :class:`Frame` with cleaned data and an extended report.
        """
        from .clean import quick_clean

        return quick_clean(self, **options)

    def write_csv(self, file_path: str | Path, **kwargs: Any) -> None:
        """Write the table to a CSV file.

        Args:
            file_path: Destination path; parent directories are created.
            **kwargs: Passed through to ``polars.DataFrame.write_csv``.
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._table.write_csv(path, **kwargs)

    def write_parquet(
        self,
        file_path: str | Path,
        *,
        compression: ParquetCompression = "snappy",
        **kwargs: Any,
    ) -> None:
        """Write the table to a Parquet file.

        Args:
            file_path: Destination path; parent directories are created.
            compression: Parquet codec (``snappy``/``gzip``/``zstd``/...).
            **kwargs: Passed through to ``polars.DataFrame.write_parquet``.
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._table.write_parquet(path, compression=compression, **kwargs)
