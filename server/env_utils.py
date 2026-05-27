from __future__ import annotations

import re
from pathlib import Path

_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    """Merge key/value pairs into a profile ``.env`` file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines(keepends=True)

    for key, value in updates.items():
        if not _ENV_VAR_NAME_RE.match(key):
            raise ValueError(f"Invalid environment variable name: {key!r}")
        clean = value.replace("\n", "").replace("\r", "")
        found = False
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"export {key}="):
                lines[idx] = f"{key}={clean}\n"
                found = True
                break
        if not found:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"{key}={clean}\n")

    path.write_text("".join(lines), encoding="utf-8")
