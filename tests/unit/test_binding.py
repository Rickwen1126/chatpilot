"""Tests for binding router."""

from chatpilot.core.types import Binding, MatchWeights, Message
from chatpilot.routing.binding import calculate_score
from chatpilot.routing.router import BindingRouter


def _msg(platform="line", group_id=None, user_id="u1"):
    return Message(
        text="test",
        user_id=user_id,
        platform=platform,
        conversation_id=group_id or user_id,
        group_id=group_id,
    )


def test_calculate_score_no_match():
    b = Binding(match={}, chatbot="bot")
    assert calculate_score(b, _msg(), MatchWeights()) == 0


def test_calculate_score_platform_match():
    b = Binding(match={"platform": "line"}, chatbot="bot")
    assert calculate_score(b, _msg(), MatchWeights()) == 5


def test_calculate_score_group_match():
    b = Binding(match={"group_id": "g1"}, chatbot="bot")
    assert calculate_score(b, _msg(group_id="g1"), MatchWeights()) == 10


def test_calculate_score_multi_match():
    b = Binding(match={"platform": "line", "group_id": "g1"}, chatbot="bot")
    assert calculate_score(b, _msg(group_id="g1"), MatchWeights()) == 15


def test_router_resolve_best_match():
    bindings = [
        Binding(match={"platform": "line"}, chatbot="general"),
        Binding(match={"platform": "line", "group_id": "g1"}, chatbot="special"),
        Binding(match={}, chatbot="default"),
    ]
    router = BindingRouter(bindings, MatchWeights())
    route = router.resolve(_msg(group_id="g1"))
    assert route is not None
    assert route.chatbot_name == "special"
    assert route.binding_score == 15


def test_router_resolve_default():
    bindings = [Binding(match={}, chatbot="default")]
    router = BindingRouter(bindings, MatchWeights())
    route = router.resolve(_msg())
    assert route is not None
    assert route.chatbot_name == "default"
    assert route.binding_score == 0


def test_router_resolve_no_match():
    bindings = [Binding(match={"platform": "slack"}, chatbot="slack-bot")]
    router = BindingRouter(bindings, MatchWeights())
    route = router.resolve(_msg())
    assert route is None
