"""Remember the last successful API payload so a later outage does not stop the app.

Only validated real responses are stored. Failures are stored separately and are
never rendered as observations.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from magic_town.errors import FetchError

REQUIRED_RECORD_KEYS = (
    "fetched_at",
    "fetched_at_epoch",
    "source_name",
    "source_url",
    "payload",
)


def cache_dir() -> Path:
    override = os.environ.get("MAGIC_TOWN_CACHE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / ".cache"


@dataclass
class LoadResult:
    ok: bool
    state: str
    record: dict | None = None
    error_code: str | None = None
    error_detail: str | None = None
    refresh_in_seconds: int | None = None
    retry_in_seconds: int | None = None


def load_live(
    name: str,
    fetcher: Callable[[], dict],
    validator: Callable[[dict], None],
    *,
    force: bool = False,
    ttl_seconds: int = 600,
    retry_seconds: int = 60,
) -> LoadResult:
    """Serve a fresh cache hit, a new fetch, or the last real fetch after an error."""
    cached = _read_record(name, validator)
    now = time.time()

    if cached and not force:
        age = now - float(cached["fetched_at_epoch"])
        if 0 <= age < ttl_seconds:
            return LoadResult(
                ok=True,
                state="cached",
                record=cached,
                refresh_in_seconds=int(ttl_seconds - age),
            )

    failure = None if force else _read_failure(name)
    if failure is not None:
        elapsed = now - float(failure["attempted_at_epoch"])
        if 0 <= elapsed < retry_seconds:
            wait = int(retry_seconds - elapsed)
            if cached:
                return LoadResult(
                    ok=True,
                    state="stale",
                    record=cached,
                    error_code=failure["code"],
                    error_detail=failure["detail"],
                    retry_in_seconds=wait,
                )
            return LoadResult(
                ok=False,
                state="error",
                error_code=failure["code"],
                error_detail=failure["detail"],
                retry_in_seconds=wait,
            )

    try:
        record = fetcher()
        _require_record(record)
        validator(record["payload"])
    except FetchError as exc:
        _write_failure(name, exc)
        if cached:
            return LoadResult(
                ok=True,
                state="stale",
                record=cached,
                error_code=exc.code,
                error_detail=exc.detail,
                retry_in_seconds=retry_seconds,
            )
        return LoadResult(
            ok=False,
            state="error",
            error_code=exc.code,
            error_detail=exc.detail,
            retry_in_seconds=retry_seconds,
        )
    except Exception as exc:
        wrapped = FetchError("unexpected", f"{type(exc).__name__}: {exc}")
        _write_failure(name, wrapped)
        if cached:
            return LoadResult(
                ok=True,
                state="stale",
                record=cached,
                error_code=wrapped.code,
                error_detail=wrapped.detail,
                retry_in_seconds=retry_seconds,
            )
        return LoadResult(
            ok=False,
            state="error",
            error_code=wrapped.code,
            error_detail=wrapped.detail,
            retry_in_seconds=retry_seconds,
        )

    _write_record(name, record)
    _clear_failure(name)
    return LoadResult(ok=True, state="fetched", record=record, refresh_in_seconds=ttl_seconds)


def _require_record(record: dict) -> None:
    if not isinstance(record, dict):
        raise FetchError("shape", "fetcher did not return an object")
    missing = [key for key in REQUIRED_RECORD_KEYS if key not in record]
    if missing:
        raise FetchError("shape", "record missing " + ", ".join(missing))
    if not isinstance(record["fetched_at"], str) or not record["fetched_at"]:
        raise FetchError("shape", "fetched_at is empty")
    if not isinstance(record["fetched_at_epoch"], (int, float)):
        raise FetchError("shape", "fetched_at_epoch is not a number")
    if not isinstance(record["source_name"], str) or not record["source_name"]:
        raise FetchError("shape", "source_name is empty")
    if not isinstance(record["source_url"], str) or not record["source_url"].startswith("https://"):
        raise FetchError("shape", "source_url must be https")
    if not isinstance(record["payload"], dict):
        raise FetchError("shape", "payload is not an object")


def _read_record(name: str, validator: Callable[[dict], None]) -> dict | None:
    path = cache_dir() / f"{name}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        _require_record(record)
        validator(record["payload"])
    except (OSError, json.JSONDecodeError, FetchError, TypeError, ValueError):
        return None
    return record


def _write_record(name: str, record: dict) -> None:
    _write_json(cache_dir() / f"{name}.json", record)


def _read_failure(name: str) -> dict | None:
    path = cache_dir() / f"{name}.error.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("code"), str) or not isinstance(data.get("detail"), str):
        return None
    if not isinstance(data.get("attempted_at_epoch"), (int, float)):
        return None
    return data


def _write_failure(name: str, exc: FetchError) -> None:
    _write_json(
        cache_dir() / f"{name}.error.json",
        {
            "code": exc.code,
            "detail": exc.detail,
            "attempted_at_epoch": time.time(),
        },
    )


def _clear_failure(name: str) -> None:
    path = cache_dir() / f"{name}.error.json"
    try:
        path.unlink()
    except OSError:
        return


def _write_json(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        return
