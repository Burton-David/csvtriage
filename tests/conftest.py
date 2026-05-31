"""Shared fixtures. Paths are anchored to this file so tests pass from any cwd."""

from collections.abc import Callable
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent.parent / "test_data"


@pytest.fixture
def data_dir() -> Path:
    """Directory holding the committed sample CSV files."""
    return DATA_DIR


@pytest.fixture
def write_file(tmp_path: Path) -> Callable[..., Path]:
    """Factory writing bytes or text to a temp file; returns the path."""

    def _write(name: str, content: str | bytes, *, encoding: str = "utf-8") -> Path:
        path = tmp_path / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding=encoding)
        return path

    return _write
