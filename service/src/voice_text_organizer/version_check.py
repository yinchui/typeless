from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any

import httpx


DEFAULT_RELEASES_API = "https://api.github.com/repos/yinchui/typeless/releases/latest"
DEFAULT_RELEASES_URL = "https://github.com/yinchui/typeless/releases"
CACHE_TTL = timedelta(hours=24)


def _normalize_version(value: str) -> str:
    return value.strip().lstrip("vV")


def _version_key(value: str) -> tuple[int, ...]:
    normalized = _normalize_version(value)
    parts = normalized.split(".")
    key: list[int] = []
    for part in parts:
        match = re.match(r"(\d+)", part)
        key.append(int(match.group(1)) if match else 0)
    while len(key) < 3:
        key.append(0)
    return tuple(key[:3])


def has_newer_version(current_version: str, latest_version: str) -> bool:
    try:
        return _version_key(latest_version) > _version_key(current_version)
    except Exception:
        return _normalize_version(latest_version) != _normalize_version(current_version)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _format_iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class VersionCheckResult:
    current_version: str
    latest_version: str
    has_update: bool
    release_url: str
    checked_at: str
    cache_payload: dict[str, str]


def resolve_version(
    *,
    current_version: str,
    runtime_settings: dict[str, Any],
    releases_api: str = DEFAULT_RELEASES_API,
    releases_url: str = DEFAULT_RELEASES_URL,
) -> VersionCheckResult:
    now = datetime.now(timezone.utc)
    cached_checked_at = _parse_iso_datetime(runtime_settings.get("last_update_check_at"))
    cached_latest = str(runtime_settings.get("last_release_version") or "").strip()
    cached_release_url = str(runtime_settings.get("last_release_url") or "").strip() or releases_url

    if cached_checked_at and cached_latest and (now - cached_checked_at) < CACHE_TTL:
        latest = _normalize_version(cached_latest)
        checked = _format_iso_datetime(cached_checked_at)
        return VersionCheckResult(
            current_version=_normalize_version(current_version),
            latest_version=latest,
            has_update=has_newer_version(current_version, latest),
            release_url=cached_release_url,
            checked_at=checked,
            cache_payload={
                "last_update_check_at": checked,
                "last_release_version": latest,
                "last_release_url": cached_release_url,
            },
        )

    latest_version = _normalize_version(current_version)
    latest_release_url = releases_url
    checked_at = _format_iso_datetime(now)

    try:
        response = httpx.get(
            releases_api,
            headers={"Accept": "application/vnd.github+json"},
            timeout=8.0,
        )
        response.raise_for_status()
        payload = response.json()
        latest_version = _normalize_version(
            str(payload.get("tag_name") or payload.get("name") or current_version)
        )
        latest_release_url = str(payload.get("html_url") or releases_url)
    except Exception:
        pass

    return VersionCheckResult(
        current_version=_normalize_version(current_version),
        latest_version=latest_version,
        has_update=has_newer_version(current_version, latest_version),
        release_url=latest_release_url,
        checked_at=checked_at,
        cache_payload={
            "last_update_check_at": checked_at,
            "last_release_version": latest_version,
            "last_release_url": latest_release_url,
        },
    )
