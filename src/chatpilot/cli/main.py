"""CLI entry point for chatpilot."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv


async def run_chatbot(chatbot_name: str, message: str) -> None:
    """Send a message to a chatbot and print the response."""
    from chatpilot.chatbot.manager import ChatbotManager
    from chatpilot.core.config import load_config
    from chatpilot.sdk.session import SdkClient
    from chatpilot.tools.factory import ToolFactory

    config = load_config(Path("config/routes.yaml"))
    sdk = SdkClient()
    await sdk.start()
    try:
        manager = ChatbotManager(sdk, config.chatbots, ToolFactory())
        route_id = f"cli:{chatbot_name}"
        session = await manager.get_or_create_session(route_id, chatbot_name)
        response = await session.send_message(message)
        print(response.text)
    finally:
        await sdk.stop()


async def run_pipeline(pipeline_name: str, input_json: str) -> None:
    """Trigger a pipeline and print the result."""
    import json
    import uuid
    from datetime import datetime, timezone

    from chatpilot.core.types import TaskInfo
    from chatpilot.pipeline.executor import PipelineExecutor
    from chatpilot.pipeline.samples.echo import EchoPipeline

    executor = PipelineExecutor()
    executor.register(EchoPipeline())

    task = TaskInfo(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        pipeline_name=pipeline_name,
        input_summary=input_json[:200],
        input_data=json.loads(input_json),
        chat_route_id="cli:local",
    )
    result = await executor.execute(task)
    print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False, default=str))


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="ChatPilot CLI")
    sub = parser.add_subparsers(dest="command")

    chat_p = sub.add_parser("chat", help="Chat with a chatbot")
    chat_p.add_argument("--chatbot", required=True, help="Chatbot name")
    chat_p.add_argument("--message", required=True, help="Message text")

    pipe_p = sub.add_parser("pipeline", help="Run a pipeline")
    pipe_p.add_argument("--name", required=True, help="Pipeline name")
    pipe_p.add_argument("--input", required=True, help="Input JSON")

    args = parser.parse_args()
    if args.command == "chat":
        asyncio.run(run_chatbot(args.chatbot, args.message))
    elif args.command == "pipeline":
        asyncio.run(run_pipeline(args.name, args.input))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
