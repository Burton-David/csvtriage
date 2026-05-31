"""Tests for line-level recovery and quarantine behavior."""

import csvtriage as ct
from csvtriage import robust


class TestContaminationDetection:
    def test_flags_html_line(self) -> None:
        assert robust.is_contamination("<html><body>error</body></html>")

    def test_flags_script_line(self) -> None:
        assert robust.is_contamination("<script>alert('x')</script>")

    def test_allows_data_with_single_angle_bracket(self) -> None:
        assert not robust.is_contamination("value < 5,ok")

    def test_ignores_blank_line(self) -> None:
        assert not robust.is_contamination("   ")


class TestRecovery:
    def test_quarantines_html_rows(self, write_file) -> None:
        content = (
            "name,age,city\n"
            "Alice,30,NYC\n"
            "<html><body>500 Server Error</body></html>\n"
            "Bob,25,LA\n"
            "<script>x</script>\n"
            "Carol,40,SF\n"
        )
        path = write_file("contaminated.csv", content)
        frame = ct.read(path, robust=True)
        assert frame.shape == (3, 3)
        assert frame.report.rows_quarantined == 2
        reasons = {q.reason for q in frame.report.quarantined}
        assert reasons == {"HTML/markup contamination"}

    def test_pads_short_rows(self, write_file) -> None:
        path = write_file("ragged.csv", "a,b,c\n1,2,3\n4,5\n6,7,8\n")
        frame = ct.read(path, robust=True)
        assert frame.shape == (3, 3)
        assert any("padded short row" in r for r in frame.report.repairs)

    def test_captures_overflow_fields(self, write_file) -> None:
        path = write_file("over.csv", "a,b\n1,2\n3,4,5,6\n")
        frame = ct.read(path, robust=True)
        assert "_overflow" in frame.columns

    def test_recovers_mixed_encoding_lines(self, write_file) -> None:
        content = b"name\nAlice\n" + "José".encode("latin-1") + b"\n"
        path = write_file("mixed.csv", content)
        frame = ct.read(path, robust=True)
        assert frame.shape[0] == 2
        assert "José" in frame.to_polars()["name"].to_list()

    def test_strict_failure_falls_back_to_recovery(self, write_file) -> None:
        # A bare row longer than the header forces a recovery path that records it.
        path = write_file("over.csv", "a,b\n1,2\n3,4,5,6,7\n")
        frame = ct.read(path)
        assert frame.shape[0] >= 2
