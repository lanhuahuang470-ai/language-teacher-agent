# AGENTS.md — 英语教学助手开发约定

## 项目目标与当前状态

Python + LangGraph + DeepSeek + PostgreSQL + Gradio，面向中文母语学习者。
重点展示教学流程、工具权限边界、持久化恢复和可复现评测，而不是单纯增加 Agent 数量。

本轮按以下顺序落地：
1. **正确性**：学生隔离、结构化事件、课程推进、上下文、正确答案、输出校验。
2. **工程整理**：标准 Python 包、惰性工厂、运行资源管理、依赖版本记录、脚本/测试分离、Ruff。
3. **可靠性**：答题事务和幂等、持久化 embedding、重试任务、增量建表、旧 checkpoint 类型兼容。
4. **求职展示基础**：种子评测集/基线/真实模型评测入口、日志、架构说明、演示路线、Docker/CI 配置。

**验证结果：86 项离线测试通过；Ruff 检查和格式检查通过；本地可编辑安装、跨目录导入通过。**
真实模型评测已跑通（60 条种子题，准确率 90%，MAE 0.177，P50 1058ms）。
Docker 镜像已构建并启动验证，Gradio 界面可正常交互（容器内独立数据库）。
真实 PostgreSQL 并发/故障恢复尚未验证。
不要把 SQLite 回归或种子基线成绩描述成生产验证或 Agent 模型准确率。

## 当前目录

```text
AGENTS.md / README.md           开发约定与运行指南
pyproject.toml                 包元数据、CLI、pytest、Ruff
requirements.txt               直接运行依赖精确版本
requirements.lock              当前 Windows/Python 3.13 环境的依赖闭包
requirements-dev.txt           pytest、Ruff、打包工具
.env.example                   配置样例，不包含密钥
Dockerfile / compose.yaml      本地容器演示配置，已构建运行
.dockerignore                  排除 .venv/.env/__pycache__/tests/evals 进镜像
.github/workflows/check.yml    离线 CI，尚未在远程执行
docs/                          架构、评测、阶段记录和面试演示
evals/                         60 条待人工复核样例、评测脚本、精确匹配基线报告
scripts/                       migrate、retry_index、smoke_agent、smoke_tutor、check_pgvector
tests/                         正确性、事务/检索/迁移、评测/日志测试
src/
  .env                         原有配置位置，保留且不纳入版本控制
  main.py                      兼容 python src/main.py
  requirements.txt             兼容旧依赖入口
  graph/state.py               兼容旧 checkpoint 的 graph.state 类型路径
  language_tutor/
    __main__.py                python -m language_tutor
    config.py                  集中读取配置，支持 LANGUAGE_TUTOR_ENV_FILE
    bootstrap.py               增量建表、PostgresSaver、索引线程、连接释放
    telemetry.py               trace_id、节点耗时、异常类型
    ui/gradio_app.py           界面、事件、学生/会话绑定、提交题号
    domain/
      schemas.py              Exercise、GradeResult
      curriculum.py           A1/A2/B1 课程
      learning_policy.py      连续答对推进、过期题号检查
    agents/                    三个 Agent 工厂、只读工具
    graph/
      state.py                TutorState 与历史类型再导出
      builder.py              显式注入 checkpointer
      nodes/                  初始化、定级、教学、评估
    services/assessment.py    答题事务、已提交结果复用
    retrieval/
      embeddings.py          DashScope 适配、批量嵌入 embed_documents
      error_store.py         持久化向量、SQL 学生过滤、余弦排序、批量重试
    llm/                       惰性客户端、JSON 解析、输出模型及有限修复
    db/                        资源工厂、ORM、CRUD、版本化增量建表
```

## 设计约束

- 模型生成内容，代码负责身份、分数合法性、课程推进和持久化。
- 工具学生身份来自 RunnableConfig，不向模型暴露 student_id 参数。
- 个人错题在 top-k 前按学生过滤；相似语义不代表相同语法错误。
- 当前学生 ID 为本地演示身份，不是登录鉴权。公开服务仍需真实认证和授权。
- default 会话兼容旧 thread_id=student_id；其他会话使用学生/会话组合键。
- 只有 answer 且题号未过期时进入评估；开始/提示/解释不判分，提示/解释保留题目。
- 正常教学跳过只换同知识点题目，不记零分；定级不允许跳过。
- 连续两题完全正确后推进；答错/跳过清空连续正确次数。该阈值是 MVP 规则。
- 新评分 correct_answer 必须非空；feedback_hint 仅为反馈要点。
- grade_result 用完清空；placement_scores 使用显式覆盖，定级结束清空。
- 答题唯一键为 (student_id, exercise_id)；评分、掌握度、错题、索引任务在一个事务中提交。
- PostgreSQL 学生行锁用于串行化掌握度更新；不要将 SQLite 测试等同于 PG 并发验证。
- embedding 请求不在答题事务中执行。失败保留任务和重试时间，不重复评分。
- 向量持久化在 error_embeddings.vector（JSON）；目前 SQL 过滤后 Python 排序，非 pgvector。
- 迁移当前只新增表，不覆盖旧数据；旧 correct_form 可能存的是反馈，需要人工复核。
- 导入模块不连接数据库、不初始化 API 客户端。运行资源由 bootstrap 管理。
- 日志不记录密钥、题目或学生答案；供应商未提供 token 用量时记为 null。
- 后续继续按小批次修改和测试，不机械拆分短文件，不以增加框架数量作为优化目标。

## 验证命令（当前虚拟环境，项目根目录）

```powershell
& src/.venv/Scripts/python.exe -m pytest -q
& src/.venv/Scripts/python.exe -m ruff check src tests scripts evals
& src/.venv/Scripts/python.exe -m ruff format --check src tests scripts evals
& src/.venv/Scripts/python.exe -m evals.run --mode exact-match
```

测试使用假模型、假 embedding 和 SQLite/内存 checkpoint，不读取真实 .env，不允许外部网络。
Windows asyncio 所需本机 socketpair 在网络拦截前创建。
真实 API 冒烟和 live 评测必须显式运行，不能混入默认测试。

真实模型评测和冒烟测试（需 API key 和 PG 服务）：

```powershell
& src/.venv/Scripts/python.exe -m evals.run --mode live --output evals/results/live_baseline.json
& src/.venv/Scripts/python.exe scripts/smoke_agent.py
& src/.venv/Scripts/python.exe scripts/smoke_tutor.py
```

Docker 容器启动（项目根目录）：

```powershell
docker compose up -d      # 启动 app + db 容器
docker compose down       # 停止并移除容器
```

## 后续验收重点

- 用独立测试数据库验证 PG 并发重复提交、断连恢复和真实 PostgresSaver 续接。
- 人工复核种子题中 6 条判定错误（02-2/04-2/05-2/07-2/09-2/10-2），优化评分 prompt 收窄分差。
- 录制演示视频，再填写简历中的模型指标。
- 多进程部署前增加索引任务领取/租约与同会话并发控制；当前运行方式是单应用进程。


## 教学输出报错修复

- 原日志仅记录 TeachingOutput 校验失败，不能据此推断具体字段；不记录用户答案正文。
- 首轮提供合法 JSON Schema；有限重试带上上一条无效输出与字段/错误类型，不能只重复原任务。
- 教学可忽略无关元数据，但 reply/exercise 仍要求非空字符串；不放宽评分校验。
- JSON 字符串中的原始换行可解析；多内容块提取文本。
- ModelOutputError 在界面转换为可读错误；日志只记录字段名和错误类型。
- checkpoint_serializer 显式登记新旧 Exercise/GradeResult 类型，不使用全局反序列化放行。
- 本次新增 12 项离线回归；未调用真实 API 复现原回复。
