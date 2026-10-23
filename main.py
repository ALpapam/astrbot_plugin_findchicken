"""找鸡插件：通过 SauceNAO 搜索图片出处。

用法：
    引用一张图片（或附带图片、发送图片链接）后发送「找鸡」，
    插件会把 SauceNAO 的搜索结果整理成文字消息返回。
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Plain, Reply
from astrbot.api.star import Context, Star

from .findchicken.client import SauceNAOClient, SauceNAOError
from .findchicken.formatter import (
    API_KEY_INVALID_TEXT,
    MATCH_DIRECT_URL,
    MATCH_VISUAL,
    NOT_FOUND_TEXT,
    NO_API_KEY_TEXT,
    PROGRESS_TEXT,
    SEARCH_FAILED_TEXT,
    TOO_FREQUENT_TEMPLATE,
    USAGE_TEXT,
    format_hits,
)
from .findchicken.image_source import ImageRef, extract_image_ref, read_image_bytes
from .findchicken.models import parse_results


def _guess_image_filename(data: bytes) -> str:
    """根据文件头猜测图片文件名后缀。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image.png"
    if data.startswith(b"\xff\xd8"):
        return "image.jpg"
    if data.startswith(b"GIF8"):
        return "image.gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image.webp"
    if data.startswith(b"BM"):
        return "image.bmp"
    return "image.jpg"


class FindChickenPlugin(Star):
    """「找鸡」插件的入口类。"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config

        self._api_key = self._get_str("api_key")
        self._proxy = self._get_str("proxy")
        self._timeout = self._get_number("timeout_seconds", 30.0, 5.0, 120.0)
        self._max_results = int(self._get_number("max_results", 1, 1, 5))
        self._threshold = self._get_number("similarity_threshold", 30.0, 0.0, 100.0)
        self._send_progress = self._get_bool("send_progress", True)
        self._show_similarity = self._get_bool("show_similarity", False)
        self._cooldown = int(self._get_number("cooldown_seconds", 10, 0, 600))

        self.client = SauceNAOClient(
            api_key=self._api_key,
            timeout_seconds=self._timeout,
            proxy=self._proxy,
            num_results=max(6, self._max_results * 3),
        )
        # 每个发送者的上次搜索时间，用于简单的防刷冷却
        self._last_search_at: dict[str, float] = {}

    # ------------------------------------------------------------------
    # 指令
    # ------------------------------------------------------------------

    @filter.command("找鸡")
    async def find_chicken(self, event: AstrMessageEvent):
        """找鸡：引用/附带图片或发送图片链接，搜索图片来源。"""
        for text in await self._run_search(event):
            yield event.plain_result(text)

    @filter.platform_adapter_type(
        filter.PlatformAdapterType.AIOCQHTTP,
        priority=2,
    )
    async def find_chicken_quoted(self, event: AstrMessageEvent):
        """兼容 QQ 回复图片时自动插入 @ 导致指令无法匹配的情况。

        QQ 回复他人消息时客户端会在消息前插入被回复者的 At，
        message_str 会变成「 @昵称(qq) 找鸡」，标准指令无法匹配。
        这里直接检查消息链结构，在确认是「回复 + 找鸡」时补发结果。
        """
        if not self._looks_like_quoted_command(event):
            return

        event.stop_event()
        for text in await self._run_search(event):
            yield event.plain_result(text)

    @staticmethod
    def _looks_like_quoted_command(event: AstrMessageEvent) -> bool:
        """判断消息是否为「回复他人 + 找鸡」的特殊消息链。"""
        messages = event.get_messages()
        if not isinstance(messages, list) or len(messages) not in (3, 4):
            return False

        reply, mention, *rest = messages
        if not isinstance(reply, Reply) or not isinstance(mention, At):
            return False

        reply_sender_id = str(getattr(reply, "sender_id", "") or "")
        mention_qq = str(getattr(mention, "qq", "") or "")
        if not reply_sender_id or reply_sender_id != mention_qq:
            return False

        self_id = str(event.get_self_id() or "")
        mentions_bot = (
            len(rest) == 2
            and bool(self_id)
            and isinstance(rest[0], At)
            and str(getattr(rest[0], "qq", "") or "") == self_id
        )
        if mentions_bot:
            rest = rest[1:]

        if len(rest) != 1 or not isinstance(rest[0], Plain):
            return False

        command_text = getattr(rest[0], "text", "")
        if not isinstance(command_text, str):
            return False
        return re.fullmatch(r"/?找鸡(?:\s+.+)?", command_text.strip()) is not None

    async def _run_search(self, event: AstrMessageEvent) -> list[str]:
        """执行一次找鸡流程，返回需要依次发送的文本消息。"""
        sender_id = str(event.get_sender_id() or "")

        remaining = self._cooldown_remaining(sender_id)
        if remaining > 0:
            return [TOO_FREQUENT_TEMPLATE.format(seconds=remaining)]

        if not self._api_key:
            # SauceNAO 已不允许匿名账号调用 API，没有 Key 时直接提示配置
            return [NO_API_KEY_TEXT]

        image_ref = await extract_image_ref(event)
        if image_ref is None:
            return [USAGE_TEXT]

        self._mark_search(sender_id)
        texts: list[str] = []
        if self._send_progress:
            texts.append(PROGRESS_TEXT)

        try:
            payload = await self._search(image_ref)
        except SauceNAOError as exc:
            logger.warning(f"[FindChicken] SauceNAO 搜索失败: {exc.message}")
            texts.append(self._error_text(exc))
            return texts
        except Exception as exc:
            logger.error(f"[FindChicken] 搜索异常: {type(exc).__name__}")
            texts.append(SEARCH_FAILED_TEXT)
            return texts

        hits = parse_results(payload, self._threshold)[: self._max_results]
        if not hits:
            texts.append(NOT_FOUND_TEXT)
            return texts

        # 图片链接输入用「图片直链」，图片输入用「视觉匹配」
        match_label = MATCH_DIRECT_URL if image_ref.from_url else MATCH_VISUAL
        texts.append(
            format_hits(hits, match_label, show_similarity=self._show_similarity)
        )
        return texts

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    async def _search(self, image_ref: ImageRef) -> dict[str, Any]:
        """根据图片引用类型选择搜索方式。"""
        if image_ref.url:
            return await self.client.search_by_url(image_ref.url)

        if image_ref.data is not None:
            return await self.client.search_by_bytes(
                image_ref.data,
                filename=_guess_image_filename(image_ref.data),
            )

        if image_ref.path:
            data = await asyncio.to_thread(read_image_bytes, image_ref.path)
            if not data:
                raise SauceNAOError("读取本地图片失败")
            filename = Path(image_ref.path).name or "image.jpg"
            return await self.client.search_by_bytes(data, filename=filename)

        raise SauceNAOError("没有找到可搜索的图片")

    # ------------------------------------------------------------------
    # 配置 / 冷却
    # ------------------------------------------------------------------

    @staticmethod
    def _error_text(exc: SauceNAOError) -> str:
        """把 SauceNAO 异常转换为用户提示。"""
        message = (exc.message or "").lower()
        if exc.status == -1 or "api key" in message or "anonymous" in message:
            return API_KEY_INVALID_TEXT
        return SEARCH_FAILED_TEXT

    def _raw_config(self, key: str, default: Any) -> Any:
        try:
            value = self.config.get(key, default)
        except Exception:
            return default
        return default if value is None else value

    def _get_str(self, key: str, default: str = "") -> str:
        value = self._raw_config(key, default)
        return value.strip() if isinstance(value, str) else default

    def _get_number(
        self,
        key: str,
        default: float,
        minimum: float,
        maximum: float,
    ) -> float:
        value = self._raw_config(key, default)
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(maximum, number))

    def _get_bool(self, key: str, default: bool) -> bool:
        value = self._raw_config(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        if isinstance(value, (int, float)):
            return bool(value)
        return default

    def _cooldown_remaining(self, sender_id: str) -> int:
        if self._cooldown <= 0 or not sender_id:
            return 0
        last = self._last_search_at.get(sender_id)
        if last is None:
            return 0
        elapsed = time.monotonic() - last
        if elapsed >= self._cooldown:
            return 0
        return max(1, int(self._cooldown - elapsed) + 1)

    def _mark_search(self, sender_id: str) -> None:
        if self._cooldown <= 0 or not sender_id:
            return
        now = time.monotonic()
        # 防止字典无限增长
        if len(self._last_search_at) > 1000:
            cutoff = now - max(self._cooldown, 60)
            self._last_search_at = {
                key: value
                for key, value in self._last_search_at.items()
                if value > cutoff
            }
        self._last_search_at[sender_id] = now
