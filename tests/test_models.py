"""SauceNAO 响应解析测试。"""

from astrbot_plugin_findchicken.findchicken.models import parse_results

PIXIV_PAYLOAD = {
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
                "member_id": 456,
                "ext_urls": ["https://www.pixiv.net/artworks/123"],
            },
        },
        {
            "header": {
                "similarity": "88.00",
                "thumbnail": "https://img.example.com/thumb2.jpg",
                "index_id": 9,
                "index_name": "Twitter",
            },
            "data": {
                "tweet_id": 1,
                "twitter_user_handle": "artist_x",
                "ext_urls": ["https://x.com/artist_x/status/1"],
            },
        },
    ],
}


def test_parse_pixiv_hit():
    hits = parse_results(PIXIV_PAYLOAD)

    assert len(hits) == 2
    pixiv = hits[0]
    assert pixiv.platform == "Pixiv"
    assert pixiv.similarity == 95.2
    assert pixiv.display_name == "夕焼け"
    assert pixiv.display_account == "@テスト絵師"
    assert pixiv.page_url == "https://www.pixiv.net/artworks/123"


def test_parse_twitter_platform_and_handle():
    hits = parse_results(PIXIV_PAYLOAD)
    twitter = hits[1]

    assert twitter.platform == "X (Twitter)"
    assert twitter.author_handle == "artist_x"
    assert twitter.display_account == "@artist_x"


def test_similarity_threshold_filters_results():
    hits = parse_results(PIXIV_PAYLOAD, min_similarity=90)

    assert len(hits) == 1
    assert hits[0].platform == "Pixiv"


def test_unknown_index_uses_api_index_name():
    payload = {
        "results": [
            {
                "header": {
                    "similarity": "73.1",
                    "index_id": 34,
                    "index_name": "deviantArt",
                },
                "data": {"title": "art", "author_name": "someone"},
            }
        ]
    }

    hits = parse_results(payload)

    assert len(hits) == 1
    assert hits[0].platform == "deviantArt"


def test_creator_list_is_joined():
    payload = {
        "results": [
            {
                "header": {"similarity": "91", "index_id": 3, "index_name": "Danbooru"},
                "data": {
                    "creator": ["alice", "bob"],
                    "ext_urls": ["https://danbooru.donmai.us/posts/1"],
                },
            }
        ]
    }

    hits = parse_results(payload)

    assert hits[0].author == "alice, bob"
    assert hits[0].display_name == "alice, bob"


def test_direct_image_url_detected():
    payload = {
        "results": [
            {
                "header": {"similarity": "90", "index_id": 3, "index_name": "Danbooru"},
                "data": {
                    "ext_urls": [
                        "https://danbooru.donmai.us/posts/1",
                        "https://cdn.example.com/image.png?size=large",
                    ]
                },
            }
        ]
    }

    hits = parse_results(payload)

    assert hits[0].direct_url == "https://cdn.example.com/image.png?size=large"


def test_missing_fields_are_safe():
    hits = parse_results({"results": [{"header": {}, "data": {}}]})

    assert len(hits) == 1
    assert hits[0].platform == "未知平台"
    assert hits[0].display_name == "未知"
    assert hits[0].display_account == "未知"


def test_invalid_payload_returns_empty():
    assert parse_results({}) == []
    assert parse_results({"results": "nope"}) == []  # type: ignore[arg-type]
