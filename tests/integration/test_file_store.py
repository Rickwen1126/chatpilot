"""Integration tests for the SQLite-backed file store."""

from __future__ import annotations

from pathlib import Path

import pytest

from chatpilot.files.center import FileHandleCenter
from chatpilot.files.models import (
    CanonicalFileHandle,
    FileKind,
    RetentionClass,
    SourceHandleInput,
)
from chatpilot.files.store import SqliteFileStore


@pytest.mark.asyncio
async def test_file_store_crud_relations_and_notes(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()

    source = SourceHandleInput(
        route_id="line:webric:C123",
        platform="line:webric",
        kind=FileKind.file,
        native_locator="native-123",
        filename="report.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    handle = CanonicalFileHandle.from_source("file-123", source)

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    await store.create_file(
        handle,
        created_at=now,
        expires_at=None,
        retention_class=RetentionClass.default,
    )
    await store.add_relation(
        from_file_id=handle.file_id,
        relation_type="attached_to_route",
        subject_type="route",
        subject_id=handle.route_id,
    )
    await store.add_note(
        file_id=handle.file_id,
        note_type="summary",
        content="這是摘要",
        created_by="test",
    )

    stored = await store.get_file(handle.file_id)
    relations = await store.list_relations(from_file_id=handle.file_id)
    notes = await store.list_notes(handle.file_id)

    assert stored["source_platform"] == "line:webric"
    assert stored["retention_class"] == "default"
    assert relations[0]["relation_type"] == "attached_to_route"
    assert relations[0]["subject_id"] == "line:webric:C123"
    assert notes[0]["note_type"] == "summary"
    assert notes[0]["content"] == "這是摘要"

    await store.close()


@pytest.mark.asyncio
async def test_generated_file_registration_lineage_and_notes(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    center = FileHandleCenter(
        store,
        {},
        asset_root=tmp_path / "assets",
    )

    source = await center.register_bytes_file(
        route_id="line:webric:C456",
        data=b"source-bytes",
        kind=FileKind.file,
        filename="source.xlsx",
        generated_by_tool="upload_bridge",
    )
    generated = await center.register_bytes_file(
        route_id="line:webric:C456",
        data=b"generated-bytes",
        kind=FileKind.file,
        filename="summary.xlsx",
        derived_from_file_id=source.file_id,
        generated_by_tool="document_edit",
    )
    await center.add_note(
        generated.file_id,
        note_type="summary",
        content="代理人已整理成出貨摘要",
        created_by="document-agent",
    )

    local_path = await center.ensure_local(generated.file_id)
    stored = await store.get_file(generated.file_id)
    relations = await store.list_relations(from_file_id=generated.file_id)
    notes = await store.list_notes(generated.file_id)

    assert Path(local_path).read_bytes() == b"generated-bytes"
    assert stored["source_filename"] == "summary.xlsx"
    assert {relation["relation_type"] for relation in relations} == {
        "derived_from",
        "generated_by_tool",
    }
    assert notes[0]["content"] == "代理人已整理成出貨摘要"

    await store.close()
