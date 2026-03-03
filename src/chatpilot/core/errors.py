"""Custom exceptions for the Agent Gateway."""


class GatewayError(Exception):
    """Base exception for all gateway errors."""

    def __init__(
        self, message: str, *, code: str = "UNKNOWN", cause: Exception | None = None
    ):
        super().__init__(message)
        self.code = code
        self.cause = cause


class AgentError(GatewayError):
    """Error from agent or SDK layer."""

    def __init__(
        self, message: str, *, code: str = "AGENT_ERROR", cause: Exception | None = None
    ):
        super().__init__(message, code=code, cause=cause)


class RouteError(GatewayError):
    """Error in routing configuration or logic."""

    def __init__(
        self, message: str, *, code: str = "ROUTE_ERROR", cause: Exception | None = None
    ):
        super().__init__(message, code=code, cause=cause)


class AdapterError(GatewayError):
    """Error from channel adapter."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "ADAPTER_ERROR",
        cause: Exception | None = None,
    ):
        super().__init__(message, code=code, cause=cause)


class TimeoutError(GatewayError):
    """Agent processing timeout."""

    def __init__(
        self,
        message: str = "Agent processing timed out",
        *,
        code: str = "TIMEOUT",
        cause: Exception | None = None,
    ):
        super().__init__(message, code=code, cause=cause)
