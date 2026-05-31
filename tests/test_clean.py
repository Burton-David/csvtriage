"""Tests for the deterministic cleaning transforms."""

from datetime import date, datetime

import csvtriage as ct


def _frame(write_file, content: str):
    return ct.read(write_file("c.csv", content))


class TestQuickClean:
    def test_strips_whitespace(self, write_file) -> None:
        frame = _frame(write_file, "name,city\n  Alice  , NYC \n")
        cleaned = frame.clean()
        assert cleaned.to_polars()["name"].to_list() == ["Alice"]

    def test_standardizes_nulls(self, write_file) -> None:
        frame = _frame(write_file, "name,note\nAlice,NA\nBob,null\n")
        cleaned = frame.clean()
        assert cleaned.to_polars()["note"].to_list() == [None, None]

    def test_drops_duplicate_rows(self, write_file) -> None:
        frame = _frame(write_file, "a,b\n1,2\n1,2\n3,4\n")
        cleaned = frame.clean()
        assert cleaned.shape[0] == 2

    def test_normalizes_column_names(self, write_file) -> None:
        frame = _frame(write_file, "First Name,Last-Name\nA,B\n")
        cleaned = frame.clean()
        assert cleaned.columns == ["first_name", "last_name"]

    def test_records_repairs_without_printing(self, write_file, capsys) -> None:
        frame = _frame(write_file, "Name ,b\n A ,2\n A ,2\n")
        cleaned = frame.clean()
        assert cleaned.report.repairs
        assert capsys.readouterr().out == ""

    def test_original_frame_unchanged(self, write_file) -> None:
        frame = _frame(write_file, "a,b\n1,2\n1,2\n")
        original_rows = frame.shape[0]
        frame.clean()
        assert frame.shape[0] == original_rows

    def test_clean_does_not_mutate_original_report(self, write_file) -> None:
        # clean() must record repairs on a copy, leaving the source report intact
        # (and not double-appending across repeated calls).
        frame = _frame(write_file, "Name ,b\n A ,2\n A ,2\n")
        before = list(frame.report.repairs)
        cleaned = frame.clean()
        assert frame.report.repairs == before
        assert cleaned.report is not frame.report
        assert cleaned.report.repairs
        frame.clean()
        assert frame.report.repairs == before


class TestDateParsing:
    def test_parses_iso_dates(self, write_file) -> None:
        frame = _frame(write_file, "event,when\nlaunch,2024-01-15\n")
        cleaned = frame.clean(parse_dates=True)
        assert cleaned.to_polars()["when"].to_list() == [datetime(2024, 1, 15)]

    def test_relative_dates_are_deterministic(self, write_file) -> None:
        frame = _frame(write_file, "event,when\na,today\nb,yesterday\n")
        cleaned = frame.clean(parse_dates=True, now=date(2026, 5, 30))
        assert cleaned.to_polars()["when"].to_list() == [
            datetime(2026, 5, 30),
            datetime(2026, 5, 29),
        ]

    def test_dayfirst_changes_interpretation(self, write_file) -> None:
        frame = _frame(write_file, "event,when\na,02/03/2024\n")
        cleaned = frame.clean(parse_dates=True, dayfirst=True)
        assert cleaned.to_polars()["when"].to_list() == [datetime(2024, 3, 2)]
