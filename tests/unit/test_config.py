"""Tests for config loader."""

from pathlib import Path

from chatpilot.core.config import load_config


def test_load_example_config():
    config = load_config(Path("config/routes.example.yaml"))
    assert len(config.bindings) == 4
    assert "buddy" in config.chatbots
    assert "my-observer" in config.chatbots
    bot = config.chatbots["buddy"]
    assert bot.model == "gpt-4.1"
    assert bot.context_window == 50
    assert config.chatbots["my-observer"].observer_mode is True
    assert config.timezone == "Asia/Taipei"
    assert config.scheduler.concurrent_runners == 2
    assert config.match_weights.group_id == 10
