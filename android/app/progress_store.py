# -*- coding: utf-8 -*-
"""独立进度存储（progress.db）——移动端移植版。

- 绝不创建/修改/删除题库文件；progress.db 与题库完全分离；
- practice_progress：普通练习进度，按 题库(bank_key)+题型+套题 唯一；
- history：答题历史，session_uuid 唯一，只追加（本步只做进度，历史接口保留）；
- 随机练习与错题本练习不调用 save_progress。

文件位置：应用私有数据目录（Android 上是
/data/data/<包名>/files/app 下的 progress.db），与题库同目录但互不影响。
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

_path = None

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS practice_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_key TEXT NOT NULL,
    question_type TEXT NOT NULL,
    set_name TEXT NOT NULL DEFAULT '',
    session_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(bank_key, question_type, set_name)
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    bank_key TEXT,
    mode TEXT NOT NULL,
    question_type TEXT,
    total_count INTEGER,
    answered_count INTEGER,
    correct_count INTEGER,
    wrong_count INTEGER,
    unanswered_count INTEGER,
    score_rate REAL,
    details_json TEXT NOT NULL,
    source TEXT
);
"""


def _default_path():
    try:
        from .platform import app_data_dir

        return os.path.join(app_data_dir(), "progress.db")
    except Exception:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "AnswerTraining", "progress.db")


def set_progress_path(path):
    """设置 progress.db 路径（测试或特殊部署时使用）。"""
    global _path
    _path = path


def get_progress_path():
    if _path:
        return _path
    return _default_path()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure():
    """创建 progress.db 与表（独立文件，绝不触碰题库）。"""
    path = get_progress_path()
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(TABLE_SQL)
        conn.commit()


def _connect():
    path = get_progress_path()
    if not os.path.exists(path):
        ensure()
    return sqlite3.connect(path)


# --------------------------------------------------------------- 普通练习进度

def save_progress(bank_key, question_type, set_name, session_dict):
    """UPSERT 普通练习进度（仅普通练习调用）。"""
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO practice_progress
               (bank_key, question_type, set_name, session_json, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(bank_key, question_type, set_name)
               DO UPDATE SET session_json=excluded.session_json,
                             updated_at=excluded.updated_at""",
            (bank_key, question_type, set_name or "",
             json.dumps(session_dict, ensure_ascii=False), _now()))
        conn.commit()
    finally:
        conn.close()


def load_progress(bank_key, question_type, set_name=""):
    """读取普通练习进度；无记录或 JSON 损坏返回 None。"""
    path = get_progress_path()
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT session_json FROM practice_progress "
            "WHERE bank_key=? AND question_type=? AND set_name=?",
            (bank_key, question_type, set_name or "")).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None


def delete_progress(bank_key, question_type, set_name=""):
    """删除一条普通练习进度（重新开始/重置用；不动题库）。"""
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM practice_progress "
            "WHERE bank_key=? AND question_type=? AND set_name=?",
            (bank_key, question_type, set_name or ""))
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------- 历史记录

def record_history(record):
    """写入一条历史；session_uuid 已存在则忽略并返回 False（防重复记录）。"""
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT OR IGNORE INTO history
               (session_uuid, created_at, bank_key, mode, question_type,
                total_count, answered_count, correct_count, wrong_count,
                unanswered_count, score_rate, details_json, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(record.get("session_uuid") or ""),
             record.get("created_at") or _now(),
             record.get("bank_key") or "",
             record.get("mode") or "normal",
             record.get("question_type") or "",
             int(record.get("total_count") or 0),
             int(record.get("answered_count") or 0),
             int(record.get("correct_count") or 0),
             int(record.get("wrong_count") or 0),
             int(record.get("unanswered_count") or 0),
             float(record.get("score_rate") or 0.0),
             json.dumps(record.get("details") or [], ensure_ascii=False),
             record.get("source") or ""))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _row_to_dict(row) -> dict:
    try:
        details = json.loads(row["details_json"] or "[]")
    except (json.JSONDecodeError, TypeError):
        details = []
    return {
        "id": int(row["id"]),
        "session_uuid": row["session_uuid"],
        "created_at": row["created_at"],
        "bank_key": row["bank_key"] or "",
        "mode": row["mode"],
        "question_type": row["question_type"] or "",
        "total_count": int(row["total_count"] or 0),
        "answered_count": int(row["answered_count"] or 0),
        "correct_count": int(row["correct_count"] or 0),
        "wrong_count": int(row["wrong_count"] or 0),
        "unanswered_count": int(row["unanswered_count"] or 0),
        "score_rate": float(row["score_rate"] or 0.0),
        "details": details,
        "source": row["source"] or "",
    }


def list_history(mode=None, question_type=None):
    """历史列表（时间倒序）。进度文件不存在返回空列表。"""
    path = get_progress_path()
    if not os.path.exists(path):
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM history"
        conds, args = [], []
        if mode:
            conds.append("mode=?")
            args.append(mode)
        if question_type:
            conds.append("question_type=?")
            args.append(question_type)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY id DESC"
        rows = conn.execute(sql, tuple(args)).fetchall()
    finally:
        conn.close()
    return [_row_to_dict(r) for r in rows]


def get_history(history_id):
    path = get_progress_path()
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM history WHERE id=?", (int(history_id),)).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row) if row else None


def delete_history(history_id):
    """删除单条历史（只影响 history 表）。"""
    conn = _connect()
    try:
        conn.execute("DELETE FROM history WHERE id=?", (int(history_id),))
        conn.commit()
    finally:
        conn.close()


def clear_history():
    """清空全部历史（调用前必须二次确认；只影响 history 表）。"""
    conn = _connect()
    try:
        conn.execute("DELETE FROM history")
        conn.commit()
    finally:
        conn.close()


def count_history():
    path = get_progress_path()
    if not os.path.exists(path):
        return 0
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM history").fetchone()
        return int(row[0])
    finally:
        conn.close()
