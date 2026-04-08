"""Tests for local logging system v1."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from chatpilot.core.types import LoggingConfig
from chatpilot.logs import configure_local_logging
from chatpilot.logs.file_backend import TimestampedRotatingFileHandler


def test_timestamped_rotating_file_handler_rotates_and_prunes(tmp_path):
    log_path = tmp_path / "log" / "chatpilot.log"
    handler = TimestampedRotatingFileHandler(
        log_path,
        max_bytes=80,
        backup_count=2,
    )
    logger = logging.getLogger("test.logging.rotation")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers[:] = [handler]
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)

    for index in range(8):
        logger.info("message-%d %s", index, "x" * 30)

    handler.close()

    archives = sorted((log_path.parent / "archive").glob("chatpilot@*.log"))
    assert log_path.exists()
    assert len(archives) <= 2
    assert archives


def test_configure_local_logging_writes_file(tmp_path):
    current = Path.cwd()
    runtime = None
    try:
        os.chdir(tmp_path)
        runtime = configure_local_logging(
            LoggingConfig(
                enabled=True,
                dir="log",
                level="INFO",
                max_bytes=1024,
                backup_count=2,
            )
        )
        logger = logging.getLogger("chatpilot.test")
        logger.info("[test] event=write route_id=line:demo:C123")
        for handler in runtime.handlers:
            handler.flush()

        path = tmp_path / "log" / "chatpilot.log"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "[test] event=write route_id=line:demo:C123" in content
    finally:
        if runtime is not None:
            runtime.close()
        os.chdir(current)
