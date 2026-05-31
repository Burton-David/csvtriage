"""Tests for the command-line interface, especially exit codes."""

from click.testing import CliRunner

from csvtriage.cli import cli


def _run(args):
    return CliRunner().invoke(cli, args)


class TestInfoCommand:
    def test_info_succeeds(self, write_file) -> None:
        path = write_file("s.csv", "a,b\n1,2\n")
        result = _run(["info", str(path)])
        assert result.exit_code == 0
        assert "delimiter" in result.output

    def test_info_json(self, write_file) -> None:
        path = write_file("s.csv", "a,b\n1,2\n")
        result = _run(["info", str(path), "--json"])
        assert result.exit_code == 0
        assert '"columns": 2' in result.output


class TestValidateCommand:
    def test_clean_file_exits_zero(self, write_file) -> None:
        path = write_file("s.csv", "a,b\n1,2\n3,4\n")
        result = _run(["validate", str(path)])
        assert result.exit_code == 0

    def test_contaminated_file_exits_one(self, write_file) -> None:
        content = "a,b\n1,2\n<html>error</html>\n3,4\n"
        path = write_file("bad.csv", content)
        result = _run(["validate", str(path)])
        assert result.exit_code == 1
        assert "Quarantined" in result.output


class TestConvertCommand:
    def test_converts_to_parquet(self, write_file, tmp_path) -> None:
        path = write_file("s.csv", "a,b\n1,2\n")
        out = tmp_path / "out.parquet"
        result = _run(["convert", str(path), str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_rejects_unknown_extension(self, write_file, tmp_path) -> None:
        path = write_file("s.csv", "a,b\n1,2\n")
        result = _run(["convert", str(path), str(tmp_path / "out.txt")])
        assert result.exit_code != 0


class TestCleanCommand:
    def test_clean_writes_cleaned_output(self, write_file, tmp_path) -> None:
        import polars as pl

        path = write_file("s.csv", "Name ,b\n A ,2\n A ,2\n")
        out = tmp_path / "out.csv"
        result = _run(["clean", str(path), str(out)])
        assert result.exit_code == 0
        assert out.exists()
        cleaned = pl.read_csv(out)
        assert cleaned.columns == ["name", "b"]
        assert cleaned.height == 1

    def test_clean_rejects_unknown_extension(self, write_file, tmp_path) -> None:
        path = write_file("s.csv", "a,b\n1,2\n")
        result = _run(["clean", str(path), str(tmp_path / "out.txt")])
        assert result.exit_code != 0
