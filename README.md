# 英语教学助手

LangGraph 编排规划、教学、评估 Agent，结合 PostgreSQL 学生档案、掌握度和个人错题检索。

当前实现：定级 → 计划 → 教学 → 判分 → 巩固或推进 → 课程结束。
支持提示、解释、跳过、会话续接、重复答题结果复用，以及 embedding 失败后的后台重试。

- [架构与取舍](docs/architecture.md)
- [分阶段修改记录](docs/optimization-progress.md)
- [评测与实测边界](docs/evaluation.md)
- [面试演示路线](docs/interview-demo.md)
- [开发约定](AGENTS.md)

## 安装与启动

当前项目已有虚拟环境在 `src/.venv`。新克隆环境可先执行 `python -m venv src/.venv`。

```powershell
& src/.venv/Scripts/python.exe -m pip install -r requirements.lock -r requirements-dev.txt
& src/.venv/Scripts/python.exe -m pip install -e . --no-deps --no-build-isolation
& src/.venv/Scripts/python.exe -m language_tutor
```

`requirements.lock` 记录本次验证的 Windows/Python 3.13 依赖闭包。其他平台先使用 `requirements.txt`，再运行测试确认。

已有 `src/.env` 可继续使用；新环境参照 `.env.example` 创建配置，并准备 PostgreSQL 数据库。
也可以用 `LANGUAGE_TUTOR_ENV_FILE` 指向其他配置文件。程序不会创建数据库本身。

兼容原启动方式：

```powershell
& src/.venv/Scripts/python.exe src/main.py
```

首次点击开始时，应用会执行增量建表、初始化 checkpoint、补齐旧错题索引任务并启动索引线程。
新增 `assessments`、`error_embeddings`、`schema_migrations` 三张表；不覆盖原学生和错题记录。

## 使用方式

1. 输入学生 ID 和会话 ID，点击“开始上课”。
2. `default` 会话续接原有学生 checkpoint；其他会话 ID 创建独立对话，共享该学生的掌握度和错题。
3. 新学生做五题定级；正常教学连续答对两题后进入下一知识点。
4. 选择“提示”“解释”保留原题；“跳过”更换同知识点题目，不记零分。
5. 完成课程后再次开始，重新生成学习计划。

学生 ID 是本地演示身份，尚未实现登录鉴权。

## 验证

```powershell
& src/.venv/Scripts/python.exe -m pytest -q
& src/.venv/Scripts/python.exe -m ruff check src tests scripts evals
& src/.venv/Scripts/python.exe -m ruff format --check src tests scripts evals
& src/.venv/Scripts/python.exe -m evals.run --mode exact-match
```

目前 86 项离线测试通过。覆盖状态路由、课程闭环、权限边界、事务回滚、幂等、索引重试、批量嵌入、历史类型兼容及 Gradio 界面/API schema 构建。

显式运维和真实 API 命令：

```powershell
& src/.venv/Scripts/python.exe -m scripts.migrate
& src/.venv/Scripts/python.exe -m scripts.retry_index
& src/.venv/Scripts/python.exe -m scripts.smoke_agent
& src/.venv/Scripts/python.exe -m evals.run --mode live --output evals/results/live.json
```

最后两条会调用真实模型。live 评测为禁用历史工具的独立判分评测，不代表整个多 Agent 系统的端到端质量。

## 容器演示

```powershell
docker compose up -d      # 启动 app + db 容器
docker compose down       # 停止并移除容器
```

配置使用独立的本地演示数据库卷，Web 端口只绑定到本机。
镜像已构建并启动验证，Gradio 界面可正常交互（容器内独立数据库，不影响宿主机数据）。
启动后浏览器打开 http://localhost:7860。

## 验证边界

真实模型评测已跑通：60 条种子题，准确率 90%，分数 MAE 0.177，延迟 P50 1058ms / P95 1414ms。
详见 [验证总结报告](docs/verification-report/verification-report.html)。
6 条判定错误种子题待人工复核；真实 PostgreSQL 并发/断连恢复测试尚未验证。
精确匹配基线成绩不等于 Agent 准确率。
检索采用 PostgreSQL 中的 JSON 向量与 Python 余弦排序，适合小规模个人错题；大规模数据再迁移 pgvector。

