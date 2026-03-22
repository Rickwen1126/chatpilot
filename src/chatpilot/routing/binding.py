"""Binding scoring — calculates match scores for bindings."""

from __future__ import annotations

from chatpilot.core.types import Binding, MatchWeights, Message

# Sentinel: binding has match conditions but none were satisfied
NO_MATCH = -1


def calculate_score(binding: Binding, message: Message, weights: MatchWeights) -> int:
    """Calculate match score for a binding against a message.

    Returns:
        Score >= 0 if binding matches (0 = default binding with no conditions).
        NO_MATCH (-1) if binding has conditions but they don't all match.
    """
    match = binding.match
    if not match:
        return 0  # default binding, always matches with score 0

    score = 0
    for key, value in match.items():
        msg_value = _get_dimension(message, key)
        if msg_value != value:
            return NO_MATCH  # hard filter: ALL conditions must match
        score += _get_weight(weights, key)
    return score


def _get_dimension(message: Message, key: str) -> str | None:
    if key == "platform":
        return message.platform
    if key == "group_id":
        return message.group_id
    if key == "user_id":
        return message.user_id
    return None


def _get_weight(weights: MatchWeights, key: str) -> int:
    if key == "platform":
        return weights.platform
    if key == "group_id":
        return weights.group_id
    if key == "user_id":
        return weights.user_id
    return 0
