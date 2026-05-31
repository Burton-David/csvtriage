"""Tests for the main read() entry point."""

import gzip

import polars as pl
import pytest

import csvtriage as ct
from csvtriage import Frame, ParseError


class TestBasicReading:
    def test_reads_simple_csv(self, write_file) -> None:
        path = write_file("simple.csv", "name,age,city\nAlice,30,NYC\nBob,25,LA\n")
        frame = ct.read(path)
        assert isinstance(frame, Frame)
        assert frame.shape == (2, 3)
        assert frame.columns == ["name", "age", "city"]

    def test_infers_numeric_types(self, write_file) -> None:
        path = write_file("nums.csv", "a,b\n1,2\n3,4\n")
        frame = ct.read(path)
        assert frame.to_polars()["a"].dtype == pl.Int64

    def test_columns_as_string_overrides_inference(self, write_file) -> None:
        path = write_file("nums.csv", "a,b\n1,2\n3,4\n")
        frame = ct.read(path, columns_as_string=["a"])
        assert frame.to_polars()["a"].dtype == pl.String

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            ct.read("definitely_not_here.csv")

    def test_invalid_on_bad_lines_raises(self, write_file) -> None:
        path = write_file("simple.csv", "a,b\n1,2\n")
        with pytest.raises(ValueError):
            ct.read(path, on_bad_lines="explode")


class TestDialectHandling:
    def test_reads_semicolon_delimited(self, write_file) -> None:
        path = write_file("semi.csv", "name;age\nAlice;30\nBob;25\n")
        frame = ct.read(path)
        assert frame.columns == ["name", "age"]
        assert frame.report.delimiter == ";"

    def test_reads_tab_delimited(self, write_file) -> None:
        path = write_file("tabs.tsv", "name\tage\nAlice\t30\n")
        frame = ct.read(path)
        assert frame.report.delimiter == "\t"

    def test_preserves_quoted_field_with_comma(self, write_file) -> None:
        path = write_file("q.csv", 'name,note\nAlice,"hi, there"\nBob,plain\n')
        frame = ct.read(path)
        assert frame.to_polars()["note"].to_list() == ["hi, there", "plain"]

    def test_reads_gzip(self, write_file) -> None:
        path = write_file("c.csv.gz", gzip.compress(b"a,b\n1,2\n3,4\n"))
        frame = ct.read(path)
        assert frame.shape == (2, 2)
        assert frame.report.compression == "gzip"


class TestEncodingRecovery:
    def test_reads_latin1_content(self, write_file) -> None:
        path = write_file("l.csv", "name,city\nJosé,São Paulo\n".encode("latin-1"))
        frame = ct.read(path)
        assert frame.report.encoding in ("cp1252", "latin-1")
        assert "José" in frame.to_polars()["name"].to_list()

    def test_records_reencoding_repair(self, write_file) -> None:
        path = write_file("l.csv", "name\nJosé\n".encode("latin-1"))
        frame = ct.read(path)
        assert any("re-encoded" in r for r in frame.report.repairs)

    def test_explicit_encoding_is_respected(self, write_file) -> None:
        path = write_file("l.csv", "name\nJosé\n".encode("latin-1"))
        frame = ct.read(path, encoding="latin-1")
        assert frame.report.encoding == "latin-1"


class TestNoSilentDataLoss:
    def test_extra_fields_are_captured_not_truncated(self, write_file) -> None:
        # A row longer than the header must not lose its extra fields silently;
        # they are captured in an overflow column and the recovery is recorded.
        path = write_file("over.csv", "a,b\n1,2\n3,4,5,6,7\n")
        frame = ct.read(path)
        assert "_overflow" in frame.columns
        assert frame.to_polars()["_overflow"].to_list() == [None, "5,6,7"]
        assert any("recovered line-by-line" in r for r in frame.report.repairs)

    def test_wrong_forced_encoding_recovers_without_replacement_chars(
        self, write_file
    ) -> None:
        # Forcing utf-8 on latin-1 bytes used to mangle them to U+FFFD silently;
        # the strict decode now fails and per-line recovery decodes correctly.
        path = write_file("l.csv", "name\ncaf\xe9\n".encode("latin-1"))
        frame = ct.read(path, encoding="utf-8")
        values = frame.to_polars()["name"].to_list()
        assert values == ["café"]
        assert "�" not in values[0]

    def test_error_mode_raises_when_a_row_is_quarantined(self, write_file) -> None:
        # The over-long row trips the strict parse into recovery; recovery then
        # quarantines the HTML line. With on_bad_lines="error" an unrecoverable
        # (quarantined) row escalates to a ParseError rather than loading silently.
        path = write_file("c.csv", "a,b\n1,2\n<html>err</html>\n3,4,5\n")
        with pytest.raises(ParseError):
            ct.read(path, on_bad_lines="error")

    def test_skip_mode_loads_rest_and_records_quarantine(self, write_file) -> None:
        # Same file, skip mode: the recoverable rows load (over-long row captured
        # in _overflow) and the HTML line is recorded in the report, not dropped.
        path = write_file("c.csv", "a,b\n1,2\n<html>err</html>\n3,4,5\n")
        frame = ct.read(path, on_bad_lines="skip")
        assert frame.report.rows_quarantined == 1
        assert frame.report.quarantined[0].reason == "HTML/markup contamination"
        assert frame.shape[0] == 2
        assert "_overflow" in frame.columns

    def test_strict_mode_short_row_is_padded_standard_behavior(
        self, write_file
    ) -> None:
        # A short row is null-padded (as pandas/Polars/csv all do) — no data is
        # lost, so it stays on the fast path and is not forced into recovery.
        path = write_file("short.csv", "a,b,c\n1,2,3\n4,5\n")
        frame = ct.read(path)
        assert frame.shape == (2, 3)
        assert frame.to_polars().row(1) == (4, 5, None)


class TestLineEndings:
    def test_cr_only_endings_plain_read(self, write_file) -> None:
        # "Old Mac" CR-only endings used to yield zero rows reported as clean.
        path = write_file("cr.csv", b"a,b\r1,2\r3,4\r")
        frame = ct.read(path)
        assert frame.shape == (2, 2)
        assert frame.to_polars()["a"].to_list() == [1, 3]

    def test_cr_only_endings_robust_read(self, write_file) -> None:
        # Robust mode used to leak a raw _csv.Error on CR-only files.
        path = write_file("cr.csv", b"a,b\r1,2\r3,4\r")
        frame = ct.read(path, robust=True)
        assert frame.shape[0] == 2

    def test_crlf_endings_unaffected(self, write_file) -> None:
        path = write_file("crlf.csv", b"a,b\r\n1,2\r\n3,4\r\n")
        frame = ct.read(path)
        assert frame.shape == (2, 2)
