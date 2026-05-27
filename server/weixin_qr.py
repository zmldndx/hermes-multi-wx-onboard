from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional

from gateway.platforms import weixin as wx

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str, Dict], Awaitable[None] | None]


@dataclass
class QrState:
    qrcode_value: str
    qr_scan_data: str
    qr_image_base64: str = ""
    qr_url: str = ""


def make_qr_png_bytes(data: str) -> bytes:
    """Render scannable QR code PNG bytes for the given payload."""
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_qr_image_base64(data: str) -> str:
    if not data:
        return ""
    try:
        return base64.b64encode(make_qr_png_bytes(data)).decode("ascii")
    except Exception as exc:
        logger.warning("QR PNG render failed: %s", exc)
        return ""


async def _emit(cb: Optional[StatusCallback], status: str, payload: Optional[Dict] = None) -> None:
    if cb is None:
        return
    result = cb(status, payload or {})
    if asyncio.iscoroutine(result):
        await result


async def qr_login_with_events(
    hermes_home: str,
    *,
    status_callback: Optional[StatusCallback] = None,
    bot_type: str = "3",
    timeout_seconds: int = 480,
) -> Optional[Dict[str, str]]:
    """Web-friendly QR login; emits status events instead of printing to terminal."""
    if not wx.AIOHTTP_AVAILABLE:
        raise RuntimeError("aiohttp is required for Weixin QR login")

    async with wx.aiohttp.ClientSession(
        trust_env=True, connector=wx._make_ssl_connector()
    ) as session:
        qr_state = await _fetch_qr(session, bot_type=bot_type)
        if qr_state is None:
            await _emit(status_callback, "error", {"message": "无法获取二维码"})
            return None

        await _emit(
            status_callback,
            "waiting",
            {
                "qr_url": qr_state.qr_url,
                "qr_scan_data": qr_state.qr_scan_data,
                "qr_image_base64": qr_state.qr_image_base64,
            },
        )

        deadline = time.monotonic() + timeout_seconds
        current_base_url = wx.ILINK_BASE_URL
        refresh_count = 0
        qrcode_value = qr_state.qrcode_value

        while time.monotonic() < deadline:
            try:
                status_resp = await wx._api_get(
                    session,
                    base_url=current_base_url,
                    endpoint=f"{wx.EP_GET_QR_STATUS}?qrcode={qrcode_value}",
                    timeout_ms=wx.QR_TIMEOUT_MS,
                )
            except asyncio.TimeoutError:
                await asyncio.sleep(1)
                continue
            except Exception as exc:
                logger.warning("weixin QR poll error: %s", exc)
                await asyncio.sleep(1)
                continue

            status = str(status_resp.get("status") or "wait")
            if status == "wait":
                pass
            elif status == "scaned":
                await _emit(status_callback, "scanned", {})
            elif status == "scaned_but_redirect":
                redirect_host = str(status_resp.get("redirect_host") or "")
                if redirect_host:
                    current_base_url = f"https://{redirect_host}"
            elif status == "expired":
                refresh_count += 1
                if refresh_count > 3:
                    await _emit(status_callback, "error", {"message": "二维码多次过期，请重新开始"})
                    return None
                await _emit(status_callback, "refreshing", {"attempt": refresh_count})
                qr_state = await _fetch_qr(session, bot_type=bot_type)
                if qr_state is None:
                    await _emit(status_callback, "error", {"message": "刷新二维码失败"})
                    return None
                qrcode_value = qr_state.qrcode_value
                qr_scan_data = qr_state.qr_scan_data
                await _emit(
                    status_callback,
                    "waiting",
                    {
                        "qr_url": qr_state.qr_url,
                        "qr_scan_data": qr_state.qr_scan_data,
                        "qr_image_base64": qr_state.qr_image_base64,
                    },
                )
            elif status == "confirmed":
                account_id = str(status_resp.get("ilink_bot_id") or "")
                token = str(status_resp.get("bot_token") or "")
                base_url = str(status_resp.get("baseurl") or wx.ILINK_BASE_URL)
                user_id = str(status_resp.get("ilink_user_id") or "")
                if not account_id or not token:
                    await _emit(status_callback, "error", {"message": "登录成功但凭证不完整"})
                    return None
                wx.save_weixin_account(
                    hermes_home,
                    account_id=account_id,
                    token=token,
                    base_url=base_url,
                    user_id=user_id,
                )
                await _emit(
                    status_callback,
                    "confirmed",
                    {"account_id": account_id, "user_id": user_id},
                )
                return {
                    "account_id": account_id,
                    "token": token,
                    "base_url": base_url,
                    "user_id": user_id,
                }
            await asyncio.sleep(1)

        await _emit(status_callback, "error", {"message": "扫码登录超时"})
        return None


async def _fetch_qr(session, *, bot_type: str) -> Optional[QrState]:
    try:
        qr_resp = await wx._api_get(
            session,
            base_url=wx.ILINK_BASE_URL,
            endpoint=f"{wx.EP_GET_BOT_QR}?bot_type={bot_type}",
            timeout_ms=wx.QR_TIMEOUT_MS,
        )
    except Exception as exc:
        logger.error("failed to fetch Weixin QR: %s", exc)
        return None

    qrcode_value = str(qr_resp.get("qrcode") or "")
    qrcode_url = str(qr_resp.get("qrcode_img_content") or "")
    if not qrcode_value:
        return None
    qr_scan_data = qrcode_url if qrcode_url else qrcode_value
    return QrState(
        qrcode_value=qrcode_value,
        qr_scan_data=qr_scan_data,
        qr_url=qrcode_url,
        qr_image_base64=_make_qr_image_base64(qr_scan_data),
    )
