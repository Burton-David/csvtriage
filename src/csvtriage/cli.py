"""Command-line interface for csvtriage.

Commands return process exit codes that scripts can rely on: ``0`` on success,
``1`` when a file has issues worth flagging (e.g. ``validate`` finds quarantined
rows), and ``2`` on usage or runtime errors. Errors are reported on stderr with a
clear message rather than a raw traceback.
"""

import json
import sys
from typing import TextIO

import click

from . import __version__, info, peek, read
from .errors import CSVTriageError
from .frame import Frame


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="csvtriage")
def cli() -> None:
    """csvtriage — load messy CSVs and report exactly what happened."""


@cli.command(name="info")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--json", "as_json", is_flag=True, help="Emit the summary as JSON.")
def info_command(file: str, as_json: bool) -> None:
    """Summarize a file (encoding, delimiter, size, estimated rows)."""
    summary = info(file)
    if as_json:
        click.echo(json.dumps(summary, indent=2))
    else:
        for key, value in summary.items():
            click.echo(f"{key:>20}: {value}")


@cli.command(name="peek")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("-n", "--rows", default=10, show_default=True, help="Rows to preview.")
def peek_command(file: str, rows: int) -> None:
    """Preview the first rows of a file without loading all of it."""
    frame = peek(file, rows=rows)
    click.echo(str(frame))


@cli.command(name="convert")
@click.argument("source", type=click.Path(exists=True, dir_okay=False))
@click.argument("destination", type=click.Path(dir_okay=False))
@click.option("--robust", is_flag=True, help="Use line-level recovery.")
@click.option(
    "--report",
    "report_format",
    type=click.Choice(["text", "json", "none"]),
    default="text",
    show_default=True,
    help="How to print the read report (to stderr).",
)
def convert_command(
    source: str, destination: str, robust: bool, report_format: str
) -> None:
    """Read SOURCE and write it to DESTINATION (.csv or .parquet)."""
    frame = read(source, robust=robust, on_bad_lines="skip")
    if destination.endswith(".parquet"):
        frame.write_parquet(destination)
    elif destination.endswith(".csv"):
        frame.write_csv(destination)
    else:
        raise click.ClickException("destination must end in .csv or .parquet")
    _emit_report(frame, report_format)


@cli.command(name="clean")
@click.argument("source", type=click.Path(exists=True, dir_okay=False))
@click.argument("destination", type=click.Path(dir_okay=False))
@click.option("--robust", is_flag=True, help="Use line-level recovery.")
@click.option(
    "--report",
    "report_format",
    type=click.Choice(["text", "json", "none"]),
    default="text",
    show_default=True,
    help="How to print the read report (to stderr).",
)
def clean_command(
    source: str, destination: str, robust: bool, report_format: str
) -> None:
    """Read SOURCE, apply quick_clean, and write to DESTINATION (.csv/.parquet)."""
    frame = read(source, robust=robust, on_bad_lines="skip").clean()
    if destination.endswith(".parquet"):
        frame.write_parquet(destination)
    elif destination.endswith(".csv"):
        frame.write_csv(destination)
    else:
        raise click.ClickException("destination must end in .csv or .parquet")
    _emit_report(frame, report_format)


@cli.command(name="validate")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--report",
    "report_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def validate_command(file: str, report_format: str) -> None:
    """Read a file and exit non-zero if any rows had to be quarantined."""
    frame = read(file, robust=True, on_bad_lines="skip")
    _emit_report(frame, report_format, stream=sys.stdout)
    if frame.report.quarantined:
        raise SystemExit(1)


def _emit_report(
    frame: Frame, report_format: str, stream: TextIO | None = None
) -> None:
    if report_format == "none":
        return
    target = stream if stream is not None else sys.stderr
    report = frame.report
    text = report.to_json() if report_format == "json" else report.explain()
    click.echo(text, file=target)


def main() -> int:
    """Entry point. Returns a process exit code.

    Returns:
        ``0`` on success, ``1`` when a file has flagged issues, ``2`` on errors.
    """
    try:
        cli.main(standalone_mode=False)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 0
    except click.ClickException as exc:
        exc.show()
        return 2
    except CSVTriageError as exc:
        click.echo(f"error: {exc}", err=True)
        return 2
    except FileNotFoundError as exc:
        click.echo(f"error: {exc}", err=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
