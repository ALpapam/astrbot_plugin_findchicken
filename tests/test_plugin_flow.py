"""插件指令处理流程测试（使用 stub 模拟 AstrBot）。"""

from __future__ import annotations

import asyncio
import types

from astrbot.api.message_components import At, Image, Plain, Reply

from astrbot_plugin_findchicken import main as plugin_module
from astrbot_plugin_findchicken.findchicken.client import SauceNAOError
from astrbot_plugin_findchicken.findchicken.formatter import (
    API_KEY_INVALID_TEXT,
    NOT_FOUND_TEXT,
    NO_API_KEY_TEXT,
    PROGRESS_TEXT,
    SEARCH_FAILED_TEXT,
    USAGE_TEXT,
)

PIXIV_RESULTS = {
    "header": {"status": 0},
    "results": [
        {
            "header": {
                "similarity": "95.20",
                "thumbnail": "https://img.example.com/thumb.jpg",
                "index_id": 5,
                "index_name": "Pixiv",
            },
            "data": {
                "pixiv_id": 123,
                "title": "夕焼け",
                "member_name": "テスト絵師",
                "ext_urls": ["https://www.pixiv.net/artworks/123"],
            },
        }
    ],
}

EXPECTED_FOUND = (
    "**已找到鸡**\n\n"
    "平台：Pixiv\n"
    "匹配：视觉匹配\n"
    "名字：夕焼け\n"
    "账号：@テスト絵師\n\n"
    "⚠识图存在误差，请自行核对哦~"
)


class FakeClient:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload or {"results": []}
        self.error = error
        self.calls: list[tuple[str, object]] = []

    async def search_by_url(self, image_url: str):
        self.calls.append(("url", image_url))
        if self.error:
            raise self.error
        return self.payload

    async def search_by_bytes(self, image_bytes: bytes, filename: str = "image.jpg"):
        self.calls.append(("bytes", filename))
        if self.error:
            raise self.error
        return self.payload


class FakeEvent:
    def __init__(
        self,
        messages=None,
        message_str: str = "",
        sender_id: str = "10001",
        raw_message=None,
        self_id: str = "999",
        is_at_or_wake_command: bool = False,
    ) -> None:
        self._messages = messages or []
        self.message_str = message_str
        self._sender_id = sender_id
        self._self_id = self_id
        self.is_at_or_wake_command = is_at_or_wake_command
        self.message_obj = types.SimpleNamespace(raw_message=raw_message)
        self.stopped = False

    def get_messages(self):
        return self._messages

    def get_sender_id(self):
        return self._sender_id

    def get_self_id(self):
        return self._self_id

    def stop_event(self):
        self.stopped = True

    def plain_result(self, text: str):
        return {"type": "plain", "text": text}


def make_plugin(payload=None, error=None, **overrides):
    config = {
        "api_key": "test-key",
        "proxy": "",
        "timeout_seconds": 30,
        "max_results": 1,
        "similarity_threshold": 30,
        "send_progress": False,
        "show_similarity": False,
        "cooldown_seconds": 0,
    }
    config.update(overrides)
    plugin = plugin_module.FindChickenPlugin(None, config)
    plugin.client = FakeClient(payload, error)
    return plugin


def run_handler(plugin, event, handler=None) -> list[str]:
    target = handler or plugin.find_chicken

    async def consume():
        return [item["text"] async for item in target(event)]

    return asyncio.run(consume())


def test_image_input_returns_template():
    plugin = make_plugin(PIXIV_RESULTS)
    event = FakeEvent(messages=[Image(url="https://img.example.com/a.jpg")])

    outputs = run_handler(plugin, event)

    assert outputs == [EXPECTED_FOUND]
    assert plugin.client.calls == [("url", "https://img.example.com/a.jpg")]


def test_url_input_uses_direct_url_match_label():
    plugin = make_plugin(PIXIV_RESULTS)
    event = FakeEvent(message_str="找鸡 https://img.example.com/a.jpg")

    outputs = run_handler(plugin, event)

    assert "匹配：图片直链" in outputs[0]
    assert plugin.client.calls == [("url", "https://img.example.com/a.jpg")]


def test_quoted_image_is_used():
    plugin = make_plugin(PIXIV_RESULTS)
    event = FakeEvent(
        messages=[
            Reply(chain=[Image(url="https://img.example.com/quoted.jpg")]),
        ],
        message_str="找鸡",
    )

    outputs = run_handler(plugin, event)

    assert outputs == [EXPECTED_FOUND]
    assert plugin.client.calls == [("url", "https://img.example.com/quoted.jpg")]


def test_no_image_returns_usage():
    plugin = make_plugin(PIXIV_RESULTS)
    event = FakeEvent(message_str="找鸡")

    outputs = run_handler(plugin, event)

    assert outputs == [USAGE_TEXT]
    assert plugin.client.calls == []


def test_empty_results_returns_not_found():
    plugin = make_plugin({"header": {"status": 0}, "results": []})
    event = FakeEvent(messages=[Image(url="https://img.example.com/a.jpg")])

    outputs = run_handler(plugin, event)

    assert outputs == [NOT_FOUND_TEXT]


def test_similarity_threshold_rejects_low_match():
    plugin = make_plugin(PIXIV_RESULTS, similarity_threshold=99)
    event = FakeEvent(messages=[Image(url="https://img.example.com/a.jpg")])

    outputs = run_handler(plugin, event)

    assert outputs == [NOT_FOUND_TEXT]


def test_sauce_nao_error_returns_failure_message():
    plugin = make_plugin(error=SauceNAOError("boom"))
    event = FakeEvent(messages=[Image(url="https://img.example.com/a.jpg")])

    outputs = run_handler(plugin, event)

    assert outputs == [SEARCH_FAILED_TEXT]


def test_missing_api_key_returns_config_hint():
    plugin = make_plugin(PIXIV_RESULTS, api_key="")
    event = FakeEvent(messages=[Image(url="https://img.example.com/a.jpg")])

    outputs = run_handler(plugin, event)

    assert outputs == [NO_API_KEY_TEXT]
    assert plugin.client.calls == []


def test_invalid_api_key_error_maps_to_config_hint():
    plugin = make_plugin(
        error=SauceNAOError(
            "The anonymous account type does not permit API usage.",
            status=-1,
        )
    )
    event = FakeEvent(messages=[Image(url="https://img.example.com/a.jpg")])

    outputs = run_handler(plugin, event)

    assert outputs == [API_KEY_INVALID_TEXT]


def test_progress_message_is_sent_first():
    plugin = make_plugin(PIXIV_RESULTS, send_progress=True)
    event = FakeEvent(messages=[Image(url="https://img.example.com/a.jpg")])

    outputs = run_handler(plugin, event)

    assert outputs[0] == PROGRESS_TEXT
    assert outputs[1] == EXPECTED_FOUND


def test_cooldown_blocks_second_search():
    plugin = make_plugin(PIXIV_RESULTS, cooldown_seconds=60)
    event = FakeEvent(messages=[Image(url="https://img.example.com/a.jpg")])

    first = run_handler(plugin, event)
    second = run_handler(plugin, event)

    assert first == [EXPECTED_FOUND]
    assert second and second[0].startswith("别急，鸡要慢慢找")
    # 第二次不应再请求 SauceNAO
    assert len(plugin.client.calls) == 1


def test_show_similarity_flag():
    plugin = make_plugin(PIXIV_RESULTS, show_similarity=True)
    event = FakeEvent(messages=[Image(url="https://img.example.com/a.jpg")])

    outputs = run_handler(plugin, event)

    assert "匹配：视觉匹配（相似度 95.2%）" in outputs[0]


def test_multiple_results_are_combined():
    payload = {
        "header": {"status": 0},
        "results": PIXIV_RESULTS["results"]
        + [
            {
                "header": {
                    "similarity": "88.00",
                    "index_id": 9,
                    "index_name": "Twitter",
                },
                "data": {
                    "twitter_user_handle": "artist_x",
                    "ext_urls": ["https://x.com/artist_x/status/1"],
                },
            }
        ],
    }
    plugin = make_plugin(payload, max_results=2)
    event = FakeEvent(messages=[Image(url="https://img.example.com/a.jpg")])

    outputs = run_handler(plugin, event)

    assert outputs[0].count("**已找到鸡**") == 1
    assert "平台：Pixiv" in outputs[0]
    assert "平台：X (Twitter)" in outputs[0]


def test_quoted_reply_auto_mention_fallback():
    """QQ 回复他人图片时自动插入的 @ 会让 message_str 变形，应能兜底处理。"""
    plugin = make_plugin(PIXIV_RESULTS)
    event = FakeEvent(
        messages=[
            Reply(
                chain=[Image(url="https://img.example.com/quoted.jpg")],
                sender_id="10002",
            ),
            At(qq="10002"),
            Plain("找鸡"),
        ],
        is_at_or_wake_command=False,
    )

    outputs = run_handler(plugin, event, plugin.find_chicken_quoted)

    assert outputs == [EXPECTED_FOUND]
    assert event.stopped is True


def test_quoted_fallback_handles_wake_event_too():
    """即使事件已被唤醒，回复消息里的 @ 文本也会让标准指令匹配失败，需要兜底。"""
    plugin = make_plugin(PIXIV_RESULTS)
    event = FakeEvent(
        messages=[
            Reply(
                chain=[Image(url="https://img.example.com/quoted.jpg")],
                sender_id="10002",
            ),
            At(qq="10002"),
            Plain("找鸡"),
        ],
        is_at_or_wake_command=True,
    )

    outputs = run_handler(plugin, event, plugin.find_chicken_quoted)

    assert outputs == [EXPECTED_FOUND]
    assert event.stopped is True


def test_quoted_fallback_with_bot_mention():
    plugin = make_plugin(PIXIV_RESULTS)
    event = FakeEvent(
        messages=[
            Reply(
                chain=[Image(url="https://img.example.com/quoted.jpg")],
                sender_id="10002",
            ),
            At(qq="10002"),
            At(qq="999"),
            Plain(" 找鸡"),
        ],
        is_at_or_wake_command=True,
    )

    outputs = run_handler(plugin, event, plugin.find_chicken_quoted)

    assert outputs == [EXPECTED_FOUND]


def test_quoted_fallback_ignores_other_commands():
    plugin = make_plugin(PIXIV_RESULTS)
    event = FakeEvent(
        messages=[
            Reply(chain=[], sender_id="10002"),
            At(qq="10002"),
            Plain("搜图"),
        ],
        is_at_or_wake_command=False,
    )

    outputs = run_handler(plugin, event, plugin.find_chicken_quoted)

    assert outputs == []
