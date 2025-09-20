#!/usr/bin/env python3
"""Run the shared autoposter for the Culture & Arts taxonomy."""

from __future__ import annotations

import importlib
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("FEEDS_FILE", str(ROOT / "feeds_cultute_arts.txt"))
os.environ.setdefault("CATEGORY", "Culture & Arts")

# Import after setting environment defaults so pull_news picks them up.
pull_news = importlib.import_module("autopost.pull_news")


def main() -> None:
    """Execute the Culture & Arts autoposter run."""

    pull_news.main()


if __name__ == "__main__":
    main()
