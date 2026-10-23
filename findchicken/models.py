"""SauceNAO 搜索结果模型与解析工具。

该模块只依赖标准库，便于脱离 AstrBot 单独测试。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

#: SauceNAO 数据库索引 ID -> 展示平台名。
#: 5/6 为 Pixiv，9 为 Twitter（X），其余不在表内的索引使用 API 返回的 index_name。
INDEX_ID_PLATFORM: dict[int, str] = {
    3: "Danbooru",
    5: "Pixiv",
    6: "Pixiv",
    7: "Anime",
    8: "Nico Nico Douga",
    9: "X (Twitter)",
    10: "Fakku",
    21: "Anime",
    34: "deviantArt",
    51: "AniDB",
}

#: 按优先级尝试的标题字段。
TITLE_FIELDS: tuple[str, ...] = (
    "title",
    "eng_name",
    "jp_name",
    "material",
    "source",
)

#: 按优先级尝试的作者字段。
AUTHOR_FIELDS: tuple[str, ...] = (
    "author",
    "member_name",
    "creator",
    "twitter_user_handle",
    "author_name",
    "user_name",
    "artist",
    "company",
)

#: 被视为“图片直链”的扩展名。
IMAGE_URL_SUFFIXES: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".avif",
)


@dataclass(slots=True)
class SearchHit:
    """一条 SauceNAO 搜索结果。"""

    index_id: int
    index_name: str
    similarity: float
    title: str
    author: str
    author_handle: str
    page_url: str
    direct_url: str
    thumbnail: str

    @property
    def platform(self) -> str:
        """展示用平台名，例如 ``Pixiv`` / ``X (Twitter)``。"""
        return INDEX_ID_PLATFORM.get(self.index_id) or self.index_name or "未知平台"

    @property
    def display_name(self) -> str:
        """展示用名字（作品标题优先，其次作者）。"""
        return self.title or self.author or "未知"

    @property
    def display_account(self) -> str:
        """展示用账号（统一带 ``@`` 前缀）。"""
        account = self.author_handle or self.author
        if not account:
            return "未知"
        account = account.strip()
        if not account:
            return "未知"
        return account if account.startswith("@") else f"@{account}"


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_text(data: dict[str, Any], fields: tuple[str, ...]) -> str:
    """按字段优先级取出第一个非空文本，列表会合并为逗号分隔文本。"""
    for key in fields:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            parts = [str(item).strip() for item in value if str(item).strip()]
            if parts:
                return ", ".join(parts)
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _looks_like_image_url(url: str) -> bool:
    if not url or not url.lower().startswith(("http://", "https://")):
        return False
    try:
        path = urlsplit(url).path.lower()
    except ValueError:
        return False
    return path.endswith(IMAGE_URL_SUFFIXES)


def _extract_direct_url(data: dict[str, Any]) -> str:
    """尝试从结果中提取图片直链。"""
    ext_urls = data.get("ext_urls")
    if isinstance(ext_urls, list):
        for url in ext_urls:
            if isinstance(url, str) and _looks_like_image_url(url):
                return url.strip()
    source = data.get("source")
    if isinstance(source, str) and _looks_like_image_url(source):
        return source.strip()
    return ""


def parse_results(
    payload: dict[str, Any],
    min_similarity: float = 0.0,
) -> list[SearchHit]:
    """把 SauceNAO JSON 响应解析为搜索结果列表。

    Args:
        payload: SauceNAO ``output_type=2`` 返回的 JSON 对象。
        min_similarity: 低于该相似度的结果会被过滤。

    Returns:
        按 API 原始顺序排列的搜索结果。
    """
    if not isinstance(payload, dict):
        return []

    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return []

    hits: list[SearchHit] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        header = item.get("header")
        data = item.get("data")
        header = header if isinstance(header, dict) else {}
        data = data if isinstance(data, dict) else {}

        similarity = _to_float(header.get("similarity"))
        if similarity < min_similarity:
            continue

        ext_urls = data.get("ext_urls")
        page_url = ""
        if isinstance(ext_urls, list):
            page_url = next(
                (
                    url.strip()
                    for url in ext_urls
                    if isinstance(url, str) and url.strip()
                ),
                "",
            )

        author_handle = data.get("twitter_user_handle")
        if not isinstance(author_handle, str):
            author_handle = ""

        thumbnail = header.get("thumbnail")
        index_name = header.get("index_name")

        hits.append(
            SearchHit(
                index_id=_to_int(header.get("index_id")),
                index_name=str(index_name).strip() if index_name else "",
                similarity=similarity,
                title=_first_text(data, TITLE_FIELDS),
                author=_first_text(data, AUTHOR_FIELDS),
                author_handle=author_handle.strip(),
                page_url=page_url,
                direct_url=_extract_direct_url(data),
                thumbnail=str(thumbnail).strip() if thumbnail else "",
            )
        )

    return hits
