#!/usr/bin/env python3
"""Orchestrate the AventurOO autopost ingestion pipeline.

The GitHub Actions workflow expects to invoke ``python scripts/your_autopost_pipeline.py``
so this module wires the individual autopost entry points together.  The
implementation keeps the pipeline configuration in one place while providing a
couple of niceties for local development such as listing the registered steps
and running only a subset of them.

Example usages::

    # Execute the full ingestion pipeline (default behaviour)
    python scripts/your_autopost_pipeline.py

    # Run a single category when testing locally
    python scripts/your_autopost_pipeline.py --only tech-ai

    # Inspect the available steps without executing anything
    python scripts/your_autopost_pipeline.py --list

The script intentionally shells out to the existing entry points rather than
importing them.  This mirrors how the GitHub workflow executes the utilities and
avoids surprises around module level side effects or environment variable
handling performed by the individual scripts.
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import subprocess
import sys
from typing import Iterable, Sequence

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


@dataclasses.dataclass(frozen=True)
class PipelineStep:
    """Metadata describing a single pipeline step."""

    name: str
    description: str
    command: Sequence[str]


def _default_steps(python: str) -> list[PipelineStep]:
    """Return the default set of pipeline steps executed in order."""

    def _cmd(script: str, *extra: str) -> tuple[str, ...]:
        path = PROJECT_ROOT / script
        return (python, str(path), *extra)

    return [
        PipelineStep(
            name="news",
            description="Ingest general news feeds",
            command=_cmd("autopost/pull_news.py"),
        ),
        PipelineStep(
            name="tech-ai",
            description="Ingest Tech & AI feeds",
            command=_cmd("autopost/pull_tech_ai.py"),
        ),
        PipelineStep(
            name="crypto",
            description="Ingest Crypto feeds",
            command=_cmd("autopost/pull_crypto.py"),
        ),
        PipelineStep(
            name="entertainment",
            description="Ingest Entertainment feeds",
            command=_cmd("autopost/pull_entertainment.py"),
        ),
        PipelineStep(
            name="lifestyle",
            description="Ingest Lifestyle feeds",
            command=_cmd("autopost/pull_lifestyle.py"),
        ),
        PipelineStep(
            name="food-drink",
            description="Ingest Food & Drink feeds",
            command=_cmd("autopost/pull_food_drink.py"),
        ),
        PipelineStep(
            name="travel",
            description="Ingest Travel feeds",
            command=_cmd("autopost/pull_travel.py"),
        ),
        PipelineStep(
            name="culture-arts",
            description="Ingest Culture & Arts feeds",
            command=_cmd("autopost/pull_cultute_arts.py"),
        ),
        PipelineStep(
            name="rotate-hot",
            description="Rotate hot shards into the archive",
            command=_cmd("scripts/rotate_hot_to_archive.py"),
        ),
    ]


def _parse_args(step_names: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the configured steps and exit",
    )
    parser.add_argument(
        "--only",
        action="append",
        dest="only",
        metavar="STEP",
        help="Restrict execution to the given step name (can be specified multiple times)",
    )
    parser.add_argument(
        "--skip",
        action="append",
        dest="skip",
        metavar="STEP",
        help="Skip the given step (can be specified multiple times)",
    )
    parser.add_argument(
        "--python",
        dest="python",
        default=sys.executable,
        help="Interpreter used when spawning steps (defaults to the current executable)",
    )
    args = parser.parse_args()

    known = set(step_names)
    for attr in ("only", "skip"):
        values = getattr(args, attr)
        if not values:
            continue
        unknown = sorted(set(values) - known)
        if unknown:
            parser.error(
                f"Unknown step(s) for --{attr.replace('_', '-')}: {', '.join(unknown)}"
            )

    return args


def _filter_steps(
    steps: Sequence[PipelineStep],
    *,
    only: Iterable[str] | None,
    skip: Iterable[str] | None,
) -> list[PipelineStep]:
    selected = list(steps)
    if only:
        allowed = set(only)
        selected = [step for step in selected if step.name in allowed]
    if skip:
        excluded = set(skip)
        selected = [step for step in selected if step.name not in excluded]
    return selected


def _run_step(step: PipelineStep) -> None:
    print(f"\n==> [{step.name}] {step.description}")
    print("   $", " ".join(step.command))
    result = subprocess.run(step.command, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    base_steps = _default_steps(sys.executable)
    args = _parse_args(step.name for step in base_steps)

    if args.python != sys.executable:
        base_steps = _default_steps(args.python)

    if args.list:
        print("Configured autopost pipeline steps:")
        for step in base_steps:
            print(f" - {step.name:12s} : {step.description}")
        return 0

    steps = _filter_steps(base_steps, only=args.only, skip=args.skip)

    if not steps:
        print("No steps selected. Nothing to do.")
        return 0

    for step in steps:
        _run_step(step)

    print("\nAutopost pipeline completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
