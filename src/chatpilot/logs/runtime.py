"""Runtime logging configuration for chatpilot."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from chatpilot.core.types import LoggingConfig
from chatpilot.logs.file_backend import LoggingBackend, WriteFileLoggingBackend

MANAGED_HANDLER_ATTR = "_chatpilot_managed_handler"
LOGGER_FORMAT = (
    "%(asctime)s %(levelname)s [%(name)s] %(filename)s:%(lineno)d %(message)s"
)


@dataclass
class LoggingRuntime:
    """Track backends/handlers installed by chatpilot logging setup."""

    backends: list[LoggingBackend] = field(default_factory=list)
    handlers: list[logging.Handler] = field(default_factory=list)

    def close(self) -> None:
        root = logging.getLogger()
        for handler in list(self.handlers):
            if handler in root.handlers:
                root.removeHandler(handler)
        for handler in self.handlers:
            try:
                handler.close()
            except Exception:
                pass
        self.handlers.clear()
        for backend in self.backends:
            try:
                backend.close()
            except Exception:
                pass
        self.backends.clear()


def configure_local_logging(config: LoggingConfig) -> LoggingRuntime:
    """Install managed handlers for local file logging."""
    root = logging.getLogger()
    _remove_managed_handlers(root)

    runtime = LoggingRuntime()
    root.setLevel(_logging_level(config.level))
    logging.getLogger("chatpilot").setLevel(_logging_level(config.level))

    if not config.enabled:
        return runtime

    formatter = logging.Formatter(LOGGER_FORMAT)
    backend = WriteFileLoggingBackend(
        log_dir=Path(config.dir),
        max_bytes=config.max_bytes,
        backup_count=config.backup_count,
    )
    handler = backend.build_handler(formatter)
    handler.setLevel(_logging_level(config.level))
    setattr(handler, MANAGED_HANDLER_ATTR, True)
    root.addHandler(handler)
    runtime.backends.append(backend)
    runtime.handlers.append(handler)
    logging.getLogger(__name__).info(
        "[logging] backend=write-file path=%s level=%s max_bytes=%d backup_count=%d",
        backend.path,
        config.level,
        config.max_bytes,
        config.backup_count,
    )
    return runtime


def _remove_managed_handlers(root: logging.Logger) -> None:
    for handler in list(root.handlers):
        if not getattr(handler, MANAGED_HANDLER_ATTR, False):
            continue
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def _logging_level(value: str) -> int:
    return getattr(logging, value.upper(), logging.INFO)
