# 英语教学助手

面向中文母语学习者的个性化英语教学 Agent。用 LangGraph 编排**规划 / 教学 / 评估**三个 Agent，
通过 **MCP** 把教学工具服务化，结合 PostgreSQL 保存学生档案、掌握度与个人错题向量，
用 Gradio 提供本地交互。重点不在堆 Agent 数量，而在于多 Agent 架构、工具服务化、
事务一致性、持久化恢复与可复现评测。

主流程：`定级 → 计划 → 教学 → 判分 → 巩固或推进 → 升级 / 结束`。
支持提示、解释、跳过、会话续接、重复答题结果复用，以及 embedding 失败后的后台重试。

**验证现状：86 项离线测试通过；Ruff 检查与格式检查通过；Docker 镜像已构建启动验证；GitHub Actions CI 已通过。
真实模型评测 94 道种子题准确率 97.9%、分数 MAE 0.052。**

## 文档

- [架构与取舍](docs/architecture.md)
- [分阶段修改记录](docs/optimization-progress.md)
- [评测与实测边界](docs/evaluation.md)
- [面试演示路线](docs/interview-demo.md)
- [验证总结报告](docs/verification-report/verification-report.html)
- [简历项目说明](docs/resume-project/resume-project.html)
- [开发约定](AGENTS.md)

## 核心设计

- **三 Agent 编排**：规划负责学什么、教学负责怎么讲、评估负责判分，职责与工具权限分离。
- **MCP 工具服务化**：教学工具（掌握度、错题、课程查询）统一走 MCP Server，共 7 个内部工具，
  与 Agent 框架解耦；`USE_MCP_TOOLS` 控制是否启用，关闭时回退到本地 LangChain 工具。
- **工具权限隔离**：规划 4 个工具、教学 5 个、评估 2 个，各自只能看到权限内子集。
- **身份安全**：工具本身带 `student_id`，但客户端包装层从模型可见 schema 中移除该字段，
  调用时从 `RunnableConfig` 自动注入——模型看不到也无法伪造学生身份。
- **事务与幂等**：`(student_id, exercise_id)` 为唯一答题键，评分、掌握度、错题、索引任务在同一事务提交；
  PostgreSQL 行锁串行化同一学生的掌握度更新，重复提交复用原评分。
- **持久化向量与重试**：错题向量存库，重启无需重算；embedding 调用独立于答题事务，
  失败保留任务与退避时间由后台线程重试。

## 架构概览

```text
用户事件 + 题号
      │
      ▼
 init_session / 续接  ──▶  定级(9题)  ──▶  规划 Agent ──▶ 教学 Agent
      │                                                       │
      ▼                                                       ▼
 评估 Agent  ──▶  事务: 评分 + 掌握度 + 错题 + 索引任务  ──▶  学会则推进 / 整级升级
      │                                                       │
      ▼                                                       ▼
 Checkpoint / 回复                              后台 embedding 重试 → 持久化 JSON 向量
```

模块职责：`domain` 题目与学习策略｜`agents` 提示词与工具工厂｜`graph` 状态流转与路由｜
`services` 答题事务｜`retrieval` 向量与检索重试｜`db` 资源/ORM/增量建表｜
`bootstrap` 连接与索引线程｜`ui` Gradio 界面｜`mcp` MCP 服务层。

## 安装与启动

当前项目已有虚拟环境在 `src/.venv`。新克隆环境可先执行 `python -m venv src/.venv`。

```powershell
& src/.venv/Scripts/python.exe -m pip install -r requirements.lock -r requirements-dev.txt
& src/.venv/Scripts/python.exe -m pip install -e . --no-deps --no-build-isolation
& src/.venv/Scripts/python.exe -m language_tutor
```

`requirements.lock` 记录本次验证的 Windows/Python 3.13 依赖闭包。其他平台先使用 `requirements.txt`，
再运行测试确认。

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
3. 新学生做 9 题定级（A1→C2 逐级探测），定级期间不写掌握度、不记错题。
4. 选择“提示”“解释”保留原题；“跳过”更换同知识点题目，不记零分。
5. 正常教学连续答对两题后进入下一知识点；当前等级全部知识点掌握度 ≥ 0.8 时自动升级。
6. 完成课程后再次开始，重新生成学习计划。

学生 ID 是本地演示身份，尚未实现登录鉴权。

## 课程与学习策略

- 课程覆盖 CEFR **A1–C2 共 6 个等级、24 个知识点**，知识点含跨级前置依赖（如“被动语态”依赖“一般过去时”）。
- 定级 9 道题，按难度递进给出初始等级。
- 规划 Agent 采用 5 级优先级（依赖检查 → 错题模式 → 薄弱优先 → 新旧搭配 → 顺序合理），输出 `focus` 字段。
- 错题不删除，标记为 `resolved` 保留历史，供 RAG 检索与规划分析；
  `get_error_history` 只返回未解决错题，`get_error_summary` 返回已解决/未解决分类计数。
- 存储控制：`state.messages` 超过 `MAX_MESSAGES`（默认 40）时裁剪最旧消息；
  每 thread 只保留最新 `CHECKPOINT_KEEP`（默认 5）个 checkpoint。

## 验证

```powershell
& src/.venv/Scripts/python.exe -m pytest -q
& src/.venv/Scripts/python.exe -m ruff check src tests scripts evals
& src/.venv/Scripts/python.exe -m ruff format --check src tests scripts evals
& src/.venv/Scripts/python.exe -m evals.run --mode exact-match
```

目前 **86 项离线测试通过**（假模型、假 embedding、SQLite 事务、内存 checkpoint，不读真实 `.env`、不联网）。
覆盖状态路由、课程闭环、权限边界、事务回滚、幂等、索引重试、批量嵌入、历史类型兼容及界面/API schema 构建。

显式运维和真实 API 命令：

```powershell
& src/.venv/Scripts/python.exe -m scripts.migrate
& src/.venv/Scripts/python.exe -m scripts.retry_index
& src/.venv/Scripts/python.exe -m scripts.smoke_agent
& src/.venv/Scripts/python.exe -m evals.run --mode live --output evals/results/live_v3.json
```

最后一行会调用真实模型。live 评测为禁用历史工具的独立判分评测，不代表整个多 Agent 系统的端到端质量。

## 评测结果

94 道人工复核种子题（10 个知识点、13 种题型），评分任务独立判分：

| 版本 | 题目数 | 判定准确率 | 分数 MAE | P50 延迟 | 有效输出率 |
|------|--------|-----------|----------|----------|-----------|
| exact-match 基线（确定性） | 94 | 76.6% | 0.326 | — | 100% |
| v1 真实模型（原始 prompt） | 60 | 90.0% | 0.177 | 1058 ms | 100% |
| v2 真实模型（答案识别优化） | 94 | **97.9%** | 0.052 | 807 ms | 100% |
| v3 真实模型（题型识别优化） | 94 | 96.8% | **0.034** | 930 ms | 97.9% |

模型为 `deepseek-chat`。v2 通过在评分 prompt 中加入“答案识别规则”（答案含正确语法形式即算对，
啰嗦表达不扣分）解决 6 道假阴性，把准确率从 90% 提升到 97.9%；v3 进一步把 MAE 降到 0.034。
对比脚本：`src/.venv/Scripts/python.exe scripts/compare_evals.py`。

## 容器演示

```powershell
docker compose up -d      # 启动 app + db 容器
docker compose down       # 停止并移除容器
```

配置使用独立的本地演示数据库卷，Web 端口只绑定到本机。镜像已构建并启动验证，
Gradio 界面可正常交互（容器内独立数据库，不影响宿主机数据）。启动后浏览器打开 http://localhost:7860。

## 验证边界

以下必须如实标注，不要把回归或基线成绩说成生产验证：

- 精确匹配基线 / 种子集成绩**不等于** Agent 真实准确率，也不代表真实学习者分布或 CEFR 测评有效性。
- live 评测只覆盖孤立评分，**不含**错题检索增强的效果。
- **真实 PostgreSQL 并发与断连恢复尚未验证**；SQLite 测试不等于 PG 并发验证。
- 真实 embedding 召回效果、端到端教学效果（有 RAG vs 无 RAG 的错题复发率）尚未验证。
- 检索使用 PostgreSQL 中的 JSON 向量 + Python 余弦排序，适合小规模个人错题；规模增长后再迁移 pgvector。
- 当前后台索引任务与运行方式适配**单应用进程**，多进程部署需先加任务租约与同会话并发控制。
- 遗留 2 道边界题型偏差：句子判断（开放式）、词汇选择（语法对但词用错）。
