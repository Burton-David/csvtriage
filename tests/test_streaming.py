"""Tests for peek, info, and stream."""

import gzip

import csvtriage as ct
from csvtriage import detect


def _many_rows(n: int) -> str:
    body = "\n".join(f"{i},{i * 2}" for i in range(n))
    return f"a,b\n{body}\n"


class TestPeek:
    def test_limits_rows(self, write_file) -> None:
        path = write_file("big.csv", _many_rows(500))
        frame = ct.peek(path, rows=10)
        assert frame.shape[0] == 10

    def test_peek_works_on_latin1(self, write_file) -> None:
        path = write_file("l.csv", "name\nJosé\n".encode("latin-1"))
        frame = ct.peek(path, rows=5)
        assert "José" in frame.to_polars()["name"].to_list()

    def test_peek_works_on_gzip(self, write_file) -> None:
        path = write_file("c.csv.gz", gzip.compress(_many_rows(100).encode()))
        frame = ct.peek(path, rows=5)
        assert frame.shape[0] == 5

    def test_peek_does_not_read_whole_file(self, write_file, monkeypatch) -> None:
        # Previewing must read a bounded prefix, not slurp the entire file.
        path = write_file("big.csv", _many_rows(200_000))
        limits: list[int | None] = []
        original = detect.read_bytes

        def spy(filepath, limit=None):  # type: ignore[no-untyped-def]
            limits.append(limit)
            return original(filepath, limit)

        monkeypatch.setattr(detect, "read_bytes", spy)
        frame = ct.peek(path, rows=5)
        assert frame.shape[0] == 5
        assert None not in limits  # never requested the whole file
        assert max(limit for limit in limits if limit is not None) <= 262144


class TestInfo:
    def test_reports_dimensions(self, write_file) -> None:
        path = write_file("big.csv", _many_rows(200))
        summary = ct.info(path)
        assert summary["columns"] == 2
        assert summary["estimated_rows"] > 0
        assert summary["compression"] is None

    def test_reports_gzip_compression(self, write_file) -> None:
        path = write_file("c.csv.gz", gzip.compress(_many_rows(50).encode()))
        summary = ct.info(path)
        assert summary["compression"] == "gzip"


class TestStream:
    def test_chunks_cover_all_rows(self, write_file) -> None:
        path = write_file("big.csv", _many_rows(250))
        chunks = list(ct.stream(path, chunk_size=100))
        assert len(chunks) >= 2
        assert sum(len(c) for c in chunks) == 250

    def test_stream_types_match_read(self, write_file) -> None:
        path = write_file("nums.csv", _many_rows(120))
        full = ct.read(path)
        chunk = next(ct.stream(path, chunk_size=50))
        assert chunk.to_polars().dtypes == full.to_polars().dtypes
