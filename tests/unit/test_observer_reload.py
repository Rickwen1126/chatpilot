from __future__ import annotations

from types import SimpleNamespace

from chatpilot.core.config import GatewayConfig
from chatpilot.core.types import Binding
from chatpilot.server.__init__ import _refresh_observer_state


class _FakeHub:
    def __init__(self) -> None:
        self.registered: list[tuple[str, int, list[str]]] = []
        self.route_policies: dict[str, dict] = {}
        self.cleared = 0
        self.policy_cleared = 0

    def clear_observers(self) -> None:
        self.cleared += 1
        self.registered.clear()

    def clear_route_policies(self) -> None:
        self.policy_cleared += 1
        self.route_policies.clear()

    def register_observer(
        self, route_id: str, batch_size: int, categories: list[str]
    ) -> None:
        self.registered.append((route_id, batch_size, categories))

    def register_capture(
        self, route_id: str, batch_size: int, categories: list[str]
    ) -> None:
        self.registered.append((route_id, batch_size, categories))

    def register_route_policy(
        self,
        route_id: str,
        *,
        reply_policy: str,
        processing_policy: str,
        capture_enabled: bool,
    ) -> None:
        self.route_policies[route_id] = {
            "reply_policy": reply_policy,
            "processing_policy": processing_policy,
            "capture_enabled": capture_enabled,
        }


def test_refresh_observer_state_registers_named_adapter_routes() -> None:
    hub = _FakeHub()
    observer_sources: dict[str, dict] = {}
    config = GatewayConfig(
        route_groups={
            "ops": {"description": "ops"},
        },
        observation_profiles={
            "warehouse_ops": {
                "mode": "batch",
                "batch_size": 10,
                "instructions": "capture ops",
                "categories": ["請假", "進料"],
            }
        },
        bindings=[
            Binding(
                match={
                    "platform": "line:shinyipaint",
                    "group_id": "C123",
                },
                chatbot="shinyipaint-observer",
                reply_policy="never",
                processing_policy="none",
                observation={
                    "capture": {
                        "group": "ops",
                        "profile": "warehouse_ops",
                    }
                },
            ),
            Binding(
                match={
                    "platform": "line:shinyipaint",
                    "user_id": "Uabc",
                },
                chatbot="shinyipaint-admin",
                reply_policy="addressed",
                processing_policy="interactive",
                observation={
                    "consume": ["ops"],
                },
            )
        ],
    )
    adapters = {
        "cli": SimpleNamespace(platform="cli"),
        "line:shinyipaint": SimpleNamespace(platform="line:shinyipaint"),
        "mock": SimpleNamespace(platform="mock"),
    }

    _refresh_observer_state(
        hub=hub,
        adapters=adapters,
        config=config,
        observer_sources=observer_sources,
    )

    assert hub.cleared == 1
    assert {
        route_id for route_id, _, _ in hub.registered
    } == {
        "line:shinyipaint:C123",
    }
    assert observer_sources == {
        "ops": {
            "source_route_ids": [
                "line:shinyipaint:C123",
            ],
            "consumer_route_ids": ["line:shinyipaint:Uabc"],
        }
    }


def test_refresh_observer_state_replaces_old_observer_bindings() -> None:
    hub = _FakeHub()
    observer_sources = {
        "old-group": {
            "source_route_ids": ["line:shinyipaint:Cold"],
            "consumer_route_ids": [],
        }
    }
    adapters = {
        "cli": SimpleNamespace(platform="cli"),
        "line:shinyipaint": SimpleNamespace(platform="line:shinyipaint"),
    }

    first = GatewayConfig(
        route_groups={"ops_old": {"description": "old"}},
        observation_profiles={
            "warehouse_ops": {
                "mode": "batch",
                "batch_size": 10,
                "instructions": "capture ops",
            }
        },
        bindings=[
            Binding(
                match={"platform": "line:shinyipaint", "group_id": "Cold"},
                chatbot="old-observer",
                reply_policy="never",
                processing_policy="none",
                observation={
                    "capture": {
                        "group": "ops_old",
                        "profile": "warehouse_ops",
                    }
                },
            )
        ],
    )
    second = GatewayConfig(
        route_groups={"ops_new": {"description": "new"}},
        observation_profiles={
            "warehouse_ops": {
                "mode": "batch",
                "batch_size": 10,
                "instructions": "capture ops",
            }
        },
        bindings=[
            Binding(
                match={"platform": "line:shinyipaint", "group_id": "Cnew"},
                chatbot="new-observer",
                reply_policy="never",
                processing_policy="none",
                observation={
                    "capture": {
                        "group": "ops_new",
                        "profile": "warehouse_ops",
                    }
                },
            )
        ],
    )

    _refresh_observer_state(
        hub=hub,
        adapters=adapters,
        config=first,
        observer_sources=observer_sources,
    )
    _refresh_observer_state(
        hub=hub,
        adapters=adapters,
        config=second,
        observer_sources=observer_sources,
    )

    assert hub.cleared == 2
    assert {
        route_id for route_id, _, _ in hub.registered
    } == {
        "line:shinyipaint:Cnew",
    }
    assert list(observer_sources) == ["ops_new"]
    assert observer_sources["ops_new"]["source_route_ids"] == [
        "line:shinyipaint:Cnew",
    ]


def test_refresh_observer_state_registers_interactive_capture_routes() -> None:
    hub = _FakeHub()
    observer_sources: dict[str, dict] = {}
    config = GatewayConfig(
        route_groups={"ops": {"description": "ops"}},
        observation_profiles={
            "warehouse_ops": {
                "mode": "batch",
                "batch_size": 10,
                "instructions": "capture ops",
            }
        },
        bindings=[
            Binding(
                match={"platform": "line:shinyipaint", "group_id": "C123"},
                chatbot="shinyipaint",
                reply_policy="addressed",
                processing_policy="interactive",
                observation={
                    "capture": {
                        "group": "ops",
                        "profile": "warehouse_ops",
                    }
                },
            )
        ],
    )
    adapters = {
        "line:shinyipaint": SimpleNamespace(platform="line:shinyipaint"),
    }

    _refresh_observer_state(
        hub=hub,
        adapters=adapters,
        config=config,
        observer_sources=observer_sources,
    )

    assert hub.registered == [("line:shinyipaint:C123", 10, [])]
    assert observer_sources == {
        "ops": {
            "source_route_ids": ["line:shinyipaint:C123"],
            "consumer_route_ids": [],
        }
    }
    assert hub.route_policies["line:shinyipaint:C123"] == {
        "reply_policy": "addressed",
        "processing_policy": "interactive",
        "capture_enabled": True,
    }
