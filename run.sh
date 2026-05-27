#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif [[ -f venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
else
  echo "未找到 .venv 或 venv，请先创建虚拟环境：" >&2
  echo "  python3 -m venv .venv && source .venv/bin/activate" >&2
  exit 1
fi

if [[ -z "${HERMES_AGENT_ROOT:-}" ]]; then
  if [[ -d "$REPO_ROOT/../hermes-agent" ]]; then
    HERMES_AGENT_ROOT="$(cd "$REPO_ROOT/../hermes-agent" && pwd)"
  fi
fi
if [[ -z "${HERMES_AGENT_ROOT:-}" || ! -d "$HERMES_AGENT_ROOT" ]]; then
  echo "错误: 请设置 HERMES_AGENT_ROOT 指向 hermes-agent 仓库根目录。" >&2
  echo "  export HERMES_AGENT_ROOT=/path/to/hermes-agent" >&2
  exit 1
fi
export HERMES_AGENT_ROOT

if [[ "${ONBOARD_SKIP_INSTALL:-0}" != "1" ]]; then
  echo "→ 安装/更新依赖 (requirements.txt)..."
  if ! python -m pip --version >/dev/null 2>&1; then
    echo "  pip 未就绪，尝试 ensurepip..."
    python -m ensurepip --upgrade >/dev/null 2>&1 || true
  fi
  if ! python -m pip --version >/dev/null 2>&1; then
    echo "错误: pip 不可用。请重建虚拟环境。" >&2
    exit 1
  fi
  python -m pip install -r "$REPO_ROOT/requirements.txt"
  if ! python -c "import gateway, hermes_cli" 2>/dev/null; then
    echo "→ 安装 hermes-agent (editable)..."
    python -m pip install -e "$HERMES_AGENT_ROOT"
  fi
fi

export PYTHONPATH="$HERMES_AGENT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python "$REPO_ROOT/run.py" "$@"
