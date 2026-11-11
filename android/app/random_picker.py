# -*- coding: utf-8 -*-
"""随机练习抽题（纯逻辑，只读题库）。

- 只调用 database.list_questions()，绝不写题库；
- 抽题结果是一份题目快照，交给 PracticeSession(MODE_RANDOM, ...)；
- 随机练习不写 progress.db，只在完成时写一条 history（由主窗口负责）。
"""
from __future__ import annotations

import random

from . import database

TYPE_ORDER = ("single", "multiple", "judge")
SCOPE_ALL = "all"


def collect_pool(scope: str = SCOPE_ALL, set_name=None):
    """按范围取题：全部题型按 单选/多选/判断 顺序合并，保持题库原顺序。"""
    if scope == SCOPE_ALL or not scope:
        pool = []
        for qtype in TYPE_ORDER:
            pool.extend(database.list_questions(qtype=qtype, set_name=set_name))
        return pool
    return database.list_questions(qtype=scope, set_name=set_name)


def count_pool(set_name=None) -> dict:
    """各范围可用题数：{"all": N, "single": n, "multiple": n, "judge": n}。"""
    counts = {SCOPE_ALL: 0}
    for qtype in TYPE_ORDER:
        n = len(database.list_questions(qtype=qtype, set_name=set_name))
        counts[qtype] = n
        counts[SCOPE_ALL] += n
    return counts


def pick_questions(scope: str = SCOPE_ALL, count=None, shuffle: bool = True,
                   set_name=None, rng=None) -> list:
    """抽取题目快照。count 为 None 表示全部；越界自动收敛到可用题数。"""
    pool = collect_pool(scope, set_name)
    total = len(pool)
    if total == 0:
        return []
    if count is None:
        n = total
    else:
        try:
            n = int(count)
        except (TypeError, ValueError):
            n = total
        n = max(1, min(n, total))
    items = list(pool)
    if shuffle:
        (rng or random).shuffle(items)
    return items[:n]
