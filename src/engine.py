"""掉落系统"""
import hashlib
import random
import secrets
import time
from dataclasses import dataclass

RARE_RARITIES = ("rare", "epic", "legendary")


@dataclass
class LootItem:
    iid: str
    name: str
    rarity: str
    drop_rate: float


class LootSystem:
    def __init__(self):
        self.drop_table: list[LootItem] = []
        self.pity_counter = 0
        self.pity_threshold = 100
        self._salt = secrets.token_hex(16)
        self._player_seeds = {}
        self._nonce = 0

    def _rng_for(self, player_id=None):
        # 每玩家独立种子 + 时间戳 + 进程内随机盐，SL 后结果不同且不可预测
        if player_id not in self._player_seeds:
            self._player_seeds[player_id] = secrets.token_hex(16)
        self._nonce += 1
        material = f"{self._salt}:{self._player_seeds[player_id]}:{time.time_ns()}:{self._nonce}"
        seed = int.from_bytes(hashlib.sha256(material.encode()).digest(), "big")
        return random.Random(seed)

    def _normalized_rates(self):
        # 概率表归一化，多个物品概率总和不超过 100%
        rates = [(item, max(0.0, item.drop_rate)) for item in self.drop_table]
        total = sum(rate for _, rate in rates)
        scale = 1.0 / total if total > 1.0 else 1.0
        return [(item, rate * scale) for item, rate in rates]

    def roll(self, player_id=None):
        rng = self._rng_for(player_id)
        table = self._normalized_rates()
        drops = [item for item, rate in table if rng.random() < rate]
        if any(item.rarity in RARE_RARITIES for item in drops):
            # 出稀有，连续未出计数清零
            self.pity_counter = 0
        elif self.check_pity():
            # 达到保底次数，必出一个稀有并重置计数
            rare_table = [(item, rate) for item, rate in table
                          if item.rarity in RARE_RARITIES]
            if rare_table:
                items = [item for item, _ in rare_table]
                weights = [max(rate, 1e-9) for _, rate in rare_table]
                drops.append(rng.choices(items, weights=weights, k=1)[0])
        return drops

    def check_pity(self):
        # 连续未出计数器，达到保底次数必出且重置
        self.pity_counter += 1
        if self.pity_counter >= self.pity_threshold:
            self.pity_counter = 0
            return True
        return False

    def party_loot(self, party_members, distribution="independent"):
        # 每人独立 roll；distribution="shared" 时按个人掉落权重分配同一份掉落
        if distribution == "shared":
            drops = self.roll()
            result = {member: [] for member in party_members}
            if party_members and drops:
                rng = self._rng_for()
                for item in drops:
                    chosen = rng.choice(list(party_members))
                    result[chosen].append(item)
            return result
        return {member: self.roll(player_id=member) for member in party_members}

    def world_boss_loot(self, participants, loot_pool=None):
        # 按伤害/治疗/贡献比例分配掉落权重
        def score(value):
            if isinstance(value, dict):
                return float(value.get("damage", 0)
                             + value.get("healing", 0)
                             + value.get("contribution", 0))
            return float(value)

        weights = {player: max(0.0, score(value))
                   for player, value in participants.items()}
        if sum(weights.values()) <= 0:
            weights = {player: 1.0 for player in participants}
        players = list(weights)
        result = {player: [] for player in participants}
        pool = list(loot_pool) if loot_pool is not None else self.roll()
        for item in pool:
            rng = self._rng_for()
            chosen = rng.choices(players,
                                 weights=[weights[p] for p in players],
                                 k=1)[0]
            result[chosen].append(item)
        return result

    def generate_stats(self, item=None, player_id=None):
        # 每玩家独立种子 + 时间戳，SL 后结果不同且不可预测
        rng = self._rng_for(player_id)
        return {"atk": rng.randint(1, 100)}
