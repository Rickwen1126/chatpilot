"""Tests for config loader."""

from pathlib import Path

from chatpilot.core.config import load_config
from chatpilot.server.__init__ import _init_adapters


def test_load_example_config():
    config = load_config(Path("config/routes.example.yaml"))
    assert len(config.bindings) == 4
    assert "buddy" in config.chatbots
    assert "my-observer" in config.chatbots
    bot = config.chatbots["buddy"]
    assert bot.model == "gpt-5.4-mini"
    assert bot.context_window == 50
    assert config.chatbots["my-observer"].observer_mode is True
    assert config.timezone == "Asia/Taipei"
    assert config.scheduler.concurrent_runners == 2
    assert config.match_weights.group_id == 10


def test_load_config_parses_named_line_adapters(tmp_path):
    path = tmp_path / "routes.yaml"
    path.write_text(
        """
adapters:
  line:
    - name: webric
      channel_secret_env: LINE_CHANNEL_SECRET
      channel_token_env: LINE_CHANNEL_ACCESS_TOKEN
    - name: shinyipaint
      channel_secret_env: SHINYIPAINT_LINE_CHANNEL_SECRET
      channel_token_env: SHINYIPAINT_LINE_CHANNEL_ACCESS_TOKEN
""".strip(),
        encoding="utf-8",
    )

    config = load_config(path)

    assert list(config.adapters.keys()) == ["line"]
    assert [c.name for c in config.adapters["line"]] == ["webric", "shinyipaint"]
    assert config.adapters["line"][1].channel_secret_env == (
        "SHINYIPAINT_LINE_CHANNEL_SECRET"
    )


def test_init_adapters_builds_named_line_adapters(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "secret-1")
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "token-1")
    monkeypatch.setenv("SHINYIPAINT_LINE_CHANNEL_SECRET", "secret-2")
    monkeypatch.setenv("SHINYIPAINT_LINE_CHANNEL_ACCESS_TOKEN", "token-2")

    config = load_config(
        Path(
            _write_tmp_config(
                """
adapters:
  line:
    - name: webric
      channel_secret_env: LINE_CHANNEL_SECRET
      channel_token_env: LINE_CHANNEL_ACCESS_TOKEN
    - name: shinyipaint
      channel_secret_env: SHINYIPAINT_LINE_CHANNEL_SECRET
      channel_token_env: SHINYIPAINT_LINE_CHANNEL_ACCESS_TOKEN
"""
            )
        )
    )

    adapters = _init_adapters(config)

    assert "line:webric" in adapters
    assert "line:shinyipaint" in adapters
    assert "mock" in adapters


def _write_tmp_config(content: str) -> str:
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(content.strip())
        return f.name
