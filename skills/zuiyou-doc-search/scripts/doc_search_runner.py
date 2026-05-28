# doc_search_runner.py
import os
import re
import sys
import json
import argparse
import requests
from bs4 import BeautifulSoup

DEFAULT_LIMIT = 15
MAX_LIMIT = 50

SKILL_NAME = "zuiyou-doc-search"
ENV_FILENAME = ".env"
CONFIG_MESSAGE_TEMPLATE = (
    f'请修改 {SKILL_NAME} skill 的 BASE64_TOKEN="<生成的 Base64>"'
)

def skill_root_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def env_file_path():
    return os.path.join(skill_root_dir(), ENV_FILENAME)

def load_env_token():
    """从 skill 根目录 .env 读取 BASE64_TOKEN，不支持交互式配置。"""
    env_path = env_file_path()
    if not os.path.exists(env_path):
        return None

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("#") or "BASE64_TOKEN" not in line:
                    continue
                match = re.search(r'BASE64_TOKEN\s*=\s*["\']?([^"\'\n]+)["\']?', line)
                if match:
                    token = match.group(1).strip()
                    if token:
                        return token
    except OSError:
        pass
    return None

def print_missing_token_error():
    print(
        "\n[错误] 未配置 BASE64_TOKEN。\n"
        f"请在 Hermes onboard 页面生成配置指令，发送到微信助手，例如：\n"
        f"  {CONFIG_MESSAGE_TEMPLATE}\n"
        f"由助手写入本 skill 的 {ENV_FILENAME} 后再重试。\n",
        file=sys.stderr,
    )

def print_auth_error(detail=None):
    lines = [
        "\n[错误] Confluence 鉴权失败，大概率是 BASE64_TOKEN 无效或已过期。",
        f"请在 onboard 页面重新生成配置指令并发送给微信助手，例如：",
        f"  {CONFIG_MESSAGE_TEMPLATE}",
        f"确认已更新 {env_file_path()} 中的 BASE64_TOKEN 后再重试。",
    ]
    if detail:
        lines.insert(1, f"详情: {detail}")
    print("\n".join(lines) + "\n", file=sys.stderr)

def html_to_markdown(html_content):
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')

    for br in soup.find_all('br'):
        try:
            br.replace_with('\n')
        except Exception:
            pass

    for li in soup.find_all('li'):
        try:
            parent = li.parent
            prefix = "-"
            if parent and parent.name == 'ol':
                siblings = [sibling for sibling in parent.children if getattr(sibling, 'name', None) == 'li']
                idx = siblings.index(li) + 1 if li in siblings else 1
                prefix = f"{idx}."
            li.replace_with(f"\n{prefix} {li.get_text().strip()}\n")
        except Exception:
            pass

    for table in soup.find_all('table'):
        markdown_table = []
        rows = table.find_all('tr')
        if not rows:
            continue

        first_row_cells = rows[0].find_all(['td', 'th'])
        col_count = len(first_row_cells)

        for idx, row in enumerate(rows):
            cells = row.find_all(['td', 'th'])
            row_data = []
            for cell in cells:
                txt = " ".join(cell.get_text().split())
                txt = txt.replace("|", "\\|")
                row_data.append(txt)

            while len(row_data) < col_count:
                row_data.append("")

            markdown_table.append("| " + " | ".join(row_data) + " |")

            if idx == 0:
                sept = "| " + " | ".join(["---"] * col_count) + " |"
                markdown_table.append(sept)

        table.replace_with("\n" + "\n".join(markdown_table) + "\n")

    for code in soup.find_all(['pre', 'code']):
        code_text = code.get_text()
        code.replace_with(f"\n```\n{code_text}\n```\n")

    for h1 in soup.find_all('h1'):
        h1.replace_with(f"\n# {h1.get_text()}\n")
    for h2 in soup.find_all('h2'):
        h2.replace_with(f"\n## {h2.get_text()}\n")
    for h3 in soup.find_all('h3'):
        h3.replace_with(f"\n### {h3.get_text()}\n")

    for p in soup.find_all('p'):
        p.replace_with(f"\n{p.get_text()}\n")

    for a in soup.find_all('a'):
        href = a.get('href', '')
        text = a.get_text()
        if href:
            if not href.startswith('http'):
                href = f"https://doc2.ixiaochuan.cn{href}"
            a.replace_with(f"[{text}]({href})")
        else:
            a.replace_with(text)

    text = soup.get_text()
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()

def search_confluence(token, keyword, limit=DEFAULT_LIMIT):
    url = "https://doc2.ixiaochuan.cn/rest/api/content/search"
    headers = {
        "Authorization": f"Basic {token}"
    }
    params = {
        "cql": f'text~"{keyword}" AND type=page',
        "expand": "space,body.view",
        "limit": limit
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code in (401, 403):
            detail = f"HTTP {resp.status_code}"
            try:
                body = resp.json()
                if isinstance(body, dict) and body.get("message"):
                    detail = f"{detail}: {body['message']}"
            except Exception:
                pass
            print_auth_error(detail)
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status in (401, 403):
            print_auth_error(f"HTTP {status}: {e}")
        else:
            print(f"Request Error: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Request Error: {e}", file=sys.stderr)
        return None

def _is_int(value):
    try:
        int(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False

def _parse_limit(value):
    if value is None:
        return DEFAULT_LIMIT
    try:
        limit = int(str(value).strip())
    except (TypeError, ValueError):
        print(f"Warning: invalid limit {value!r}; using default {DEFAULT_LIMIT}", file=sys.stderr)
        return DEFAULT_LIMIT
    if limit <= 0:
        print(f"Warning: limit must be positive; using default {DEFAULT_LIMIT}", file=sys.stderr)
        return DEFAULT_LIMIT
    return min(limit, MAX_LIMIT)

def parse_args(argv, env_token=None):
    """解析 CLI：仅关键词与 limit，token 固定来自 .env。"""
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--limit", "-n", dest="limit")
    parser.add_argument("args", nargs="*")
    ns = parser.parse_args(argv)

    args = list(ns.args)
    limit = _parse_limit(ns.limit) if ns.limit is not None else DEFAULT_LIMIT

    if ns.limit is None and args and _is_int(args[-1]):
        limit = _parse_limit(args.pop())

    keyword = " ".join(part.strip() for part in args if part and part.strip()).strip()
    return env_token, keyword, limit

def main():
    env_token = load_env_token()
    if not env_token:
        print_missing_token_error()
        sys.exit(1)

    token, keyword, limit = parse_args(sys.argv[1:], env_token=env_token)

    if not keyword:
        print("Error: Missing search keyword", file=sys.stderr)
        sys.exit(1)

    results = search_confluence(token, keyword, limit)
    if results is None:
        print(json.dumps({"error": "auth_or_request_failed", "results": []}, ensure_ascii=False))
        sys.exit(1)

    if "results" not in results:
        print(json.dumps({"results": []}))
        return

    processed_results = []
    for item in results["results"]:
        webui = item.get("_links", {}).get("webui", "")
        full_url = f"https://doc2.ixiaochuan.cn{webui}" if webui else ""

        body_html = item.get("body", {}).get("view", {}).get("value", "")
        markdown_content = html_to_markdown(body_html)

        processed_results.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "url": full_url,
            "space": item.get("space", {}).get("name"),
            "content_markdown": markdown_content
        })

    print(json.dumps({"results": processed_results}, ensure_ascii=False))

if __name__ == "__main__":
    main()
