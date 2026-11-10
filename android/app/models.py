# -*- coding: utf-8 -*-
"""题目数据模型与校验。"""
from __future__ import annotations

QUESTION_TYPES = ("single", "multiple", "judge")

TYPE_LABELS = {
    "single": "单选题",
    "multiple": "多选题",
    "judge": "判断题",
}

TYPE_NAMES = {label: key for key, label in TYPE_LABELS.items()}

OPTION_KEYS = [chr(ord("A") + i) for i in range(8)]  # A - H

JUDGE_OPTIONS = [
    {"key": "A", "text": "正确"},
    {"key": "B", "text": "错误"},
]


class Question:
    """题目数据模型。"""

    def __init__(self, id=None, type="single", stem="", options=None,
                 answer=None, explanation="", category="", order_no=0,
                 set_name=""):
        self.id = id
        self.type = type
        self.stem = stem
        self.options = options if options is not None else []
        self.answer = answer if answer is not None else []
        self.explanation = explanation or ""
        self.category = category or ""
        self.order_no = order_no or 0
        self.set_name = set_name or ""

    def to_dict(self):
        """转为可导出的字典（不含 id，便于跨库导入）。"""
        return {
            "type": self.type,
            "stem": self.stem,
            "options": [dict(opt) for opt in self.options],
            "answer": list(self.answer),
            "explanation": self.explanation,
            "category": self.category,
            "order_no": self.order_no,
            "set_name": self.set_name,
        }


def normalize_question(data):
    """清洗并规范化题目字典，容错处理常见脏数据。"""
    qtype = str(data.get("type") or "").strip().lower()
    qtype = TYPE_NAMES.get(qtype, qtype)

    options = []
    for opt in data.get("options") or []:
        if isinstance(opt, dict):
            options.append({
                "key": str(opt.get("key") or "").strip().upper(),
                "text": str(opt.get("text") or "").strip(),
            })

    answer = [str(a).strip().upper() for a in (data.get("answer") or [])
              if str(a).strip()]

    try:
        order_no = int(data.get("order_no") or 0)
    except (TypeError, ValueError):
        order_no = 0

    return {
        "type": qtype,
        "stem": str(data.get("stem") or "").strip(),
        "options": options,
        "answer": answer,
        "explanation": str(data.get("explanation") or "").strip(),
        "category": str(data.get("category") or "").strip(),
        "order_no": order_no,
        "set_name": str(data.get("set_name") or "").strip(),
    }


def validate_question(data):
    """校验题目字典，返回 (是否合法, 错误信息列表)。"""
    d = normalize_question(data)
    errors = []

    if d["type"] not in QUESTION_TYPES:
        errors.append("题型无效（应为 single / multiple / judge）")
        return False, errors

    if not d["stem"]:
        errors.append("题干不能为空")

    option_keys = []
    if not d["options"]:
        errors.append("选项不能为空")
    else:
        seen = set()
        for i, opt in enumerate(d["options"], 1):
            key = opt["key"]
            text = opt["text"]
            if not key:
                errors.append(f"第 {i} 个选项缺少 key")
            elif key in seen:
                errors.append(f"选项 key {key} 重复")
            if not text:
                errors.append(f"选项 {key or i} 缺少内容")
            if key:
                seen.add(key)
                option_keys.append(key)

    if d["type"] in ("single", "multiple") and len(option_keys) < 2:
        errors.append("单选题/多选题至少需要 2 个选项")
    if d["type"] == "judge" and len(option_keys) < 2:
        errors.append("判断题至少需要 2 个选项")

    if not d["answer"]:
        errors.append("答案不能为空")
    else:
        if d["type"] in ("single", "judge") and len(d["answer"]) != 1:
            errors.append("单选题/判断题答案必须恰好 1 个")
        for a in d["answer"]:
            if option_keys and a not in option_keys:
                errors.append(f"答案 {a} 不在选项 key 中")

    return (not errors), errors
