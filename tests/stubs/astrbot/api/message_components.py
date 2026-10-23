"""测试用的消息组件 stub。"""

from __future__ import annotations


class Plain:
    def __init__(self, text: str = "") -> None:
        self.text = text


class At:
    def __init__(self, qq: str = "0", name: str = "") -> None:
        self.qq = qq
        self.name = name


class Image:
    def __init__(
        self,
        file: str | None = "",
        url: str | None = "",
        path: str | None = "",
    ) -> None:
        self.file = file
        self.url = url
        self.path = path


class Reply:
    def __init__(
        self,
        id: str = "0",
        chain=None,
        message_str: str = "",
        sender_id: str = "0",
    ) -> None:
        self.id = id
        self.chain = chain or []
        self.message_str = message_str
        self.sender_id = sender_id
