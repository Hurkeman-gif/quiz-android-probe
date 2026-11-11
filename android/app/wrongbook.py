# -*- coding: utf-8 -*-
"""错题本：独立文件 wrongbook.db（绝不写入题库）。

记录字段：question_id、wrong_count、last_wrong_at、last_selected、
          last_correct_answer、source、created_at、set_name。
- question_id 全局唯一，set_name 只用于按套题过滤显示（保持与题库一致）；
- 错题通过 question_id 只读关联原题库显示题干/选项；
- 移除 / 清空错题只删除本文件记录，绝不影响原题库；
- dump/merge 供 JSON 备份使用。
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
    created_at          TEXT NOT NULL DEFAULT '',
    set_name            TEXT NOT NULL DEFAULT ''
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


def _table_columns(conn, table):
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(%s)" % table)}
    except sqlite3.Error:
        return set()


def _migrate(conn):
    """老版本 wrongbook.db 升级：补 set_name 列（不删数据）。"""
    cols = _table_columns(conn, "wrongbook")
    if cols and "set_name" not in cols:
        conn.execute(
            "ALTER TABLE wrongbook ADD COLUMN set_name TEXT NOT NULL DEFAULT ''")
    conn.commit()


def ensure():
    """创建错题本文件与表（独立文件，绝不触碰题库）。"""
    path = get_wrongbook_path()
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(TABLE_SQL)
        _migrate(conn)
        conn.commit()


def _connect():
    path = get_wrongbook_path()
    if not os.path.exists(path):
        ensure()
    conn = sqlite3.connect(path)
    _migrate(conn)
    return conn


def record_wrong(question_id, selection, correct_answer, source="",
                 set_name=""):
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
                "last_selected=?, last_correct_answer=?, source=?, set_name=? "
                "WHERE question_id=?",
                (int(row[0]) + 1, now,
                 json.dumps(list(selection or []), ensure_ascii=False),
                 json.dumps(list(correct_answer or []), ensure_ascii=False),
                 source or "", set_name or "", int(question_id)))
        else:
            conn.execute(
                "INSERT INTO wrongbook (question_id, wrong_count, last_wrong_at, "
                "last_selected, last_correct_answer, source, created_at, set_name) "
                "VALUES (?, 1, ?, ?, ?, ?, ?, ?)",
                (int(question_id), now,
                 json.dumps(list(selection or []), ensure_ascii=False),
                 json.dumps(list(correct_answer or []), ensure_ascii=False),
                 source or "", now, set_name or ""))
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


def clear_all(set_name=None):
    """清空错题本（调用前需二次确认）。set_name=None 清全部。"""
    conn = _connect()
    try:
        if set_name is None:
            conn.execute("DELETE FROM wrongbook")
        else:
            conn.execute("DELETE FROM wrongbook WHERE set_name=?",
                         (set_name or "",))
        conn.commit()
    finally:
        conn.close()


def count(set_name=None):
    path = get_wrongbook_path()
    if not os.path.exists(path):
        return 0
    conn = sqlite3.connect(path)
    try:
        if set_name is None:
            row = conn.execute("SELECT COUNT(*) FROM wrongbook").fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM wrongbook WHERE set_name=?",
                (set_name or "",)).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def list_records(set_name=None):
    """错题记录（按最近答错时间倒序）。set_name=None 表示全部套题。"""
    path = get_wrongbook_path()
    if not os.path.exists(path):
        return []
    conn = sqlite3.connect(path)
    try:
        sql = ("SELECT question_id, wrong_count, last_wrong_at, last_selected, "
               "last_correct_answer, source, created_at FROM wrongbook")
        args = ()
        if set_name is not None:
            sql += " WHERE set_name=?"
            args = (set_name or "",)
        sql += " ORDER BY last_wrong_at DESC, question_id"
        rows = conn.execute(sql, args).fetchall()
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


def wrong_question_ids(set_name=None):
    return [r["question_id"] for r in list_records(set_name)]


def dump_records():
    """导出全部错题（含 set_name，供备份用）。"""
    path = get_wrongbook_path()
    if not os.path.exists(path):
        return []
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM wrongbook ORDER BY question_id").fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        try:
            selected = json.loads(r["last_selected"] or "[]")
        except (json.JSONDecodeError, TypeError):
            selected = []
        try:
            answer = json.loads(r["last_correct_answer"] or "[]")
        except (json.JSONDecodeError, TypeError):
            answer = []
        out.append({
            "question_id": int(r["question_id"]),
            "wrong_count": int(r["wrong_count"] or 1),
            "last_wrong_at": r["last_wrong_at"] or "",
            "last_selected": selected,
            "last_correct_answer": answer,
            "source": r["source"] or "",
            "created_at": r["created_at"] or "",
            "set_name": (r["set_name"] or "") if "set_name" in r.keys() else "",
        })
    return out


def merge_records(items):
    """导入错题：按 question_id 合并，保留答错次数较多 / 时间较新的一条。"""
    if not items:
        return 0, 0
    conn = _connect()
    changed = 0
    skipped = 0
    try:
        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            try:
                qid = int(item.get("question_id") or 0)
            except (TypeError, ValueError):
                skipped += 1
                continue
            if qid <= 0:
                skipped += 1
                continue
            row = conn.execute(
                "SELECT wrong_count, last_wrong_at FROM wrongbook WHERE question_id=?",
                (qid,)).fetchone()
            wrong_count = int(item.get("wrong_count") or 1)
            last_at = str(item.get("last_wrong_at") or _now())
            if row:
                if int(row[0] or 0) >= wrong_count and str(row[1] or "") >= last_at:
                    skipped += 1
                    continue
                wrong_count = max(wrong_count, int(row[0] or 0))
                conn.execute(
                    "UPDATE wrongbook SET wrong_count=?, last_wrong_at=?, "
                    "last_selected=?, last_correct_answer=?, set_name=? "
                    "WHERE question_id=?",
                    (wrong_count, last_at,
                     json.dumps(list(item.get("last_selected") or []),
                                ensure_ascii=False),
                     json.dumps(list(item.get("last_correct_answer") or []),
                                ensure_ascii=False),
                     str(item.get("set_name") or ""), qid))
            else:
                conn.execute(
                    "INSERT INTO wrongbook (question_id, wrong_count, "
                    "last_wrong_at, last_selected, last_correct_answer, source, "
                    "created_at, set_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (qid, wrong_count, last_at,
                     json.dumps(list(item.get("last_selected") or []),
                                ensure_ascii=False),
                     json.dumps(list(item.get("last_correct_answer") or []),
                                ensure_ascii=False),
                     str(item.get("source") or ""),
                     str(item.get("created_at") or last_at),
                     str(item.get("set_name") or "")))
            changed += 1
        conn.commit()
    finally:
        conn.close()
    return changed, skipped
