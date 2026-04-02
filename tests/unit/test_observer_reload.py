from __future__ import annotations

from types import SimpleNamespace

from chatpilot.core.config import GatewayConfig
from chatpilot.core.types import Binding, ChatbotConfig
from chatpilot.server.__init__ import _refresh_observer_state


class _FakeHub:
    def __init__(self) -> None:
        self.registered: list[tuple[str, int, list[str]]] = []
        self.cleared = 0

    def clear_observers(self) -> None:
        self.cleared += 1
        self.registered.clear()

    def register_observer(
        self, route_id: str, batch_size: int, categories: list[str]
    ) -> None:
        self.registered.append((route_id, batch_size, categories))


def _observer_cfg(name: str, allowed: list[str] | None = None) -> ChatbotConfig:
    return ChatbotConfig(
        name=name,
        model="gpt-4.1",
        system_message="observer",
        observer_mode=True,
        observer_batch_size=10,
        observer_categories=["請假", "進料"],
        observer_allowed_consumers=allowed or [],
    )


def test_refresh_observer_state_registers_named_adapter_routes() -> None:
    hub = _FakeHub()
    observer_sources: dict[str, dict] = {}
    config = GatewayConfig(
        bindings=[
            Binding(
                match={"group_id": "C123"},
                chatbot="shinyipaint-observer",
            )
        ],
        chatbots={
            "shinyipaint-observer": _observer_cfg(
                "shinyipaint-observer",
                allowed=["line:shinyipaint:Uabc"],
            )
        },
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
        "cli:C123",
        "line:shinyipaint:C123",
        "mock:C123",
    }
    assert observer_sources == {
        "shinyipaint-observer": {
            "route_id": "line:C123",
            "all_route_ids": [
                "line:shinyipaint:C123",
            ],
            "allowed_consumers": ["line:shinyipaint:Uabc"],
        }
    }


def test_refresh_observer_state_replaces_old_observer_bindings() -> None:
    hub = _FakeHub()
    observer_sources = {
        "old-observer": {
            "route_id": "line:Cold",
            "all_route_ids": ["line:shinyipaint:Cold"],
            "allowed_consumers": [],
        }
    }
    adapters = {
        "cli": SimpleNamespace(platform="cli"),
        "line:shinyipaint": SimpleNamespace(platform="line:shinyipaint"),
    }

    first = GatewayConfig(
        bindings=[
            Binding(match={"group_id": "Cold"}, chatbot="old-observer")
        ],
        chatbots={"old-observer": _observer_cfg("old-observer")},
    )
    second = GatewayConfig(
        bindings=[
            Binding(match={"group_id": "Cnew"}, chatbot="new-observer")
        ],
        chatbots={"new-observer": _observer_cfg("new-observer")},
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
        "cli:Cnew",
        "line:shinyipaint:Cnew",
    }
    assert list(observer_sources) == ["new-observer"]
    assert observer_sources["new-observer"]["all_route_ids"] == [
        "line:shinyipaint:Cnew",
    ]
