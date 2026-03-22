"""Custom exceptions for the Agent Gateway v2."""


class GatewayError(Exception):
    """Base exception for all gateway errors."""

    def __init__(
        self, message: str, *, code: str = "UNKNOWN", cause: Exception | None = None
    ):
        super().__init__(message)
        self.code = code
        self.cause = cause


class AdapterError(GatewayError):
    """Error from channel adapter."""

    def __init__(
        self, message: str, *, code: str = "ADAPTER_ERROR", cause: Exception | None = None
    ):
        super().__init__(message, code=code, cause=cause)


class BindingError(GatewayError):
    """Error in binding routing."""

    def __init__(
        self, message: str, *, code: str = "BINDING_ERROR", cause: Exception | None = None
    ):
        super().__init__(message, code=code, cause=cause)


class HubError(GatewayError):
    """Error in message hub processing."""

    def __init__(
        self, message: str, *, code: str = "HUB_ERROR", cause: Exception | None = None
    ):
        super().__init__(message, code=code, cause=cause)


class SchedulerError(GatewayError):
    """Error in task scheduling."""

    def __init__(
        self, message: str, *, code: str = "SCHEDULER_ERROR", cause: Exception | None = None
    ):
        super().__init__(message, code=code, cause=cause)


class PipelineError(GatewayError):
    """Error in pipeline execution."""

    def __init__(
        self, message: str, *, code: str = "PIPELINE_ERROR", cause: Exception | None = None
    ):
        super().__init__(message, code=code, cause=cause)


class ToolFactoryError(GatewayError):
    """Error in tool factory."""

    def __init__(
        self, message: str, *, code: str = "TOOL_FACTORY_ERROR", cause: Exception | None = None
    ):
        super().__init__(message, code=code, cause=cause)


class QueueFullError(SchedulerError):
    """Task queue is full."""

    def __init__(
        self,
        message: str = "Task queue is full",
        *,
        code: str = "QUEUE_FULL",
        cause: Exception | None = None,
    ):
        super().__init__(message, code=code, cause=cause)
