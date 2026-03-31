"""Unit tests for FileHandleCenter models."""

from __future__ import annotations

import pytest

from chatpilot.files.models import (
    CanonicalFileHandle,
    FileKind,
    SourceFetchResult,
    SourceHandleInput,
)


def test_source_handle_requires_non_empty_native_locator():
    with pytest.raises(ValueError):
        SourceHandleInput(
            route_id="line:webric:C123",
            platform="line:webric",
            kind=FileKind.image,
            native_locator="",
        )


def test_canonical_handle_can_be_built_from_source():
    source = SourceHandleInput(
        route_id="line:webric:C123",
        platform="line:webric",
        kind=FileKind.image,
        native_locator="mid-123",
        filename="photo.jpg",
        mime_type="image/jpeg",
    )

    handle = CanonicalFileHandle.from_source("file-1", source)

    assert handle.file_id == "file-1"
    assert handle.route_id == source.route_id
    assert handle.platform == "line:webric"
    assert handle.filename == "photo.jpg"


def test_source_fetch_result_normalizes_size_bytes():
    result = SourceFetchResult(data=b"hello", filename="a.txt")

    assert result.normalized_size_bytes() == 5
