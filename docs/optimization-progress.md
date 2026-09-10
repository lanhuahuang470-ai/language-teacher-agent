# 本轮优化记录

## 第一阶段：正确性

修复跨学生向量检索、模型指定身份、开始/提示被判分、课程不推进、正确答案存成反馈要点的问题。
新增输出校验与最多一次修复重试，修复 JSON 字符串内花括号解析。
定级节点独立，分数列表可清空；通过 46 项离线回归。

## 第二阶段：工程整理

应用进入 language_tutor 包；课程、策略与数据对象放入 domain。
模型和 Agent 使用惰性工厂，数据库资源由 bootstrap 管理。
原 API 脚本移入 scripts，新增 pyproject、精确直接依赖和本地环境依赖闭包。
保留旧入口和历史 checkpoint 类型路径。可编辑安装、跨目录导入通过。

## 第三阶段：可靠性

新增 assessments 唯一答题记录；掌握度、错题、索引任务统一提交。
增加 error_embeddings 持久化向量与失败退避，旧错题可补建索引任务。
新增 schema_migrations 记录增量建表版本，保留旧数据。
界面增加会话 ID 和提交题号，过期答案不进入评估。
SQLite 测试验证回滚、幂等、重试和重复迁移；未操作真实 PostgreSQL。

## 第四阶段：展示与评测基础

新增 trace_id、节点耗时、工具次数与可用 token 日志。
新增 60 条待人工复核样例、精确匹配基线及真实独立判分评测入口。
提供架构、面试演示、Docker Compose 和 CI 配置。
最终 58 项离线测试通过，Ruff 通过；Compose 静态解析成功，容器未启动。

## 第五阶段：代码风格与课程扩展（2026-09-09）

按 CODESTYLE_GUIDE.md 补充模块级 docstring、类 docstring、方法 docstring；
全量添加 `from __future__ import annotations`；补全 `__init__.py` 的 `__all__` 重导出。
课程从 A1–B1 扩展到 A1–C2，共 6 个等级 24 个知识点；定级题从 5 道扩展到 9 道。
新增自动升级机制：当前等级全部知识点掌握度 ≥ 0.8 时升一级。
规划 Agent 增强：新增错题模式聚合和前置依赖工具，从 3 工具扩展到 4 工具，
策略从"按掌握度排序"升级为 5 级优先级（依赖检查 → 错题模式 → 薄弱优先 → 新旧搭配 → 顺序合理），
输出增加 focus 字段（review/mixed/new）。
错题从"连续答对两题删除"改为"标记 resolved"，保留历史供 RAG 检索和规划分析；
`get_error_history` 只返回未解决错题，`get_error_summary` 返回已解决/未解决分类计数。
新增 PG 存储控制：state.messages 超过 MAX_MESSAGES（默认 40）时删除最旧的；
启动时清理旧 checkpoint，每 thread 保留最新 CHECKPOINT_KEEP（默认 5）个。
最终 84 项离线测试通过，Ruff 检查和格式检查通过。

## 后续需要真实环境的验收

真实模型与检索评测、独立 PG 库并发/恢复测试、容器构建和浏览器演示。
这些验收没有被"已有 checkpoint"或"离线测试通过"替代。
