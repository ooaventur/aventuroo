#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run all autopost pullers and RSS-to-HTML converter sequentially."""
from . import pull_culture, pull_lifestyle, pull_stories, pull_travel, rss_to_html


def main() -> None:
    steps = [
        ("pull_culture", pull_culture.main),
        ("pull_lifestyle", pull_lifestyle.main),
        ("pull_stories", pull_stories.main),
        ("pull_travel", pull_travel.main),
        ("rss_to_html", rss_to_html.main),
    ]
    for name, func in steps:
        print(f"\n=== Running {name} ===")
        try:
            func()
        except Exception as exc:  # pragma: no cover - defensive
            print(f"{name} failed: {exc}")


if __name__ == "__main__":
    main()
