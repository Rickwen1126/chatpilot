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
from chatpilot.memory.store import SqliteMemoryStore as MemoryStore
from chatpilot.pipeline.executor import PipelineExecutor
from chatpilot.pipeline.samples.browser import BrowserPipeline
from chatpilot.pipeline.samples.echo import EchoPipeline
from chatpilot.routing.router import BindingRouter
from chatpilot.scheduler.runner import RunnerPool
from chatpilot.scheduler.scheduler import InMemoryTaskScheduler
from chatpilot.scheduler.store import SqliteTaskStore
from chatpilot.sdk.session import SdkClient
from chatpilot.server.webhook import router
from chatpilot.tools.factory import ToolFactory

logger = logging.getLogger(__name__)


# ── Startup helpers ──────────────────────────────────────────────


def _load_gateway_config(config_path: Path) -> GatewayConfig:
    try:
        return load_config(config_path)
    except FileNotFoundError:
        logger.warning("Config not found: %s — using defaults", config_path)
        return GatewayConfig()


def _init_adapters() -> dict[str, ChannelAdapter]:
    adapters: dict[str, ChannelAdapter] = {}
    try:
        from chatpilot.adapters.line.adapter import LineAdapter

        adapters["line"] = LineAdapter()
    except Exception:
        logger.warning("LINE adapter not available (missing env vars?)")

    from chatpilot.adapters.mock import MockAdapter

    adapters["mock"] = MockAdapter()
    return adapters


def _init_hub(
    context_buffer: ContextBuffer,
    adapters: dict[str, ChannelAdapter],
    binding_router: BindingRouter,
    chatbot_manager: ChatbotManager,
) -> InMemoryMessageHub:
    hub = InMemoryMessageHub(
        context_buffer=context_buffer,
        adapters=adapters,
    )

    async def on_proceed(
        message: Message, context_prefix: str | None, adapter: ChannelAdapter
    ) -> None:
        route = binding_router.resolve(message)
        if route is None:
            logger.warning("No binding matched for %s", message.conversation_id)
            return
        hint = getattr(adapter, "format_hint", None)
        if hint:
            context_prefix = f"{context_prefix}\n{hint}" if context_prefix else hint
        session = await chatbot_manager.get_or_create_session(
            route.route_id, route.chatbot_name
        )
        response = await session.send_message(message.text, context_prefix)

        # Check for pending warehouse zone image
        from chatpilot.core.types import Attachment
        from chatpilot.tools.builtin.warehouse_query import pop_pending_image

        sdk_sid = route.route_id.replace(":", "-")
        # Try with chatbot suffix
        chatbot_name_for_sid = chatbot_manager.get_current_chatbot(
            route.route_id
        ) or route.chatbot_name
        full_sid = f"{sdk_sid}-{chatbot_name_for_sid}"
        pending_img = pop_pending_image(full_sid)
        if pending_img:
            response = Response(
                text=response.text,
                attachments=[Attachment(type="image", url=pending_img)],
            )

        await adapter.send_reply(message, response)

    async def on_command(
        command: str, args: str, message: Message, adapter: ChannelAdapter
    ) -> None:
        route_id = f"{message.platform}:{message.conversation_id}"
        if command == "model" and args.strip():
            await chatbot_manager.switch_model(route_id, args.strip())
            await adapter.send_reply(
                message, Response(text=f"已切換模型為 {args.strip()}")
            )
        elif command == "chatbot":
            arg = args.strip()
            if not arg:
                # Show current chatbot + tools
                current = chatbot_manager.get_current_chatbot(route_id)
                if not current:
                    route = binding_router.resolve(message)
                    current = route.chatbot_name if route else "unknown"
                cfg = chatbot_manager._configs.get(current)
                tools_str = ", ".join(cfg.tools) if cfg else "none"
                await adapter.send_reply(
                    message,
                    Response(
                        text=f"目前: {current}\n"
                        f"Model: {cfg.model if cfg else '?'}\n"
                        f"Tools: {tools_str}"
                    ),
                )
            elif arg == "list":
                names = list(chatbot_manager._configs.keys())
                await adapter.send_reply(
                    message,
                    Response(text=f"可用 chatbot：\n{chr(10).join(names)}"),
                )
            elif not chatbot_manager.has_chatbot(arg):
                await adapter.send_reply(
                    message, Response(text=f"未知的 chatbot: {arg}")
                )
            else:
                await chatbot_manager.switch_chatbot(route_id, arg)
                await adapter.send_reply(
                    message, Response(text=f"已切換 chatbot 為 {arg}")
                )
        else:
            logger.debug("Unknown command: /%s", command)

    hub.set_on_proceed(on_proceed)
    hub.set_on_command(on_command)
    return hub


def _register_tools(
    tool_factory: ToolFactory,
    scheduler: InMemoryTaskScheduler,
    adapters: dict[str, ChannelAdapter],
    memory_store: MemoryStore,
    chatbot_manager: ChatbotManager,
) -> None:
    from chatpilot.tools.builtin.add_reminder import create_add_reminder_tool
    from chatpilot.tools.builtin.browse_task import create_browse_task_tool
    from chatpilot.tools.builtin.cancel_schedule import create_cancel_schedule_tool
    from chatpilot.tools.builtin.delete_custom_prompt import (
        create_delete_custom_prompt_tool,
    )
    from chatpilot.tools.builtin.delete_memo import create_delete_memo_tool
    from chatpilot.tools.builtin.download_media import create_download_media_tool
    from chatpilot.tools.builtin.list_custom_prompts import (
        create_list_custom_prompts_tool,
    )
    from chatpilot.tools.builtin.list_memos import create_list_memos_tool
    from chatpilot.tools.builtin.list_schedules import create_list_schedules_tool
    from chatpilot.tools.builtin.save_custom_prompt import (
        create_save_custom_prompt_tool,
    )
    from chatpilot.tools.builtin.save_memo import create_save_memo_tool
    from chatpilot.tools.builtin.schedule_task_cron import (
        create_schedule_task_cron_tool,
    )
    from chatpilot.tools.builtin.submit_task import create_submit_task_tool
    from chatpilot.tools.builtin.task_history import create_task_history_tool
    from chatpilot.tools.builtin.web_search import create_web_search_tool

    def _get_session(route_id: str):
        return chatbot_manager.get_session(route_id)

    # Warehouse tool
    from chatpilot.tools.builtin.warehouse_query import create_warehouse_query_tool

    tool_factory.register(create_warehouse_query_tool())

    # Task tools
    tool_factory.register(create_submit_task_tool(scheduler))
    tool_factory.register(create_task_history_tool(scheduler))
    tool_factory.register(create_browse_task_tool(scheduler))

    # Search + media
    tool_factory.register(create_web_search_tool())
    tool_factory.register(create_download_media_tool(adapters))

    # Memory tools
    tool_factory.register(create_save_memo_tool(memory_store))
    tool_factory.register(create_list_memos_tool(memory_store))
    tool_factory.register(create_delete_memo_tool(memory_store))
    tool_factory.register(create_save_custom_prompt_tool(memory_store, _get_session))
    tool_factory.register(create_list_custom_prompts_tool(memory_store))
    tool_factory.register(create_delete_custom_prompt_tool(memory_store, _get_session))

    # Reminder + schedule tools
    tool_factory.register(create_add_reminder_tool(memory_store))
    tool_factory.register(create_schedule_task_cron_tool(memory_store))
    tool_factory.register(create_list_schedules_tool(memory_store))
    tool_factory.register(create_cancel_schedule_tool(memory_store))


# ── Lifespan ─────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    app.state.start_time = time.time()

    # Config
    config_path = Path(os.environ.get("ROUTES_PATH", "config/routes.yaml"))
    app.state.config_path = config_path
    config = _load_gateway_config(config_path)

    # Core services
    sdk_client = SdkClient()
    await sdk_client.start()

    memory_store = MemoryStore()
    await memory_store.initialize()

    tool_factory = ToolFactory()
    adapters = _init_adapters()
    app.state.adapters = adapters

    # Routing + chatbot
    binding_router = BindingRouter(config.bindings, config.match_weights)
    chatbot_manager = ChatbotManager(
        sdk_client, config.chatbots, tool_factory, memory_store=memory_store
    )

    # Trigger keywords
    from chatpilot.hub.mention_filter import configure as configure_keywords

    configure_keywords(config.trigger_keywords)

    # Hub
    hub = _init_hub(ContextBuffer(), adapters, binding_router, chatbot_manager)
    app.state.hub = hub

    # Task scheduler + pipeline
    task_store = SqliteTaskStore()
    await task_store.initialize()

    scheduler = InMemoryTaskScheduler(
        store=task_store, max_queue_size=config.scheduler.max_queue_size
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

    # Cron scheduler
    from chatpilot.cron.scheduler import CronScheduler

    cron_scheduler = CronScheduler(
        memory_store=memory_store, hub=hub, task_scheduler=scheduler
    )
    await cron_scheduler.start()

    # Tools
    _register_tools(tool_factory, scheduler, adapters, memory_store, chatbot_manager)
    app.state.scheduler = scheduler

    # Hot reload
    def on_config_reload(new_config: GatewayConfig) -> None:
        binding_router.update(new_config.bindings, new_config.match_weights)
        chatbot_manager.update_configs(new_config.chatbots)
        logger.info("Config reloaded successfully")

    observer = watch_config(config_path, on_config_reload) if config_path.exists() else None

    logger.info("Server started. Webhook: POST /webhook/{platform}")
    yield

    # Shutdown
    await cron_scheduler.stop()
    await runner_pool.stop()
    await task_store.close()
    await memory_store.close()
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
