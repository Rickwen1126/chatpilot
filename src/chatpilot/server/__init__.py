"""FastAPI application factory and startup lifecycle."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

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
    response_injector=None,
) -> InMemoryMessageHub:
    hub = InMemoryMessageHub(
        context_buffer=context_buffer,
        adapters=adapters,
        resolve_binding=binding_router.resolve,
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

        # Inject pending items from tools (images, links, files)
        from chatpilot.core.types import Attachment

        chatbot_for_sid = chatbot_manager.get_current_chatbot(
            route.route_id
        ) or route.chatbot_name
        sdk_sid = f"{route.route_id.replace(':', '-')}__{chatbot_for_sid}"
        pending = response_injector.pop(sdk_sid)
        if pending:
            attachments = list(response.attachments)
            text = response.text
            for item in pending:
                if item.type == "image":
                    attachments.append(Attachment(type="image", url=item.data))
                elif item.type == "link":
                    # Append link at end to prevent LLM rewriting
                    if item.data not in text:
                        text = f"{text}\n\n👉 {item.data}"
                elif item.type == "file":
                    attachments.append(Attachment(type="file", url=item.data))
            response = Response(text=text, attachments=attachments)

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
    response_injector=None,
    r2_storage: Any = None,
    get_available_tools: Any = None,
    observer_sources: dict | None = None,
) -> None:
    from chatpilot.tools.builtin.add_reminder import create_add_reminder_tool
    from chatpilot.tools.builtin.batch_image_analyze import (
        create_batch_image_analyze_tool,
    )
    from chatpilot.tools.builtin.browse_task import create_browse_task_tool
    from chatpilot.tools.builtin.cancel_schedule import create_cancel_schedule_tool
    from chatpilot.tools.builtin.delete_custom_prompt import (
        create_delete_custom_prompt_tool,
    )
    from chatpilot.tools.builtin.delete_memo import create_delete_memo_tool
    from chatpilot.tools.builtin.document_edit import create_document_edit_tool
    from chatpilot.tools.builtin.download_media import create_download_media_tool
    from chatpilot.tools.builtin.list_custom_prompts import (
        create_list_custom_prompts_tool,
    )
    from chatpilot.tools.builtin.list_memos import create_list_memos_tool
    from chatpilot.tools.builtin.list_schedules import create_list_schedules_tool
    from chatpilot.tools.builtin.quote_search import create_quote_search_tool
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

    # Warehouse + quote tools
    from chatpilot.tools.builtin.warehouse import create_warehouse_tool

    tool_factory.register(create_warehouse_tool(response_injector))
    tool_factory.register(create_quote_search_tool())

    # Task tools
    tool_factory.register(create_submit_task_tool(scheduler))
    tool_factory.register(create_task_history_tool(scheduler))
    tool_factory.register(create_browse_task_tool(scheduler))
    tool_factory.register(create_batch_image_analyze_tool(scheduler))

    # Calendar + search + media
    from chatpilot.tools.builtin.calendar_tool import create_calendar_tool

    tool_factory.register(create_calendar_tool())
    tool_factory.register(create_web_search_tool())
    tool_factory.register(create_download_media_tool(adapters))

    # Browser tools (Chrome CDP)
    from chatpilot.tools.builtin.browser_tools import (
        create_browser_eval_tool,
        create_browser_navigate_tool,
        create_browser_tabs_tool,
    )

    tool_factory.register(create_browser_navigate_tool())
    tool_factory.register(create_browser_eval_tool())
    tool_factory.register(create_browser_tabs_tool())

    # Document edit + show image
    if r2_storage is not None:
        tool_factory.register(create_document_edit_tool(adapters, r2_storage))
        from chatpilot.tools.builtin.show_image import create_show_image_tool

        tool_factory.register(
            create_show_image_tool(adapters, r2_storage, response_injector)
        )

    # Memory tools
    tool_factory.register(create_save_memo_tool(memory_store))
    tool_factory.register(create_list_memos_tool(memory_store))
    tool_factory.register(create_delete_memo_tool(memory_store))
    tool_factory.register(create_save_custom_prompt_tool(memory_store, _get_session))
    tool_factory.register(create_list_custom_prompts_tool(memory_store))
    tool_factory.register(create_delete_custom_prompt_tool(memory_store, _get_session))

    # Reminder + schedule tools
    tool_factory.register(create_add_reminder_tool(memory_store))
    tool_factory.register(
        create_schedule_task_cron_tool(memory_store, get_available_tools)
    )
    tool_factory.register(create_list_schedules_tool(memory_store))
    tool_factory.register(create_cancel_schedule_tool(memory_store))

    # Trigger keyword management
    from chatpilot.tools.builtin.manage_keywords import (
        create_manage_keywords_tool,
    )

    tool_factory.register(create_manage_keywords_tool(memory_store))

    # Observer query tool
    if observer_sources:
        from chatpilot.tools.builtin.query_observations import (
            create_query_observations_tool,
        )

        tool_factory.register(
            create_query_observations_tool(memory_store, observer_sources)
        )


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

    # TimeService — must be first, everything depends on it
    from chatpilot.core.time_service import TimeService

    TimeService.init(config.timezone)
    logger.info("TimeService initialized: %s", config.timezone)

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

    # Image injector
    from chatpilot.core.response_injector import ResponseInjector

    response_injector = ResponseInjector()

    # Trigger keywords + auto-trigger
    from chatpilot.hub.mention_filter import configure as configure_keywords
    from chatpilot.hub.mention_filter import (
        configure_auto_triggers,
        load_route_keywords,
    )

    configure_keywords(config.trigger_keywords)
    configure_auto_triggers({
        name: cfg.auto_trigger_keywords
        for name, cfg in config.chatbots.items()
        if cfg.auto_trigger_keywords
    })

    # Load per-route trigger keywords from DB → in-memory cache
    db_keywords = await memory_store.load_all_trigger_keywords()
    load_route_keywords(db_keywords)

    # Hub
    hub = _init_hub(
        ContextBuffer(), adapters, binding_router, chatbot_manager, response_injector
    )
    app.state.hub = hub
    app.state.chatbot_manager = chatbot_manager
    app.state.binding_router = binding_router

    # Observer mode — register observer routes + batch callback
    observer_sources: dict[str, dict] = {}
    for binding in config.bindings:
        chatbot_name = binding.chatbot
        cfg = config.chatbots.get(chatbot_name)
        if cfg and cfg.observer_mode:
            gid = binding.match.get("group_id", "")
            uid = binding.match.get("user_id", "")
            cid = gid or uid
            if cid:
                # Register for all adapters
                for platform in adapters:
                    rid = f"{platform}:{cid}"
                    hub.register_observer(
                        rid,
                        batch_size=cfg.observer_batch_size,
                        categories=cfg.observer_categories,
                    )
                # Build observer_sources for query tool
                import json as _json
                from pathlib import Path as _Path

                labels: dict = {}
                lp = _Path("data/route_labels.json")
                if lp.exists():
                    labels = _json.loads(lp.read_text("utf-8"))
                # Use line route_id as canonical
                canonical = f"line:{cid}"
                label = labels.get(canonical, chatbot_name)
                # Allow query from any platform
                observer_sources[label] = {
                    "route_id": canonical,
                    "all_route_ids": [
                        f"{p}:{cid}" for p in adapters
                    ],
                    "allowed_consumers": cfg.observer_allowed_consumers,
                }
    app.state.observer_sources = observer_sources

    async def on_observer_batch(
        route_id: str, formatted: str, categories: list[str]
    ) -> None:
        """Process observer batch: LLM summarize → store observation."""
        import uuid

        ts = TimeService.get()
        record_date = ts.today()
        cat_hint = ", ".join(categories) if categories else "自動分類"
        prompt = (
            f"今天日期：{record_date}\n"
            f"整理以下群組對話，按分類（{cat_hint}）提取重點。\n"
            "回傳 JSON array，每筆格式：\n"
            '{"category":"分類","who":"誰","content":"原文",'
            f'"record_date":"{record_date}"}}\n\n'
            "規則：\n"
            "- who：用 user_name\n"
            "- content：保留原文，不改寫不推理\n"
            "- 閒聊（天氣、吃飯等）跳過\n"
            "- 只回傳 JSON array\n\n"
            f"{formatted}"
        )
        logger.info(
            "[observer] %s processing batch, categories=%s",
            route_id, categories,
        )
        try:
            sid = f"observer-{uuid.uuid4().hex[:8]}"
            sdk_session = await sdk_client.create_session(
                sid,
                model="gpt-4.1",
                system_message="你是資訊整理助手。只回傳 JSON array。",
            )
            try:
                logger.info("[observer] %s LLM session=%s", route_id, sid)
                result = await sdk_session.send_and_wait(
                    prompt, timeout=120.0
                )
                logger.info(
                    "[observer] %s LLM result: %d chars",
                    route_id, len(result),
                )
                import json as _json

                # Parse LLM result as JSON entries
                entries = []
                try:
                    entries = _json.loads(result)
                except (_json.JSONDecodeError, TypeError):
                    import re

                    match = re.search(r"\[.*\]", result, re.DOTALL)
                    if match:
                        entries = _json.loads(match.group())

                logger.info(
                    "[observer] %s parsed %d entries from LLM",
                    route_id, len(entries),
                )
                if entries:
                    await memory_store.save(route_id, "observation", {
                        "message_count": len(formatted.split("\n")),
                        "entries": entries,
                        "summary": f"{len(entries)} 筆紀錄",
                    })
                    logger.info(
                        "[observer] %s saved to DB: %d entries",
                        route_id, len(entries),
                    )
                else:
                    logger.info(
                        "[observer] %s no entries to save (all chat?)",
                        route_id,
                    )
            finally:
                await sdk_session.destroy()
        except Exception:
            logger.exception("[observer] batch failed for %s", route_id)

    hub._on_observer_batch = on_observer_batch

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
        memory_store=memory_store,
        hub=hub,
        task_scheduler=scheduler,
        tick_interval=config.cron_scheduler.tick_interval,
        available_tools=config.cron_scheduler.available_tools,
        chatbot_configs=config.chatbots,
    )
    await cron_scheduler.start()

    # R2 storage
    from chatpilot.storage.r2 import R2Storage

    r2_storage = R2Storage()

    # Tools
    def get_available_tools() -> list[str]:
        return config.cron_scheduler.available_tools

    _register_tools(
        tool_factory, scheduler, adapters, memory_store,
        chatbot_manager, response_injector, r2_storage,
        get_available_tools, observer_sources,
    )
    app.state.scheduler = scheduler

    # Pipelines that need tools (registered after _register_tools)
    from chatpilot.pipeline.samples.general_agent import GeneralAgentPipeline

    pipeline_executor.register(
        GeneralAgentPipeline(sdk_client, tool_factory)
    )

    from chatpilot.pipeline.samples.batch_vision import BatchImageVisionPipeline

    pipeline_executor.register(
        BatchImageVisionPipeline(sdk_client, tool_factory)
    )

    from chatpilot.pipeline.samples.schedule_agent import ScheduleAgentPipeline

    pipeline_executor.register(
        ScheduleAgentPipeline(sdk_client, tool_factory)
    )

    # Hot reload
    def on_config_reload(new_config: GatewayConfig) -> None:
        binding_router.update(new_config.bindings, new_config.match_weights)
        chatbot_manager.update_configs(new_config.chatbots)
        # Rebuild config keyword cache (DB cache untouched)
        configure_keywords(new_config.trigger_keywords)
        configure_auto_triggers({
            name: cfg.auto_trigger_keywords
            for name, cfg in new_config.chatbots.items()
            if cfg.auto_trigger_keywords
        })
        logger.info("Config reloaded successfully (keywords refreshed)")

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
