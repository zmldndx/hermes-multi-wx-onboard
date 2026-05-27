from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.env_utils import update_env_file


def test_update_env_file_merge(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENROUTER_API_KEY=abc\nWEIXIN_TOKEN=old\n", encoding="utf-8")

    update_env_file(
        env_path,
        {
            "WEIXIN_TOKEN": "new-token",
            "WEIXIN_ACCOUNT_ID": "bot@im.bot",
        },
    )

    text = env_path.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=abc" in text
    assert "WEIXIN_TOKEN=new-token" in text
    assert "WEIXIN_ACCOUNT_ID=bot@im.bot" in text
    assert "WEIXIN_TOKEN=old" not in text
