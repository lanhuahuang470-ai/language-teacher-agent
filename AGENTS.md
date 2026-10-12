# AGENTS.md — 英语教学助手开发约定

## 项目目标与当前状态

Python + LangGraph + MCP + DeepSeek + PostgreSQL + Gradio，面向中文母语学习者。
重点展示多 Agent 架构、MCP 工具服务化、事务一致性、持久化恢复和可复现评测，而不是单纯增加 Agent 数量。

已完成阶段：
1. **正确性**：学生隔离、结构化事件、课程推进、上下文、正确答案、输出校验。
2. **工程整理**：标准 Python 包、惰性工厂、运行资源管理、依赖版本记录、脚本/测试分离、Ruff。
3. **可靠性**：答题事务和幂等、持久化 embedding、重试任务、增量建表、旧 checkpoint 类型兼容。
4. **求职展示基础**：种子评测集/基线/真实模型评测、日志、架构说明、Docker/CI 配置。
5. **MCP 工具服务化**：教学工具 MCP Server（7 个内部工具），Agent 编排与业务工具解耦。
6. **评测优化**：94 道人工复核种子题，评分准确率 97.9%，MAE 0.052。

**验证结果：86 项离线测试通过；Ruff 检查和格式检查通过；本地可编辑安装、跨目录导入通过。**
真实模型评测已跑通（94 道种子题，准确率 97.9%，MAE 0.052，P50 807ms）。
Docker 镜像已构建并启动验证，Gradio 界面可正常交互（容器内独立数据库）。
GitHub Actions CI 已通过（ubuntu-latest）。
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
.github/workflows/check.yml    离线 CI，已在 GitHub Actions 通过（ubuntu-latest）
docs/                          架构、评测、阶段记录和面试演示
evals/                         94 道人工复核样例、评测脚本、精确匹配基线报告
scripts/                       migrate、retry_index、smoke_agent、smoke_tutor、check_pgvector
tests/                         正确性、事务/检索/迁移、评测/日志测试
src/
  .env                         原有配置位置，保留且不纳入版本控制
  main.py                      兼容 python src/main.py
  requirements.txt             兼容旧依赖入口
  graph/state.py               兼容旧 checkpoint 的 graph.state 类型路径
  language_tutor/
    __main__.py                python -m language_tutor
    config.py                  集中读取配置，支持 LANGUAGE_TUTOR_ENV_FILE / USE_MCP_TOOLS
    bootstrap.py               增量建表、PostgresSaver、索引线程、连接释放
    telemetry.py               trace_id、节点耗时、异常类型
    mcp_server.py              教学工具 MCP Server（7 个内部工具）
    mcp_client.py              MCP 客户端封装 + 工具包装（隐藏 student_id）
    mcp/
      __init__.py
    ui/gradio_app.py           界面、事件、学生/会话绑定、提交题号
    domain/
      schemas.py              Exercise、GradeResult
      curriculum.py           A1/A2/B1 课程
      learning_policy.py      连续答对推进、过期题号检查
    agents/                    三个 Agent 工厂、本地工具（MCP 关闭时的 fallback）
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

## MCP 架构

### MCP Server

| Server | 类型 | 工具数 | 调用方 | 用途 |
|--------|------|--------|--------|------|
| 教学工具 MCP | 内部业务 | 7 | 三个 Agent | 掌握度、错题、课程查询 |

### 工具权限隔离

- Planning Agent：get_weak_points / get_curriculum / get_error_summary / get_kp_dependencies（4 个）
- Teaching Agent：get_mastery / get_weak_points / get_curriculum / get_error_history / get_similar_errors（5 个）
- Assessment Agent：get_error_history / get_similar_errors（2 个）

### 身份安全

- MCP 工具本身带 student_id 参数
- 客户端包装层从输入 schema 中移除 student_id 字段
- 调用时从 RunnableConfig 取出 student_id 自动注入
- 模型侧看不到也无法伪造学生身份

### 可插拔设计

- `USE_MCP_TOOLS=true`（默认）：Agent 走 MCP 工具路径
- `USE_MCP_TOOLS=false`：回退到本地 LangChain 工具（测试使用）

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
测试环境 USE_MCP_TOOLS=false，走本地工具路径，保证 monkeypatch 生效。
Windows asyncio 所需本机 socketpair 在网络拦截前创建。
真实 API 冒烟和 live 评测必须显式运行，不能混入默认测试。

真实模型评测和冒烟测试（需 API key 和 PG 服务）：

```powershell
& src/.venv/Scripts/python.exe -m evals.run --mode live --output evals/results/live_v2.json
& src/.venv/Scripts/python.exe scripts/smoke_agent.py
& src/.venv/Scripts/python.exe scripts/smoke_tutor.py
```

MCP Server 单独验证：

```powershell
# 教学工具 MCP
& src/.venv/Scripts/python.exe -c "from mcp.server.fastmcp import FastMCP; from language_tutor.mcp_server import mcp; print('OK')"
```

Docker 容器启动（项目根目录）：

```powershell
docker compose up -d      # 启动 app + db 容器
docker compose down       # 停止并移除容器
```

## 评测数据

- 94 道种子题（human_reviewed=true），10 个知识点，13 种题型
- 题型：标准填空、啰嗦但正确（英/中）、完全错误、提示词注入、答非所问、部分正确（多空）、拼写错误、大小写/空格、句子判断、词汇选择、拒绝回答、易混淆错误、翻译填空
- 真实模型（deepseek-chat）评测结果：准确率 97.9%，MAE 0.052，P50 807ms，有效输出率 100%
- 优化过程：v1 基线 90% → v2 答案识别规则优化 97.9%（解决 6 道假阴性）
- 遗留偏差：2 道边界题型（句子判断开放式、词汇选择）

## 后续验收重点

- 用独立测试数据库验证 PG 并发重复提交、断连恢复和真实 PostgresSaver 续接。
- 录制演示视频，展示完整教学流程（定级→教学→答题→评分）。
- 端到端评测：有 RAG vs 无 RAG 的错题复发率对比。
- 多 Agent 对比实验：单次模型调用 vs 固定工具流程 vs 三 Agent ReAct 的质量/耗时/token 对比。
- 多进程部署前增加索引任务领取/租约与同会话并发控制；当前运行方式是单应用进程。
- pgvector 迁移（可选）：目前 JSON 向量够用，规模增长后再考虑。
