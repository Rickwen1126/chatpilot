"""CronScheduler — periodic scan of Memory Store for due items."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from chatpilot.core.time_service import TimeService
from chatpilot.cron.parser import calculate_next_run
from chatpilot.memory.types import MemoryStatus

logger = logging.getLogger(__name__)


class CronScheduler:
    """Scans Memory Store for due reminders and schedules."""

    def __init__(
        self,
        memory_store,
        hub,
        task_scheduler=None,
        tick_interval: int = 60,
        available_tools: list[str] | None = None,
        chatbot_configs: dict | None = None,
    ) -> None:
        self._memory_store = memory_store
        self._hub = hub
        self._task_scheduler = task_scheduler
        self._tick_interval = tick_interval
        self._available_tools = available_tools or []
        self._chatbot_configs = chatbot_configs or {}
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._tick_loop())
        logger.info(
            "CronScheduler started (tick=%ds)", self._tick_interval
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CronScheduler stopped")

    async def _tick_loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("CronScheduler tick error")
            await asyncio.sleep(self._tick_interval)

    async def _tick(self) -> None:
        now = TimeService.get().utc_now()

        # Scan due reminders
        due_reminders = await self._memory_store.query_due_before(
            "reminder", now
        )
        if due_reminders:
            logger.info(
                "[cron] tick found %d due reminders", len(due_reminders)
            )
        for r in due_reminders:
            await self._handle_reminder(r)

        # Scan due schedules
        due_schedules = await self._memory_store.query_due_before(
            "schedule", now
        )
        if due_schedules:
            logger.info(
                "[cron] tick found %d due schedules", len(due_schedules)
            )
        for s in due_schedules:
            await self._handle_schedule(s)

        # Warn about failed items
        await self._warn_failed()

    async def _handle_reminder(self, reminder: dict) -> None:
        rid = reminder["id"]
        route_id = reminder["route_id"]
        text = reminder.get("text", "")

        # Mark running
        await self._memory_store.update(
            route_id, "reminder", rid, {"status": MemoryStatus.running.value}
        )

        try:
            if self._task_scheduler is None:
                raise RuntimeError("No task_scheduler configured")

            import uuid

            from chatpilot.core.types import TaskInfo

            task = TaskInfo(
                id=str(uuid.uuid4()),
                created_at=TimeService.get().utc_now(),
                pipeline_name="general-agent",
                input_summary=f"提醒：{text}",
                input_data={"description": f"提醒使用者：{text}"},
                chat_route_id=route_id,
            )
            await self._task_scheduler.enqueue(task)

            # Mark completed (task enqueued successfully)
            await self._memory_store.update(
                route_id, "reminder", rid,
                {"status": MemoryStatus.completed.value},
            )
            logger.info(
                "Reminder %s enqueued as general-agent task for %s",
                rid[:8], route_id[:16],
            )
        except Exception as e:
            await self._memory_store.update(
                route_id, "reminder", rid,
                {
                    "status": MemoryStatus.failed.value,
                    "last_error": str(e),
                },
            )
            logger.error(
                "Reminder %s failed: %s", rid[:8], e
            )

    async def _handle_schedule(self, schedule: dict) -> None:
        sid = schedule["id"]
        route_id = schedule["route_id"]
        tool_name = schedule.get("tool_name", "")
        cron_expr = schedule.get("cron_expr", "")
        chatbot_name = schedule.get("chatbot_name", "")

        # Mark running
        await self._memory_store.update(
            route_id, "schedule", sid,
            {"status": MemoryStatus.running.value},
        )

        try:
            if self._task_scheduler is None:
                raise RuntimeError("No task_scheduler configured")

            import uuid

            from chatpilot.core.types import TaskInfo

            # Resolve chatbot_name → tool list at trigger time
            input_data = dict(schedule.get("input_data", {}))
            if chatbot_name:
                cfg = self._chatbot_configs.get(chatbot_name)
                if cfg:
                    tools = cfg.tools if hasattr(cfg, "tools") else []
                    input_data["chatbot_tools"] = tools
                    input_data["chatbot_name"] = chatbot_name

            task = TaskInfo(
                id=str(uuid.uuid4()),
                created_at=TimeService.get().utc_now(),
                pipeline_name=tool_name,
                input_summary=f"Cron: {cron_expr}",
                input_data=input_data,
                chat_route_id=route_id,
            )
            await self._task_scheduler.enqueue(task)

            # Calculate next run + reset to pending
            next_run = calculate_next_run(cron_expr)
            await self._memory_store.update(
                route_id, "schedule", sid,
                {
                    "status": MemoryStatus.pending.value,
                    "last_run_at": TimeService.get().utc_now().isoformat(),
                    "next_run_at": next_run.isoformat(),
                },
            )
            logger.info(
                "Schedule %s triggered, next=%s",
                sid[:8], next_run.isoformat(),
            )
        except Exception as e:
            await self._memory_store.update(
                route_id, "schedule", sid,
                {
                    "status": MemoryStatus.failed.value,
                    "last_error": str(e),
                },
            )
            logger.error("Schedule %s failed: %s", sid[:8], e)

    async def _warn_failed(self) -> None:
        """Log warnings for failed items."""
        for type_name in ("reminder", "schedule"):
            try:
                all_items = await self._memory_store.query_due_before(
                    type_name, datetime(9999, 1, 1, tzinfo=timezone.utc)
                )
            except Exception:
                continue
            failed = [
                i for i in all_items
                if i.get("status") == MemoryStatus.failed.value
            ]
            for item in failed:
                logger.warning(
                    "Failed %s %s: %s",
                    type_name, item["id"][:8],
                    item.get("last_error", "unknown"),
                )
