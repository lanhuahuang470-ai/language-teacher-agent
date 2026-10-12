"""查看 v3 评测的错题和无效输出。"""

import json
from pathlib import Path

with open(Path("evals/results/live_v3.json"), encoding="utf-8") as f:
    r = json.load(f)

valid = [x for x in r["results"] if x.get("score") is not None]
invalid = [x for x in r["results"] if x.get("score") is None]

print(f"有效: {len(valid)}, 无效: {len(invalid)}")
print()

print("无效输出:")
for x in invalid:
    raw = str(x.get("raw_output", ""))[:100]
    print(f"  {x['id']}: {raw}")

print()
print("判错的题:")
for x in valid:
    if x.get("correct") != x.get("expected_correct"):
        d = "漏判" if x["expected_correct"] else "误判"
        print(f"  {x['id']}: 预期{x['expected_score']}, 模型{x['score']} -> {d}")
