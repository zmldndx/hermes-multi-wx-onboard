#!/usr/bin/env python3
"""Entry point: python run.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

hermes_root = os.environ.get("HERMES_AGENT_ROOT", "").strip()
if not hermes_root:
    sibling = REPO_ROOT.parent / "hermes-agent"
    if sibling.is_dir():
        hermes_root = str(sibling.resolve())
if hermes_root:
    hermes_path = str(Path(hermes_root).resolve())
    if hermes_path not in sys.path:
        sys.path.insert(0, hermes_path)
else:
    print(
        "错误: 未找到 hermes-agent。请设置 HERMES_AGENT_ROOT 或将本仓库与 hermes-agent 并列放置。",
        file=sys.stderr,
    )
    sys.exit(1)

from server.app import main

if __name__ == "__main__":
    main()
