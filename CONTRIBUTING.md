# Contributing

Thanks for your interest in csvtriage.

## Development setup

```bash
git clone https://github.com/Burton-David/csvtriage
cd csvtriage
make install          # creates .venv and installs the package with dev extras
```

## The quality gate

Every change must pass the full gate before it is merged:

```bash
make check            # black --check, ruff, mypy, and pytest
```

Individually: `make fmt` (format), `make lint`, `make type`, `make test`.

## Conventions

- **Python 3.10+**, fully type-annotated; `mypy` runs clean.
- **black** (line length 88) and **ruff** (`E,W,F,I,B,C4,UP,N`) are enforced.
- Google-style docstrings on public functions and classes.
- Every behavior change ships with tests; every bug fix ships with a regression
  test. Tests use real assertions and unique names, and read fixtures from
  `test_data/` via the `conftest.py` fixtures (never bare relative paths).
- **No silent data loss:** anything dropped or altered during a read must be
  recorded on the `ReadReport`. No bare `except:`.

## Commits and pull requests

- [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`,
  `refactor:`, `test:`, `docs:`, `chore:`. Imperative mood, no trailing period.
- One logical change per pull request, with CI green.

See [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) for the product vision and
roadmap.
