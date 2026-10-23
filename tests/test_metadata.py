"""插件元数据与配置 schema 校验。"""

import json
import keyword
import re
from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

METADATA_REQUIRED = ("name", "desc", "version", "author")
SCHEMA_TYPES = {"string", "text", "int", "float", "bool", "object", "list"}


def test_metadata_is_valid():
    metadata = yaml.safe_load((PLUGIN_ROOT / "metadata.yaml").read_text("utf-8"))

    for field in METADATA_REQUIRED:
        assert isinstance(metadata.get(field), str) and metadata[field].strip()

    name = metadata["name"]
    assert name.isidentifier() and not keyword.iskeyword(name)
    assert name == PLUGIN_ROOT.name
    assert re.fullmatch(r"\d+(\.\d+){0,2}", metadata["version"])
    assert metadata["display_name"] == "找鸡"


def test_conf_schema_is_valid():
    schema = json.loads((PLUGIN_ROOT / "_conf_schema.json").read_text("utf-8"))

    expected_keys = {
        "api_key",
        "proxy",
        "timeout_seconds",
        "max_results",
        "similarity_threshold",
        "send_progress",
        "show_similarity",
        "cooldown_seconds",
    }
    assert set(schema) == expected_keys

    for key, item in schema.items():
        assert item["type"] in SCHEMA_TYPES, key
        assert "default" in item, key

    assert schema["api_key"]["secret"] is True
    assert schema["max_results"]["type"] == "int"
    assert schema["send_progress"]["type"] == "bool"
