# hermes-multi-wx-onboard

多用户微信助手扫码绑定服务：为 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 提供 Web  onboarding 页面，自动创建 Profile、写入 iLink 凭证、启动 Gateway，并在 Gateway 异常退出时尝试自动拉起。

## 前置条件

1. 已安装并配置好 **hermes-agent**（含 `~/.hermes` 默认 profile 与模型 API Key）
2. Python 3.10+

推荐目录布局（两个仓库并列）：

```
codes/
├── hermes-agent/
└── hermes-multi-wx-onboard/   # 本仓库
```

## 安装

```bash
cd hermes-multi-wx-onboard
python3 -m venv .venv
source .venv/bin/activate

# 若 hermes-agent 在 ../hermes-agent，run.sh 会自动识别；否则：
export HERMES_AGENT_ROOT=/path/to/hermes-agent

./run.sh
```

`run.sh` 会自动：

- `pip install -r requirements.txt`
- 若未安装 hermes-agent 包，则 `pip install -e $HERMES_AGENT_ROOT`

跳过依赖安装（已确认环境就绪）：

```bash
ONBOARD_SKIP_INSTALL=1 ./run.sh
```

## 启动

```bash
./run.sh
```

浏览器打开：**http://127.0.0.1:8765/**

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `HERMES_AGENT_ROOT` | `../hermes-agent` | hermes-agent 仓库路径 |
| `ONBOARD_HOST` | `0.0.0.0` | 监听地址 |
| `ONBOARD_PORT` | `8765` | 端口 |
| `ONBOARD_QR_TIMEOUT` | `480` | 扫码超时（秒） |
| `ONBOARD_SKIP_INSTALL` | `0` | 设为 `1` 跳过 pip 安装 |

## 流程

1. 用户点击「开始绑定」
2. 页面展示二维码，微信扫码确认
3. 创建 `wx-{uuid}` profile（clone default 的 config/.env）
4. 写入 `WEIXIN_*` 凭证
5. `hermes -p <profile> gateway install && gateway start`（失败则 detached `gateway run`）

## 绑定注册表

```
~/.hermes/onboard/registry.json
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/onboard/sessions` | 开始新绑定 |
| GET | `/api/onboard/sessions/{id}` | 查询进度 |
| GET | `/api/onboard/sessions/{id}/qr.png` | 二维码 PNG |
| WS | `/api/onboard/sessions/{id}/ws` | 实时进度 |
| GET | `/api/bindings` | 列出绑定 |
| POST | `/api/bindings/{profile}/restart-gateway` | 重启 gateway |
| POST | `/api/onboard/reauth` | 重新扫码 `{ "profile": "wx-xxx" }` |

## 依赖

见 `requirements.txt`。运行时还需 **hermes-agent** 提供 `gateway`、`hermes_cli`、`utils` 等模块。

## 注意

- 绑定的是 **iLink Bot** 身份，需在 DM 中与 bot 对话
- Session 过期（`-14`）需重新扫码（`/api/onboard/reauth`）
- Gateway 崩溃时：systemd/launchd `Restart=always` + 本服务 60 秒 watchdog
