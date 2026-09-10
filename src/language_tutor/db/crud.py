"""数据访问层：所有 PG 读写都集中在这里。

其他层（nodes、services、tools）不直接写 SQL，都调这里的函数。
每个函数职责单一，参数明确，返回 ORM 对象或基础类型。
"""

from __future__ import annotations

from language_tutor.db.models import Error, Mastery, Student


def get_or_create_student(session, student_id: str) -> tuple[Student, bool]:
    """查或建学生档案。返回 (student, is_new)。

    新学生自动建档，cefr_level 默认 A1。
    被调用方：init_session.run
    """
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
    """更新或新建知识点的掌握度。

    用滚动平均（0.7*旧 + 0.3*新）平滑单次判分噪声（蒙对/手滑）。
    被调用方：services/assessment.record_assessment（在事务内，commit=False）
    """
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
        # 首次记录该知识点
        existing = Mastery(
            student_id=student_id,
            knowledge_point=knowledge_point,
            score=score,
        )
        session.add(existing)
    else:
        # 滚动平均更新
        existing.score = 0.7 * existing.score + 0.3 * score

    session.commit() if commit else session.flush()


def get_mastery_map(session, student_id: str) -> dict[str, float]:
    """返回该学生全部知识点的掌握度 {知识点: 分数}。

    被调用方：
      - init_session.run：检查是否满足升级条件
      - tools.get_mastery / get_weak_points：Agent 工具查询
    """
    # 拉取该学生全部知识点的掌握度，转成 {知识点: 分数} 便于 O(1) 查表
    rows = session.query(Mastery).filter_by(student_id=student_id).all()
    return {r.knowledge_point: r.score for r in rows}


def update_student_level(session, student_id: str, level: str):
    """更新学生 CEFR 等级（A1/A2/B1/B2/C1/C2）。

    被调用方：
      - placement.handle_placement：定级结束后写入最终等级
      - init_session.run：自动升级时写入新等级
    """
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
    """保存一条错题记录。只在答错时调用（is_correct=False）。

    被调用方：services/assessment.record_assessment（在事务内，commit=False）
    返回 Error 对象，调用方用 error.id 创建 ErrorEmbedding 索引任务。
    """
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
    """查某学生在某知识点最近 5 条未解决错题。

    SQL 精确查询（按知识点过滤 + resolved=False），用于复习工具 get_error_history。
    只返回未解决的错题——已标记 resolved 的不再干扰当前教学。
    按时间降序 + id 降序（时间相同时用 id 兜底排序）。
    """
    return (
        session.query(Error)
        .filter_by(
            student_id=student_id,
            knowledge_point=knowledge_point,
            resolved=False,
        )
        .order_by(Error.created_at.desc(), Error.id.desc())
        .limit(5)
        .all()
    )


def get_error_summary(session, student_id: str) -> list[dict]:
    """聚合统计学生在每个知识点的错题数量和错误类型（含已解决/未解决分类）。

    返回示例: [{"knowledge_point": "一般过去时", "count": 3,
               "unresolved": 2, "resolved": 1, "error_types": ["时态混淆", "主谓一致"]}, ...]
    被调用方：tools.get_error_summary（规划 Agent 用，不返回具体错句内容）
    """
    rows = (
        session.query(Error)
        .filter_by(student_id=student_id)
        .order_by(Error.created_at.desc())
        .all()
    )
    summary: dict[str, dict] = {}
    for row in rows:
        kp = row.knowledge_point
        if kp not in summary:
            summary[kp] = {
                "knowledge_point": kp,
                "count": 0,
                "unresolved": 0,
                "resolved": 0,
                "error_types": set(),
            }
        summary[kp]["count"] += 1
        if row.resolved:
            summary[kp]["resolved"] += 1
        else:
            summary[kp]["unresolved"] += 1
        if row.error_types:
            for t in row.error_types.split(","):
                if t:
                    summary[kp]["error_types"].add(t)
    return [
        {**v, "error_types": sorted(v["error_types"])}
        for v in sorted(summary.values(), key=lambda x: x["count"], reverse=True)
    ]


def resolve_errors_by_kp(
    session,
    student_id: str,
    knowledge_point: str,
    *,
    commit: bool = True,
):
    """标记某学生在某知识点的全部未解决错题为已解决（resolved=True）。

    触发时机：连续答对两题后，tutor._handle_teaching 调用。
    不删除数据——保留历史错题供 RAG 语义检索和规划 Agent 分析错误模式。
    后续学生重新犯错时，新错题的 resolved=False，不影响旧已解决记录。
    """
    session.query(Error).filter(
        Error.student_id == student_id,
        Error.knowledge_point == knowledge_point,
        Error.resolved == False,  # noqa: E712 — SQLAlchemy 需要显式 == False
    ).update({"resolved": True}, synchronize_session=False)
    session.commit() if commit else session.flush()
