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


def _coerce_non_negative_int(value, *, default: int | None = 0) -> int | None:
    """Return ``value`` coerced to a non-negative ``int`` or ``default``."""

    if value is None:
        return default

    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default

    return max(0, coerced)


class HealthReport:
    """Accumulate run errors and persist them to ``_health/<name>.json``."""

    def __init__(self, name: str, *, health_dir: pathlib.Path | None = None) -> None:
        self.name = name
        self.health_dir = health_dir or HEALTH_DIR
        self.errors: list[str] = []
        self._feeds_override: int | None = None
        self._items_override: int | None = None
        self._last_fetch_override: str | None = None

    # Public API ---------------------------------------------------------
    def record_error(self, message: str) -> None:
        text = str(message or "").strip()
        if text:
            self.errors.append(text)

    def extend_errors(self, messages: Iterable[str]) -> None:
        for message in messages:
            self.record_error(str(message))

    def set_feeds_count(self, value: int | None) -> None:
        self._feeds_override = _coerce_non_negative_int(value, default=None)

    def set_items_ingested(self, value: int | None) -> None:
        self._items_override = _coerce_non_negative_int(value, default=None)

    def set_last_fetch(self, value: str | None) -> None:
        text = str(value or "").strip()
        self._last_fetch_override = text or None

    @property
    def has_errors(self) -> bool:
        return bool(_coerce_errors(self.errors))

    def write(
        self,
        *,
        feeds_count: int | None = None,
        items_ingested: int | None = None,
        last_fetch: str | None = None,
    ) -> pathlib.Path:
        if feeds_count is not None:
            self.set_feeds_count(feeds_count)
        if items_ingested is not None:
            self.set_items_ingested(items_ingested)
        if last_fetch is not None:
            self.set_last_fetch(last_fetch)

        path = self.health_dir / f"{self.name}.json"
        existing = _load_existing(path)

        feeds_value = self._feeds_override
        if feeds_value is None:
            feeds_value = _coerce_non_negative_int(existing.get("feeds_count"), default=0)
        if feeds_value is None:
            feeds_value = 0

        existing_items = existing.get("items_ingested")
        if existing_items is None:
            existing_items = existing.get("items_published")
        items_value = self._items_override
        if items_value is None:
            items_value = _coerce_non_negative_int(existing_items, default=0)
        if items_value is None:
            items_value = 0

        last_fetch_value = self._last_fetch_override or _utc_now_iso()

        payload = {
            "last_fetch": last_fetch_value,
            "feeds_count": feeds_value,
            "items_ingested": items_value,
            "errors": _coerce_errors(self.errors),
        }

        self.health_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path
