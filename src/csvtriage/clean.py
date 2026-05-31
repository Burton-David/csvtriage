"""Deterministic cleaning transforms for parsed tables.

Each transform is a pure function of its inputs: there is no hidden state, no
stdout, and any value that depends on the current date is computed from an
injected ``now`` so results are reproducible. Every change is recorded on the
frame's report rather than printed.
"""

import copy
from datetime import date, datetime, timedelta

import polars as pl

from .frame import Frame

_NULL_TOKENS = ("", "na", "n/a", "null", "none", "-", "--", "nan")

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
)


def quick_clean(
    frame: Frame,
    *,
    strip_whitespace: bool = True,
    standardize_nulls: bool = True,
    drop_empty_rows: bool = True,
    drop_duplicate_rows: bool = True,
    fix_column_names: bool = True,
    parse_dates: bool = False,
    dayfirst: bool = False,
    now: date | None = None,
) -> Frame:
    """Apply common cleaning operations and return a new Frame.

    Args:
        frame: The frame to clean.
        strip_whitespace: Trim leading/trailing whitespace in string columns.
        standardize_nulls: Map common null tokens (``NA``, ``null``, ``-``, ...)
            to actual nulls.
        drop_empty_rows: Drop rows where every value is null.
        drop_duplicate_rows: Drop exact duplicate rows.
        fix_column_names: Normalize column names to ``snake_case``.
        parse_dates: Attempt to parse string columns that look like dates.
        dayfirst: Interpret ambiguous numeric dates as day-first (European).
        now: Reference date for relative tokens (``today``/``yesterday``); defaults
            to ``date.today()``. Injectable for deterministic tests.

    Returns:
        A new :class:`~csvtriage.frame.Frame`; the original is left unchanged.
    """
    table = frame.to_polars().clone()
    # Deep-copy so cleaning never mutates the caller's original report.
    report = copy.deepcopy(frame.report)
    reference = now or date.today()

    string_cols = [
        c for c, dt in zip(table.columns, table.dtypes, strict=False) if dt == pl.String
    ]

    if strip_whitespace and string_cols:
        table = table.with_columns(pl.col(string_cols).str.strip_chars())
        report.add_repair(f"stripped whitespace in {len(string_cols)} column(s)")

    if standardize_nulls and string_cols:
        table = table.with_columns(
            pl.when(pl.col(string_cols).str.to_lowercase().is_in(_NULL_TOKENS))
            .then(None)
            .otherwise(pl.col(string_cols))
            .name.keep()
        )
        report.add_repair("standardized null tokens")

    if drop_empty_rows:
        before = table.height
        table = table.filter(~pl.all_horizontal(pl.all().is_null()))
        removed = before - table.height
        if removed:
            report.add_repair(f"dropped {removed} empty row(s)")

    if drop_duplicate_rows:
        before = table.height
        table = table.unique(maintain_order=True)
        removed = before - table.height
        if removed:
            report.add_repair(f"dropped {removed} duplicate row(s)")

    if fix_column_names:
        renamed = {c: _snake_case(c) for c in table.columns}
        changed = {old: new for old, new in renamed.items() if old != new}
        if changed:
            table = table.rename(_dedupe_names(renamed))
            report.add_repair(f"normalized {len(changed)} column name(s)")

    if parse_dates:
        date_cols = [
            c
            for c, dt in zip(table.columns, table.dtypes, strict=False)
            if dt == pl.String and _looks_like_dates(table[c])
        ]
        for col in date_cols:
            table = table.with_columns(
                _parse_date_series(table[col], reference, dayfirst).alias(col)
            )
        if date_cols:
            report.add_repair(f"parsed dates in {len(date_cols)} column(s)")

    return Frame(table, report)


def _snake_case(name: str) -> str:
    out = []
    for char in name.strip():
        out.append(char if char.isalnum() else "_")
    collapsed = "_".join(filter(None, "".join(out).split("_")))
    return collapsed.lower()


def _dedupe_names(renamed: dict) -> dict:
    seen: dict = {}
    result = {}
    for old, new in renamed.items():
        if new in seen:
            seen[new] += 1
            new = f"{new}_{seen[new]}"
        else:
            seen[new] = 0
        result[old] = new
    return result


def _looks_like_dates(series: pl.Series, threshold: float = 0.6) -> bool:
    sample = series.drop_nulls().head(50)
    if sample.is_empty():
        return False
    hits = sum(1 for value in sample if _parse_one(value, date.today(), False))
    return hits / len(sample) >= threshold


def _parse_date_series(series: pl.Series, reference: date, dayfirst: bool) -> pl.Series:
    parsed: list[datetime | None] = [
        _parse_one(value, reference, dayfirst) for value in series
    ]
    return pl.Series(series.name, parsed, dtype=pl.Datetime)


def _parse_one(value: str | None, reference: date, dayfirst: bool) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None

    lowered = text.lower()
    base = datetime(reference.year, reference.month, reference.day)
    if lowered == "today":
        return base
    if lowered == "yesterday":
        return base - timedelta(days=1)
    if lowered == "tomorrow":
        return base + timedelta(days=1)

    formats: tuple[str, ...] = _DATE_FORMATS
    if dayfirst:
        formats = ("%d/%m/%Y", "%d-%m-%Y") + formats
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None
