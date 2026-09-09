# 自测 tutor 分支一：依据判分给反馈
from language_tutor.graph.nodes.tutor import run
from language_tutor.graph.state import GradeResult


def main():
    state = {
        "student_id": "test_user",
        "messages": [],
        "cefr_level": "A1",
        "session_plan": ["be动词"],
        "current_kp": "be动词",
        "grade_result": GradeResult(
            exercise_id="test001",
            is_correct=False,
            score=0.0,
            error_types=["主谓一致"],
            feedback_hint="be动词应改为was，主语是第三人称单数",
        ),
    }
    result = run(state)
    print(f"反馈: {result['messages'][0][1][:80]}...")
    print(f"grade 已清空: {result['grade_result']}")
    print(f"巩固题: {result.get('pending_exercise')}")


if __name__ == "__main__":
    main()
