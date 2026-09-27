"""掉落核心入口。

核心实现位于 src/engine.py，此处统一对外导出，保持
`from loot.system import LootSystem, LootItem` 可用。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.engine import LootItem, LootSystem, PlayerRNG

__all__ = ["LootItem", "LootSystem", "PlayerRNG"]
