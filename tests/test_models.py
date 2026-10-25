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
                "index_name": "Index #5: Pixiv Images - 4933944_s.jpg",
            },
            "data": {
                "pixiv_id": 4933944,
                "title": "妖キャラをカリスマ化してみた。",
                "member_name": "佳虫",
                "member_id": 724886,
                "ext_urls": ["https://www.pixiv.net/artworks/4933944"],
            },
        },
        {
            "header": {
                "similarity": "88.00",
                "thumbnail": "https://img.example.com/thumb2.jpg",
                "index_id": 41,
                "index_name": "Index #41: Twitter - DDPiisvUwAQOGWR.jpg",
            },
            "data": {
                "tweet_id": "1",
                "twitter_user_handle": "mamamia1008",
                "ext_urls": ["https://x.com/mamamia1008/status/1"],
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
    # 名字显示画师昵称，账号显示画师数字用户 ID
    assert pixiv.display_name == "佳虫"
    assert pixiv.display_account == "@724886"
    assert pixiv.page_url == "https://www.pixiv.net/artworks/4933944"


def test_parse_twitter_platform_and_handle():
    hits = parse_results(PIXIV_PAYLOAD)
    twitter = hits[1]

    assert twitter.platform == "X (Twitter)"
    assert twitter.author_handle == "mamamia1008"
    assert twitter.display_name == "mamamia1008"
    assert twitter.display_account == "@mamamia1008"


def test_index_name_prefix_is_cleaned_for_unknown_platform():
    payload = {
        "results": [
            {
                "header": {
                    "similarity": "73.1",
                    "index_id": 99,
                    "index_name": "Index #99: NewSite - illustration.jpg",
                },
                "data": {"title": "art", "author_name": "someone"},
            }
        ]
    }

    hits = parse_results(payload)

    assert hits[0].platform == "NewSite"


def test_known_index_ids_map_to_platform_names():
    payload = {
        "results": [
            {
                "header": {
                    "similarity": "90",
                    "index_id": 9,
                    "index_name": "Index #9: Danbooru - x.jpg",
                },
                "data": {"creator": "nichimatsu seri", "title": "touhou"},
            },
            {
                "header": {
                    "similarity": "90",
                    "index_id": 6,
                    "index_name": "Index #6: Pixiv Historical - y.jpg",
                },
                "data": {
                    "member_name": "白菜",
                    "member_id": 58228,
                    "title": "【pixiv袁紹軍】",
                },
            },
        ]
    }

    hits = parse_results(payload)

    assert hits[0].platform == "Danbooru"
    assert hits[1].platform == "Pixiv"
    assert hits[1].display_account == "@58228"


def test_creator_list_is_joined():
    payload = {
        "results": [
            {
                "header": {"similarity": "91", "index_id": 9, "index_name": "Danbooru"},
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
                "header": {"similarity": "90", "index_id": 9, "index_name": "Danbooru"},
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
    hits = parse_results({"results": [{"header": {"index_id": 99}, "data": {}}]})

    assert len(hits) == 1
    assert hits[0].platform == "未知平台"
    assert hits[0].display_name == "未知"
    assert hits[0].display_account == "未知"


def test_invalid_payload_returns_empty():
    assert parse_results({}) == []
    assert parse_results({"results": "nope"}) == []  # type: ignore[arg-type]
