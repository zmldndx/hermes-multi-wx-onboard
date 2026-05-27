from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils import atomic_json_write

from .config import ONBOARD_DIR, REGISTRY_PATH


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class BindingRecord:
    profile: str
    hermes_home: str
    weixin_account_id: str = ""
    weixin_user_id: str = ""
    service_name: str = ""
    gateway_mode: str = ""  # "service" | "detached"
    gateway_pid: Optional[int] = None
    status: str = "pending"  # pending | ready | auth_expired | stopped | error
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    last_error: str = ""
    onboard_session_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BindingRegistry:
    def __init__(self, path: Path = REGISTRY_PATH):
        self._path = path
        self._lock = threading.RLock()

    def _load(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {"bindings": []}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"bindings": []}

    def _save(self, data: Dict[str, Any]) -> None:
        ONBOARD_DIR.mkdir(parents=True, exist_ok=True)
        atomic_json_write(self._path, data)

    def list_bindings(self) -> List[BindingRecord]:
        with self._lock:
            rows = self._load().get("bindings") or []
            return [BindingRecord(**row) for row in rows if isinstance(row, dict)]

    def get_by_profile(self, profile: str) -> Optional[BindingRecord]:
        for row in self.list_bindings():
            if row.profile == profile:
                return row
        return None

    def get_by_session(self, session_id: str) -> Optional[BindingRecord]:
        for row in self.list_bindings():
            if row.onboard_session_id == session_id:
                return row
        return None

    def upsert(self, record: BindingRecord) -> BindingRecord:
        with self._lock:
            data = self._load()
            rows = data.get("bindings") or []
            record.updated_at = _utc_now()
            payload = record.to_dict()
            replaced = False
            for idx, row in enumerate(rows):
                if isinstance(row, dict) and row.get("profile") == record.profile:
                    rows[idx] = payload
                    replaced = True
                    break
            if not replaced:
                rows.append(payload)
            data["bindings"] = rows
            self._save(data)
            return record
