"""输出文案格式化测试。"""

from astrbot_plugin_findchicken.findchicken.formatter import (
    HEADER,
    NOT_FOUND_TEXT,
    format_hit,
    format_hits,
)
from astrbot_plugin_findchicken.findchicken.models import SearchHit


def make_hit(**overrides) -> SearchHit:
    values = {
        "index_id": 5,
        "index_name": "Pixiv",
        "similarity": 95.2,
        "title": "夕焼け",
        "author": "テスト絵師",
        "author_handle": "",
        "member_id": "724886",
        "page_url": "https://www.pixiv.net/artworks/123",
        "direct_url": "",
        "thumbnail": "https://img.example.com/thumb.jpg",
    }
    values.update(overrides)
    return SearchHit(**values)


def test_format_single_hit_matches_template():
    text = format_hits([make_hit()], match_label="视觉匹配")

    assert text == (
        "**已找到鸡**\n\n"
        "平台：Pixiv\n"
        "匹配：视觉匹配\n"
        "名字：テスト絵師\n"
        "账号：@724886\n\n"
        "⚠识图存在误差，请自行核对哦~"
    )


def test_twitter_hit_uses_handle_for_name_and_account():
    hit = make_hit(
        index_id=41,
        index_name="Twitter",
        title="",
        author="mamamia1008",
        author_handle="mamamia1008",
        member_id="",
    )
    text = format_hit(hit, "视觉匹配")

    assert "平台：X (Twitter)" in text
    assert "名字：mamamia1008" in text
    assert "账号：@mamamia1008" in text


def test_format_direct_url_match_label():
    text = format_hits([make_hit()], match_label="图片直链")

    assert "匹配：图片直链" in text


def test_show_similarity_only_for_visual_match():
    visual = format_hit(make_hit(), "视觉匹配", show_similarity=True)
    direct = format_hit(make_hit(), "图片直链", show_similarity=True)

    assert "匹配：视觉匹配（相似度 95.2%）" in visual
    assert direct.count("匹配：图片直链") == 1
    assert "相似度" not in direct


def test_multiple_hits_share_header_and_footer():
    first = make_hit()
    second = make_hit(
        index_id=41,
        index_name="Twitter",
        title="",
        author="artist_x",
        author_handle="artist_x",
        member_id="",
    )

    text = format_hits([first, second], match_label="视觉匹配")

    assert text.count(HEADER) == 1
    assert text.count("⚠识图存在误差，请自行核对哦~") == 1
    assert "平台：X (Twitter)" in text
    assert text.endswith("⚠识图存在误差，请自行核对哦~")


def test_not_found_text_is_non_empty():
    assert NOT_FOUND_TEXT.startswith("**没找到鸡**")
