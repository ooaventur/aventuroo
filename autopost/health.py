"""Helpers for writing autopost health heartbeat files."""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Iterable, Sequence

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEALTH_DIR = ROOT / "_health"

__all__ = ["HealthReport", "HEALTH_DIR"]


def _utc_now_iso() -> str:
    """Return a second-precision UTC timestamp with a ``Z`` suffix."""

    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _coerce_errors(messages: Sequence[str], *, limit: int = 20) -> list[str]:
    """Clean and deduplicate error strings while preserving order."""

    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in messages:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _load_existing(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


class HealthReport:
    """Accumulate run errors and persist them to ``_health/<name>.json``."""

    def __init__(self, name: str, *, health_dir: pathlib.Path | None = None) -> None:
        self.name = name
        self.health_dir = health_dir or HEALTH_DIR
        self.errors: list[str] = []
        self._items_override: int | None = None

    # Public API ---------------------------------------------------------
    def record_error(self, message: str) -> None:
        text = str(message or "").strip()
        if text:
            self.errors.append(text)

    def extend_errors(self, messages: Iterable[str]) -> None:
        for message in messages:
            self.record_error(str(message))

    def set_items_published(self, value: int | None) -> None:
        if value is None:
            self._items_override = None
        else:
            try:
                coerced = int(value)
            except (TypeError, ValueError):
                coerced = 0
            self._items_override = max(0, coerced)

    def write(self, *, items_published: int | None = None) -> pathlib.Path:
        if items_published is not None:
            self.set_items_published(items_published)

        path = self.health_dir / f"{self.name}.json"
        existing = _load_existing(path)

        if self._items_override is not None:
            items_value = self._items_override
        else:
            existing_value = existing.get("items_published")
            try:
                items_value = int(existing_value)
            except (TypeError, ValueError):
                items_value = 0
            items_value = max(0, items_value)

        payload = {
            "last_run": _utc_now_iso(),
            "items_published": items_value,
            "errors": _coerce_errors(self.errors),
        }

        self.health_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path
