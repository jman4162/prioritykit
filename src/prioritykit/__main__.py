"""Run the CLI with ``python -m prioritykit``, for when the console script is not on PATH."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
