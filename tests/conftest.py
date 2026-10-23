"""pytest 环境准备：注入 AstrBot stub 与插件包路径。"""

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_STUBS = Path(__file__).resolve().parent / "stubs"

for _path in (str(_STUBS), str(_PLUGIN_ROOT.parent)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
