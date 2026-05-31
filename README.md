# csvtriage

**Load messy CSVs, recover what you can, and report every decision.**

csvtriage is the CSV reader that never silently fails. It loads files other
parsers choke on — wrong encodings, odd delimiters, ragged rows, mixed line
endings, HTML junk, compression — recovers what it can, and hands back a
structured `ReadReport` describing every assumption, repair, and quarantined row.
So you can trust the data, or know exactly why you can't.

The parsing engine is [Polars](https://pola.rs/); encoding detection uses
`chardet` and mojibake repair uses [ftfy](https://github.com/rspeer/python-ftfy).
Every path — `read`, `peek`, `stream`, and the CLI — goes through the same engine,
so a previewed or streamed chunk types identically to a full read.

## Installation

```bash
pip install -e .          # from a clone (PyPI release pending)
pip install -e ".[dev]"   # with the test / lint / type-check toolchain
```

Optional extras: `[parquet]` (PyArrow, for Parquet I/O) and `[pandas]`
(`.to_pandas()`). Python 3.10–3.13.

## Quick start

```python
import csvtriage as ct

# Auto-detects encoding, delimiter, quote char, header, and compression.
frame = ct.read("messy_data.csv")

print(frame.shape)            # (rows, columns)
print(frame.report.explain()) # what was detected and repaired, in plain English

# Clean common messiness; the original frame is left untouched.
cleaned = frame.clean()

# Hand off to Polars / pandas / Arrow, or write out.
df = cleaned.to_polars()
cleaned.write_parquet("clean_data.parquet")
```

## Reading

```python
# Auto-detect everything.
frame = ct.read("data.csv")

# Or force any of it.
frame = ct.read(
    "data.csv",
    encoding="latin-1",
    delimiter="\t",
    has_header=True,
    columns_as_string=["zip_code"],   # keep leading zeros
    on_bad_lines="skip",              # quarantine bad rows instead of raising
)

# Aggressive line-level recovery for genuinely broken files.
frame = ct.read("scraped.csv", robust=True)
```

`read()` first tries a fast strict parse. If that fails — or you pass
`robust=True` — it falls back to line-level recovery: per-line encoding fallback,
mojibake repair, HTML/markup filtering, ragged-row handling, and mixed/old-Mac
line endings. Recovered structure is recorded as repairs; rows that still can't be
parsed are **quarantined**, never silently dropped. With `on_bad_lines="error"`
(the default) an unrecoverable row raises `ParseError`; with `"skip"` it loads the
rest and records each quarantined row in `frame.report`.

## The report

Every read attaches a `ReadReport` at `frame.report`:

```python
r = frame.report
r.encoding, r.encoding_confidence   # e.g. ("cp1252", 0.99)
r.delimiter, r.quote_char, r.has_header
r.rows_read, r.columns
r.repairs                           # list[str] of what was changed
r.quarantined                       # list[QuarantinedRow(line_number, raw, reason)]
r.rows_quarantined, r.is_clean

r.explain()                         # human-readable narrative
r.to_dict(); r.to_json()            # machine-readable, for logging/alerting
```

## Cleaning

`Frame.clean()` (a wrapper over `csvtriage.quick_clean`) applies deterministic
transforms and records each on a copy of the report. It never prints and never
mutates the original frame:

```python
cleaned = frame.clean(
    strip_whitespace=True,
    standardize_nulls=True,     # NA / null / none / - / "" -> null
    drop_empty_rows=True,
    drop_duplicate_rows=True,
    fix_column_names=True,      # "First Name" -> "first_name"
    parse_dates=False,          # opt-in date parsing
    dayfirst=False,             # interpret ambiguous dates as European
)
for change in cleaned.report.repairs:
    print(change)
```

## Preview, inspect, stream

```python
preview = ct.peek("huge_file.csv", rows=1000)   # reads only a bounded prefix

summary = ct.info("huge_file.csv")              # no full load
print(f"{summary['size_mb']} MB, ~{summary['estimated_rows']:,} rows")
print(summary["encoding"], summary["delimiter"])

for chunk in ct.stream("huge_file.csv", chunk_size=50_000):
    process(chunk.to_polars())                  # each chunk is a Frame
```

## Command line

```bash
csvtriage info data.csv [--json]            # encoding, delimiter, size, est. rows
csvtriage peek data.csv -n 20               # preview the first rows
csvtriage clean in.csv out.parquet          # read + quick_clean + write
csvtriage convert in.csv out.parquet        # read + write (.csv / .parquet)
csvtriage validate data.csv                 # exit non-zero if rows were quarantined
```

Exit codes are script-friendly: `0` on success, `1` when `validate` finds
quarantined rows, `2` on a usage or runtime error. `convert`/`clean` accept
`--robust` and `--report text|json|none`.

## Error handling

Errors are the library's own (`csvtriage.errors`) and carry an actionable message
plus the parameter to get past them:

```python
# Instead of a bare UnicodeDecodeError you get:
# EncodingError: Failed to decode 'data.csv' with detected encoding 'utf-8'
#   (confidence: 73.2%). Specify it explicitly, e.g.
#   read('data.csv', encoding='latin-1').
```

The hierarchy: `CSVTriageError` (base), `EncodingError`, `DelimiterError`,
`FileTooLargeError`, `ParseError`.

## Performance

The strict path is Polars with a thin detection layer in front, so clean files
read at close to raw `pl.read_csv` speed. Robust mode does extra per-line work and
is slower by design — that is the cost of recovering files a strict parser rejects.
No benchmark numbers are published here yet; a reproducible harness is on the
roadmap rather than hand-quoted figures.

## Examples

Runnable scripts in [`examples/`](examples/):

- `basic_usage.py` — read a file and inspect the report
- `encoding_recovery_example.py` — non-UTF-8 input, auto-detected
- `robust_reading_example.py` — recover a contaminated file and review quarantine
- `streaming_example.py` — `info`, `peek`, and `stream` on a large file

## Status

Alpha (v0.1.0). The core — detection, strict + robust reading, the report,
cleaning, peek/info/stream, and the CLI — is implemented and tested across Python
3.10–3.13. See [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) for the product
vision and roadmap (numeric/date normalization, recovery policies, CleverCSV-grade
dialect detection, optional validation).

## Contributing

Issues and PRs welcome. Run the full gate before submitting:

```bash
make check    # black --check, ruff, mypy, pytest
```

## License

MIT
