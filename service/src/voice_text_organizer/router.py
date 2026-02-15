from __future__ import annotations

from typing import Callable


def route_rewrite(
    prompt: str,
    cloud_fn: Callable[[str], str],
    local_fn: Callable[[str], str],
    default_mode: str = "cloud",
    fallback: bool = True,
) -> str:
    if default_mode == "local":
        return local_fn(prompt)

    try:
        return cloud_fn(prompt)
    except Exception:
        if fallback:
            return local_fn(prompt)
        raise
