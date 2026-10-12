"""对比 v1 / v2 / v3 评测结果。"""

import json
from pathlib import Path

versions = [
    ("v1 (原始prompt, 60题)", Path("evals/results/live_baseline.json")),
    ("v2 (答案识别优化, 94题)", Path("evals/results/live_v2.json")),
    ("v3 (题型识别优化, 94题)", Path("evals/results/live_v3.json")),
]

results = []
for label, path in versions:
    if not path.exists():
        print(f"[跳过] 未找到 {path}")
        continue
    with open(path, encoding="utf-8") as f:
        results.append((label, json.load(f)))

if not results:
    raise SystemExit("没有可用的评测结果文件，请先运行 evals.run。")

print("=" * 70)
print(" 评测版本对比")
print("=" * 70)
print(f"{'版本':<28} {'题目数':<6} {'准确率':<8} {'MAE':<8} {'P50':<8} {'有效率':<8}")
print("-" * 70)
for label, r in results:
    print(
        f"{label:<28} "
        f"{r['case_count']:<6} "
        f"{r['correctness_accuracy']:<8.1%} "
        f"{r['score_mae_valid_only']:<8.3f} "
        f"{r['latency_p50_ms']:<8.0f} "
        f"{r['valid_output_rate']:<8.1%}"
    )

print()
print("=" * 70)
print(" v3 错题明细")
print("=" * 70)
_, v3 = results[-1]
rows = v3["results"]

# 无效输出没有 score/correct 字段，单列统计，避免 KeyError
invalid = [r for r in rows if r.get("score") is None]
if invalid:
    print(f"无效输出 {len(invalid)} 条（计入分类准确率分母，不计入 MAE）:")
    for row in invalid:
        print(f"  {row['id']}: {row.get('error_type', '未知错误')}")
    print()

wrong = [
    r for r in rows if r.get("score") is not None and r.get("correct") != r.get("expected_correct")
]
print(f"共 {len(wrong)} 道判错:")
for row in wrong:
    direction = "漏判 (应为对却判错)" if row.get("expected_correct") else "误判 (应为错却判对)"
    print(f"  {row['id']}: 预期{row['expected_score']}分, 模型给{row['score']}分 -> {direction}")
