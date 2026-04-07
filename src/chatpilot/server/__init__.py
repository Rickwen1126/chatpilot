"""FastAPI application factory and startup lifecycle."""

from __future__ import annotations

import asyncio
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
from chatpilot.core.route_bindings import RouteBindingService
from chatpilot.core.types import Message, Response
from chatpilot.files.center import FileHandleCenter
from chatpilot.files.ingress import InboundFilePreprocessor
from chatpilot.files.policy import DEFAULT_CLEANUP_INTERVAL_SECONDS
from chatpilot.files.store import SqliteFileStore
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
from chatpilot.tools.session_context import (
    SessionContextRegistry,
    build_sdk_session_id,
)

logger = logging.getLogger(__name__)


# ── Startup helpers ──────────────────────────────────────────────


def _load_gateway_config(
    settings_path: Path,
    bindings_path: Path | None = None,
) -> GatewayConfig:
    try:
        return load_config(settings_path, bindings_path)
    except FileNotFoundError:
        logger.warning("Config not found: %s — using defaults", settings_path)
        return GatewayConfig()


def _is_queryable_observer_platform(platform: str) -> bool:
    """Return True for platforms that should contribute persisted observer source data.

    `cli` and `mock` are useful ingress/test adapters, but their observations
    should not be merged into user-facing sources queried from real chats.
    """
    return platform not in {"cli", "mock"}


def _init_adapters(config: GatewayConfig) -> dict[str, ChannelAdapter]:
    adapters: dict[str, ChannelAdapter] = {}
    from chatpilot.adapters.cli import CliAdapter

    adapters["cli"] = CliAdapter()

    try:
        from chatpilot.adapters.line.adapter import LineAdapter

        line_channels = config.adapters.get("line", [])
        if line_channels:
            for channel in line_channels:
                secret = os.environ.get(channel.channel_secret_env, "")
                token = os.environ.get(channel.channel_token_env, "")
                if not secret or not token:
                    logger.warning(
                        "Skip LINE channel %s (missing env: %s / %s)",
                        channel.name,
                        channel.channel_secret_env,
                        channel.channel_token_env,
                    )
                    continue
                adapter = LineAdapter(
                    name=channel.name,
                    secret=secret,
                    token=token,
                )
                adapters[adapter.platform] = adapter
        else:
            logger.error(
                "Legacy LINE adapter fallback enabled: config.adapters.line[] "
                "is missing or empty. This path should only be used for "
                "migration/debug catch-up."
            )
            adapters["line"] = LineAdapter()
    except Exception:
        logger.warning("LINE adapter not available (missing env vars?)")

    from chatpilot.adapters.mock import MockAdapter

    adapters["mock"] = MockAdapter()
    return adapters


def _refresh_observer_state(
    *,
    hub: InMemoryMessageHub,
    adapters: dict[str, ChannelAdapter],
    config: GatewayConfig,
    observation_groups: dict[str, dict],
) -> None:
    """Rebuild observer registrations and group membership metadata.

    Current implementation supports group-based query identity for both:
    - silent capture routes (`reply=never + processing=none + capture`)
    - interactive capture routes (`reply=addressed + processing=interactive + capture`)
    """

    hub.clear_observers()
    hub.clear_route_policies()
    observation_groups.clear()

    def _apply_route_runtime_policy(
        *,
        route_id: str,
        platform: str,
        reply_policy: str,
        processing_policy: str,
        observation,
    ) -> None:
        capture = observation.capture if observation is not None else None
        consume = observation.consume if observation is not None else []
        hub.register_route_policy(
            route_id,
            reply_policy=reply_policy,
            processing_policy=processing_policy,
            capture_enabled=capture is not None,
        )

        def _ensure_group(name: str) -> dict[str, list[str]]:
            return observation_groups.setdefault(
                name,
                {
                    "source_route_ids": [],
                    "consumer_route_ids": [],
                },
            )

        for group in consume:
            state = _ensure_group(group)
            if route_id not in state["consumer_route_ids"]:
                state["consumer_route_ids"].append(route_id)

        if capture is None:
            return

        profile = config.observation_profiles.get(capture.profile)
        if profile is None:
            logger.warning(
                "Observer capture profile missing for group=%s profile=%s",
                capture.group, capture.profile,
            )
            return

        state = _ensure_group(capture.group)
        hub.register_capture(
            route_id,
            batch_size=profile.batch_size,
            categories=profile.categories,
        )
        if _is_queryable_observer_platform(platform):
            if route_id not in state["source_route_ids"]:
                state["source_route_ids"].append(route_id)

    for binding in config.bindings:
        gid = binding.match.get("group_id", "")
        uid = binding.match.get("user_id", "")
        cid = gid or uid
        if not cid:
            continue

        match_platform = binding.match.get("platform")
        if match_platform:
            platforms = [match_platform] if match_platform in adapters else []
        else:
            platforms = list(adapters)

        obs = binding.observation
        for platform in platforms:
            route_id = f"{platform}:{cid}"
            _apply_route_runtime_policy(
                route_id=route_id,
                platform=platform,
                reply_policy=binding.reply_policy,
                processing_policy=binding.processing_policy,
                observation=obs,
            )


def _init_hub(
    context_buffer: ContextBuffer,
    adapters: dict[str, ChannelAdapter],
    binding_router: BindingRouter,
    chatbot_manager: ChatbotManager,
    response_injector=None,
    stt_transcriber=None,
    file_ingress: InboundFilePreprocessor | None = None,
    file_handle_center: FileHandleCenter | None = None,
) -> InMemoryMessageHub:
    hub = InMemoryMessageHub(
        context_buffer=context_buffer,
        adapters=adapters,
        resolve_binding=binding_router.resolve,
        stt_transcriber=stt_transcriber,
        file_ingress=file_ingress,
        file_handle_center=file_handle_center,
    )

    async def on_proceed(
        message: Message, context_prefix: str | None, adapter: ChannelAdapter
    ) -> None:
        route = binding_router.resolve(message)
        if route is None:
            logger.warning("No binding matched for %s", message.conversation_id)
            return
        logger.info(
            "[route] %s → chatbot=%s (score=%d)",
            route.route_id, route.chatbot_name, route.binding_score,
        )
        hint = getattr(adapter, "format_hint", None)
        if hint:
            context_prefix = f"{context_prefix}\n{hint}" if context_prefix else hint
        session = await chatbot_manager.get_or_create_session(
            route.route_id, route.chatbot_name
        )
        response = await session.send_message(message.text, context_prefix)
        logger.info(
            "[response] %s → %d chars: %s",
            route.route_id, len(response.text),
            response.text[:150].replace("\n", " "),
        )

        # Inject pending items from tools (images, links, files)
        from chatpilot.core.types import Attachment

        chatbot_for_sid = chatbot_manager.get_current_chatbot(
            route.route_id
        ) or route.chatbot_name
        sdk_sid = build_sdk_session_id(route.route_id, chatbot_for_sid)
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
                configured_model = chatbot_manager.get_configured_model(
                    current
                )
                effective_model = chatbot_manager.get_effective_model(
                    route_id, current
                )
                runtime_model = None
                session = chatbot_manager.get_session(route_id)
                if session is not None:
                    runtime_model = await session.get_runtime_model()
                model_lines = [
                    f"Effective model: {effective_model or '?'}",
                    f"Configured model: {configured_model or '?'}",
                ]
                if runtime_model:
                    model_lines.append(f"SDK current model: {runtime_model}")
                await adapter.send_reply(
                    message,
                    Response(
                        text=f"目前: {current}\n"
                        f"{chr(10).join(model_lines)}\n"
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
    file_handle_center: FileHandleCenter,
    memory_store: MemoryStore,
    chatbot_manager: ChatbotManager,
    response_injector=None,
    r2_storage: Any = None,
    get_available_tools: Any = None,
    observation_groups: dict | None = None,
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
    tool_factory.register(create_download_media_tool(adapters, file_handle_center))

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
        tool_factory.register(
            create_document_edit_tool(adapters, r2_storage, file_handle_center)
        )
        from chatpilot.tools.builtin.show_image import create_show_image_tool

        tool_factory.register(
            create_show_image_tool(
                adapters,
                r2_storage,
                response_injector,
                file_handle_center,
            )
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
    if observation_groups:
        from chatpilot.tools.builtin.query_observations import (
            create_query_observations_tool,
        )

        tool_factory.register(
            create_query_observations_tool(memory_store, observation_groups)
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
    logging.getLogger("chatpilot").setLevel(logging.INFO)
    app.state.start_time = time.time()

    # Config
    settings_env = (
        os.environ.get("ROUTE_SETTINGS_PATH")
        or os.environ.get("ROUTES_PATH")
    )
    settings_path = Path(
        settings_env
        or (
            "config/route_settings.yaml"
            if Path("config/route_settings.yaml").exists()
            else "config/routes.yaml"
        )
    )
    bindings_path = Path(
        os.environ.get("ROUTE_BINDINGS_PATH", "config/route_bindings.yaml")
    )
    app.state.route_settings_path = settings_path
    app.state.route_bindings_path = bindings_path
    config = _load_gateway_config(settings_path, bindings_path)
    route_binding_service = RouteBindingService(bindings_path)
    route_binding_service.load()
    if not route_binding_service.merged_bindings() and config.bindings:
        route_binding_service.replace_fallback_bindings(config.bindings)
    config.bindings = route_binding_service.merged_bindings()

    # TimeService — must be first, everything depends on it
    from chatpilot.core.time_service import TimeService

    TimeService.init(config.timezone)
    logger.info("TimeService initialized: %s", config.timezone)

    # Core services
    sdk_client = SdkClient()
    await sdk_client.start()

    memory_store = MemoryStore(
        db_path=os.environ.get("CHATPILOT_DB", "data/chatpilot.db")
    )
    await memory_store.initialize()

    file_store = SqliteFileStore(
        db_path=os.environ.get("CHATPILOT_FILES_DB", "data/files.db")
    )
    await file_store.initialize()

    session_context_registry = SessionContextRegistry()
    tool_factory = ToolFactory(
        session_context_registry=session_context_registry
    )
    adapters = _init_adapters(config)
    app.state.adapters = adapters
    file_center = FileHandleCenter(
        file_store,
        adapters,
        asset_root=os.environ.get(
            "CHATPILOT_FILE_ASSETS_DIR",
            "data/file_assets",
        ),
    )
    file_ingress = InboundFilePreprocessor(file_center)
    app.state.file_store = file_store
    app.state.file_handle_center = file_center
    app.state.file_ingress = file_ingress
    cleanup_interval = int(
        os.environ.get(
            "CHATPILOT_FILE_CLEANUP_INTERVAL_SECONDS",
            str(DEFAULT_CLEANUP_INTERVAL_SECONDS),
        )
    )
    cleanup_task: asyncio.Task[None] | None = None

    async def _run_file_cleanup_loop() -> None:
        while True:
            try:
                await file_center.cleanup_expired()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[file] cleanup loop failed")
            await asyncio.sleep(cleanup_interval)

    if cleanup_interval > 0:
        cleanup_task = asyncio.create_task(_run_file_cleanup_loop())
        app.state.file_cleanup_task = cleanup_task
        logger.info(
            "[file] cleanup loop started interval=%ss",
            cleanup_interval,
        )

    # Routing + chatbot
    binding_router = BindingRouter(
        config.bindings,
        config.match_weights,
    )
    chatbot_manager = ChatbotManager(
        sdk_client,
        config.chatbots,
        tool_factory,
        memory_store=memory_store,
        session_context_registry=session_context_registry,
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

    # STT Transcriber
    from chatpilot.stt import SttTranscriber

    stt = SttTranscriber()

    # Hub
    hub = _init_hub(
        ContextBuffer(), adapters, binding_router, chatbot_manager,
        response_injector, stt_transcriber=stt,
        file_ingress=file_ingress, file_handle_center=file_center,
    )
    app.state.hub = hub
    app.state.chatbot_manager = chatbot_manager
    app.state.binding_router = binding_router
    app.state.route_binding_service = route_binding_service
    app.state.session_context_registry = session_context_registry
    app.state.config = config

    # Observer mode — register observer routes + batch callback
    observation_groups: dict[str, dict] = {}
    app.state.observation_groups = observation_groups

    def refresh_routing_runtime() -> None:
        current_config = app.state.config
        current_config.bindings = route_binding_service.merged_bindings()
        binding_router.update(current_config.bindings, current_config.match_weights)
        _refresh_observer_state(
            hub=hub,
            adapters=adapters,
            config=current_config,
            observation_groups=observation_groups,
        )

    refresh_routing_runtime()
    app.state.refresh_routing_runtime = refresh_routing_runtime

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
                model="gpt-5.4",
                system_message="你是資訊整理助手。只回傳 JSON array。",
            )
            try:
                logger.info(
                    "[observer] %s worker_session=%s lane=observation",
                    route_id,
                    sid,
                )
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
    task_store = SqliteTaskStore(
        db_path=os.environ.get("CHATPILOT_TASK_DB", "data/tasks.db")
    )
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
        tick_interval=int(os.environ.get(
            "CHATPILOT_TICK_INTERVAL",
            str(config.cron_scheduler.tick_interval),
        )),
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
        tool_factory, scheduler, adapters, file_center, memory_store,
        chatbot_manager, response_injector, r2_storage,
        get_available_tools, observation_groups,
    )
    app.state.scheduler = scheduler

    # Pipelines that need tools (registered after _register_tools)
    from chatpilot.pipeline.samples.general_agent import GeneralAgentPipeline

    pipeline_executor.register(
        GeneralAgentPipeline(sdk_client, tool_factory)
    )

    from chatpilot.pipeline.samples.batch_vision import BatchImageVisionPipeline

    pipeline_executor.register(
        BatchImageVisionPipeline(
            sdk_client,
            tool_factory,
            file_center,
            adapters,
        )
    )

    from chatpilot.pipeline.samples.schedule_agent import ScheduleAgentPipeline

    pipeline_executor.register(
        ScheduleAgentPipeline(sdk_client, tool_factory)
    )

    # Hot reload
    def on_config_reload(new_config: GatewayConfig) -> None:
        route_binding_service.load()
        if not route_binding_service.merged_bindings() and new_config.bindings:
            route_binding_service.replace_fallback_bindings(new_config.bindings)
        new_config.bindings = route_binding_service.merged_bindings()
        adapters.clear()
        adapters.update(_init_adapters(new_config))
        binding_router.update(new_config.bindings, new_config.match_weights)
        chatbot_manager.update_configs(new_config.chatbots)
        app.state.config = new_config
        refresh_routing_runtime()
        # Rebuild config keyword cache (DB cache untouched)
        configure_keywords(new_config.trigger_keywords)
        configure_auto_triggers({
            name: cfg.auto_trigger_keywords
            for name, cfg in new_config.chatbots.items()
            if cfg.auto_trigger_keywords
        })
        logger.info(
            "Config reloaded successfully (keywords/observers refreshed)"
        )

    app.state.reload_config = lambda: on_config_reload(
        _load_gateway_config(settings_path, bindings_path)
    )

    observer = (
        watch_config(
            [settings_path, bindings_path],
            lambda: _load_gateway_config(settings_path, bindings_path),
            on_config_reload,
        )
        if settings_path.exists() or bindings_path.exists()
        else None
    )

    logger.info("Server started. Webhook: POST /webhook/{platform}")
    yield

    # Shutdown
    if cleanup_task is not None:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    await cron_scheduler.stop()
    await runner_pool.stop()
    await task_store.close()
    await file_store.close()
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
