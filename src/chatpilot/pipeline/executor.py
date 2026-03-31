"""PipelineExecutor — executes a chain of pipeline nodes."""

from __future__ import annotations

import logging
import time

from chatpilot.core.errors import PipelineError
from chatpilot.core.types import NodeOutput, TaskInfo
from chatpilot.pipeline.node import PipelineNode

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 10


class PipelineDefinition:
    """Base class for pipeline definitions."""

    name: str = ""
    nodes: list[PipelineNode]
    max_iterations: int = 1

    def should_continue(self, iteration: int, last_output: NodeOutput) -> bool:
        return iteration < self.max_iterations and last_output.status == "success"


class PipelineExecutor:
    """Executes pipelines by their name."""

    def __init__(self) -> None:
        self._pipelines: dict[str, PipelineDefinition] = {}

    def register(self, pipeline: PipelineDefinition) -> None:
        self._pipelines[pipeline.name] = pipeline
        logger.info("Registered pipeline: %s", pipeline.name)

    async def execute(self, task: TaskInfo) -> NodeOutput:
        """Execute the complete pipeline for a task."""
        pipeline = self._pipelines.get(task.pipeline_name)
        if pipeline is None:
            raise PipelineError(f"Pipeline '{task.pipeline_name}' not found")

        current_input = self._with_task_context(task, task.input_data)
        last_output = NodeOutput(status="success", data=current_input)
        iteration = 0

        while True:
            for node in pipeline.nodes:
                start = time.monotonic()
                try:
                    last_output = await node.execute(current_input)
                except Exception as e:
                    logger.error("Node '%s' failed: %s", node.name, e)
                    last_output = NodeOutput(
                        status="error", data={}, error=str(e)
                    )

                duration_ms = int((time.monotonic() - start) * 1000)
                logger.info(
                    "Pipeline=%s node=%s status=%s duration=%dms",
                    task.pipeline_name, node.name, last_output.status, duration_ms,
                )

                if last_output.status == "error":
                    return last_output

                if isinstance(last_output.data, dict):
                    current_input = self._with_task_context(
                        task, last_output.data
                    )
                else:
                    current_input = self._with_task_context(
                        task, {"data": last_output.data}
                    )

            iteration += 1
            if not pipeline.should_continue(iteration, last_output):
                break

            if iteration >= DEFAULT_MAX_ITERATIONS:
                logger.warning("Pipeline '%s' hit max iterations", task.pipeline_name)
                break

        return last_output

    @staticmethod
    def _with_task_context(task: TaskInfo, data: dict) -> dict:
        """Inject canonical task context into pipeline node input."""
        enriched = dict(data)
        enriched["route_id"] = task.chat_route_id
        return enriched
