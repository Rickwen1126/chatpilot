"""Tests for config loader."""

from pathlib import Path

from chatpilot.core.config import load_config
from chatpilot.server.__init__ import _init_adapters


def test_load_example_config():
    config = load_config(
        Path("config/route_settings.example.yaml"),
        Path("config/route_bindings.example.yaml"),
    )
    assert len(config.bindings) >= 12
    assert "buddy" in config.chatbots
    assert "my-assistant" in config.chatbots
    bot = config.chatbots["buddy"]
    assert bot.model == "gpt-5.4-mini"
    assert bot.context_window == 50
    observer_binding = next(
        binding
        for binding in config.bindings
        if binding.reply_policy == "never"
        and binding.processing_policy == "none"
        and binding.observation is not None
        and binding.observation.capture is not None
    )
    assert observer_binding.reply_policy == "never"
    assert observer_binding.processing_policy == "none"
    assert observer_binding.observation is not None
    assert observer_binding.observation.capture is not None
    assert observer_binding.observation.capture.group == "ops"
    assert config.timezone == "Asia/Taipei"
    assert config.scheduler.concurrent_runners == 2
    assert config.match_weights.group_id == 10
    assert "ops" in config.route_groups
    assert "ops_batch" in config.observation_profiles
    assert "stock" in config.observation_profiles["ops_batch"].retrieval.keywords


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


def test_route_group_rejects_members(tmp_path):
    path = tmp_path / "routes.yaml"
    path.write_text(
        """
route_groups:
  ops:
    description: test
    members:
      - accidental
""".strip(),
        encoding="utf-8",
    )

    try:
        load_config(path)
    except ValueError as exc:
        assert "must not define members" in str(exc)
    else:
        raise AssertionError("expected route_group members validation error")


def test_binding_policy_combo_rejects_addressed_none(tmp_path):
    path = tmp_path / "routes.yaml"
    path.write_text(
        """
bindings:
  - chatbot: buddy
    reply_policy: addressed
    processing_policy: none

chatbots:
  buddy:
    model: gpt-5.4-mini
    system_message: test
""".strip(),
        encoding="utf-8",
    )

    try:
        load_config(path)
    except ValueError as exc:
        assert "reply_policy=addressed" in str(exc)
    else:
        raise AssertionError("expected invalid policy combination error")


def test_load_config_parses_discovery_profiles_and_rules(tmp_path):
    path = tmp_path / "routes.yaml"
    path.write_text(
        """
route_groups:
  ops:
    description: ops

observation_profiles:
  warehouse_ops:
    mode: batch
    batch_size: 10
    instructions: capture ops

discovery_profiles:
  safe_group:
    chatbot: buddy
    reply_policy: never
    processing_policy: none
    observation:
      capture:
        group: ops
        profile: warehouse_ops

discovery_rules:
  - platform: line:shinyipaint
    route_type: group
    label_keywords: ["信益"]
    profile: safe_group

chatbots:
  buddy:
    model: gpt-5.4-mini
    system_message: test
""".strip(),
        encoding="utf-8",
    )

    config = load_config(path)

    assert "safe_group" in config.discovery_profiles
    assert config.discovery_rules[0].profile == "safe_group"
    assert config.discovery_profiles["safe_group"].observation is not None


def test_load_config_rejects_discovery_profile_unknown_chatbot(tmp_path):
    path = tmp_path / "routes.yaml"
    path.write_text(
        """
discovery_profiles:
  safe_group:
    chatbot: missing
    reply_policy: never
    processing_policy: none
""".strip(),
        encoding="utf-8",
    )

    try:
        load_config(path)
    except ValueError as exc:
        assert "references unknown chatbot" in str(exc)
    else:
        raise AssertionError("expected invalid discovery profile chatbot error")


def _write_tmp_config(content: str) -> str:
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(content.strip())
        return f.name
