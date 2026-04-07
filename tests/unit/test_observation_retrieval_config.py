from pathlib import Path

from chatpilot.core.config import load_config


def test_observation_profile_retrieval_metadata_loads_from_example() -> None:
    config = load_config(
        Path("config/route_settings.example.yaml"),
        Path("config/route_bindings.example.yaml"),
    )

    profile = config.observation_profiles["ops_batch"]
    assert profile.retrieval.description
    assert "inventory" in profile.retrieval.description
    assert "stock" in profile.retrieval.keywords


def test_observation_profile_retrieval_defaults_to_empty(tmp_path) -> None:
    path = tmp_path / "route_settings.yaml"
    path.write_text(
        """
observation_profiles:
  warehouse_ops:
    mode: batch
    batch_size: 10
    instructions: capture ops

chatbots:
  buddy:
    model: gpt-5.4-mini
    system_message: test
""".strip(),
        encoding="utf-8",
    )

    config = load_config(path)
    profile = config.observation_profiles["warehouse_ops"]
    assert profile.retrieval.description == ""
    assert profile.retrieval.keywords == []
