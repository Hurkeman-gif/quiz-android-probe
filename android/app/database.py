# -*- coding: utf-8 -*-
"""题库数据访问层（默认只读，最高优先级保护现有题库）。

题库保护规则：
1. 绝不新建题库文件、绝不自动建库、绝不导入示例题；
2. 找不到题库时抛 BankNotFoundError，由调用方弹窗让用户选择现有题库文件；
3. 练习全部通过 SQLite 只读连接（mode=ro）访问题库，写入在数据库层直接被拒绝；
4. 写操作（新增/编辑/删除/导入）仅由题库管理界面在用户显式开启「编辑题库」
   并二次确认后调用，且仅对 SQLite 题库可用；JSON/CSV 题库永远只读；
5. 作答进度保存在独立 progress.db（app/progress_store.py），本模块绝不写题库。
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

from . import import_export as ie
from .models import normalize_question, validate_question

APP_NAME = "答题练习软件"


class BankNotFoundError(Exception):
    """题库文件不存在。"""

    def __init__(self, path):
        self.path = path
        super().__init__(f"题库文件不存在：{path}")


class BankFormatError(Exception):
    """题库文件格式/结构不合法（程序不会修改题库）。"""


class BankReadOnlyError(Exception):
    """当前题库不可写（JSON/CSV 题库或未开启编辑模式）。"""


# ---------------- 当前题库状态 ----------------
_bank_path = None      # 已打开的题库文件绝对路径
_bank_kind = ""        # "sqlite" | "json" | "csv"
_external_cache = None  # JSON/CSV 题库的内存快照（带合成 id）


def is_frozen() -> bool:
    """是否 PyInstaller 打包环境。"""
    return bool(getattr(sys, "frozen", False))


def _appdata_dir() -> str:
    """打包运行时的用户数据目录（优先 QStandardPaths.AppDataLocation）。"""
    try:
        from PySide6.QtCore import QStandardPaths
        loc = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation)
        if loc:
            appdata_root = os.environ.get("APPDATA", "")
            if appdata_root and os.path.normcase(os.path.normpath(loc)) == \
                    os.path.normcase(os.path.normpath(appdata_root)):
                return os.path.join(loc, APP_NAME)
            return loc
    except Exception:
        pass
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)


def get_default_db_path() -> str:
    """原题库位置保持不变：Android → assets 复制；打包 → AppData；开发 → 项目 data/quiz.db。"""
    from . import platform
    if platform.is_android():
        return platform.ensure_bank_from_assets()
    if is_frozen():
        return os.path.join(_appdata_dir(), "quiz.db")
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "quiz.db")


def bank_path():
    """当前已打开题库的绝对路径。"""
    return _bank_path


def bank_kind() -> str:
    return _bank_kind


def bank_is_writable() -> bool:
    """仅 SQLite 题库可能通过「编辑题库」写入；JSON/CSV 题库永远只读。"""
    return _bank_kind == "sqlite"


def _ro_uri(path: str) -> str:
    """构造 SQLite 只读 URI（mode=ro：任何写语句都会被 SQLite 拒绝）。"""
    return Path(path).resolve().as_uri() + "?mode=ro"


@contextmanager
def _ro_conn():
    """SQLite 只读连接。练习/浏览全部走这里，不可能修改题库文件。"""
    if _bank_kind != "sqlite":
        raise BankReadOnlyError("当前题库不是 SQLite 文件")
    conn = sqlite3.connect(_ro_uri(_bank_path), uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _rw_conn():
    """可写连接：仅题库管理（编辑模式、二次确认后）使用。"""
    if _bank_kind != "sqlite":
        raise BankReadOnlyError("JSON/CSV 题库为只读文件，不支持写入")
    conn = sqlite3.connect(_bank_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _verify_sqlite_bank() -> None:
    """只读校验题库结构；发现缺表/缺字段时报告问题，绝不 ALTER/修复。"""
    with _ro_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='questions'"
        ).fetchone()
        if row is None:
            raise BankFormatError(
                f"题库文件缺少 questions 表：{_bank_path}\n请选择正确的题库文件。")
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(questions)")}
        missing = [c for c in ("id", "type", "stem", "options", "answer")
                   if c not in cols]
        if missing:
            raise BankFormatError(
                f"题库 questions 表缺少字段：{', '.join(missing)}（文件：{_bank_path}）\n"
                f"程序不会修改题库，请更换题库文件。")


def open_bank(path=None) -> dict:
    """打开现有题库（只读使用）。

    找不到 → BankNotFoundError；格式/字段不匹配 → BankFormatError。
    SQLite 题库以只读连接校验结构；JSON/CSV 题库只读加载到内存，绝不写回。
    """
    global _bank_path, _bank_kind, _external_cache
    p = path or os.environ.get("QUIZ_BANK_PATH", "").strip() or get_default_db_path()
    p = os.path.abspath(p)
    if not os.path.exists(p):
        raise BankNotFoundError(p)
    ext = os.path.splitext(p)[1].lower()
    if ext == ".json":
        valid, errors = ie.validate_import_items(ie.load_json(p))
        if errors:
            raise BankFormatError(
                f"题库文件字段不匹配（{p}）：\n" + "\n".join(errors[:8]) +
                ("\n……" if len(errors) > 8 else ""))
        cache = []
        for i, item in enumerate(valid, 1):
            item = dict(item)
            item["id"] = i
            cache.append(item)
        _bank_kind, _external_cache, _bank_path = "json", cache, p
    elif ext == ".csv":
        valid, errors = ie.validate_import_items(ie.load_csv(p))
        if errors:
            raise BankFormatError(
                f"题库文件字段不匹配（{p}）：\n" + "\n".join(errors[:8]) +
                ("\n……" if len(errors) > 8 else ""))
        cache = []
        for i, item in enumerate(valid, 1):
            item = dict(item)
            item["id"] = i
            cache.append(item)
        _bank_kind, _external_cache, _bank_path = "csv", cache, p
    else:
        _bank_kind, _external_cache, _bank_path = "sqlite", None, p
        _verify_sqlite_bank()
    return bank_info()


def bank_info() -> dict:
    return {"path": _bank_path, "kind": _bank_kind, "count": count_questions()}


# ---------------------------------------------------------------------------
# 只读查询（全部只读访问，绝不写题库）
# ---------------------------------------------------------------------------

def count_questions(set_name=None) -> int:
    if _bank_kind == "sqlite":
        with _ro_conn() as conn:
            if set_name is None:
                row = conn.execute("SELECT COUNT(*) AS n FROM questions").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM questions WHERE set_name=?",
                    (set_name,)).fetchone()
        return int(row["n"])
    if set_name is None:
        return len(_external_cache)
    return sum(1 for q in _external_cache if q.get("set_name") == set_name)


def list_sets():
    """题库中出现的全部套题名称（按名称排序，可能含空串）。"""
    if _bank_kind == "sqlite":
        with _ro_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT set_name FROM questions ORDER BY set_name").fetchall()
        return [r["set_name"] for r in rows]
    sets = []
    for q in _external_cache:
        s = q.get("set_name") or ""
        if s not in sets:
            sets.append(s)
    sets.sort()
    return sets


def categories():
    """题库中出现的全部分类（不含空串，按名称排序）。"""
    if _bank_kind == "sqlite":
        with _ro_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM questions "
                "WHERE category != '' ORDER BY category").fetchall()
        return [r["category"] for r in rows]
    cats = sorted({q.get("category") or "" for q in _external_cache})
    return [c for c in cats if c]


def _row_to_question(row) -> dict:
    """数据库行 → 纯 dict（UI 层全部按 dict 访问）。"""
    try:
        options = json.loads(row["options"] or "[]")
    except (json.JSONDecodeError, TypeError):
        options = []
    try:
        answer = json.loads(row["answer"] or "[]")
    except (json.JSONDecodeError, TypeError):
        answer = []
    return {
        "id": int(row["id"]), "type": row["type"], "stem": row["stem"],
        "options": options, "answer": answer,
        "explanation": row["explanation"], "category": row["category"],
        "order_no": int(row["order_no"]),
        "set_name": row["set_name"] if "set_name" in row.keys() else "",
    }


def list_questions(qtype=None, set_name=None):
    """题目列表（只读）。SQLite 按 order_no,id 排序；JSON/CSV 保持文件顺序。"""
    if _bank_kind == "sqlite":
        sql = "SELECT * FROM questions"
        conds, args = [], []
        if qtype:
            conds.append("type=?")
            args.append(qtype)
        if set_name is not None:
            conds.append("set_name=?")
            args.append(set_name)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY order_no, id"
        with _ro_conn() as conn:
            rows = conn.execute(sql, tuple(args)).fetchall()
        return [_row_to_question(r) for r in rows]
    out = []
    for q in _external_cache:
        if qtype and q["type"] != qtype:
            continue
        if set_name is not None and (q.get("set_name") or "") != set_name:
            continue
        out.append(q)
    return out


def get_question(question_id):
    """按 id 只读取题；不存在返回 None（错题本据此标记失效）。"""
    if _bank_kind == "sqlite":
        with _ro_conn() as conn:
            row = conn.execute(
                "SELECT * FROM questions WHERE id=?", (int(question_id),)).fetchone()
        return _row_to_question(row) if row else None
    for q in _external_cache:
        if q["id"] == int(question_id):
            return q
    return None


def get_questions(qtype=None, set_name=None):
    """题目列表（与 list_questions 同义，供 UI 层调用）。"""
    return list_questions(qtype, set_name)


def question_exists(qtype, stem, set_name=""):
    if _bank_kind == "sqlite":
        with _ro_conn() as conn:
            row = conn.execute(
                "SELECT id FROM questions WHERE type=? AND stem=? AND set_name=?",
                (qtype, stem, set_name or "")).fetchone()
        return row is not None
    return any(
        q["type"] == qtype and q["stem"] == stem
        and (q.get("set_name") or "") == (set_name or "")
        for q in _external_cache)


# ---------------------------------------------------------------------------
# 写操作：仅题库管理「编辑题库」模式（显式开启 + 二次确认）可用，SQLite 题库限定。
# 练习、测试、浏览一律不得调用；JSON/CSV 题库调用会抛 BankReadOnlyError。
# ---------------------------------------------------------------------------

# ---------------- 写操作闸门 ----------------
_edit_enabled = False


def enable_writes() -> None:
    """题库管理「编辑题库」显式开启并二次确认后调用（仅内存开关）。"""
    global _edit_enabled
    _edit_enabled = True


def disable_writes() -> None:
    """关闭写操作（退出编辑模式时调用）。"""
    global _edit_enabled
    _edit_enabled = False


def writes_enabled() -> bool:
    return bool(_edit_enabled) and _bank_kind == "sqlite"


def add_question(data):
    """新增题目（写入题库文件），返回新 id。校验失败抛 ValueError。"""
    if not writes_enabled():
        raise BankReadOnlyError("题库处于只读保护状态，请先开启「编辑题库」。")
    d = normalize_question(data)
    ok, errs = validate_question(d)
    if not ok:
        raise ValueError("；".join(errs))
    with _rw_conn() as conn:
        if not d["order_no"]:
            row = conn.execute(
                "SELECT COALESCE(MAX(order_no), 0) + 1 AS n FROM questions").fetchone()
            d["order_no"] = int(row["n"])
        cur = conn.execute(
            """INSERT INTO questions
               (type, stem, options, answer, explanation, category, order_no, set_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (d["type"], d["stem"], json.dumps(d["options"], ensure_ascii=False),
             json.dumps(d["answer"], ensure_ascii=False), d["explanation"],
             d["category"], d["order_no"], d.get("set_name", "")))
        return int(cur.lastrowid)


def update_question(question_id, data):
    """更新题目（写入题库文件）。校验失败抛 ValueError。"""
    if not writes_enabled():
        raise BankReadOnlyError("题库处于只读保护状态，请先开启「编辑题库」。")
    d = normalize_question(data)
    ok, errs = validate_question(d)
    if not ok:
        raise ValueError("；".join(errs))
    with _rw_conn() as conn:
        conn.execute(
            """UPDATE questions SET type=?, stem=?, options=?, answer=?,
               explanation=?, category=?, order_no=?, set_name=? WHERE id=?""",
            (d["type"], d["stem"], json.dumps(d["options"], ensure_ascii=False),
             json.dumps(d["answer"], ensure_ascii=False), d["explanation"],
             d["category"], d["order_no"], d.get("set_name", ""), int(question_id)))


def delete_question(question_id):
    """删除题目（写入题库文件）。"""
    if not writes_enabled():
        raise BankReadOnlyError("题库处于只读保护状态，请先开启「编辑题库」。")
    with _rw_conn() as conn:
        conn.execute("DELETE FROM questions WHERE id=?", (int(question_id),))


def import_questions(items):
    """批量导入（按 套题+题型+题干 去重），返回 (新增数, 跳过数)。"""
    if not writes_enabled():
        raise BankReadOnlyError("题库处于只读保护状态，请先开启「编辑题库」。")
    inserted = 0
    skipped = 0
    with _rw_conn() as conn:
        for raw in items:
            d = normalize_question(raw)
            ok, errs = validate_question(d)
            if not ok:
                skipped += 1
                continue
            row = conn.execute(
                "SELECT id FROM questions WHERE type=? AND stem=? AND set_name=?",
                (d["type"], d["stem"], d.get("set_name", ""))).fetchone()
            if row:
                skipped += 1
                continue
            if not d["order_no"]:
                mx = conn.execute(
                    "SELECT COALESCE(MAX(order_no), 0) + 1 AS n FROM questions").fetchone()
                d["order_no"] = int(mx["n"])
            conn.execute(
                """INSERT INTO questions
                   (type, stem, options, answer, explanation, category, order_no, set_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (d["type"], d["stem"], json.dumps(d["options"], ensure_ascii=False),
                 json.dumps(d["answer"], ensure_ascii=False), d["explanation"],
                 d["category"], d["order_no"], d.get("set_name", "")))
            inserted += 1
    return inserted, skipped


# ---------------------------------------------------------------------------
# 错题本路径（独立文件 wrongbook.db，绝不叫 quiz.db）
# ---------------------------------------------------------------------------

def _dir_writable(directory: str) -> bool:
    if not os.path.isdir(directory):
        return False
    probe = os.path.join(directory, ".wb_probe.tmp")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("x")
        os.remove(probe)
        return True
    except OSError:
        return False


def resolve_wrongbook_path(bank_file=None) -> str:
    """错题本独立文件路径：优先题库同目录（可写时），否则用户数据目录。"""
    env = os.environ.get("QUIZ_WRONGBOOK_PATH", "").strip()
    if env:
        return env
    bank = bank_file or _bank_path or get_default_db_path()
    bank_dir = os.path.dirname(os.path.abspath(bank))
    if _dir_writable(bank_dir):
        return os.path.join(bank_dir, "wrongbook.db")
    return os.path.join(_appdata_dir(), "wrongbook.db")


def bank_key() -> str:
    """当前题库稳定标识：题库文件绝对路径（进度按 题库+题型+套题 保存）。"""
    return _bank_path or get_default_db_path()


def resolve_progress_path(bank_file=None) -> str:
    """进度/历史独立文件路径（progress.db）：优先题库同目录（可写时），否则用户数据目录。"""
    env = os.environ.get("QUIZ_PROGRESS_PATH", "").strip()
    if env:
        return env
    bank = bank_file or _bank_path or get_default_db_path()
    bank_dir = os.path.dirname(os.path.abspath(bank))
    if _dir_writable(bank_dir):
        return os.path.join(bank_dir, "progress.db")
    return os.path.join(_appdata_dir(), "progress.db")
