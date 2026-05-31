"""Tests for the read report."""

import json

from csvtriage import ReadReport


class TestReadReport:
    def test_clean_report(self) -> None:
        report = ReadReport(rows_read=10, columns=3)
        assert report.is_clean
        assert report.rows_quarantined == 0

    def test_repairs_make_it_not_clean(self) -> None:
        report = ReadReport()
        report.add_repair("re-encoded from latin-1 to utf-8")
        assert not report.is_clean
        assert report.repairs == ["re-encoded from latin-1 to utf-8"]

    def test_quarantine_records_row(self) -> None:
        report = ReadReport()
        report.quarantine(7, "a,b,c,d", "too many fields")
        assert report.rows_quarantined == 1
        assert report.quarantined[0].line_number == 7
        assert report.quarantined[0].reason == "too many fields"

    def test_to_dict_includes_derived_fields(self) -> None:
        report = ReadReport(rows_read=2, columns=2)
        report.quarantine(3, "bad", "unparseable")
        data = report.to_dict()
        assert data["rows_quarantined"] == 1
        assert data["is_clean"] is False
        assert len(data["quarantined"]) == 1

    def test_to_json_round_trips(self) -> None:
        report = ReadReport(encoding="utf-8", rows_read=5, columns=2)
        report.quarantine(9, "x", "y")
        restored = json.loads(report.to_json())
        assert restored["encoding"] == "utf-8"
        assert restored["rows_quarantined"] == 1

    def test_explain_mentions_repairs_and_quarantine(self) -> None:
        report = ReadReport(encoding="utf-8", rows_read=3, columns=2)
        report.add_repair("padded short row")
        report.quarantine(4, "junk", "HTML contamination")
        text = report.explain()
        assert "padded short row" in text
        assert "Quarantined 1" in text
