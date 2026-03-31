"""Legacy ref parsing helpers during FileHandleCenter migration."""

from __future__ import annotations

from typing import Any, Mapping


def parse_media_ref(ref: str, adapters: Mapping[str, Any]) -> tuple[str, str, str | None]:
    """Parse legacy media ref into (platform, native_locator, filename?)."""
    for platform in sorted(adapters.keys(), key=len, reverse=True):
        prefix = f"{platform}:"
        if not ref.startswith(prefix):
            continue
        remainder = ref[len(prefix):]
        if not remainder:
            break
        if ":" in remainder:
            native_locator, filename = remainder.split(":", 1)
        else:
            native_locator, filename = remainder, None
        return platform, native_locator, filename

    parts = ref.split(":", 2)
    if len(parts) < 2:
        raise ValueError(f"無效的 ref 格式: {ref}（應為 platform:media_id）")
    platform = parts[0]
    native_locator = parts[1]
    filename = parts[2] if len(parts) == 3 else None
    return platform, native_locator, filename
