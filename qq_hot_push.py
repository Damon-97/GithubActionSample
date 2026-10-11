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


def clip(text, limit=72):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def short_label(label):
    label = (label or "").strip()
    for suffix in ("热搜", "热榜"):
        if label.endswith(suffix) and len(label) > len(suffix):
            return label[: -len(suffix)]
    return label


def entry_block(index, title, url, note=""):
    lines = ["{}. {}".format(index, clip(title))]
    if note:
        lines.append(note)
    if url:
        lines.append(url.strip())
    return "\n".join(lines)


def section_block(title, body):
    return "▸ {}\n{}".format(title, body)


def build_sections(data, page_url):
    sections = []
    header = ["全网热榜", str(data.get("generated_at") or "").strip() or "刚刚更新"]
    if page_url:
        header.extend(["", "完整看板", page_url.strip()])
    sections.append("\n".join(header))

    topics = data.get("topics") or []
    topic_blocks = []
    for idx, topic in enumerate(topics[:6], start=1):
        where = " · ".join(
            "{} #{}".format(short_label(m.get("label") or m.get("platform") or ""), m.get("rank") or "-")
            for m in (topic.get("mentions") or [])[:4]
        )
        topic_blocks.append(entry_block(idx, topic.get("title"), topic.get("url"), where))
    if topic_blocks:
        sections.append(section_block("跨平台", "\n\n".join(topic_blocks)))

    shown = 0
    for sid, board in (data.get("boards") or {}).items():
        if board.get("kind") != "board" or sid == "hackernews":
            continue
        items = board.get("items") or []
        if not items:
            continue
        blocks = [
            entry_block(item.get("rank") or "-", item.get("title"), item.get("url"))
            for item in items[:3]
        ]
        sections.append(section_block(board.get("label") or sid, "\n\n".join(blocks)))
        shown += 1
        if shown >= 6:
            break
    return sections


def build_message(data, page_url):
    return "\n\n".join(build_sections(data, page_url)).strip()


def _section_entries(section):
    blocks = [block for block in section.split("\n\n") if block.strip()]
    if not blocks:
        return "", []
    first = blocks[0]
    if not first.startswith("▸ "):
        return "", ["\n\n".join(blocks)]
    heading, _, rest = first.partition("\n")
    entries = ([rest] if rest else []) + blocks[1:]
    return heading, entries


def pack_sections(sections, limit=1400):
    """按栏目打包。同一条消息里栏目标题只出现一次，拆到下一条时再带上。"""
    parts = []
    current = ""

    def append(piece):
        nonlocal current
        if not piece:
            return
        if current and len(current) + 2 + len(piece) > limit:
            parts.append(current)
            current = piece
        elif current:
            current = current + "\n\n" + piece
        else:
            current = piece

    for section in sections:
        heading, entries = _section_entries(section)
        if not heading:
            append(section.strip())
            continue
        show_heading = True
        for entry in entries:
            piece = "{}\n{}".format(heading, entry) if show_heading else entry
            if current and len(current) + 2 + len(piece) > limit:
                parts.append(current)
                current = "{}\n{}".format(heading, entry)
            else:
                append(piece)
            show_heading = False
    if current:
        parts.append(current)
    return parts


def push_hot():
    if not qq.credentials_ready():
        return
    url = os.environ.get("HOT_JSON_URL", "").strip() or DEFAULT_JSON_URL
    page = os.environ.get("HOT_PAGE_URL", "").strip() or DEFAULT_PAGE_URL
    data = fetch_hot(url)
    sections = build_sections(data, page)
    content = "\n\n".join(sections)
    print(content)
    token = qq.get_qq_token(qq.require_qq_env("QQ_APP_ID"), qq.require_qq_env("QQ_APP_SECRET"))
    group = qq.require_qq_env("QQ_GROUP_OPENID")
    parts = pack_sections(sections)
    for idx, part in enumerate(parts, start=1):
        body = "({}/{})\n{}".format(idx, len(parts), part) if len(parts) > 1 else part
        qq.send_group_message(token, group, body)
        if idx != len(parts):
            time.sleep(1)


if __name__ == "__main__":
    push_hot()
