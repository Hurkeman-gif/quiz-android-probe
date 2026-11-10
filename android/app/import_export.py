# -*- coding: utf-8 -*-
"""JSON / CSV 导入导出。"""

import csv
import io
import json
import re

from .models import TYPE_NAMES, normalize_question, validate_question

JUDGE_YES = {"正确", "对", "√", "T", "TRUE", "是", "Y", "YES"}
JUDGE_NO = {"错误", "错", "×", "X", "F", "FALSE", "否", "N", "NO"}

CSV_HEADERS = [
    "type", "stem",
    "optionA", "optionB", "optionC", "optionD",
    "optionE", "optionF", "optionG", "optionH",
    "answer", "explanation", "category", "order_no", "set",
]

_ANSWER_SPLIT = re.compile(r"[,;，；、|\s]+")


# ---------- JSON ----------
def load_json(path: str):
    """读取 JSON 文件，返回题目 dict 列表。"""
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, dict):
        if isinstance(data.get("questions"), list):
            data = data["questions"]
        else:
            raise ValueError("JSON 顶层必须是题目数组，或包含 questions 数组的对象")
    if not isinstance(data, list):
        raise ValueError("JSON 顶层必须是题目数组")
    return [d for d in data if isinstance(d, dict)]


def save_json(path: str, rows) -> None:
    """导出题目为 JSON 文件。"""
    payload = []
    for r in rows:
        payload.append(dict(r))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ---------- CSV ----------
def _read_text(path: str) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文件编码（仅支持 UTF-8 / GBK）")


def _detect_delim(text: str) -> str:
    sample = "\n".join([ln for ln in text.splitlines() if ln.strip()][:5])
    return "\t" if sample.count("\t") > sample.count(",") else ","


def load_csv(path: str):
    """读取 CSV 文件，返回题目 dict 列表。"""
    text = _read_text(path)
    delim = _detect_delim(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    fields = [f.strip().lower() for f in (reader.fieldnames or [])]
    if "stem" not in fields:
        raise ValueError("CSV 缺少必需的 stem 列")
    items = []
    for raw in reader:
        row = {str(k).strip().lower(): (str(v) if v is not None else "") for k, v in raw.items()}
        stem = row.get("stem", "").strip()
        qtype = row.get("type", "single").strip().lower()
        qtype = TYPE_NAMES.get(qtype, qtype)
        if qtype not in ("single", "multiple", "judge"):
            if qtype.startswith("判断"):
                qtype = "judge"
            elif qtype.startswith("多选"):
                qtype = "multiple"
            elif qtype.startswith("单选"):
                qtype = "single"
            else:
                qtype = "single"
        # 选项：优先 options 列（JSON 数组），其次 optionA..optionH
        options = None
        if row.get("options", "").strip().startswith("["):
            try:
                options = json.loads(row["options"])
            except Exception:
                options = None
        if not options:
            options = []
            for key in "ABCDEFGH":
                text = row.get(f"option{key.lower()}", "").strip()
                if text:
                    options.append({"key": key, "text": text})
        if qtype == "judge" and not options:
            options = [{"key": "A", "text": "正确"}, {"key": "B", "text": "错误"}]
        answer_raw = row.get("answer", "").strip()
        answer = [a.upper() for a in _ANSWER_SPLIT.split(answer_raw) if a]
        if qtype == "judge" and answer:
            mapped = []
            for a in answer:
                if a in ("A", "B"):
                    mapped.append(a)
                elif a in JUDGE_YES:
                    mapped.append("A")
                elif a in JUDGE_NO:
                    mapped.append("B")
            if mapped:
                answer = mapped
        explanation = row.get("explanation", "").strip()
        category = row.get("category", "").strip()
        order_raw = row.get("order_no", "").strip()
        try:
            order_no = int(float(order_raw))
        except Exception:
            order_no = 0
        set_name = (row.get("set") or row.get("set_name") or row.get("套题") or "").strip()
        items.append({
            "type": qtype,
            "stem": stem,
            "options": options,
            "answer": answer,
            "explanation": explanation,
            "category": category,
            "order_no": order_no,
            "set_name": set_name,
        })
    return items


def save_csv(path: str, rows) -> None:
    """导出题目为 CSV 文件（UTF-8 with BOM，Excel 可直接打开）。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        for r in rows:
            row = {}
            for h in CSV_HEADERS:
                row[h] = ""
            row["type"] = r.get("type", "")
            row["stem"] = r.get("stem", "")
            for opt in (r.get("options") or []):
                key = str(opt.get("key", "")).upper()
                if key in "ABCDEFGH":
                    row[f"option{key}"] = opt.get("text", "")
            answer = r.get("answer") or []
            row["answer"] = ",".join(str(a).upper() for a in answer)
            row["explanation"] = r.get("explanation", "")
            row["category"] = r.get("category", "")
            row["order_no"] = r.get("order_no", 0)
            row["set"] = r.get("set_name", "")
            writer.writerow([row[h] for h in CSV_HEADERS])


# ---------- 校验 ----------
def validate_import_items(items):
    """逐条规范化并校验，返回 (有效题目列表, 错误信息列表)。"""
    valid = []
    errors = []
    for i, raw in enumerate(items, 1):
        try:
            item = normalize_question(raw)
        except Exception as e:
            errors.append(f"第 {i} 条：数据格式错误（{e}）")
            continue
        ok, errs = validate_question(item)
        if not ok:
            errors.append(f"第 {i} 条：{'；'.join(errs)}")
        else:
            valid.append(item)
    return valid, errors
