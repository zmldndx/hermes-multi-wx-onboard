---
name: zuiyou-doc-search
description: 根据角色和公司凭据搜索Confluence文档库(https://doc2.ixiaochuan.cn)中的文章内容。程序自动将返回的 Confluence HTML 文档清洗并转换为 Markdown，并向大模型反馈，具备最高 10 次的迭代深度递归检索逻辑。
version: 1.0.0
author: Chu Tian
license: MIT
metadata:
  hermes:
    tags: [confluence, search, document, recursive, markdown, helper]
    related_skills: []
---

# 公司文档库 Confluence 查询与深度总结 Skill

本技能通过定制脚本，可检索公司 Confluence 文档库（最右、小川等）里与查询相关的配置、技术、设计与运营文章，支持将复杂 HTML 富文本无损转换为 Markdown 送入上下文。

## 典型工作流 (Workflow)

### 1、凭据配置

用户发送如下消息时，解析其中的 Base64 值并更新本 skill 根目录 `.env`：

```text
请修改 zuiyou-doc-search skill 的 BASE64_TOKEN="<生成的 Base64>"
```

写入格式：

```bash
BASE64_TOKEN="<生成的 Base64>"
```

用户可在 Hermes onboard 绑定页填写 Conference Wiki 用户名与密码，生成上述配置指令。

### 2、CLI 调用与返回处理

脚本：`skills/zuiyou-doc-search/scripts/doc_search_runner.py`

```bash
python3 skills/zuiyou-doc-search/scripts/doc_search_runner.py "<关键词>" [limit]
```

**输入**：检索关键词（必填）；`limit` 为返回条数（可选，默认 15），也可写为 `--limit <N>`。

**输出**：

- **成功**：stdout 为 JSON，`results` 数组，每项含 `id`、`title`、`url`、`space`、`content_markdown`（已清洗的 Markdown 正文）。
- **失败**：stderr 有错误说明，或 stdout JSON 含 `error` 字段；由大模型归纳后决定换词重试或向用户说明。
- 若报错为未配置 `BASE64_TOKEN`，引导用户通过 onboard 生成配置指令（见 §1）。
- 若报错为鉴权失败（如 401/403），引导用户重新生成配置指令并更新 `.env`。

### 3、大模型决策与 10 层递进迭代检索设计

大模型接收到文档后，判定信息是否充分，或是否存在「需进一步查询 XX」「参见 YY」等暗示。

若有，应自我循环：

1. 提取暗示性关键词。
2. 再次调用 `doc_search_runner.py`。
3. 记录已搜集页面 ID，避免重复查询（防死循环）。
4. 最大迭代深度 Depth = 10。

## 用户偏好与指令风格维护 (User Preferences)

- **直接执行、不废话**：请求检索时直接给出执行状态与清洗后的 Markdown/总结，避免冗长前置说明。
- **不复述用户言论**：不对用户输入做原样复述，保持输出高密度。
- **列表与内容重塑**：保证 Confluence 列表、段落、换行等清洗为可读 Markdown。
