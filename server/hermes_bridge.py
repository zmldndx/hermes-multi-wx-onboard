from __future__ import annotations

import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from hermes_cli import profiles as profiles_mod

from .env_utils import update_env_file

logger = logging.getLogger(__name__)


def new_profile_name() -> str:
    return f"wx-{uuid.uuid4().hex[:8]}"


def create_onboard_profile(name: str) -> Path:
    """Create a named profile cloned from default config/.env for API keys."""
    return profiles_mod.create_profile(
        name,
        clone_from="default",
        clone_config=True,
        no_alias=True,
    )


def apply_weixin_credentials(
    profile_dir: Path,
    credentials: Dict[str, str],
    *,
    owner_user_id: str = "",
) -> None:
    env_path = profile_dir / ".env"
    updates = {
        "WEIXIN_ACCOUNT_ID": credentials.get("account_id", ""),
        "WEIXIN_TOKEN": credentials.get("token", ""),
        "WEIXIN_BASE_URL": credentials.get("base_url", "") or "https://ilinkai.weixin.qq.com",
        "WEIXIN_CDN_BASE_URL": "https://novac2c.cdn.weixin.qq.com/c2c",
        "WEIXIN_DM_POLICY": "open",
        "WEIXIN_GROUP_POLICY": "disabled",
    }
    if owner_user_id:
        updates["WEIXIN_ALLOWED_USERS"] = owner_user_id
        updates["WEIXIN_DM_POLICY"] = "allowlist"
    update_env_file(env_path, updates)


def _profile_env(profile: str, profile_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HERMES_HOME"] = str(profile_dir.resolve())
    return env


def _run_hermes(profile: str, profile_dir: Path, args: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "hermes_cli.main", "--profile", profile, *args]
    logger.info("Running: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        env=_profile_env(profile, profile_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _service_name(profile: str) -> str:
    try:
        from hermes_cli.gateway import get_service_name

        prev = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(profiles_mod.get_profile_dir(profile).resolve())
        try:
            return get_service_name()
        finally:
            if prev is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = prev
    except Exception:
        return f"hermes-gateway-{profile}"


def start_profile_gateway(profile: str) -> Dict[str, Any]:
    """Install/start a profile gateway service, with detached fallback."""
    profile_dir = profiles_mod.get_profile_dir(profile)
    service_name = _service_name(profile)

    install = _run_hermes(profile, profile_dir, ["gateway", "install"])
    if install.returncode != 0:
        logger.warning(
            "gateway install failed for %s: %s",
            profile,
            install.stderr or install.stdout,
        )
        return _start_detached_gateway(profile, profile_dir, service_name, install.stderr or install.stdout)

    start = _run_hermes(profile, profile_dir, ["gateway", "start"])
    if start.returncode != 0:
        logger.warning(
            "gateway start failed for %s: %s",
            profile,
            start.stderr or start.stdout,
        )
        return _start_detached_gateway(profile, profile_dir, service_name, start.stderr or start.stdout)

    pid = _read_gateway_pid(profile_dir)
    return {
        "ok": True,
        "mode": "service",
        "service_name": service_name,
        "gateway_pid": pid,
        "message": "Gateway 已通过系统服务启动",
        "detail": (start.stdout or "").strip(),
    }


def _start_detached_gateway(
    profile: str,
    profile_dir: Path,
    service_name: str,
    reason: str,
) -> Dict[str, Any]:
    from hermes_cli._subprocess_compat import windows_detach_popen_kwargs

    cmd = [sys.executable, "-m", "hermes_cli.main", "--profile", profile, "gateway", "run", "--replace"]
    kwargs = windows_detach_popen_kwargs()
    proc = subprocess.Popen(
        cmd,
        env=_profile_env(profile, profile_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )
    return {
        "ok": True,
        "mode": "detached",
        "service_name": service_name,
        "gateway_pid": proc.pid,
        "message": "Gateway 以独立进程方式启动（服务安装/启动失败时的回退）",
        "detail": reason.strip(),
    }


def _read_gateway_pid(profile_dir: Path) -> Optional[int]:
    pid_path = profile_dir / "gateway.pid"
    if not pid_path.exists():
        return None
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        return pid if pid > 0 else None
    except (OSError, ValueError):
        return None


def gateway_is_running(profile_dir: Path) -> bool:
    pid = _read_gateway_pid(profile_dir)
    if not pid:
        return False
    from gateway.status import _pid_exists

    return _pid_exists(pid)


def ensure_gateway_running(profile: str) -> Dict[str, Any]:
    profile_dir = profiles_mod.get_profile_dir(profile)
    if gateway_is_running(profile_dir):
        return {
            "ok": True,
            "restarted": False,
            "gateway_pid": _read_gateway_pid(profile_dir),
            "message": "Gateway 已在运行",
        }
    result = start_profile_gateway(profile)
    result["restarted"] = True
    return result
