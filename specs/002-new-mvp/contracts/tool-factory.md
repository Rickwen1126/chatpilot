# Contract: ToolFactory Protocol

**對應 FR**: FR-022 ~ FR-022d

## Protocol 定義

```python
class ToolFactory(Protocol):
    """中央 tool 註冊與產出中心。"""

    def register(self, definition: ToolDefinition) -> None:
        """註冊一個 tool。

        Args:
            definition: Tool 完整定義（名稱、描述、參數、handler、存取級別）
        Raises:
            ValueError: tool name 已存在
        """
        ...

    def get_tools_for_chatbot(self, tool_names: list[str]) -> list[ExternalTool]:
        """取得 chatbot session 可用的 tools。

        過濾規則：
        - 只回傳 access_level 為 global 或 chatbot_only 的 tool
        - 只回傳 tool_names 中列出的 tool

        Args:
            tool_names: chatbot config 中宣告的 tool 名稱清單
        Returns:
            SDK ExternalTool 列表（可直接傳入 session config）
        """
        ...

    def get_tools_for_pipeline(self, tool_names: list[str]) -> list[ExternalTool]:
        """取得 pipeline agent 可用的 tools。

        過濾規則：
        - 只回傳 access_level 為 global 或 agent_team_only 的 tool
        - 只回傳 tool_names 中列出的 tool
        - 硬約束：排除所有 agent team tool（防止遞迴呼叫）

        Args:
            tool_names: agent config 中宣告的 tool 名稱清單
        Returns:
            SDK ExternalTool 列表
        Raises:
            ValueError: 如果 tool_names 包含 agent team tool（遞迴嘗試）
        """
        ...

    def get_handler(self, tool_name: str) -> ToolHandler:
        """取得 tool 的執行 handler。

        Args:
            tool_name: tool 名稱
        Returns:
            Tool handler callable
        Raises:
            KeyError: tool 不存在
        """
        ...

    def is_agent_team_tool(self, tool_name: str) -> bool:
        """判斷是否為 agent team tool（會觸發 async task）。"""
        ...

    def list_tools(self) -> list[ToolDefinition]:
        """列出所有已註冊的 tool 定義。"""
        ...
```

## ExternalTool 格式

```python
# 對應 SDK 的 tool 定義格式
ExternalTool = TypedDict("ExternalTool", {
    "name": str,
    "description": str,
    "parameters": dict,  # JSON Schema
})
```

## Agent Team Tool 機制

Agent team tool 是特殊的 tool，呼叫時不直接執行，
而是將任務送入 TaskScheduler 異步執行：

```python
def create_agent_team_tool(
    pipeline_name: str,
    scheduler: TaskScheduler,
    description: str,
) -> ToolDefinition:
    """建立一個 agent team tool。

    Handler 行為：
    1. 建立 TaskInfo（UUID、input、chat_route_id）
    2. enqueue 到 scheduler
    3. 回傳「任務已排定，ID: {task_id}」
    """
```

## 行為約束

- 所有 tool MUST 透過 ToolFactory 註冊，不得在 agent 內部自行實作
- Tool MUST 為 stateless function
- Agent team 內部 agent 呼叫 agent team tool 時 MUST 被拒絕（log error）
- 每個 tool MUST 可獨立測試（不依賴 agent 或 pipeline context）
