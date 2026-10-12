"""Offline tests must never load real credentials or contact external services."""

import asyncio
import os
import socket

import pytest

os.environ.update(
    {
        "PYTHON_DOTENV_DISABLED": "1",
        "GRADIO_ANALYTICS_ENABLED": "False",
        "DATABASE_URL": "sqlite://",
        "DEEPSEEK_API_KEY": "offline-test-key",
        "DASHSCOPE_API_KEY": "offline-test-key",
        "USE_MCP_TOOLS": "false",  # 测试用本地工具，MCP 子进程拿不到 SQLite 内存库
    }
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch, local_event_loop):
    def blocked(*args, **kwargs):
        raise AssertionError("Offline tests cannot access the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture(scope="session")
def local_event_loop():
    # Windows asyncio requires a local socketpair; create it before blocking external IO.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture
def database(monkeypatch):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from language_tutor.db.models import Base, Student
    from language_tutor.retrieval import error_store
    from language_tutor.services import assessment

    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session, session.begin():
        session.add_all([Student(id="alice"), Student(id="bob")])
    monkeypatch.setattr(assessment, "SessionLocal", factory)
    monkeypatch.setattr(error_store, "SessionLocal", factory)
    yield factory
    engine.dispose()
