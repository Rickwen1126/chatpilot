"""Echo pipeline — simple pipeline for framework validation."""

from __future__ import annotations

from chatpilot.core.types import NodeOutput
from chatpilot.pipeline.executor import PipelineDefinition
from chatpilot.pipeline.node import PipelineNode


class EchoNode:
    """Echoes input back as output."""

    @property
    def name(self) -> str:
        return "echo"

    async def execute(self, input: dict) -> NodeOutput:
        return NodeOutput(
            status="success",
            data={"echo": input},
        )


class EchoPipeline(PipelineDefinition):
    """Sample pipeline: echoes input for testing."""

    name = "echo"

    def __init__(self) -> None:
        self.nodes: list[PipelineNode] = [EchoNode()]
        self.max_iterations = 1
