"""Tests for pipeline executor."""

import uuid
from datetime import datetime, timezone

import pytest

from chatpilot.core.types import NodeOutput, TaskInfo
from chatpilot.pipeline.executor import PipelineDefinition, PipelineExecutor
from chatpilot.pipeline.samples.echo import EchoPipeline


@pytest.fixture
def executor():
    e = PipelineExecutor()
    e.register(EchoPipeline())
    return e


def _task(pipeline="echo", input_data=None):
    return TaskInfo(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        pipeline_name=pipeline,
        input_summary="test",
        input_data=input_data or {"query": "hello"},
        chat_route_id="test:route",
    )


class _CaptureNode:
    name = "capture"

    def __init__(self) -> None:
        self.seen = None

    async def execute(self, input):
        self.seen = dict(input)
        return NodeOutput(status="success", data=input)


class _CapturePipeline(PipelineDefinition):
    name = "capture"

    def __init__(self, node):
        self.nodes = [node]
        self.max_iterations = 1


async def test_echo_pipeline(executor):
    result = await executor.execute(_task())
    assert result.status == "success"
    assert result.data["echo"]["query"] == "hello"


async def test_unknown_pipeline(executor):
    with pytest.raises(Exception, match="not found"):
        await executor.execute(_task("nonexistent"))


async def test_pipeline_executor_injects_canonical_route_id():
    executor = PipelineExecutor()
    node = _CaptureNode()
    executor.register(_CapturePipeline(node))

    result = await executor.execute(_task(
        "capture",
        input_data={"query": "hello", "route_id": "wrong:route"},
    ))

    assert result.status == "success"
    assert node.seen["route_id"] == "test:route"
    assert result.data["route_id"] == "test:route"
