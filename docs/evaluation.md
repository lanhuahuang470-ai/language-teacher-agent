# 评测说明

## 已执行

- 58 项离线测试：假模型、假 embedding、SQLite 事务、内存 checkpoint、界面/API schema。
- Ruff lint 与格式检查。
- 可编辑安装以及项目目录之外的惰性导入。
- 60 条种子数据上的精确匹配基线，报告见 [baseline.json](../evals/results/baseline.json)。

基线正确性分类准确率为 50/60（约 83.3%），评分 MAE 为 0.25。
这些是确定性字符串匹配在合成题集上的结果，**不是 DeepSeek 或 Agent 的准确率**。
基线不能很好处理答案解释和部分正确，适合作为后续模型对照。

## 数据集状态

[assessment_seed.json](../evals/data/assessment_seed.json) 包含十组语法题，每组覆盖：
标准正确答案、自然语言表达的正确答案、错误答案、提示词注入、答非所问、部分正确。

数据由项目开发过程整理，human_reviewed=false。使用前需要人工复核题目、参考答案和部分分标准。
不要用这些样例的成绩代表真实学习者分布、CEFR 测评有效性或教学收益。

## 真实模型评测入口

```powershell
& src/.venv/Scripts/python.exe -m evals.run --mode live --output evals/results/live.json
```

该命令使用评估提示词，但禁用历史查询工具，评估独立判分。
输出包含合法输出率、正确性分类准确率、有效评分 MAE、p50/p95 耗时、模型名、提示词哈希、数据哈希和逐条结果。
失败案例计入分类准确率分母；MAE 只统计有效输出，必须同时查看合法输出率。

本轮没有执行 live，也没有生成伪造的 live 报告。模型 token 用量通过运行日志记录；缺失值为 null。

## 下一轮实验

1. 人工复核种子集，并加入真实使用中出现的匿名化失败样例。
2. 分别测无历史、SQL 历史和语义检索增强的判分/反馈表现。
3. 给相似错题标注相关性，测 Recall@3、错误类型匹配率及跨学生泄漏。
4. 对比单次模型调用、固定工具流程、多 Agent 方案的质量、耗时和 token。
5. 使用独立 PostgreSQL 测试库验证并发提交、提交后断连和 checkpoint 续接。

## 未验证

真实模型质量、真实 embedding 召回效果、PostgreSQL 并发与网络故障恢复、容器构建运行和浏览器完整交互。
CI 配置已提供，但没有远程仓库执行结果。

