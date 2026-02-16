from __future__ import annotations

from typing import Callable

Messages = list[dict[str, str]]


def route_rewrite(
    messages: Messages,
    cloud_fn: Callable[[Messages], str],
    local_fn: Callable[[Messages], str],
    default_mode: str = "cloud",
    fallback: bool = True,
) -> str:
    if default_mode == "local":
        return local_fn(messages)

    try:
        return cloud_fn(messages)
    except Exception:
        if fallback:
            return local_fn(messages)
        raise
