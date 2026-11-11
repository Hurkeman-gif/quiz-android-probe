# -*- coding: utf-8 -*-
"""数据备份：progress.db + wrongbook.db <-> 单个 JSON 文件。

- 导出：读取练习进度、答题记录（含明细）、错题本，写成带版本号的 JSON；
- 导入：校验格式与版本，按 (bank_key,题型,套题) / session_uuid / question_id
  去重合并，绝不覆盖题库；
- 只读写两个"数据"文件，绝不触碰 questions 表。

JSON 结构：
{
  "format": "answer-training-backup",
  "version": 1,
  "exported_at": "2026-11-11 20:00:00",
  "app": "答题练习软件",
  "platform": "android" | "desktop",
  "bank": {"name": "quiz.db", "sets": [...]},
  "progress": [{bank_key, question_type, set_name, session, updated_at}],
  "history": [{session_uuid, created_at, ..., details: [...]}],
  "wrongbook": [{question_id, wrong_count, ..., set_name}]
}
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime

from . import platform, progress_store, wrongbook

FORMAT_NAME = "answer-training-backup"
FORMAT_VERSION = 1


# ---------------------------------------------------------------- 目录与文件名

def _android_package() -> str:
    """从 p4a 的 ANDROID_PRIVATE 推出包名（用于外部可访问目录）。"""
    private = os.environ.get("ANDROID_PRIVATE") or ""
    for prefix in ("/data/user/0/", "/data/data/"):
        if private.startswith(prefix):
            rest = private[len(prefix):]
            return rest.split("/")[0]
    return ""


def _writable(directory: str) -> bool:
    try:
        os.makedirs(directory, exist_ok=True)
        probe = os.path.join(directory, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


def backup_dir() -> str:
    """备份目录：优先 Android 外部私有目录（文件管理器/电脑都能取到）。"""
    candidates = []
    if platform.is_android():
        pkg = _android_package()
        if pkg:
            candidates.append(
                "/storage/emulated/0/Android/data/%s/files/backup" % pkg)
    try:
        candidates.append(os.path.join(platform.app_data_dir(), "backup"))
    except Exception:
        pass
    candidates.append(os.path.join(
        os.path.expanduser("~"), "AnswerTraining", "backup"))
    for directory in candidates:
        if _writable(directory):
            return directory
    raise RuntimeError("没有可写的备份目录")


def default_filename() -> str:
    return "答题练习备份-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json"


def list_backups() -> list:
    """备份目录下的 JSON 文件（按修改时间倒序）。"""
    try:
        directory = backup_dir()
    except Exception:
        return []
    out = []
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    for name in names:
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(directory, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        out.append({
            "name": name,
            "path": path,
            "size": int(st.st_size),
            "mtime": int(st.st_mtime),
            "mtime_text": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
        })
    out.sort(key=lambda item: item["mtime"], reverse=True)
    return out


# ---------------------------------------------------------------- 导出

def build_payload() -> dict:
    """收集当前数据生成备份字典（只读两个数据文件）。"""
    from . import database

    progress = progress_store.dump_progress()
    history = progress_store.dump_history()
    wrong = wrongbook.dump_records()
    try:
        sets = database.list_sets()
    except Exception:
        sets = []
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "app": "答题练习软件",
        "platform": "android" if platform.is_android() else "desktop",
        "bank": {
            "name": os.path.basename(database.get_default_db_path() or ""),
            "sets": list(sets),
        },
        "counts": {
            "progress": len(progress),
            "history": len(history),
            "wrongbook": len(wrong),
        },
        "progress": progress,
        "history": history,
        "wrongbook": wrong,
    }


def export_to(path: str) -> dict:
    """导出到指定路径，返回统计信息。"""
    payload = build_payload()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return {
        "path": path,
        "size": os.path.getsize(path),
        "counts": payload["counts"],
    }


def export_default() -> dict:
    """导出到默认备份目录（文件名带时间戳）。"""
    return export_to(os.path.join(backup_dir(), default_filename()))


# ---------------------------------------------------------------- 导入

def read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate(payload) -> list:
    """校验备份结构，返回错误列表（空列表=通过）。"""
    errors = []
    if not isinstance(payload, dict):
        return ["文件内容不是 JSON 对象"]
    fmt = payload.get("format")
    if fmt != FORMAT_NAME:
        errors.append("不是本软件的备份文件（format=%r）" % (fmt,))
    try:
        version = int(payload.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    if version <= 0:
        errors.append("缺少版本号")
    elif version > FORMAT_VERSION:
        errors.append("备份版本 %d 高于当前支持的 %d" % (version, FORMAT_VERSION))
    for key in ("progress", "history", "wrongbook"):
        if key in payload and not isinstance(payload.get(key), list):
            errors.append("字段 %s 必须是数组" % key)
    if not any(isinstance(payload.get(k), list) for k in
               ("progress", "history", "wrongbook")):
        errors.append("备份里没有任何可导入的数据")
    return errors


def import_payload(payload) -> dict:
    """合并导入（去重），返回统计；调用前应先 validate。"""
    progress_items = payload.get("progress") or []
    history_items = payload.get("history") or []
    wrong_items = payload.get("wrongbook") or []
    p_changed, p_skipped = progress_store.merge_progress(progress_items)
    h_added, h_skipped = progress_store.merge_history(history_items)
    w_changed, w_skipped = wrongbook.merge_records(wrong_items)
    return {
        "progress": {"changed": p_changed, "skipped": p_skipped},
        "history": {"added": h_added, "skipped": h_skipped},
        "wrongbook": {"changed": w_changed, "skipped": w_skipped},
    }


def import_file(path: str) -> dict:
    """从文件导入；返回 {"ok": bool, "errors": [...], "stats": {...}}。"""
    try:
        payload = read_json(path)
    except Exception as exc:
        return {"ok": False, "errors": ["读取失败：%s" % exc], "stats": {}}
    errors = validate(payload)
    if errors:
        return {"ok": False, "errors": errors, "stats": {}}
    try:
        stats = import_payload(payload)
    except Exception as exc:
        return {"ok": False, "errors": ["导入失败：%s" % exc], "stats": {}}
    stats["exported_at"] = payload.get("exported_at") or ""
    return {"ok": True, "errors": [], "stats": stats}
