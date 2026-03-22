# Contract: Pipeline Protocol

**對應 FR**: FR-023 ~ FR-028

## PipelineNode Protocol

```python
class PipelineNode(Protocol):
    """Pipeline 內的單一執行單元。"""

    @property
    def name(self) -> str:
        """Node 名稱（pipeline 內唯一）。"""
        ...

    async def execute(self, input: dict) -> NodeOutput:
        """執行 node 邏輯。

        Args:
            input: 上一個 node 的 output.data（第一個 node 收到 task input）
        Returns:
            NodeOutput with status + data
        """
        ...
```

## PipelineExecutor

```python
class PipelineExecutor:
    """Pipeline 執行引擎。按定義的 node chain 依序執行。"""

    async def execute(self, task: TaskInfo) -> NodeOutput:
        """執行完整 pipeline。

        流程：
        1. 根據 task.pipeline_name 找到對應的 pipeline 定義
        2. 依序執行 node chain：node_1 → node_2 → ... → node_n
        3. 每個 node 的 output.data 作為下一個 node 的 input
        4. 自動注入 metadata（duration_ms, node_name）
        5. 任一 node status="error" → 中止 pipeline，回傳該 node 的 error

        Args:
            task: 任務資訊（含 input_data 和 pipeline_name）
        Returns:
            最終 node 的 NodeOutput
        """
        ...
```

## Pipeline 定義（code-based）

```python
# 範例：inventory-report pipeline
class InventoryReportPipeline:
    """庫存報告 pipeline。"""

    name = "inventory-report"

    def __init__(self, tool_factory: ToolFactory):
        self.nodes = [
            DataCollectorNode(tool_factory),
            AnalyzerNode(tool_factory),
            ReporterNode(tool_factory),
        ]

    # 可選：迴圈 pipeline
    max_iterations: int = 3

    def should_continue(self, context: PipelineContext) -> bool:
        return (
            context.iteration < self.max_iterations
            and context.last_output.status == "success"
        )
```

## SDK Session Node（使用 LLM 的 node）

```python
class SdkSessionNode(PipelineNode):
    """需要 LLM 能力的 pipeline node。

    建立獨立 SDK session，使用 ToolFactory 取得允許的 tools。
    """

    def __init__(
        self,
        name: str,
        agent_config: AgentConfig,
        tool_factory: ToolFactory,
    ):
        self._name = name
        self._config = agent_config
        self._tools = tool_factory.get_tools_for_pipeline(agent_config.tools)

    async def execute(self, input: dict) -> NodeOutput:
        """
        1. 建立 SDK session（model, system_message, tools from config）
        2. send_and_wait(input as prompt)
        3. 回傳 NodeOutput
        4. destroy session
        """
        ...
```

## Memory Tool

```python
class MemoryTool:
    """跨 node 脈絡保留。Pipeline 內的 node 可透過此 tool 讀寫共享記憶。

    每個 task 有獨立的 memory space，互不干擾。
    """

    async def get(self, task_id: str, key: str) -> Any: ...
    async def set(self, task_id: str, key: str, value: Any) -> None: ...
    async def list_keys(self, task_id: str) -> list[str]: ...
    async def delete(self, task_id: str, key: str) -> None: ...
```

## 行為約束

- Pipeline 是 code-defined，不可由使用者任意組合
- Node 間資料傳遞 MUST 為 JSON object
- 每個 SDK session node MUST 建立獨立 session
- SDK session node 的 tools MUST 從 ToolFactory 取得
- Agent team tool MUST NOT 出現在 pipeline agent 的 tool 清單中
- 含迴圈的 pipeline MUST 有 `max_iterations` 安全閥（預設 10）
- Memory Tool 每個 task 獨立 namespace
