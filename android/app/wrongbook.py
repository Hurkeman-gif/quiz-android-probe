# -*- coding: utf-8 -*-
"""错题本：独立文件 wrongbook.db（绝不写入题库）。

记录字段：question_id、wrong_count、last_wrong_at、last_selected、
          last_correct_answer、source、created_at。
错题通过 question_id 只读关联原题库显示题干/选项；
移除 / 清空错题只删除本文件记录，绝不影响原题库。
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS wrongbook (
    question_id         INTEGER PRIMARY KEY,
    wrong_count         INTEGER NOT NULL DEFAULT 1,
    last_wrong_at       TEXT NOT NULL DEFAULT '',
    last_selected       TEXT NOT NULL DEFAULT '[]',
    last_correct_answer TEXT NOT NULL DEFAULT '[]',
    source              TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT ''
);
"""

_path = None


def _default_path():
    try:
        from .platform import app_data_dir

        return os.path.join(app_data_dir(), "wrongbook.db")
    except Exception:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "AnswerTraining", "wrongbook.db")


def set_wrongbook_path(path):
    """设置错题本文件路径（测试或特殊部署时使用）。"""
    global _path
    _path = path


def get_wrongbook_path():
    if _path:
        return _path
    return _default_path()


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure():
    """创建错题本文件与表（独立文件，绝不触碰题库）。"""
    path = get_wrongbook_path()
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(TABLE_SQL)
        conn.commit()


def _connect():
    path = get_wrongbook_path()
    if not os.path.exists(path):
        ensure()
    return sqlite3.connect(path)


def record_wrong(question_id, selection, correct_answer, source=""):
    """答错时写入 / 累加错题记录（只写 wrongbook.db，不碰题库）。"""
    now = _now()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT wrong_count FROM wrongbook WHERE question_id=?",
            (int(question_id),)).fetchone()
        if row:
            conn.execute(
                "UPDATE wrongbook SET wrong_count=?, last_wrong_at=?, "
                "last_selected=?, last_correct_answer=?, source=? "
                "WHERE question_id=?",
                (int(row[0]) + 1, now,
                 json.dumps(list(selection or []), ensure_ascii=False),
                 json.dumps(list(correct_answer or []), ensure_ascii=False),
                 source or "", int(question_id)))
        else:
            conn.execute(
                "INSERT INTO wrongbook (question_id, wrong_count, last_wrong_at, "
                "last_selected, last_correct_answer, source, created_at) "
                "VALUES (?, 1, ?, ?, ?, ?, ?)",
                (int(question_id), now,
                 json.dumps(list(selection or []), ensure_ascii=False),
                 json.dumps(list(correct_answer or []), ensure_ascii=False),
                 source or "", now))
        conn.commit()
    finally:
        conn.close()


def remove_wrong(question_id):
    """错题本练习中答对 / 手动移除时调用：只删除本文件记录。"""
    conn = _connect()
    try:
        conn.execute("DELETE FROM wrongbook WHERE question_id=?",
                     (int(question_id),))
        conn.commit()
    finally:
        conn.close()


def clear_all():
    """清空错题本（调用前需二次确认）。只影响 wrongbook.db。"""
    conn = _connect()
    try:
        conn.execute("DELETE FROM wrongbook")
        conn.commit()
    finally:
        conn.close()


def list_records():
    """全部错题记录（按最近答错时间倒序）。文件不存在时返回空列表。"""
    path = get_wrongbook_path()
    if not os.path.exists(path):
        return []
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT question_id, wrong_count, last_wrong_at, last_selected, "
            "last_correct_answer, source, created_at "
            "FROM wrongbook ORDER BY last_wrong_at DESC, question_id").fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        try:
            last_selected = json.loads(r[3] or "[]")
        except (json.JSONDecodeError, TypeError):
            last_selected = []
        try:
            last_answer = json.loads(r[4] or "[]")
        except (json.JSONDecodeError, TypeError):
            last_answer = []
        out.append({
            "question_id": int(r[0]),
            "wrong_count": int(r[1]),
            "last_wrong_at": r[2],
            "last_selected": last_selected,
            "last_correct_answer": last_answer,
            "source": r[5] or "",
            "created_at": r[6] or "",
        })
    return out


def wrong_question_ids():
    return [r["question_id"] for r in list_records()]


def count():
    return len(list_records())
