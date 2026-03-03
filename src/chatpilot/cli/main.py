"""CLI entry point — direct agent interaction without webhook server."""

from __future__ import annotations

import argparse
import asyncio
import sys

from dotenv import load_dotenv


async def async_main(
    agent_name: str, message_text: str, session_id: str | None
) -> None:
    from chatpilot.agents import agent_registry, register_agent
    from chatpilot.agents.general import general_agent
    from chatpilot.core.types import Message
    from chatpilot.sdk.session_manager import session_manager

    # Register agents
    register_agent(general_agent)

    # Start SDK
    await session_manager.start()

    # Look up agent
    agent = agent_registry.get(agent_name)
    if agent is None:
        print(f"Error: unknown agent '{agent_name}'", file=sys.stderr)
        print(f"Available agents: {list(agent_registry.keys())}", file=sys.stderr)
        sys.exit(1)

    # Compute session_id
    import time

    sid = session_id or f"cli-{int(time.time())}"

    # Build message
    msg = Message(
        text=message_text,
        user_id="cli-user",
        platform="cli",
        conversation_id=None,
    )

    try:
        response = await agent.handle(msg, sid)
        print(response.text)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await session_manager.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="ChatPilot CLI")
    parser.add_argument(
        "--agent", required=True, help="Agent name (e.g., general-agent)"
    )
    parser.add_argument("--message", required=True, help="Message text to send")
    parser.add_argument("--session-id", default=None, help="Optional session ID")
    args = parser.parse_args()

    load_dotenv()
    asyncio.run(async_main(args.agent, args.message, args.session_id))


if __name__ == "__main__":
    main()
