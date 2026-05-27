from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from hermes_cli import profiles as profiles_mod

from .hermes_bridge import ensure_gateway_running, gateway_is_running
from .registry import BindingRegistry

logger = logging.getLogger(__name__)


class GatewayWatchdog:
    """Periodically restart profile gateways that are registered but not running."""

    def __init__(
        self,
        registry: BindingRegistry,
        *,
        interval_seconds: float = 60.0,
    ):
        self._registry = registry
        self._interval = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="onboard-gateway-watchdog")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("gateway watchdog tick failed")
            await asyncio.sleep(self._interval)

    async def _tick(self) -> None:
        for record in self._registry.list_bindings():
            if record.status != "ready":
                continue
            profile_dir = profiles_mod.get_profile_dir(record.profile)
            if gateway_is_running(profile_dir):
                continue
            logger.warning("Gateway for profile %s is down; restarting", record.profile)
            result = await asyncio.to_thread(ensure_gateway_running, record.profile)
            if result.get("ok"):
                record.gateway_pid = result.get("gateway_pid")
                record.last_error = ""
                self._registry.upsert(record)
            else:
                record.status = "error"
                record.last_error = str(result.get("detail") or result.get("message") or "restart failed")
                self._registry.upsert(record)
