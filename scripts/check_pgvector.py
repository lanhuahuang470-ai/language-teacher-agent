# 检查 pgvector 扩展是否可用
from sqlalchemy import text

from language_tutor.db.engine import get_engine


def main():
    with get_engine().connect() as conn:
        result = conn.execute(text("SELECT * FROM pg_available_extensions WHERE name = 'vector'"))
        rows = result.fetchall()
        if rows:
            print(f"pgvector 可用: {rows[0]}")
        else:
            print("pgvector 扩展不可用，需要安装")

        result2 = conn.execute(text("SELECT version()"))
        print(f"PG 版本: {result2.fetchone()[0]}")


if __name__ == "__main__":
    main()
