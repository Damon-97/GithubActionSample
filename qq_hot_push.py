import os
import time

import requests

import qq_gold_push as qq


DEFAULT_JSON_URL = "https://damon-97.github.io/last30days-skill-cn/hot.json"
DEFAULT_PAGE_URL = "https://damon-97.github.io/last30days-skill-cn/"


def fetch_hot(url):
    last_error = "未知错误"
    for attempt in range(1, 9):
        try:
            response = requests.get(
                url,
                timeout=30,
                headers={"User-Agent": "GithubActionSample/hot"},
            )
            if response.status_code == 200:
                return response.json()
            last_error = "HTTP {}".format(response.status_code)
        except requests.RequestException as exc:
            last_error = str(exc)
        print("热榜还没取到（第 {} 次）：{}".format(attempt, last_error))
        if attempt < 8:
            time.sleep(20)
    raise RuntimeError("读取热榜失败: {}".format(last_error))


def clip(text, limit=60):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def build_message(data, page_url):
    lines = ["全网热榜", str(data.get("generated_at") or "").strip()]
    if page_url:
        lines.append(page_url)
    topics = data.get("topics") or []
    if topics:
        lines.extend(["", "多平台热搜"])
        for idx, topic in enumerate(topics[:8], start=1):
            lines.append("{}. {}".format(idx, clip(topic.get("title"))))
    shown = 0
    for sid, board in (data.get("boards") or {}).items():
        if board.get("kind") != "board" or sid == "hackernews":
            continue
        items = board.get("items") or []
        if not items:
            continue
        lines.extend(["", board.get("label") or sid])
        for item in items[:3]:
            lines.append("{}. {}".format(item.get("rank") or "-", clip(item.get("title"), 50)))
        shown += 1
        if shown >= 6:
            break
    return "\n".join(lines).strip()


def chunks(text, limit=900):
    parts = []
    current = []
    size = 0
    for line in text.splitlines():
        extra = len(line) + 1
        if current and size + extra > limit:
            parts.append("\n".join(current))
            current = [line]
            size = len(line) + 1
        else:
            current.append(line)
            size += extra
    if current:
        parts.append("\n".join(current))
    return parts


def push_hot():
    if not qq.credentials_ready():
        return
    url = os.environ.get("HOT_JSON_URL", "").strip() or DEFAULT_JSON_URL
    page = os.environ.get("HOT_PAGE_URL", "").strip() or DEFAULT_PAGE_URL
    data = fetch_hot(url)
    content = build_message(data, page)
    print(content)
    token = qq.get_qq_token(qq.require_qq_env("QQ_APP_ID"), qq.require_qq_env("QQ_APP_SECRET"))
    group = qq.require_qq_env("QQ_GROUP_OPENID")
    parts = chunks(content)
    for idx, part in enumerate(parts, start=1):
        body = "({}/{})\n{}".format(idx, len(parts), part) if len(parts) > 1 else part
        qq.send_group_message(token, group, body)
        if idx != len(parts):
            time.sleep(1)


if __name__ == "__main__":
    push_hot()
