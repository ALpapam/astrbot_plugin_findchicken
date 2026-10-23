"""基于本地 aiohttp 服务端的客户端请求测试（不访问外网）。"""

from __future__ import annotations

import asyncio

import pytest
from aiohttp import web

from astrbot_plugin_findchicken.findchicken import client as client_module
from astrbot_plugin_findchicken.findchicken.client import SauceNAOClient, SauceNAOError

SAMPLE_RESULT = {
    "header": {"status": 0, "short_remaining": 4, "long_remaining": 100},
    "results": [
        {
            "header": {
                "similarity": "93.10",
                "index_id": 5,
                "index_name": "Pixiv",
                "thumbnail": "https://img.example.com/t.jpg",
            },
            "data": {
                "pixiv_id": 1,
                "title": "テスト",
                "member_name": "作者",
                "ext_urls": ["https://www.pixiv.net/artworks/1"],
            },
        }
    ],
}


def run_with_server(handler, operation):
    """启动临时 HTTP 服务，把客户端地址指向它后执行 operation。"""

    async def runner():
        app = web.Application()
        app.router.add_post("/search.php", handler)
        app_runner = web.AppRunner(app)
        await app_runner.setup()
        site = web.TCPSite(app_runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        original_url = client_module.SAUCENAO_SEARCH_URL
        client_module.SAUCENAO_SEARCH_URL = f"http://127.0.0.1:{port}/search.php"
        try:
            return await operation()
        finally:
            client_module.SAUCENAO_SEARCH_URL = original_url
            await app_runner.cleanup()

    return asyncio.run(runner())


def test_search_by_url_passes_query_params():
    captured: dict = {}

    async def handler(request):
        captured["query"] = dict(request.query)
        return web.json_response(SAMPLE_RESULT)

    async def operation():
        client = SauceNAOClient(api_key="test-key", num_results=6)
        return await client.search_by_url("https://img.example.com/a.jpg")

    payload = run_with_server(handler, operation)

    assert payload["results"][0]["data"]["title"] == "テスト"
    query = captured["query"]
    assert query["output_type"] == "2"
    assert query["db"] == "999"
    assert query["numres"] == "6"
    assert query["api_key"] == "test-key"
    assert query["url"] == "https://img.example.com/a.jpg"


def test_search_by_url_omits_empty_api_key():
    captured: dict = {}

    async def handler(request):
        captured["query"] = dict(request.query)
        return web.json_response(SAMPLE_RESULT)

    async def operation():
        return await SauceNAOClient().search_by_url("https://img.example.com/a.jpg")

    run_with_server(handler, operation)

    assert "api_key" not in captured["query"]


def test_search_by_bytes_uploads_file_field():
    captured: dict = {}

    async def handler(request):
        form: dict[str, bytes] = {}
        reader = await request.multipart()
        while True:
            part = await reader.next()
            if part is None:
                break
            form[part.name] = await part.read()
        captured["form"] = form
        return web.json_response(SAMPLE_RESULT)

    image_bytes = b"\x89PNG\r\n\x1a\nfake-image-content"

    async def operation():
        return await SauceNAOClient().search_by_bytes(image_bytes, "image.png")

    payload = run_with_server(handler, operation)

    assert payload["results"][0]["header"]["index_id"] == 5
    assert captured["form"]["file"] == image_bytes


def test_api_error_status_raises():
    async def handler(request):
        return web.json_response(
            {"header": {"status": -1, "message": "Invalid API key"}}
        )

    async def operation():
        return await SauceNAOClient().search_by_url("https://img.example.com/a.jpg")

    with pytest.raises(SauceNAOError) as exc_info:
        run_with_server(handler, operation)

    assert "Invalid API key" in str(exc_info.value)
    assert exc_info.value.status == -1


def test_http_403_json_api_error_is_surfaced():
    async def handler(request):
        return web.json_response(
            {
                "header": {
                    "status": -1,
                    "message": "The anonymous account type does not permit API usage.",
                }
            },
            status=403,
        )

    async def operation():
        return await SauceNAOClient().search_by_url("https://img.example.com/a.jpg")

    with pytest.raises(SauceNAOError) as exc_info:
        run_with_server(handler, operation)

    assert "anonymous account" in str(exc_info.value)
    assert exc_info.value.status == -1


def test_cloudflare_html_gives_friendly_error():
    async def handler(request):
        return web.Response(
            text="<html><title>Just a moment...</title></html>",
            content_type="text/html",
        )

    async def operation():
        return await SauceNAOClient().search_by_url("https://img.example.com/a.jpg")

    with pytest.raises(SauceNAOError) as exc_info:
        run_with_server(handler, operation)

    assert "Cloudflare" in str(exc_info.value)


def test_http_error_status_raises():
    async def handler(request):
        return web.Response(status=500, text="server error")

    async def operation():
        return await SauceNAOClient().search_by_url("https://img.example.com/a.jpg")

    with pytest.raises(SauceNAOError) as exc_info:
        run_with_server(handler, operation)

    assert "HTTP 500" in str(exc_info.value)
