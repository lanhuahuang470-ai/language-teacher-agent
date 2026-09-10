"""ORM table definitions; MVP uses ``Base.metadata.create_all``, not Alembic."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Student(Base):
    """Student profile; ``id`` is the demo username, not an auth identity."""

    __tablename__ = "students"

    id = Column(String, primary_key=True)  # 直接用 Gradio 传来的用户名，MVP 不做注册体系
    cefr_level = Column(String, nullable=False, default="A1")
    created_at = Column(DateTime, server_default=func.now())


class Mastery(Base):
    """知识点掌握度 —— 学习计划和复习排期的唯一数据源。"""

    __tablename__ = "mastery"

    student_id = Column(String, ForeignKey("students.id"), primary_key=True)
    knowledge_point = Column(String, primary_key=True)
    score = Column(Float, nullable=False, default=0.0)  # 0~1 滚动掌握度
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Error(Base):
    """错题记录 —— 评估节点判分时自动产生，供 RAG 语义检索和 SQL 精确查询。"""

    __tablename__ = "errors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String, ForeignKey("students.id"), nullable=False)
    knowledge_point = Column(String, nullable=False)
    error_sentence = Column(Text, nullable=False)  # 学生的原始错句
    correct_form = Column(Text, nullable=False)  # 正确形式
    error_types = Column(String, nullable=False)  # 逗号分隔，如 "时态,主谓一致"
    resolved = Column(Boolean, nullable=False, default=False)  # 连续答对后标记为已解决
    created_at = Column(DateTime, server_default=func.now())


class Assessment(Base):
    __tablename__ = "assessments"
    student_id = Column(String, ForeignKey("students.id"), primary_key=True)
    exercise_id = Column(String, primary_key=True)
    question = Column(Text, nullable=False)
    student_answer = Column(Text, nullable=False)
    grade = Column(JSON, nullable=False)
    error_id = Column(Integer, ForeignKey("errors.id"))
    created_at = Column(DateTime, server_default=func.now())


class ErrorEmbedding(Base):
    __tablename__ = "error_embeddings"
    error_id = Column(Integer, ForeignKey("errors.id"), primary_key=True)
    vector = Column(JSON(none_as_null=True), nullable=True)
    model = Column(String, nullable=False, default="")
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String, nullable=True)
    retry_after = Column(DateTime, nullable=False, server_default=func.now())


class SchemaMigration(Base):
    """Tracks which additive migrations have been applied."""

    __tablename__ = "schema_migrations"
    version = Column(String, primary_key=True)
    applied_at = Column(DateTime, server_default=func.now())
