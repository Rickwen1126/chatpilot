"""Write-file logging backend with size-based timestamped rotation."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Protocol


class LoggingBackend(Protocol):
    """Minimal backend contract for raw log sinks."""

    def build_handler(self, formatter: logging.Formatter) -> logging.Handler:
        """Build a handler bound to this backend."""

    def close(self) -> None:
        """Release any backend resources."""


class TimestampedRotatingFileHandler(logging.Handler):
    """Single current file + timestamped archive rotation."""

    terminator = "\n"

    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int,
        backup_count: int,
        encoding: str = "utf-8",
    ) -> None:
        super().__init__()
        self._path = path
        self._archive_dir = path.parent / "archive"
        self._max_bytes = max(0, int(max_bytes))
        self._backup_count = max(0, int(backup_count))
        self._encoding = encoding
        self._stream = None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        self._open()

    def _open(self) -> None:
        self._stream = self._path.open("a", encoding=self._encoding)

    def _close_stream(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record) + self.terminator
            self.acquire()
            try:
                self._maybe_rollover(msg)
                if self._stream is None:
                    self._open()
                assert self._stream is not None
                self._stream.write(msg)
                self._stream.flush()
            finally:
                self.release()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            self.acquire()
            try:
                self._close_stream()
            finally:
                self.release()
        finally:
            super().close()

    def flush(self) -> None:
        if self._stream is not None:
            self._stream.flush()

    def _maybe_rollover(self, next_message: str) -> None:
        if self._max_bytes <= 0:
            return
        current_size = self._path.stat().st_size if self._path.exists() else 0
        projected = current_size + len(next_message.encode(self._encoding))
        if current_size > 0 and projected > self._max_bytes:
            self._do_rollover()

    def _do_rollover(self) -> None:
        self._close_stream()
        if self._path.exists() and self._path.stat().st_size > 0:
            archive_path = self._next_archive_path()
            self._path.replace(archive_path)
            self._prune_archives()
        self._open()

    def _next_archive_path(self) -> Path:
        stem = self._path.stem
        suffix = "".join(self._path.suffixes) or ".log"
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        candidate = self._archive_dir / f"{stem}@{stamp}{suffix}"
        idx = 1
        while candidate.exists():
            candidate = self._archive_dir / f"{stem}@{stamp}-{idx}{suffix}"
            idx += 1
        return candidate

    def _prune_archives(self) -> None:
        if self._backup_count <= 0:
            for path in self._archive_paths():
                path.unlink(missing_ok=True)
            return
        archives = sorted(
            self._archive_paths(),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for stale in archives[self._backup_count:]:
            stale.unlink(missing_ok=True)

    def _archive_paths(self) -> list[Path]:
        stem = self._path.stem
        suffix = "".join(self._path.suffixes) or ".log"
        return list(self._archive_dir.glob(f"{stem}@*{suffix}"))


class WriteFileLoggingBackend:
    """V1 backend: write all raw logs to a local rotating file."""

    def __init__(
        self,
        *,
        log_dir: Path,
        filename: str = "chatpilot.log",
        max_bytes: int,
        backup_count: int,
    ) -> None:
        self._log_dir = log_dir
        self._filename = filename
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._handler: logging.Handler | None = None

    @property
    def path(self) -> Path:
        return self._log_dir / self._filename

    def build_handler(self, formatter: logging.Formatter) -> logging.Handler:
        handler = TimestampedRotatingFileHandler(
            self.path,
            max_bytes=self._max_bytes,
            backup_count=self._backup_count,
        )
        handler.setFormatter(formatter)
        self._handler = handler
        return handler

    def close(self) -> None:
        if self._handler is not None:
            self._handler.close()
            self._handler = None
