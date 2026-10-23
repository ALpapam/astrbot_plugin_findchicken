"""搜索结果与提示文案格式化。

该模块只依赖标准库，便于脱离 AstrBot 单独测试。
"""

from __future__ import annotations

from collections.abc import Sequence

from .models import SearchHit

#: 找到结果时的固定开头。
HEADER = "**已找到鸡**"

#: 找到结果时的固定结尾。
FOOTER = "⚠识图存在误差，请自行核对哦~"

#: 没有识别到图片时发送的使用说明。
USAGE_TEXT = (
    "请发送「找鸡」时附带或引用一张图片，也可以直接发送图片链接哦～\n\n"
    "用法示例：\n"
    "1. 引用一张图片后发送「找鸡」\n"
    "2. 发送图片并发送「找鸡」\n"
    "3. 发送「找鸡 https://example.com/image.jpg」"
)

#: SauceNAO 没有返回结果。
NOT_FOUND_TEXT = (
    "**没找到鸡**\n\n没有找到这张图的出处，可能是原创或尚未被收录，换张图再试试吧～"
)

#: 没有配置 SauceNAO API Key。
NO_API_KEY_TEXT = (
    "**找鸡失败了**\n\n"
    "还没有配置 SauceNAO API Key，请到插件配置里填写后再试～\n"
    "获取地址：https://saucenao.com/user.php?page=search-api"
)

#: API Key 无效 / 匿名账号不允许调用 API。
API_KEY_INVALID_TEXT = (
    "**找鸡失败了**\n\n"
    "SauceNAO API Key 无效或未生效，请到插件配置里检查后再试～\n"
    "获取地址：https://saucenao.com/user.php?page=search-api"
)

#: 网络或 SauceNAO 服务异常。
SEARCH_FAILED_TEXT = (
    "**找鸡失败了**\n\n"
    "SauceNAO 暂时没有响应，请稍后再试；如果经常失败，可以检查网络/代理设置，"
    "或在插件配置中填写 SauceNAO API Key。"
)

#: 冷却提示。
TOO_FREQUENT_TEMPLATE = "别急，鸡要慢慢找～请 {seconds} 秒后再试。"

#: 正在搜索的提示。
PROGRESS_TEXT = "🐔 正在找鸡，请稍等…"

#: 「匹配」字段的两种取值。
MATCH_VISUAL = "视觉匹配"
MATCH_DIRECT_URL = "图片直链"


def format_hit(
    hit: SearchHit,
    match_label: str,
    show_similarity: bool = False,
) -> str:
    """格式化单条搜索结果。"""
    match = match_label
    if show_similarity and match_label == MATCH_VISUAL:
        match = f"{match}（相似度 {hit.similarity:.1f}%）"

    return "\n".join(
        (
            f"平台：{hit.platform}",
            f"匹配：{match}",
            f"名字：{hit.display_name}",
            f"账号：{hit.display_account}",
        )
    )


def format_hits(
    hits: Sequence[SearchHit],
    match_label: str,
    show_similarity: bool = False,
) -> str:
    """格式化全部搜索结果，返回一条可直接发送的文本消息。"""
    blocks = [format_hit(hit, match_label, show_similarity) for hit in hits]
    body = "\n\n".join(blocks)
    return f"{HEADER}\n\n{body}\n\n{FOOTER}"
