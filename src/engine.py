"""掉落系统

修复点：
1. 多物品概率归一化（总概率不超过 100%），归一化后逐项独立 roll。
2. 稀有度保底：连续未出稀有计数器，达到保底次数必出稀有并重置。
3. 组队掉落：每个队员独立 roll（或使用队伍分配模式 round_robin / shared）。
4. 世界 BOSS：按伤害/治疗/贡献度比例分配掉落权重。
5. 随机性：每位玩家独立 RNG，种子混合玩家标识 + 时间戳 + 系统熵，
   SL（存档读档）后结果不同且不可预测；不再使用全局 random。
"""

import os
import random
import time
from dataclasses import dataclass, field


@dataclass
class LootItem:
    iid: str
    name: str
    rarity: str
    drop_rate: float


def _member_id(member):
    if isinstance(member, str):
        return member
    return getattr(member, "pid", None) or getattr(member, "id", None) or getattr(member, "name", str(member))


class PlayerRNG:
    """每玩家独立的随机源。

    种子由玩家标识、当前时间戳和 os.urandom 系统熵混合而成，
    因此即使立刻 SL 重开，时间戳/熵不同，掉落序列也无法预测。
    """

    def __init__(self, player_id):
        self.player_id = str(player_id)
        self.rng = random.Random()
        self.reseed()

    def reseed(self):
        entropy = int.from_bytes(os.urandom(16), "big")
        self.seed = hash((self.player_id, time.time_ns(), entropy, id(self)))
        self.rng.seed(self.seed)
        return self.seed

    def random(self):
        return self.rng.random()

    def randint(self, a, b):
        return self.rng.randint(a, b)

    def weighted_choice(self, entries):
        weights = [float(w) for _, w in entries]
        if not entries or sum(weights) <= 0:
            return None
        return self.rng.choices(entries, weights=weights, k=1)[0][0]


class LootSystem:
    RARE_RARITIES = ("rare", "epic", "legendary", "稀有", "史诗", "传说")

    def __init__(self):
        self.drop_table: list[LootItem] = []
        self.pity_threshold = 100
        # 连续未出稀有计数器（默认/全局玩家）
        self.pity_counter = 0
        # 每玩家独立计数器与随机源
        self._pity = {}
        self._rngs = {}

    # ---- 随机性 ----
    def _rng(self, player_id=None):
        if player_id is None:
            if None not in self._rngs:
                self._rngs[None] = PlayerRNG(f"system@{id(self)}")
            return self._rngs[None]
        pid = str(player_id)
        if pid not in self._rngs:
            self._rngs[pid] = PlayerRNG(pid)
        return self._rngs[pid]

    def reseed_player(self, player_id):
        """玩家读档/重进时重新播种，保证 SL 后结果不同。"""
        pid = str(player_id)
        if pid in self._rngs:
            return self._rngs[pid].reseed()
        return self._rng(pid).seed

    # ---- bug1: 概率归一化 ----
    def normalized_rates(self):
        total = sum(item.drop_rate for item in self.drop_table)
        scale = 1.0 if total <= 1.0 else 1.0 / total
        return [(item, item.drop_rate * scale) for item in self.drop_table]

    def _get_pity(self, player_id):
        if player_id is None:
            return self.pity_counter
        return self._pity.setdefault(str(player_id), 0)

    def _set_pity(self, player_id, value):
        if player_id is None:
            self.pity_counter = value
        else:
            self._pity[str(player_id)] = value

    def roll(self, player_id=None):
        """归一化后逐项独立 roll；保底触发时强制补一件稀有。"""
        rng = self._rng(player_id)
        results = []
        for item, rate in self.normalized_rates():
            if rng.random() < rate:
                results.append(item)

        got_rare = any(item.rarity in self.RARE_RARITIES for item in results)
        if got_rare:
            self._set_pity(player_id, 0)
        else:
            counter = self._get_pity(player_id) + 1
            if counter >= self.pity_threshold:
                rare_items = [
                    item for item, _ in self.normalized_rates()
                    if item.rarity in self.RARE_RARITIES
                ]
                if rare_items:
                    forced = rng.rng.choice(rare_items)
                    if forced not in results:
                        results.append(forced)
                counter = 0
            self._set_pity(player_id, counter)
        return results

    # ---- bug2: 保底 ----
    def check_pity(self, player_id=None):
        """记录一次未出稀有；达到保底次数返回 True 并重置计数器。"""
        counter = self._get_pity(player_id) + 1
        if counter >= self.pity_threshold:
            self._set_pity(player_id, 0)
            return True
        self._set_pity(player_id, counter)
        return False

    def get_pity_counter(self, player_id=None):
        return self._get_pity(player_id)

    def reset_pity(self, player_id=None):
        self._set_pity(player_id, 0)

    # ---- bug3: 组队独立 roll / 分配模式 ----
    def party_loot(self, party_members, mode="independent"):
        """掉落归属。

        - independent（默认）：每人独立 roll，互不影响。
        - round_robin：roll 一次，物品在队伍内轮流分配。
        - shared：roll 一次，所有物品归首人（保留旧行为的显式选项）。
        """
        if not party_members:
            return {}

        if mode == "independent":
            return {
                member: self.roll(player_id=_member_id(member))
                for member in party_members
            }

        drops = self.roll(player_id=f"party@{id(party_members)}")
        if mode == "shared":
            return {member: list(drops) if member == party_members[0] else []
                    for member in party_members}

        # round_robin
        buckets = {member: [] for member in party_members}
        for index, item in enumerate(drops):
            buckets[party_members[index % len(party_members)]].append(item)
        return buckets

    # ---- bug4: 世界 BOSS 参与度分配 ----
    def world_boss_loot(self, contributions, rolls=None):
        """contributions: {玩家: 伤害/治疗/贡献值}，按比例加权掉落。"""
        if not contributions:
            return {}

        participants = list(contributions.keys())
        weights = [max(0.0, float(contributions[p])) for p in participants]
        total_weight = sum(weights)

        drops = self.roll(player_id=f"boss@{id(contributions)}-{time.time_ns()}")
        if rolls is None:
            rolls = max(1, len(drops)) if drops else 1

        result = {p: [] for p in participants}
        if total_weight <= 0:
            return result

        rng = self._rng(f"boss@{id(contributions)}")
        pool = list(drops)
        # 掉落不足时用表中物品按权重补抽
        while len(pool) < rolls:
            table = self.normalized_rates()
            if not table:
                break
            pool.append(rng.weighted_choice(table))

        for _ in range(min(rolls, len(pool))):
            winner = rng.rng.choices(participants, weights=weights, k=1)[0]
            result[winner].append(pool.pop(0))
        return result

    # ---- bug5: 每玩家独立种子的属性随机 ----
    def generate_stats(self, item, player_id=None):
        rng = self._rng(player_id)
        return {"atk": rng.randint(1, 100)}
