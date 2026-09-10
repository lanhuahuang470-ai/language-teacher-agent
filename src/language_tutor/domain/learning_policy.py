"""Deterministic course progression, independent of model decisions."""

CORRECT_STREAK_TO_ADVANCE = 2


def advance(plan: list[str], current: str, streak: int, grade) -> tuple[str, int, bool]:
    """Return ``(next_kp, new_streak, plan_completed)`` based on the correct streak.

    只看 ``grammar_correct``：语法结构对了就算掌握，拼写错误不影响推进。
    """
    if not plan:
        raise ValueError("学习计划不能为空")
    current = current if current in plan else plan[0]
    if grade is None:
        return current, streak, False
    streak = streak + 1 if grade.grammar_correct else 0
    if streak < CORRECT_STREAK_TO_ADVANCE:
        return current, streak, False
    index = plan.index(current) + 1
    return (plan[index], 0, False) if index < len(plan) else (current, 0, True)


def stale_answer(state) -> bool:
    """Return True when the answer targets a stale exercise_id that no longer matches ``pending_exercise``."""
    pending = state.get("pending_exercise")
    expected = state.get("expected_exercise_id")
    return bool(
        state.get("input_event") == "answer"
        and pending
        and expected
        and expected != pending.exercise_id
    )
