"""Tests for config loader."""

from pathlib import Path

from chatpilot.core.config import load_config


def test_load_example_config():
    config = load_config(Path("config/routes.example.yaml"))
    assert len(config.bindings) == 2
    assert "general-bot" in config.chatbots
    bot = config.chatbots["general-bot"]
    assert bot.model == "gpt-4.1"
    assert bot.context_window == 20
    assert config.scheduler.concurrent_runners == 2
    assert config.match_weights.group_id == 10
