from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hermes_cli import profiles as profiles_mod

from .config import QR_TIMEOUT_SECONDS
from .hermes_bridge import (
    apply_weixin_credentials,
    create_onboard_profile,
    ensure_gateway_running,
    new_profile_name,
    start_profile_gateway,
)
from .registry import BindingRecord, BindingRegistry
from .weixin_qr import qr_login_with_events

logger = logging.getLogger(__name__)


@dataclass
class OnboardSession:
    session_id: str
    profile: str = ""
    profile_dir: str = ""
    status: str = "creating"
    message: str = ""
    qr_url: str = ""
    qr_scan_data: str = ""
    qr_image_base64: str = ""
    account_id: str = ""
    user_id: str = ""
    gateway_pid: Optional[int] = None
    gateway_mode: str = ""
    error: str = ""
    reauth: bool = False
    events: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "profile": self.profile,
            "status": self.status,
            "message": self.message,
            "qr_url": self.qr_url,
            "qr_scan_data": self.qr_scan_data,
            "qr_image_base64": self.qr_image_base64,
            "qr_image_url": f"/api/onboard/sessions/{self.session_id}/qr.png" if self.qr_scan_data else "",
            "account_id": self.account_id,
            "user_id": self.user_id,
            "gateway_pid": self.gateway_pid,
            "gateway_mode": self.gateway_mode,
            "error": self.error,
            "reauth": self.reauth,
            "updated_at": self.updated_at,
        }


class OnboardSessionManager:
    def __init__(self, registry: Optional[BindingRegistry] = None):
        self._sessions: Dict[str, OnboardSession] = {}
        self._lock = threading.RLock()
        self._registry = registry or BindingRegistry()
        self._tasks: Dict[str, asyncio.Task] = {}

    def get(self, session_id: str) -> Optional[OnboardSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def create(self, *, reauth: bool = False, profile: str = "") -> OnboardSession:
        session = OnboardSession(session_id=uuid.uuid4().hex, reauth=reauth, profile=profile)
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def _update(self, session: OnboardSession, **fields: Any) -> None:
        for key, value in fields.items():
            setattr(session, key, value)
        session.updated_at = time.time()

    async def _append_event(self, session: OnboardSession, event: str, payload: Optional[Dict] = None) -> None:
        entry = {"event": event, "payload": payload or {}, "ts": time.time()}
        with self._lock:
            session.events.append(entry)
            session.updated_at = time.time()

    def _make_status_callback(self, session: OnboardSession):
        async def status_callback(event: str, payload: Dict) -> None:
            if event == "waiting":
                qr_scan_data = str(payload.get("qr_scan_data") or payload.get("qr_url") or "")
                self._update(
                    session,
                    status="waiting",
                    message="请使用微信扫描二维码",
                    qr_url=str(payload.get("qr_url") or ""),
                    qr_scan_data=qr_scan_data,
                    qr_image_base64=str(payload.get("qr_image_base64") or ""),
                )
            elif event == "scanned":
                self._update(session, status="scanned", message="已扫码，请在微信中确认")
            elif event == "refreshing":
                self._update(
                    session,
                    status="refreshing",
                    message=f"二维码过期，正在刷新 ({payload.get('attempt')}/3)...",
                )
            elif event == "confirmed":
                self._update(
                    session,
                    status="confirmed",
                    message="微信绑定成功，正在启动 Gateway...",
                    account_id=str(payload.get("account_id") or ""),
                    user_id=str(payload.get("user_id") or ""),
                )
            elif event == "error":
                self._update(
                    session,
                    status="failed",
                    error=str(payload.get("message") or "未知错误"),
                    message=str(payload.get("message") or "绑定失败"),
                )
            await self._append_event(session, event, payload)

        return status_callback

    async def _run_flow(self, session: OnboardSession) -> None:
        try:
            if session.reauth:
                if not session.profile or not profiles_mod.profile_exists(session.profile):
                    raise FileNotFoundError(f"Profile '{session.profile}' does not exist")
                profile = session.profile
                profile_dir = profiles_mod.get_profile_dir(profile)
                self._update(
                    session,
                    profile_dir=str(profile_dir),
                    status="qr",
                    message="正在获取重新绑定二维码...",
                )
            else:
                self._update(session, status="creating", message="正在创建专属 Profile...")
                profile = new_profile_name()
                profile_dir = create_onboard_profile(profile)
                self._update(
                    session,
                    profile=profile,
                    profile_dir=str(profile_dir),
                    status="qr",
                    message="Profile 已创建，正在获取二维码...",
                )

            credentials = await qr_login_with_events(
                str(profile_dir),
                status_callback=self._make_status_callback(session),
                timeout_seconds=QR_TIMEOUT_SECONDS,
            )
            if not credentials:
                if session.status != "failed":
                    self._update(session, status="failed", error="扫码未完成", message="扫码未完成或已超时")
                return

            apply_weixin_credentials(
                profile_dir,
                credentials,
                owner_user_id=str(credentials.get("user_id") or ""),
            )

            self._update(session, status="starting_gateway", message="正在启动 Gateway...")
            if session.reauth:
                gateway_result = await asyncio.to_thread(ensure_gateway_running, profile)
            else:
                gateway_result = await asyncio.to_thread(start_profile_gateway, profile)

            if not gateway_result.get("ok"):
                self._update(
                    session,
                    status="failed",
                    error=str(gateway_result.get("detail") or "Gateway 启动失败"),
                    message="Gateway 启动失败",
                )
                return

            record = self._registry.get_by_profile(profile) or BindingRecord(
                profile=profile,
                hermes_home=str(profile_dir),
                onboard_session_id=session.session_id,
            )
            record.weixin_account_id = credentials.get("account_id", "")
            record.weixin_user_id = credentials.get("user_id", "")
            record.service_name = str(gateway_result.get("service_name") or record.service_name)
            record.gateway_mode = str(gateway_result.get("mode") or "")
            record.gateway_pid = gateway_result.get("gateway_pid")
            record.status = "ready"
            record.last_error = ""
            record.onboard_session_id = session.session_id
            self._registry.upsert(record)

            self._update(
                session,
                status="ready",
                message="绑定完成！请在微信里给 bot 发消息开始对话。",
                account_id=credentials.get("account_id", ""),
                user_id=credentials.get("user_id", ""),
                gateway_pid=gateway_result.get("gateway_pid"),
                gateway_mode=str(gateway_result.get("mode") or ""),
            )
            await self._append_event(session, "ready", gateway_result)
        except Exception as exc:
            logger.exception("onboard session %s failed", session.session_id)
            self._update(
                session,
                status="failed",
                error=str(exc),
                message=f"绑定失败: {exc}",
            )
            await self._append_event(session, "error", {"message": str(exc)})

    def schedule(self, session_id: str) -> None:
        loop = asyncio.get_running_loop()
        session = self.get(session_id)
        if session is None:
            return
        with self._lock:
            existing = self._tasks.get(session_id)
            if existing and not existing.done():
                return
            self._tasks[session_id] = loop.create_task(self._run_flow(session))
