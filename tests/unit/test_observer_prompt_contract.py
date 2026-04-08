from datetime import datetime, timezone

from chatpilot.core.types import (
    ContextMessage,
    ContextMessageType,
    ObserverBatchPayload,
)
from chatpilot.observer.prompting import (
    build_observation_worker_prompt,
    build_observation_worker_system_message,
)


def test_observer_worker_system_message_is_strict() -> None:
    system_message = build_observation_worker_system_message()

    assert "observation capture worker" in system_message
    assert "JSON object" in system_message
    assert "reported_by" in system_message
    assert "不可創造新事實" in system_message
    assert "observe_image_ref" in system_message
    assert "圖片標示白漆 2 桶" in system_message


def test_observer_worker_prompt_includes_profile_contract() -> None:
    payload = ObserverBatchPayload(
        route_id="line:demo:Cops",
        captured_profile_name="warehouse_ops",
        instructions="持續整理營運脈絡，忽略純閒聊。",
        categories=["請假", "進料", "庫存"],
        messages=[
            ContextMessage(
                user_id="U1",
                user_name="小王",
                text="阿明明天下午請假",
                timestamp=datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc),
                message_type=ContextMessageType.background,
            )
        ],
        formatted_messages="[群組近期對話]\n[背景] 小王 (17:00): 阿明明天下午請假",
    )

    prompt = build_observation_worker_prompt(payload)

    assert "warehouse_ops" in prompt
    assert "持續整理營運脈絡" in prompt
    assert "請假" in prompt
    assert "reported_by_name" in prompt
    assert "canonical_fact_index" in prompt
    assert "[群組近期對話]" in prompt
    assert "observe_image_ref" in prompt
    assert "圖片標示白漆 2 桶" in prompt
