# 数据访问层：所有 PG 读写集中在这里，节点不直接写 SQL
# 好处：换库/加缓存/改查询时只改这一层
from language_tutor.db.models import Error, Mastery, Student


def get_or_create_student(session, student_id: str) -> tuple[Student, bool]:
    # 返回 (student, is_new)：is_new=True 说明是刚建档的新学生
    student = session.query(Student).filter_by(id=student_id).first()
    if student is None:
        student = Student(id=student_id, cefr_level="A1")
        session.add(student)
        session.commit()
        return student, True
    return student, False


def upsert_mastery(
    session, student_id: str, knowledge_point: str, score: float, *, commit: bool = True
):
    # 滚动平均：0.7*旧 + 0.3*新 —— 单次判分有噪声（蒙对/手滑），平滑抗抖
    existing = (
        session.query(Mastery)
        .filter_by(
            student_id=student_id,
            knowledge_point=knowledge_point,
        )
        .first()
    )

    if existing is None:
        existing = Mastery(
            student_id=student_id,
            knowledge_point=knowledge_point,
            score=score,
        )
        session.add(existing)
    else:
        existing.score = 0.7 * existing.score + 0.3 * score

    session.commit() if commit else session.flush()


def get_mastery_map(session, student_id: str) -> dict[str, float]:
    # 拉取该学生全部知识点的掌握度，转成 {知识点: 分数} 便于 O(1) 查表
    # 用途：路由/出题节点据此判断薄弱点，无需逐条回查数据库
    rows = session.query(Mastery).filter_by(student_id=student_id).all()
    return {r.knowledge_point: r.score for r in rows}


def update_student_level(session, student_id: str, level: str):
    # 定级测试结束后更新学生等级（A1/A2/B1）
    student = session.query(Student).filter_by(id=student_id).first()
    if student:
        student.cefr_level = level
        session.commit()


def save_error(
    session,
    student_id: str,
    knowledge_point: str,
    error_sentence: str,
    correct_form: str,
    error_types: list[str],
    *,
    commit: bool = True,
):
    # 评估节点判分后自动保存错题到 PG
    # 只保存答错的题（is_correct=False），答对的不存
    error = Error(
        student_id=student_id,
        knowledge_point=knowledge_point,
        error_sentence=error_sentence,
        correct_form=correct_form,
        error_types=",".join(error_types),
    )
    session.add(error)
    session.commit() if commit else session.flush()
    return error


def get_errors_by_kp(session, student_id: str, knowledge_point: str) -> list[Error]:
    # 查某学生在某知识点的最近五条错题（SQL 精确查询，用于复习工具）
    return (
        session.query(Error)
        .filter_by(
            student_id=student_id,
            knowledge_point=knowledge_point,
        )
        .order_by(Error.created_at.desc(), Error.id.desc())
        .limit(5)
        .all()
    )
