"""Tests for dialect, encoding, and compression detection."""

import gzip

from csvtriage import detect


class TestEncodingDetection:
    def test_detects_utf8(self) -> None:
        encoding, confidence = detect.detect_encoding("café,price\n".encode())
        assert encoding in ("utf-8", "ascii")
        assert confidence > 0

    def test_detects_utf8_bom(self) -> None:
        encoding, confidence = detect.detect_encoding(b"\xef\xbb\xbfname,age\n")
        assert encoding == "utf-8-sig"
        assert confidence == 1.0

    def test_detects_utf16_le_bom(self) -> None:
        encoding, _ = detect.detect_encoding(b"\xff\xfename\x00")
        assert encoding == "utf-16-le"

    def test_falls_back_to_decodable_encoding(self) -> None:
        # Bytes that are not valid UTF-8 but decode under cp1252/latin-1.
        encoding, _ = detect.detect_encoding(("é" * 200).encode("latin-1"))
        assert encoding in ("cp1252", "latin-1")

    def test_does_not_collapse_iso_8859_2_to_latin1(self) -> None:
        # Regression: the old alias map silently mapped 8859-2 onto latin-1.
        assert detect._normalize_encoding("ISO-8859-2") == "iso-8859-2"


class TestDelimiterDetection:
    def test_detects_comma(self) -> None:
        delimiter, confidence = detect.detect_delimiter("a,b,c\n1,2,3\n4,5,6\n")
        assert delimiter == ","
        assert confidence > 0.5

    def test_detects_semicolon(self) -> None:
        delimiter, _ = detect.detect_delimiter("a;b;c\n1;2;3\n4;5;6\n")
        assert delimiter == ";"

    def test_detects_tab(self) -> None:
        delimiter, _ = detect.detect_delimiter("a\tb\tc\n1\t2\t3\n")
        assert delimiter == "\t"

    def test_defaults_to_comma_on_single_column(self) -> None:
        delimiter, confidence = detect.detect_delimiter("justonecolumn\nvalue\n")
        assert delimiter == ","
        assert confidence == 0.0


class TestQuoteAndHeader:
    def test_detects_double_quote(self) -> None:
        text = 'name,note\nAlice,"hi, there"\nBob,"x"\n'
        assert detect.detect_quote_char(text, ",") == '"'

    def test_header_present_when_first_row_is_labels(self) -> None:
        assert detect.detect_header("name,age\nAlice,30\nBob,25\n", ",") is True

    def test_header_absent_when_first_row_is_data(self) -> None:
        assert detect.detect_header("Alice,30\nBob,25\nCarol,40\n", ",") is False


class TestCompression:
    def test_detects_gzip_by_magic(self, write_file) -> None:
        path = write_file("x.bin", gzip.compress(b"a,b\n1,2\n"))
        assert detect.detect_compression(path) == "gzip"

    def test_none_for_plain_file(self, write_file) -> None:
        path = write_file("x.csv", "a,b\n1,2\n")
        assert detect.detect_compression(path) is None

    def test_read_bytes_transparently_decompresses(self, write_file) -> None:
        path = write_file("x.csv.gz", gzip.compress(b"a,b\n1,2\n"))
        assert detect.read_bytes(path) == b"a,b\n1,2\n"
