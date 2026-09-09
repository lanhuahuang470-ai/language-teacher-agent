"""Deterministic course progression, independent of model decisions."""

CORRECT_STREAK_TO_ADVANCE = 2


def advance(plan: list[str], current: str, streak: int, grade) -> tuple[str, int, bool]:
    if not plan:
        raise ValueError("学习计划不能为空")
    current = current if current in plan else plan[0]
    if grade is None:
        return current, streak, False
    streak = streak + 1 if grade.is_correct else 0
    if streak < CORRECT_STREAK_TO_ADVANCE:
        return current, streak, False
    index = plan.index(current) + 1
    return (plan[index], 0, False) if index < len(plan) else (current, 0, True)


def stale_answer(state) -> bool:
    pending = state.get("pending_exercise")
    expected = state.get("expected_exercise_id")
    return bool(
        state.get("input_event") == "answer"
        and pending
        and expected
        and expected != pending.exercise_id
    )
