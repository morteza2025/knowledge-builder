#!/usr/bin/env python3

from app.core.settings import settings
from app.interfaces.telegram.application import run_bot


def main() -> None:
    run_bot(settings)


if __name__ == "__main__":
    main()
