"""SauceNAO 搜图客户端（基于 aiohttp 的异步实现）。

SauceNAO API 文档：https://saucenao.com/user.php?page=search-api
请求方式：POST https://saucenao.com/search.php
  - ``output_type=2`` 返回 JSON
  - 传 ``url`` 参数按图片链接搜索
  - 或使用 multipart 表单字段 ``file`` 上传图片
  - ``api_key`` 为必填项：SauceNAO 已不允许匿名账号调用 API
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

SAUCENAO_SEARCH_URL = "https://saucenao.com/search.php"

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_NUM_RESULTS = 6

# 使用常见浏览器 UA，降低被 Cloudflare 直接拦截的概率。
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_IMAGE_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
}


class SauceNAOError(Exception):
    """SauceNAO 请求或响应异常。"""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _guess_mime(filename: str) -> str:
    lowered = filename.lower()
    for suffix, mime in _IMAGE_MIME_BY_SUFFIX.items():
        if lowered.endswith(suffix):
            return mime
    return "image/jpeg"


def _parse_json_object(body: str) -> dict[str, Any]:
    text = (body or "").strip()
    if not text:
        raise SauceNAOError("SauceNAO 返回了空响应")

    if not text.startswith("{"):
        lowered = text.lower()
        if "just a moment" in lowered or "cloudflare" in lowered:
            raise SauceNAOError("SauceNAO 被 Cloudflare 拦截，请稍后重试或配置代理")
        raise SauceNAOError("SauceNAO 返回了非 JSON 响应")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SauceNAOError("SauceNAO 返回的 JSON 解析失败") from exc

    if not isinstance(payload, dict):
        raise SauceNAOError("SauceNAO 返回的数据格式异常")
    return payload


def _header_error(payload: dict[str, Any]) -> SauceNAOError | None:
    """从响应 header 中提取 API 级错误（没有结果时才算错误）。"""
    header = payload.get("header")
    header = header if isinstance(header, dict) else {}
    status = header.get("status", 0)
    try:
        status_int = int(status)
    except (TypeError, ValueError):
        status_int = 0

    if status_int != 0 and not payload.get("results"):
        message = header.get("message") or f"SauceNAO 错误码 {status_int}"
        return SauceNAOError(str(message), status=status_int)
    return None


def parse_json_body(body: str) -> dict[str, Any]:
    """解析 SauceNAO 响应正文，并把常见异常转换为可读错误。"""
    payload = _parse_json_object(body)
    error = _header_error(payload)
    if error is not None:
        raise error
    return payload


def extract_api_error(body: str) -> SauceNAOError | None:
    """尝试从非 200 响应中提取 JSON 形式的 API 错误。"""
    text = (body or "").strip()
    if not text.startswith("{"):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return _header_error(payload)


class SauceNAOClient:
    """SauceNAO 异步客户端。"""

    def __init__(
        self,
        api_key: str = "",
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        proxy: str = "",
        num_results: int = DEFAULT_NUM_RESULTS,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.timeout_seconds = timeout_seconds
        self.proxy = (proxy or "").strip()
        self.num_results = max(1, min(40, int(num_results)))

    def _build_params(self) -> dict[str, str]:
        params = {
            "output_type": "2",
            "db": "999",
            "numres": str(self.num_results),
            "hide": "0",
        }
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    async def search_by_url(self, image_url: str) -> dict[str, Any]:
        """按图片链接搜索。"""
        if not image_url.lower().startswith(("http://", "https://")):
            raise SauceNAOError("不支持的图片链接")
        return await self._post(params_extra={"url": image_url})

    async def search_by_bytes(
        self,
        image_bytes: bytes,
        filename: str = "image.jpg",
    ) -> dict[str, Any]:
        """上传图片文件搜索。"""
        if not image_bytes:
            raise SauceNAOError("图片内容为空")
        return await self._post(file_bytes=image_bytes, filename=filename)

    async def _post(
        self,
        *,
        params_extra: dict[str, str] | None = None,
        file_bytes: bytes | None = None,
        filename: str = "image.jpg",
    ) -> dict[str, Any]:
        params = self._build_params()
        if params_extra:
            params.update(params_extra)

        form_data: aiohttp.FormData | None = None
        if file_bytes is not None:
            form_data = aiohttp.FormData()
            form_data.add_field(
                "file",
                file_bytes,
                filename=filename,
                content_type=_guess_mime(filename),
            )

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    SAUCENAO_SEARCH_URL,
                    params=params,
                    data=form_data,
                    headers=headers,
                    proxy=self.proxy or None,
                ) as response:
                    body = await response.text()
                    status = response.status
        except SauceNAOError:
            raise
        except asyncio.TimeoutError as exc:
            raise SauceNAOError("请求 SauceNAO 超时") from exc
        except aiohttp.ClientError as exc:
            # 不记录完整 URL，避免 api_key 泄漏到日志里
            raise SauceNAOError(
                f"SauceNAO 网络请求失败（{type(exc).__name__}）"
            ) from exc

        if status != 200:
            # SauceNAO 可能用 403 + JSON 返回 API 错误（如 Key 无效）
            api_error = extract_api_error(body)
            if api_error is not None:
                raise api_error
            if status == 429:
                raise SauceNAOError("搜索太频繁了（HTTP 429），请稍后再试")
            lowered = body.lower()
            if "just a moment" in lowered or "cloudflare" in lowered:
                raise SauceNAOError("SauceNAO 被 Cloudflare 拦截，请稍后重试或配置代理")
            raise SauceNAOError(f"HTTP {status}")

        return parse_json_body(body)
