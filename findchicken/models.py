"""SauceNAO 搜索结果模型与解析工具。

该模块只依赖标准库，便于脱离 AstrBot 单独测试。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

#: SauceNAO 数据库索引 ID -> 展示平台名。
#: 索引表来源：https://saucenao.com/tools/examples/api/index_details.txt
#: 其中 5/6 为 Pixiv，9 为 Danbooru，41 为 Twitter（X）。
INDEX_ID_PLATFORM: dict[int, str] = {
    0: "H-Magazines",
    1: "H-Anime",
    2: "H-Game CG",
    3: "Doujinshi DB",
    4: "Doujinshi DB Samples",
    5: "Pixiv",
    6: "Pixiv",
    7: "Anime",
    8: "Nico Nico Seiga",
    9: "Danbooru",
    10: "drawr",
    11: "Nijie",
    12: "yande.re",
    13: "Anime Openings",
    14: "IMDb",
    15: "Shutterstock",
    16: "FAKKU",
    18: "H-Misc (nhentai)",
    19: "2D Market",
    20: "MediBang",
    21: "Anime",
    22: "H-Anime",
    23: "Movies",
    24: "Shows",
    25: "Gelbooru",
    26: "Konachan",
    27: "Sankaku Channel",
    28: "Anime-Pictures",
    29: "e621",
    30: "Idol Complex",
    31: "bcy illust",
    32: "bcy cosplay",
    33: "PortalGraphics",
    34: "deviantArt",
    35: "Pawoo",
    36: "Madokami",
    37: "MangaDex",
    38: "H-Misc (ehentai)",
    39: "ArtStation",
    40: "FurAffinity",
    41: "X (Twitter)",
    42: "Furry Network",
    43: "Kemono",
    44: "Skeb",
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
    "author_name",
    "twitter_user_handle",
    "creator",
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

#: SauceNAO 的 index_name 可能是 "Index #41: Twitter - xxx.jpg" 这种形式。
_INDEX_NAME_PREFIX = re.compile(r"^Index #\d+:\s*")


@dataclass(slots=True)
class SearchHit:
    """一条 SauceNAO 搜索结果。"""

    index_id: int
    index_name: str
    similarity: float
    title: str
    author: str
    author_handle: str
    member_id: str
    page_url: str
    direct_url: str
    thumbnail: str

    @property
    def platform(self) -> str:
        """展示用平台名，例如 ``Pixiv`` / ``X (Twitter)``。"""
        return (
            INDEX_ID_PLATFORM.get(self.index_id)
            or _clean_index_name(self.index_name)
            or "未知平台"
        )

    @property
    def display_name(self) -> str:
        """展示用名字：作者昵称优先，缺失时退回作品标题。"""
        return self.author or self.title or "未知"

    @property
    def display_account(self) -> str:
        """展示用账号。

        - Pixiv（索引 5/6）：画师数字用户 ID，例如 ``@724886``；
        - Twitter（索引 41）：``twitter_user_handle``，例如 ``@mamamia1008``；
        - 其他来源：退回作者名。
        """
        if self.index_id in (5, 6) and self.member_id:
            account = self.member_id
        else:
            account = self.author_handle or self.author
        account = (account or "").strip()
        if not account:
            return "未知"
        return account if account.startswith("@") else f"@{account}"


def _clean_index_name(value: str) -> str:
    """清理 SauceNAO 返回的 index_name，去掉索引号前缀和缩略图文件名。"""
    text = (value or "").strip()
    text = _INDEX_NAME_PREFIX.sub("", text)
    if " - " in text:
        text = text.split(" - ", 1)[0].strip()
    return text


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

        member_id = data.get("member_id")
        member_id_text = ""
        if isinstance(member_id, (int, str)) and not isinstance(member_id, bool):
            member_id_text = str(member_id).strip()

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
                member_id=member_id_text,
                page_url=page_url,
                direct_url=_extract_direct_url(data),
                thumbnail=str(thumbnail).strip() if thumbnail else "",
            )
        )

    return hits
