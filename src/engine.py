"""掉落系统 - 带5个bug"""
import random
from dataclasses import dataclass, field

@dataclass
class LootItem:
    iid: str
    name: str
    rarity: str
    drop_rate: float

class LootSystem:
    def __init__(self):
        self.drop_table: list[LootItem] = []
        self.pity_counter = 0  # bug2: 无保底计数
        self.pity_threshold = 100

    def roll(self):
        # bug1: 逐个roll，概率超100%
        results = []
        for item in self.drop_table:
            if random.random() < item.drop_rate:
                results.append(item)
        return results

    def check_pity(self):
        # bug2: 不保证
        self.pity_counter += 1
        return self.pity_counter >= self.pity_threshold

    def party_loot(self, party_members):
        # bug3: 非独立roll
        drops = self.roll()
        return {party_members[0]: drops}

    def generate_stats(self, item):
        # bug5: 全局随机
        return {"atk": random.randint(1, 100)}
