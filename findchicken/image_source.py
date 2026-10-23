"""从 AstrBot 消息事件中提取要搜索的图片。

支持三种来源：
1. 当前消息自带的图片；
2. 命令文本中的图片链接（如 ``找鸡 https://...``）；
3. 被引用（回复）消息中的图片。
"""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Reply

try:  # AstrBot 4.25+ 提供的引用消息解析工具，低版本回退到自行解析
    from astrbot.core.utils.quoted_message_parser import (
        extract_quoted_message_images,
    )
except Exception:  # pragma: no cover - 兼容旧版本
    extract_quoted_message_images = None  # type: ignore[assignment]


URL_PATTERN = re.compile(r"https?://[^\s<>\"'，。；！？、）】》]+")


@dataclass(slots=True)
class ImageRef:
    """待搜索图片的引用。"""

    url: str | None = None
    path: str | None = None
    data: bytes | None = None
    #: 是否来自用户直接发送的图片链接（用于区分「图片直链」和「视觉匹配」）
    from_url: bool = False


def _is_http_url(value: Any) -> bool:
    return isinstance(value, str) and value.lower().startswith(("http://", "https://"))


def _strip_url_punctuation(url: str) -> str:
    return url.rstrip(".,;:!?)]}>，。；：！？）】》")


def _ref_from_string(value: str, *, from_url: bool = False) -> ImageRef | None:
    """把字符串形式的图片来源转换为 ImageRef。"""
    text = (value or "").strip()
    if not text:
        return None

    if _is_http_url(text):
        return ImageRef(url=text, from_url=from_url)

    if text.startswith("base64://"):
        try:
            return ImageRef(data=base64.b64decode(text[9:]))
        except Exception:
            logger.warning("[FindChicken] base64 图片解码失败")
            return None

    if text.startswith("data:image"):
        try:
            _, encoded = text.split(",", 1)
            return ImageRef(data=base64.b64decode(encoded))
        except Exception:
            logger.warning("[FindChicken] data URI 图片解码失败")
            return None

    raw_path = text
    if text.startswith("file://"):
        parsed = urlparse(text)
        raw_path = unquote(parsed.path or "")
        if parsed.netloc and not raw_path:
            raw_path = unquote(parsed.netloc)
        # Windows 下 file:///C:/... 解析出的 path 以 /C:/ 开头
        if re.match(r"^/[A-Za-z]:", raw_path):
            raw_path = raw_path[1:]

    candidate = Path(raw_path)
    if candidate.is_file():
        return ImageRef(path=str(candidate))

    return None


async def _ref_from_image_component(image: Image) -> ImageRef | None:
    """从消息链的 Image 组件中提取图片引用。"""
    url = getattr(image, "url", None)
    file = getattr(image, "file", None)
    path = getattr(image, "path", None)

    if _is_http_url(url):
        return ImageRef(url=url)
    if isinstance(path, str) and path and Path(path).is_file():
        return ImageRef(path=path)
    if _is_http_url(file):
        return ImageRef(url=file)
    if isinstance(file, str) and file:
        ref = _ref_from_string(file)
        if ref:
            return ref

    # 兜底：让 AstrBot 帮忙把图片转换为本地文件（会自动下载网络图片）
    convert = getattr(image, "convert_to_file_path", None)
    if callable(convert):
        try:
            local_path = await convert()
            if isinstance(local_path, str) and Path(local_path).is_file():
                return ImageRef(path=local_path)
        except Exception as exc:
            logger.debug(f"[FindChicken] 图片转换本地路径失败: {type(exc).__name__}")
    return None


def _raw_image_urls(event: AstrMessageEvent) -> list[str]:
    """从平台原始消息中提取图片 URL（兼容部分适配器）。"""
    message_obj = getattr(event, "message_obj", None)
    raw_message = getattr(message_obj, "raw_message", None)
    if isinstance(raw_message, Mapping):
        segments = raw_message.get("message")
    else:
        segments = getattr(raw_message, "message", None)
    if not isinstance(segments, (list, tuple)):
        return []

    urls: list[str] = []
    for segment in segments:
        if not isinstance(segment, Mapping) or segment.get("type") != "image":
            continue
        data = segment.get("data")
        if isinstance(data, Mapping) and _is_http_url(data.get("url")):
            urls.append(str(data["url"]))
    return urls


def _text_urls(text: str | None) -> list[str]:
    if not text:
        return []
    return [
        stripped
        for url in URL_PATTERN.findall(text)
        if (stripped := _strip_url_punctuation(url))
    ]


async def _ref_from_quoted(event: AstrMessageEvent) -> ImageRef | None:
    """从被引用的消息中提取图片。"""
    messages = event.get_messages() or []
    reply = next(
        (component for component in messages if isinstance(component, Reply)),
        None,
    )
    if reply is None:
        return None

    # 优先使用 AstrBot 内置的引用消息解析器（可处理合并转发等复杂情况）
    if extract_quoted_message_images is not None:
        try:
            refs = await extract_quoted_message_images(event)
        except Exception as exc:
            logger.debug(f"[FindChicken] 引用图片解析失败: {type(exc).__name__}")
            refs = []
        for ref in refs:
            if isinstance(ref, str):
                image_ref = _ref_from_string(ref)
                if image_ref:
                    return image_ref

    # 回退：直接检查 Reply 组件携带的消息链
    for component in getattr(reply, "chain", None) or []:
        if isinstance(component, Image):
            image_ref = await _ref_from_image_component(component)
            if image_ref:
                return image_ref

    # 被引用的消息本身带有图片链接时也可以使用
    quoted_text = getattr(reply, "message_str", "") or ""
    for url in _text_urls(quoted_text):
        return ImageRef(url=url, from_url=True)

    return None


async def extract_image_ref(event: AstrMessageEvent) -> ImageRef | None:
    """按优先级提取本次命令要搜索的图片。"""
    messages = event.get_messages() or []

    # 1. 当前消息附带的图片
    for component in messages:
        if isinstance(component, Image):
            image_ref = await _ref_from_image_component(component)
            if image_ref:
                return image_ref

    # 2. 命令文本中的图片链接
    for url in _text_urls(getattr(event, "message_str", "")):
        return ImageRef(url=url, from_url=True)

    # 3. 被引用消息中的图片
    quoted_ref = await _ref_from_quoted(event)
    if quoted_ref:
        return quoted_ref

    # 4. 原始事件中的图片 URL（兜底）
    for url in _raw_image_urls(event):
        return ImageRef(url=url)

    return None


def read_image_bytes(path: str) -> bytes | None:
    """读取本地图片文件。"""
    try:
        candidate = Path(path)
        if candidate.is_file():
            return candidate.read_bytes()
    except (OSError, ValueError) as exc:
        logger.warning(f"[FindChicken] 读取图片失败: {type(exc).__name__}")
    return None
