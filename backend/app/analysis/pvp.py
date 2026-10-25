"""PvP IV ranking per species form and league (spec §12.1).

For each of the 4096 IV combinations the highest allowed level whose CP stays within the
league cap is found, and the stat product at that level is ranked. Ties share a rank
(competition ranking: 1, 2, 2, 4). The level range and CP multipliers come from the active
dataset; the maximum level is a setting (50, or 51 with a Best Buddy).

The table is computed with numpy in one vectorized pass (about a millisecond per table), so a
collection of thousands of Pokémon with all their evolutions is analysed in seconds.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from app.analysis.stats import BaseStats

IV_VALUES = 16
COMBINATIONS = IV_VALUES**3
CP_DIVISOR = 10.0
MIN_CP = 10
MIN_HP = 10
TIE_TOLERANCE = 1e-9

_IV_A, _IV_D, _IV_S = (
    axis.ravel()
    for axis in np.meshgrid(np.arange(IV_VALUES), np.arange(IV_VALUES), np.arange(IV_VALUES), indexing="ij")
)


@dataclass(frozen=True, slots=True)
class RankEntry:
    rank: int
    level: float
    cp: int
    stat_product: float
    percent_of_best: float
    attack: float
    defense: float
    hp: int


@dataclass(frozen=True, slots=True)
class RankTable:
    cap: int | None
    max_level: float
    ranks: npt.NDArray[np.int64]
    levels: npt.NDArray[np.float64]
    cps: npt.NDArray[np.int64]
    products: npt.NDArray[np.float64]
    attack: npt.NDArray[np.float64]
    defense: npt.NDArray[np.float64]
    hp: npt.NDArray[np.int64]
    eligible: npt.NDArray[np.bool_]
    best_product: float

    @property
    def eligible_count(self) -> int:
        return int(self.eligible.sum())

    def lookup(self, attack: int, defense: int, stamina: int) -> RankEntry | None:
        if not (0 <= attack < IV_VALUES and 0 <= defense < IV_VALUES and 0 <= stamina < IV_VALUES):
            return None
        index = attack * IV_VALUES * IV_VALUES + defense * IV_VALUES + stamina
        if not self.eligible[index]:
            return None
        product = float(self.products[index])
        return RankEntry(
            rank=int(self.ranks[index]),
            level=float(self.levels[index]),
            cp=int(self.cps[index]),
            stat_product=product,
            percent_of_best=product / self.best_product * 100 if self.best_product else 0.0,
            attack=float(self.attack[index]),
            defense=float(self.defense[index]),
            hp=int(self.hp[index]),
        )

    def top(self, count: int) -> list[tuple[tuple[int, int, int], RankEntry]]:
        order = np.argsort(np.where(self.eligible, self.ranks, COMBINATIONS + 1), kind="stable")[:count]
        result = []
        for index in order:
            if not self.eligible[index]:
                break
            ivs = (int(_IV_A[index]), int(_IV_D[index]), int(_IV_S[index]))
            entry = self.lookup(*ivs)
            if entry is not None:
                result.append((ivs, entry))
        return result


def build_rank_table(
    base: BaseStats,
    cap: int | None,
    levels: list[tuple[float, float]],
    *,
    iv_floor: int = 0,
) -> RankTable:
    """``levels`` is the ascending list of ``(level, cpm)`` pairs that may be used."""
    level_values = np.array([lv for lv, _ in levels], dtype=np.float64)
    cpm = np.array([c for _, c in levels], dtype=np.float64)
    attack_total = (base.attack + _IV_A).astype(np.float64)
    defense_total = (base.defense + _IV_D).astype(np.float64)
    stamina_total = (base.stamina + _IV_S).astype(np.float64)
    eligible = (iv_floor <= _IV_A) & (iv_floor <= _IV_D) & (iv_floor <= _IV_S)
    if cpm.size == 0:
        empty_f = np.zeros(COMBINATIONS)
        empty_i = np.zeros(COMBINATIONS, dtype=np.int64)
        return RankTable(
            cap,
            0.0,
            empty_i,
            empty_f,
            empty_i,
            empty_f,
            empty_f,
            empty_f,
            empty_i,
            np.zeros(COMBINATIONS, dtype=bool),
            0.0,
        )

    factor = attack_total * np.sqrt(defense_total) * np.sqrt(stamina_total) / CP_DIVISOR
    cpm_squared = cpm**2
    last = cpm.size - 1

    def cp_at(idx: npt.NDArray[np.int64]) -> npt.NDArray[np.int64]:
        safe = np.clip(idx, 0, last)
        return np.maximum(MIN_CP, np.floor(factor * cpm_squared[safe])).astype(np.int64)

    if cap is None:
        index = np.full(COMBINATIONS, last, dtype=np.int64)
    else:
        # CP rises monotonically with level, and floor(f·c²) <= cap  ⟺  c² < (cap+1)/f. The
        # bisection gives the candidate; the two corrections absorb float rounding at the edge.
        index = np.searchsorted(cpm_squared, (cap + 1) / factor, side="left").astype(np.int64) - 1
        index = np.where((index >= 0) & (cp_at(index) > cap), index - 1, index)
        step_up = (index + 1 <= last) & (cp_at(index + 1) <= cap)
        index = np.where(step_up, index + 1, index)
        eligible &= (index >= 0) & (cp_at(index) <= cap)
        index = np.clip(index, 0, last)
    chosen_cpm = cpm[index]
    hp = np.maximum(MIN_HP, np.floor(stamina_total * chosen_cpm)).astype(np.int64)
    attack = attack_total * chosen_cpm
    defense = defense_total * chosen_cpm
    products = attack * defense * hp
    cps = cp_at(index)

    masked = np.where(eligible, products, -1.0)
    best = float(masked.max()) if eligible.any() else 0.0
    # Competition ranking: rank = 1 + number of eligible combinations with a strictly larger
    # stat product (relative tolerance keeps float noise from splitting real ties).
    sorted_desc = np.sort(masked[eligible])[::-1]
    threshold = products * (1 + TIE_TOLERANCE)
    greater = np.searchsorted(-sorted_desc, -threshold, side="left")
    ranks = (greater + 1).astype(np.int64)
    return RankTable(
        cap=cap,
        max_level=float(level_values[-1]),
        ranks=ranks,
        levels=level_values[index],
        cps=cps,
        products=products,
        attack=attack,
        defense=defense,
        hp=hp,
        eligible=eligible,
        best_product=best,
    )


class RankTableCache:
    """Process-wide LRU cache. Tables depend only on base stats, cap, level range and floor."""

    def __init__(self, max_entries: int = 6000) -> None:
        self._max = max_entries
        self._data: OrderedDict[tuple[object, ...], RankTable] = OrderedDict()
        self._lock = threading.Lock()

    def get(
        self,
        version_id: int,
        base: BaseStats,
        cap: int | None,
        levels: list[tuple[float, float]],
        iv_floor: int = 0,
    ) -> RankTable:
        key = (version_id, base, cap, levels[-1][0] if levels else 0.0, iv_floor)
        with self._lock:
            table = self._data.get(key)
            if table is not None:
                self._data.move_to_end(key)
                return table
        table = build_rank_table(base, cap, levels, iv_floor=iv_floor)
        with self._lock:
            self._data[key] = table
            if len(self._data) > self._max:
                self._data.popitem(last=False)
        return table

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


RANK_TABLES = RankTableCache()
