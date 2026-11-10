# -*- coding: utf-8 -*-
"""练习会话（内存态）与序列化。

- 会话只存在于内存，绝不写题库；
- 普通练习会话可通过 serialize()/restore_state() 持久化到 progress.db；
- 随机练习与错题本练习不序列化进度，只在完成时 build_history_record()。
"""
from __future__ import annotations

import uuid
from datetime import datetime

VIEW_QUIZ = "quiz"
VIEW_FINISH = "finish"

MODE_NORMAL = "normal"
MODE_RANDOM = "random"
MODE_WRONGBOOK = "wrongbook"
MODE_LABELS = {
    MODE_NORMAL: "普通练习",
    MODE_RANDOM: "随机练习",
    MODE_WRONGBOOK: "错题本练习",
}

TYPE_LABELS = {"single": "单选题", "multiple": "多选题", "judge": "判断题"}


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _brief(text: str, limit: int = 60) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_accuracy(correct, total) -> str:
    """统一格式化正确率：保留 1 位小数；分母为 0（或无效）时返回 "--"。"""
    try:
        total = int(total or 0)
        correct = int(correct or 0)
    except (TypeError, ValueError):
        return "--"
    if total <= 0:
        return "--"
    return f"{(correct / total * 100.0):.1f}%"


class PracticeSession:
    """一次练习会话。questions 为题目 dict 快照（含 id/type/stem/options/answer/...）。"""

    def __init__(self, mode: str, questions: list, random_config=None,
                 wrongbook_snapshot=None):
        self.mode = mode
        self.questions = list(questions or [])
        self.question_ids = [q["id"] for q in self.questions]
        self.current_index = 0
        # answers: {qid: {"selected": [...], "correct": bool, "answered_at": str,
        #                  "forced_unanswered": bool}}
        self.answers = {}
        self.view_mode = VIEW_QUIZ
        self.random_config = random_config
        self.wrongbook_snapshot = wrongbook_snapshot
        self.session_uuid = uuid.uuid4().hex
        self.history_recorded = False
        self.manual_submitted = False

    # ------------------------------------------------------------- 基本导航

    def current_question(self):
        if not self.questions or not (0 <= self.current_index < len(self.questions)):
            return None
        return self.questions[self.current_index]

    def count(self) -> int:
        return len(self.questions)

    def navigate_to_question(self, index: int) -> bool:
        if self.questions and 0 <= index < len(self.questions):
            self.current_index = index
            return True
        return False

    def is_all_answered(self) -> bool:
        return len(self.answers) >= len(self.question_ids)

    def show_finish_view(self) -> None:
        """仅在全部已答时切换到完成页。"""
        if self.is_all_answered():
            self.view_mode = VIEW_FINISH

    def advance_after_answer(self) -> bool:
        """答完一题后前进：优先下一个未答题，找不到则从头找；全部已答返回 False 并切完成页。"""
        if not self.questions:
            return False
        n = len(self.questions)
        start = self.current_index
        for offset in range(1, n + 1):
            idx = (start + offset) % n
            qid = self.question_ids[idx]
            if qid not in self.answers:
                self.current_index = idx
                return True
        self.show_finish_view()
        return False

    # ------------------------------------------------------------- 作答

    def record_answer(self, qid, correct: bool, selection: list,
                      forced_unanswered: bool = False) -> None:
        self.answers[int(qid)] = {
            "selected": list(selection or []),
            "correct": bool(correct),
            "answered_at": _now_str(),
            "forced_unanswered": bool(forced_unanswered),
        }

    def clear_answer(self, qid) -> None:
        self.answers.pop(int(qid), None)

    def progress_for(self, qid):
        """返回该题作答进度（含历史选择，供答题区重放）；未答返回 None。"""
        return self.answers.get(int(qid))

    def mark_unanswered(self) -> int:
        """手动提交：所有未答题标记为未答强制判错（绝不写错题本，由调用方保证）。"""
        n = 0
        for qid in self.question_ids:
            if qid not in self.answers:
                self.record_answer(qid, False, [], forced_unanswered=True)
                n += 1
        if n:
            self.manual_submitted = True
        return n

    def restart_current_session(self) -> None:
        """重新开始：清空作答，重置会话标识。"""
        self.answers = {}
        self.current_index = 0
        self.view_mode = VIEW_QUIZ
        self.session_uuid = uuid.uuid4().hex
        self.history_recorded = False
        self.manual_submitted = False

    # ------------------------------------------------------------- 统计

    # ---- 统一统计口径（所有界面必须调用这些函数，禁止各写一套公式） ----

    def get_live_stats(self) -> dict:
        """答题过程中的实时统计：未答题不进正确率分母、也不进错误数。

        只统计真正提交过的题；已答为 0 时 accuracy_text 返回 "--"。
        """
        total = len(self.question_ids)
        recorded = [a for a in self.answers.values()
                    if not a.get("forced_unanswered")]
        answered = len(recorded)
        correct = sum(1 for a in recorded if a["correct"])
        wrong = answered - correct
        unanswered = max(0, total - answered)
        return {
            "answered_count": answered,
            "correct_count": correct,
            "wrong_count": wrong,
            "unanswered_count": unanswered,
            "accuracy_text": format_accuracy(correct, answered),
        }

    def get_finish_stats(self) -> dict:
        """完成页统计（正常完成 / 手动提交完成通用）。

        - wrong_count 只统计正常答错数（不含强制判错）；
        - forced_unanswered_count 为手动提交时被按错误计入的未答数；
        - wrong_display_count = wrong_count + forced_unanswered_count；
        - accuracy_text = 答对数 / 总题数（分母为 0 时 "--"）。
        """
        total = len(self.question_ids)
        forced = sum(1 for a in self.answers.values()
                     if a.get("forced_unanswered"))
        recorded = len(self.answers) - forced
        correct = sum(1 for a in self.answers.values() if a["correct"])
        wrong = max(0, recorded - correct)
        unanswered = max(0, total - recorded)
        return {
            "total_count": total,
            "answered_count": recorded,
            "correct_count": correct,
            "wrong_count": wrong,
            "forced_unanswered_count": forced,
            "wrong_display_count": wrong + forced,
            "unanswered_count": unanswered,
            "accuracy_text": format_accuracy(correct, total),
        }

    def stats(self) -> dict:
        """兼容旧接口：等价于完成页统计（供内部收尾逻辑使用）。"""
        st = self.get_finish_stats()
        return {
            "total": st["total_count"],
            "answered": st["answered_count"],
            "correct": st["correct_count"],
            "wrong": st["wrong_count"],
            "unanswered": st["unanswered_count"],
            "accuracy": (st["correct_count"] / st["total_count"] * 100.0)
            if st["total_count"] else 0.0,
        }

    # ------------------------------------------------------------- 序列化

    def serialize(self) -> dict:
        """序列化为 progress.db 的 session_json。"""
        return {
            "question_ids": list(self.question_ids),
            "current_index": self.current_index,
            "answers": {
                str(qid): dict(a) for qid, a in self.answers.items()
            },
            "view_mode": self.view_mode,
            "history_recorded": self.history_recorded,
            "manual_submitted": self.manual_submitted,
            "session_uuid": self.session_uuid,
        }

    def restore_state(self, state: dict) -> None:
        """从 session_json 恢复。question_ids 已由外部按现存题目过滤。"""
        if not state:
            return
        ids = list(state.get("question_ids") or [])
        if not ids:
            return
        self.question_ids = [int(i) for i in ids]
        self.current_index = max(0, min(int(state.get("current_index") or 0),
                                       len(self.question_ids) - 1))
        answers = state.get("answers") or {}
        self.answers = {
            int(qid): {
                "selected": list(a.get("selected") or a.get("selection") or []),
                "correct": bool(a.get("correct")),
                "answered_at": a.get("answered_at") or _now_str(),
                "forced_unanswered": bool(a.get("forced_unanswered")),
            }
            for qid, a in answers.items()
        }
        self.view_mode = state.get("view_mode") or VIEW_QUIZ
        if self.view_mode not in (VIEW_QUIZ, VIEW_FINISH):
            self.view_mode = VIEW_QUIZ
        self.history_recorded = bool(state.get("history_recorded"))
        self.manual_submitted = bool(state.get("manual_submitted"))
        self.session_uuid = str(state.get("session_uuid") or uuid.uuid4().hex)
        # 恢复为完成页但实际未全答（如部分题目 id 失效被过滤）：回到答题页
        if self.view_mode == VIEW_FINISH and not self.is_all_answered():
            self.view_mode = VIEW_QUIZ

    # ------------------------------------------------------------- 历史明细

    def build_history_record(self, bank_key: str, question_type: str,
                             source: str = "") -> dict:
        """构造 history 表记录。details 每题含题干摘要/答案/正解/结果/是否强制未答/解析。"""
        details = []
        by_id = {q["id"]: q for q in self.questions}
        for qid in self.question_ids:
            q = by_id.get(qid)
            a = self.answers.get(qid)
            selected = list(a["selected"]) if a else []
            is_correct = bool(a["correct"]) if a else False
            forced = bool(a["forced_unanswered"]) if a else False
            details.append({
                "question_id": qid,
                "stem_summary": _brief(q["stem"]) if q else "",
                "type": (q or {}).get("type", ""),
                "selected": selected,
                "correct_answer": list((q or {}).get("answer") or []),
                "is_correct": is_correct,
                "is_forced_unanswered": forced,
                "explanation": (q or {}).get("explanation") or "",
            })
        st = self.get_finish_stats()
        return {
            "session_uuid": self.session_uuid,
            "created_at": _now_str(),
            "bank_key": bank_key,
            "mode": self.mode,
            "question_type": question_type,
            "total_count": st["total_count"],
            "answered_count": st["answered_count"],
            "correct_count": st["correct_count"],
            "wrong_count": st["wrong_count"],
            "unanswered_count": st["unanswered_count"],
            "score_rate": round(
                st["correct_count"] / st["total_count"] * 100.0, 2)
            if st["total_count"] else 0.0,
            "details": details,
            "source": source,
        }
