"""PipelineNode Protocol — single execution unit in a pipeline."""

from __future__ import annotations

from typing import Protocol

from chatpilot.core.types import NodeOutput


class PipelineNode(Protocol):
    """Pipeline execution unit."""

    @property
    def name(self) -> str: ...

    async def execute(self, input: dict) -> NodeOutput: ...
