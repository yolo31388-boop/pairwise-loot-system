"""掉落系统测试"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.engine import LootSystem, LootItem

class TestDropRate:
    def test_total_probability_normalized(self):
        ls = LootSystem()
        ls.drop_table = [LootItem("a","a","rare",0.8), LootItem("b","b","epic",0.8)]
        # 总概率160%，应该归一化
        results = [ls.roll() for _ in range(100)]
        # 至少b应该有机会掉
        assert any("b" in [i.iid for i in r] for r in results), "概率超100%导致后面物品不掉"

class TestPity:
    def test_pity_guaranteed(self):
        ls = LootSystem()
        ls.pity_threshold = 10
        for i in range(9):
            ls.check_pity()
        assert ls.check_pity(), "保底未触发"
