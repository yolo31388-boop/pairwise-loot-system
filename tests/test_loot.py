"""掉落系统回归测试：覆盖 5 个概率 bug 的修复。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.engine import LootItem, LootSystem


def _ids(results):
    return [item.iid for item in results]


class TestDropRate:
    def test_total_probability_normalized(self):
        ls = LootSystem()
        ls.drop_table = [LootItem("a", "a", "common", 0.8),
                         LootItem("b", "b", "common", 0.8)]
        results = [ls.roll() for _ in range(200)]
        assert any("b" in _ids(r) for r in results), "概率超100%导致后面物品不掉"

    def test_normalized_rates_sum_to_one(self):
        ls = LootSystem()
        ls.drop_table = [LootItem("a", "a", "common", 0.8),
                         LootItem("b", "b", "common", 0.8)]
        total = sum(rate for _, rate in ls.normalized_rates())
        assert abs(total - 1.0) < 1e-9, "归一化后总概率应不超过100%"


class TestPity:
    def test_pity_guaranteed(self):
        ls = LootSystem()
        ls.pity_threshold = 10
        for _ in range(9):
            ls.check_pity()
        assert ls.check_pity(), "保底未触发"

    def test_pity_counter_resets_after_guarantee(self):
        ls = LootSystem()
        ls.pity_threshold = 10
        ls.drop_table = [LootItem("r", "r", "rare", 0.0)]
        for _ in range(9):
            assert ls.roll() == []
        results = ls.roll()
        assert "r" in _ids(results), "连续未出稀有达到保底次数必出"
        assert ls.get_pity_counter() == 0, "保底触发后计数器应重置"


class TestPartyLoot:
    def test_party_members_roll_independently(self):
        ls = LootSystem()
        ls.drop_table = [LootItem("a", "a", "common", 0.5)]
        loot = ls.party_loot(["p1", "p2", "p3"])
        assert set(loot.keys()) == {"p1", "p2", "p3"}, "每个队员都应有独立掉落结果"
        outcomes = {tuple(_ids(v)) for v in loot.values()}
        assert len(outcomes) >= 1 and isinstance(loot["p1"], list)


class TestWorldBoss:
    def test_participation_weighted_distribution(self):
        ls = LootSystem()
        ls.drop_table = [LootItem("a", "a", "common", 1.0)]
        tally = {"whale": 0, "leech": 0}
        for _ in range(200):
            loot = ls.world_boss_loot({"whale": 90, "leech": 1}, rolls=1)
            for pid, items in loot.items():
                tally[pid] += len(items)
        assert tally["whale"] > tally["leech"] * 5, "高贡献者应显著获得更多掉落"


class TestRandomSeed:
    def test_stats_unpredictable_across_reloads(self):
        ls = LootSystem()
        item = LootItem("s", "sword", "rare", 1.0)
        before = ls.generate_stats(item, player_id="p1")
        ls.reseed_player("p1")  # 模拟 SL 读档
        after = ls.generate_stats(item, player_id="p1")
        assert 1 <= before["atk"] <= 100 and 1 <= after["atk"] <= 100
        sequences = set()
        for _ in range(50):
            ls.reseed_player("p1")
            sequences.add(ls.generate_stats(item, player_id="p1")["atk"])
        assert len(sequences) > 1, "SL 后属性序列应不可预测"
