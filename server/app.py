from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from gateway.platforms.weixin import check_weixin_requirements

from hermes_cli import profiles as profiles_mod

from .config import HOST, PORT, WEB_DIR
from .hermes_bridge import ensure_gateway_running
from .registry import BindingRegistry
from .sessions import OnboardSessionManager
from .watchdog import GatewayWatchdog
from .weixin_qr import make_qr_png_bytes

logger = logging.getLogger(__name__)

registry = BindingRegistry()
sessions = OnboardSessionManager(registry)
watchdog = GatewayWatchdog(registry)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await watchdog.start()
    yield
    await watchdog.stop()


app = FastAPI(title="Hermes Weixin Onboard", lifespan=lifespan)


class ReauthRequest(BaseModel):
    profile: str = Field(..., min_length=1)


@app.get("/api/health")
async def health():
    qr_ready = False
    try:
        make_qr_png_bytes("health-check")
        qr_ready = True
    except Exception as exc:
        logger.warning("QR render health check failed: %s", exc)
    return {
        "ok": True,
        "weixin_ready": check_weixin_requirements(),
        "qr_render_ready": qr_ready,
        "web_dir": str(WEB_DIR),
    }


@app.post("/api/onboard/sessions")
async def create_onboard_session():
    if not check_weixin_requirements():
        raise HTTPException(
            status_code=503,
            detail="缺少 Weixin 依赖，请安装: pip install aiohttp cryptography qrcode",
        )
    session = sessions.create()
    sessions.schedule(session.session_id)
    return {"session": session.to_public_dict()}


@app.get("/api/onboard/sessions/{session_id}/qr.png")
async def get_session_qr_png(session_id: str):
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    scan_data = (session.qr_scan_data or session.qr_url or "").strip()
    if not scan_data:
        raise HTTPException(status_code=404, detail="QR code not ready")
    try:
        png = await asyncio.to_thread(make_qr_png_bytes, scan_data)
    except Exception as exc:
        logger.exception("failed to render QR PNG for session %s", session_id)
        raise HTTPException(status_code=500, detail=f"QR render failed: {exc}") from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/onboard/sessions/{session_id}")
async def get_onboard_session(session_id: str):
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session.to_public_dict()}


@app.post("/api/onboard/reauth")
async def reauth_onboard(body: ReauthRequest):
    if not check_weixin_requirements():
        raise HTTPException(status_code=503, detail="缺少 Weixin 依赖")
    profile = body.profile.strip()
    if not profiles_mod.profile_exists(profile):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' does not exist")
    session = sessions.create(reauth=True, profile=profile)
    sessions.schedule(session.session_id)
    return {"session": session.to_public_dict()}


@app.get("/api/bindings")
async def list_bindings():
    rows = registry.list_bindings()
    return {"bindings": [row.to_dict() for row in rows]}


@app.post("/api/bindings/{profile}/restart-gateway")
async def restart_binding_gateway(profile: str):
    if not registry.get_by_profile(profile):
        raise HTTPException(status_code=404, detail="Binding not found")
    result = await asyncio.to_thread(ensure_gateway_running, profile)
    record = registry.get_by_profile(profile)
    if record and result.get("ok"):
        record.gateway_pid = result.get("gateway_pid")
        record.status = "ready"
        record.last_error = ""
        registry.upsert(record)
    return result


@app.websocket("/api/onboard/sessions/{session_id}/ws")
async def onboard_session_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    last_ts = 0.0
    try:
        while True:
            session = sessions.get(session_id)
            if session is None:
                await websocket.send_json({"error": "session not found"})
                break
            if session.updated_at > last_ts:
                await websocket.send_json({"session": session.to_public_dict()})
                last_ts = session.updated_at
            if session.status in {"ready", "failed"}:
                await websocket.send_json({"done": True, "session": session.to_public_dict()})
                break
            await asyncio.sleep(0.8)
    except WebSocketDisconnect:
        return


static_dir = WEB_DIR
if static_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(static_dir)), name="assets")


@app.get("/")
async def index():
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_path)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
