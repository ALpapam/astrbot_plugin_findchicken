"""测试用的 astrbot.api.event stub。"""

from __future__ import annotations


class AstrMessageEvent:
    """仅用于类型标注的占位类。"""


class PlatformAdapterType:
    AIOCQHTTP = "aiocqhttp"
    ALL = "all"


class _Filter:
    PlatformAdapterType = PlatformAdapterType

    def command(self, name: str, **kwargs):
        def decorator(func):
            func.__command__ = name
            return func

        return decorator

    def event_message_type(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def platform_adapter_type(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator


filter = _Filter()
