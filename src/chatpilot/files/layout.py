"""Filesystem layout helpers for file assets."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FILE_ASSET_ROOT = Path("data/file_assets")
_SAFE_SEGMENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class FileAssetPaths:
    root: Path
    file_dir: Path
    source_path: Path
    meta_path: Path
    derived_dir: Path


def build_route_partition(route_id: str) -> str:
    """Build a readable but filesystem-safe partition key for a route."""
    readable = _SAFE_SEGMENT_PATTERN.sub("_", route_id).strip("_") or "route"
    readable = readable[:80]
    digest = hashlib.sha1(route_id.encode("utf-8")).hexdigest()[:8]
    return f"{readable}__{digest}"


def build_asset_paths(
    route_id: str,
    file_id: str,
    *,
    root: str | Path | None = None,
) -> FileAssetPaths:
    asset_root = Path(root) if root is not None else DEFAULT_FILE_ASSET_ROOT
    file_dir = asset_root / build_route_partition(route_id) / file_id
    return FileAssetPaths(
        root=asset_root,
        file_dir=file_dir,
        source_path=file_dir / "source.bin",
        meta_path=file_dir / "meta.json",
        derived_dir=file_dir / "derived",
    )


def ensure_asset_dirs(paths: FileAssetPaths) -> None:
    paths.file_dir.mkdir(parents=True, exist_ok=True)
    paths.derived_dir.mkdir(parents=True, exist_ok=True)
