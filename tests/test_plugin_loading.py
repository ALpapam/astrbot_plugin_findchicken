"""按 AstrBot 的插件加载方式做一次导入冒烟测试。"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def test_astrbot_import_style(tmp_path, monkeypatch):
    """模拟 data/plugins/<name>/main.py 的导入方式，确认相对导入可用。"""
    plugins_dir = tmp_path / "data" / "plugins"
    plugins_dir.mkdir(parents=True)
    target = plugins_dir / PLUGIN_ROOT.name
    shutil.copytree(
        PLUGIN_ROOT,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "tests"),
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module(f"data.plugins.{PLUGIN_ROOT.name}.main")

    try:
        assert module.FindChickenPlugin.__mro__[-2].__name__ == "Star"
        assert module.FindChickenPlugin.find_chicken.__command__ == "找鸡"
    finally:
        for name in list(sys.modules):
            if name == "data" or name.startswith(f"data.plugins.{PLUGIN_ROOT.name}"):
                sys.modules.pop(name, None)
