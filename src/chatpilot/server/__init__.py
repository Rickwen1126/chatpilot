"""FastAPI application factory and startup lifecycle."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from chatpilot.adapters.protocol import ChannelAdapter
from chatpilot.chatbot.manager import ChatbotManager
from chatpilot.core.config import GatewayConfig, load_config, watch_config
from chatpilot.core.types import Message, Response
from chatpilot.hub.context_buffer import ContextBuffer
from chatpilot.hub.hub import InMemoryMessageHub
from chatpilot.pipeline.executor import PipelineExecutor
from chatpilot.pipeline.samples.browser import BrowserPipeline
from chatpilot.pipeline.samples.echo import EchoPipeline
from chatpilot.routing.router import BindingRouter
from chatpilot.scheduler.runner import RunnerPool
from chatpilot.scheduler.scheduler import InMemoryTaskScheduler
from chatpilot.scheduler.store import SqliteTaskStore
from chatpilot.sdk.session import SdkClient
from chatpilot.server.webhook import router
from chatpilot.tools.builtin.browse_task import create_browse_task_tool
from chatpilot.tools.builtin.submit_task import create_submit_task_tool
from chatpilot.tools.builtin.task_history import create_task_history_tool
from chatpilot.tools.builtin.web_search import create_web_search_tool
from chatpilot.tools.factory import ToolFactory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    app.state.start_time = time.time()

    # Load config
    config_path = Path(os.environ.get("ROUTES_PATH", "config/routes.yaml"))
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        logger.warning("Config not found: %s — using defaults", config_path)
        config = GatewayConfig()

    # Start SDK client
    sdk_client = SdkClient()
    await sdk_client.start()

    # Tool factory
    tool_factory = ToolFactory()

    # Adapters
    adapters: dict[str, ChannelAdapter] = {}
    try:
        from chatpilot.adapters.line.adapter import LineAdapter
        adapters["line"] = LineAdapter()
    except Exception:
        logger.warning("LINE adapter not available (missing env vars?)")

    from chatpilot.adapters.mock import MockAdapter
    adapters["mock"] = MockAdapter()

    app.state.adapters = adapters

    # Binding router
    binding_router = BindingRouter(config.bindings, config.match_weights)

    # Chatbot manager
    chatbot_manager = ChatbotManager(sdk_client, config.chatbots, tool_factory)

    # Context buffer
    context_buffer = ContextBuffer()

    # Message hub
    hub = InMemoryMessageHub(
        context_buffer=context_buffer,
        adapters=adapters,
    )

    async def on_proceed(
        message: Message, context_prefix: str | None, adapter: ChannelAdapter
    ) -> None:
        """Hub callback: route message → chatbot → reply."""
        route = binding_router.resolve(message)
        if route is None:
            logger.warning("No binding matched for %s", message.conversation_id)
            return
        session = await chatbot_manager.get_or_create_session(
            route.route_id, route.chatbot_name
        )
        response = await session.send_message(message.text, context_prefix)
        await adapter.send_reply(message, response)

    async def on_command(
        command: str, args: str, message: Message, adapter: ChannelAdapter
    ) -> None:
        """Hub callback: handle prefix commands."""
        route_id = f"{message.platform}:{message.conversation_id}"
        if command == "model" and args.strip():
            await chatbot_manager.switch_model(route_id, args.strip())
            await adapter.send_reply(
                message, Response(text=f"已切換模型為 {args.strip()}")
            )
        elif command == "chatbot":
            arg = args.strip()
            if not arg or arg == "list":
                names = list(chatbot_manager._configs.keys())
                await adapter.send_reply(
                    message, Response(text=f"可用 chatbot：\n{chr(10).join(names)}")
                )
            elif not chatbot_manager.has_chatbot(arg):
                await adapter.send_reply(
                    message, Response(text=f"未知的 chatbot: {arg}")
                )
            else:
                await chatbot_manager.destroy_session(route_id)
                await chatbot_manager.get_or_create_session(route_id, arg)
                await adapter.send_reply(
                    message, Response(text=f"已切換 chatbot 為 {arg}")
                )
        else:
            logger.debug("Unknown command: /%s", command)

    hub.set_on_proceed(on_proceed)
    hub.set_on_command(on_command)
    app.state.hub = hub

    # Task scheduler + pipeline
    task_store = SqliteTaskStore()
    await task_store.initialize()

    scheduler = InMemoryTaskScheduler(
        store=task_store,
        max_queue_size=config.scheduler.max_queue_size,
    )

    pipeline_executor = PipelineExecutor()
    pipeline_executor.register(EchoPipeline())
    pipeline_executor.register(BrowserPipeline())

    runner_pool = RunnerPool(
        max_workers=config.scheduler.concurrent_runners,
        pipeline_executor=pipeline_executor,
        task_store=task_store,
        hub=hub,
        task_timeout=config.scheduler.task_timeout,
    )
    await runner_pool.start(scheduler)

    # Register built-in tools
    submit_tool = create_submit_task_tool(scheduler)
    tool_factory.register(submit_tool)

    history_tool = create_task_history_tool(scheduler)
    tool_factory.register(history_tool)

    web_search_tool = create_web_search_tool()
    tool_factory.register(web_search_tool)

    browse_tool = create_browse_task_tool(scheduler)
    tool_factory.register(browse_tool)

    app.state.scheduler = scheduler

    # Config hot reload
    def on_config_reload(new_config: GatewayConfig) -> None:
        binding_router.update(new_config.bindings, new_config.match_weights)
        chatbot_manager.update_configs(new_config.chatbots)
        logger.info("Config reloaded successfully")

    observer = None
    if config_path.exists():
        observer = watch_config(config_path, on_config_reload)

    logger.info("Server started. Webhook: POST /webhook/{platform}")

    yield

    # Shutdown
    await runner_pool.stop()
    await task_store.close()
    if observer:
        observer.stop()
    await chatbot_manager.destroy_all()
    await sdk_client.stop()
    logger.info("Server stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="ChatPilot Agent Gateway v2", lifespan=lifespan)
    app.include_router(router)
    return app
