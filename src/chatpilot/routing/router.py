"""Binding router — resolves messages to chat routes."""

from __future__ import annotations

import logging

from chatpilot.core.types import Binding, ChatRoute, MatchWeights, Message
from chatpilot.routing.binding import NO_MATCH, calculate_score

logger = logging.getLogger(__name__)


class BindingRouter:
    """Routes messages to chatbots via binding score competition."""

    def __init__(
        self,
        bindings: list[Binding],
        weights: MatchWeights,
    ) -> None:
        self._bindings = bindings
        self._weights = weights

    def update(self, bindings: list[Binding], weights: MatchWeights) -> None:
        self._bindings = bindings
        self._weights = weights

    def resolve(self, message: Message) -> ChatRoute | None:
        """Find the best matching binding for a message.

        Returns None if no binding matches (not even a default).
        """
        best_binding: Binding | None = None
        best_score = NO_MATCH

        for binding in self._bindings:
            score = calculate_score(binding, message, self._weights)
            if score == NO_MATCH:
                continue
            if score >= best_score:
                best_score = score
                best_binding = binding

        if best_binding is None:
            return None

        route_id = f"{message.platform}:{message.conversation_id}"
        return ChatRoute(
            route_id=route_id,
            chatbot_name=best_binding.chatbot,
            platform=message.platform,
            conversation_id=message.conversation_id,
            binding_score=best_score,
        )
