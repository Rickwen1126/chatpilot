"""Tests for pipeline executor."""

import uuid
from datetime import datetime, timezone

import pytest

from chatpilot.core.types import TaskInfo
from chatpilot.pipeline.executor import PipelineExecutor
from chatpilot.pipeline.samples.echo import EchoPipeline


@pytest.fixture
def executor():
    e = PipelineExecutor()
    e.register(EchoPipeline())
    return e


def _task(pipeline="echo"):
    return TaskInfo(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        pipeline_name=pipeline,
        input_summary="test",
        input_data={"query": "hello"},
        chat_route_id="test:route",
    )


async def test_echo_pipeline(executor):
    result = await executor.execute(_task())
    assert result.status == "success"
    assert result.data["echo"]["query"] == "hello"


async def test_unknown_pipeline(executor):
    with pytest.raises(Exception, match="not found"):
        await executor.execute(_task("nonexistent"))
