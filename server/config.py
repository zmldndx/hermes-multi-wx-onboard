from __future__ import annotations

import os
from pathlib import Path

from hermes_constants import get_default_hermes_root

ONBOARD_DIR = get_default_hermes_root() / "onboard"
REGISTRY_PATH = ONBOARD_DIR / "registry.json"
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

HOST = os.getenv("ONBOARD_HOST", "0.0.0.0")
PORT = int(os.getenv("ONBOARD_PORT", "8765"))

QR_TIMEOUT_SECONDS = int(os.getenv("ONBOARD_QR_TIMEOUT", "480"))
