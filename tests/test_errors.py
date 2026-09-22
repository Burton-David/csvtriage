"""Tests for the public exception surface."""

import csvtriage as ct


def test_every_exported_error_is_one_the_library_raises() -> None:
    # DelimiterError and FileTooLargeError were exported for a while with no code
    # path raising them. Adding an error class here should come with the raise.
    exported = {
        name
        for name in ct.__all__
        if isinstance(getattr(ct, name), type)
        and issubclass(getattr(ct, name), Exception)
    }
    assert exported == {"CSVTriageError", "EncodingError", "ParseError"}


def test_library_errors_share_the_csvtriage_base() -> None:
    assert issubclass(ct.EncodingError, ct.CSVTriageError)
    assert issubclass(ct.ParseError, ct.CSVTriageError)
