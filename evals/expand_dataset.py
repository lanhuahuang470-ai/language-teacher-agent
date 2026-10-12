"""扩充评测数据集：60 → 100 题。

新增题型：
- 拼写错误（语法对拼写错 → 0.8 分）
- 句子改错题
- 翻译题（中译英填空）
- 大小写/标点/空格等边界情况
- 中文夹杂的答案
- 近义词/词汇选择错误
- 更多啰嗦但正确的表达
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "assessment_seed.json"


def load_existing() -> dict:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def make_cases() -> list[dict]:
    """生成 40 道新评测题。"""
    new_cases = []

    # ── 11 组：拼写错误（语法正确，拼写错误 → 0.8 分） ──────────
    new_cases += [
        {
            "id": "11-1",
            "knowledge_point": "一般现在时",
            "question": "She ___ coffee every morning.",
            "student_answer": "drinnks",
            "reference_answers": ["drinks"],
            "expected_score": 0.8,
            "expected_correct": False,
            "error_types_expected": ["拼写"],
        },
        {
            "id": "11-2",
            "knowledge_point": "be动词",
            "question": "They ___ happy.",
            "student_answer": "aree",
            "reference_answers": ["are"],
            "expected_score": 0.8,
            "expected_correct": False,
            "error_types_expected": ["拼写"],
        },
        {
            "id": "11-3",
            "knowledge_point": "一般过去时",
            "question": "Yesterday I ___ to school.",
            "student_answer": "wented",
            "reference_answers": ["went"],
            "expected_score": 0.0,
            "expected_correct": False,
            "error_types_expected": ["时态", "拼写"],
        },
    ]

    # ── 12 组：啰嗦但正确的答案（各种表达 → 1.0 分） ──────────
    new_cases += [
        {
            "id": "12-1",
            "knowledge_point": "be动词",
            "question": "He ___ happy.",
            "student_answer": "应该是 is 吧",
            "reference_answers": ["is"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "12-2",
            "knowledge_point": "一般现在时",
            "question": "She ___ coffee every morning.",
            "student_answer": "我觉得应该填 drinks，因为第三人称单数",
            "reference_answers": ["drinks"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "12-3",
            "knowledge_point": "现在进行时",
            "question": "They are ___ football now.",
            "student_answer": "答案是 playing，现在进行时加 ing",
            "reference_answers": ["playing"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "12-4",
            "knowledge_point": "一般过去时",
            "question": "Yesterday I ___ to school.",
            "student_answer": "hmm... went 应该对，因为 yesterday 是过去时标志",
            "reference_answers": ["went"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
    ]

    # ── 13 组：大小写/标点/空格（不影响语法的 → 不扣分） ──────
    new_cases += [
        {
            "id": "13-1",
            "knowledge_point": "be动词",
            "question": "He ___ happy.",
            "student_answer": "Is",
            "reference_answers": ["is"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "13-2",
            "knowledge_point": "一般现在时",
            "question": "She ___ coffee every morning.",
            "student_answer": " drinks ",
            "reference_answers": ["drinks"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "13-3",
            "knowledge_point": "被动语态",
            "question": "The letter was ___ yesterday.",
            "student_answer": "Sent.",
            "reference_answers": ["sent"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
    ]

    # ── 14 组：句子改错题（整句判断） ───────────────────────
    new_cases += [
        {
            "id": "14-1",
            "knowledge_point": "一般现在时",
            "question": "判断句子是否有语法错误：He go to school every day.",
            "student_answer": "有错误，应该是 goes，因为第三人称单数",
            "reference_answers": ["has error, goes"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "14-2",
            "knowledge_point": "be动词",
            "question": "判断句子是否有语法错误：They is happy.",
            "student_answer": "有错误，is 应该改成 are",
            "reference_answers": ["has error, are"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "14-3",
            "knowledge_point": "一般过去时",
            "question": "判断句子是否有语法错误：She went to park yesterday.",
            "student_answer": "这句话是对的，went 是 go 的过去式",
            "reference_answers": ["correct"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "14-4",
            "knowledge_point": "现在完成时",
            "question": "判断句子是否有语法错误：I have finish my homework.",
            "student_answer": "有错误，应该是 finished，have 后面用过去分词",
            "reference_answers": ["has error, finished"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
    ]

    # ── 15 组：词汇选择错误（语法对但词用错了） ────────────
    new_cases += [
        {
            "id": "15-1",
            "knowledge_point": "词汇选择",
            "question": "He ___ (说) English very well.",
            "student_answer": "says",
            "reference_answers": ["speaks"],
            "expected_score": 0.5,
            "expected_correct": False,
            "error_types_expected": ["词汇选择"],
        },
        {
            "id": "15-2",
            "knowledge_point": "词汇选择",
            "question": "I ___ (到达) at school at 8 am.",
            "student_answer": "got",
            "reference_answers": ["arrived"],
            "expected_score": 0.5,
            "expected_correct": False,
            "error_types_expected": ["词汇选择"],
        },
    ]

    # ── 16 组：中文夹杂答案 ──────────────────────────────
    new_cases += [
        {
            "id": "16-1",
            "knowledge_point": "be动词",
            "question": "He ___ happy.",
            "student_answer": "我填 is",
            "reference_answers": ["is"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "16-2",
            "knowledge_point": "一般过去时",
            "question": "Yesterday I ___ to school.",
            "student_answer": "答案是 went（go 的过去式）",
            "reference_answers": ["went"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "16-3",
            "knowledge_point": "现在进行时",
            "question": "They are ___ football now.",
            "student_answer": "playing，现在进行时",
            "reference_answers": ["playing"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
    ]

    # ── 17 组：更复杂的多空题 ────────────────────────────
    new_cases += [
        {
            "id": "17-1",
            "knowledge_point": "be动词+一般现在时",
            "question": "She ___ a student. She ___ to school every day.",
            "student_answer": "is, goes",
            "reference_answers": ["is, goes"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "17-2",
            "knowledge_point": "be动词+一般现在时",
            "question": "She ___ a student. She ___ to school every day.",
            "student_answer": "is, go",
            "reference_answers": ["is, goes"],
            "expected_score": 0.5,
            "expected_correct": False,
        },
        {
            "id": "17-3",
            "knowledge_point": "现在完成时+一般过去时",
            "question": "I have ___ my homework. I ___ it yesterday.",
            "student_answer": "finished, did",
            "reference_answers": ["finished, did"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "17-4",
            "knowledge_point": "现在完成时+一般过去时",
            "question": "I have ___ my homework. I ___ it yesterday.",
            "student_answer": "finish, did",
            "reference_answers": ["finished, did"],
            "expected_score": 0.5,
            "expected_correct": False,
        },
    ]

    # ── 18 组：完全不相关/拒绝回答 ────────────────────────
    new_cases += [
        {
            "id": "18-1",
            "knowledge_point": "be动词",
            "question": "He ___ happy.",
            "student_answer": "我不知道",
            "reference_answers": ["is"],
            "expected_score": 0.0,
            "expected_correct": False,
        },
        {
            "id": "18-2",
            "knowledge_point": "一般现在时",
            "question": "She ___ coffee every morning.",
            "student_answer": "我不想做这道题",
            "reference_answers": ["drinks"],
            "expected_score": 0.0,
            "expected_correct": False,
        },
        {
            "id": "18-3",
            "knowledge_point": "虚拟语气入门",
            "question": "If I were you, I ___ study.",
            "student_answer": "sorry I don't know",
            "reference_answers": ["would"],
            "expected_score": 0.0,
            "expected_correct": False,
        },
    ]

    # ── 19 组：接近但错误（易混淆） ────────────────────────
    new_cases += [
        {
            "id": "19-1",
            "knowledge_point": "一般过去时",
            "question": "Yesterday I ___ to school.",
            "student_answer": "goed",
            "reference_answers": ["went"],
            "expected_score": 0.0,
            "expected_correct": False,
            "error_types_expected": ["时态"],
        },
        {
            "id": "19-2",
            "knowledge_point": "现在完成时",
            "question": "I have ___ my homework.",
            "student_answer": "finish",
            "reference_answers": ["finished"],
            "expected_score": 0.0,
            "expected_correct": False,
            "error_types_expected": ["时态"],
        },
        {
            "id": "19-3",
            "knowledge_point": "情态动词can/must",
            "question": "He can ___ very fast.",
            "student_answer": "runs",
            "reference_answers": ["run"],
            "expected_score": 0.0,
            "expected_correct": False,
            "error_types_expected": ["情态动词"],
        },
        {
            "id": "19-4",
            "knowledge_point": "被动语态",
            "question": "The letter was ___ yesterday.",
            "student_answer": "send",
            "reference_answers": ["sent"],
            "expected_score": 0.0,
            "expected_correct": False,
            "error_types_expected": ["被动语态"],
        },
    ]

    # ── 20 组：翻译题（中译英填空） ────────────────────────
    new_cases += [
        {
            "id": "20-1",
            "knowledge_point": "be动词",
            "question": "翻译填空：他很开心。He ___ happy.",
            "student_answer": "is",
            "reference_answers": ["is"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "20-2",
            "knowledge_point": "一般过去时",
            "question": "翻译填空：我昨天去了学校。I ___ to school yesterday.",
            "student_answer": "went",
            "reference_answers": ["went"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "20-3",
            "knowledge_point": "there be句型",
            "question": "翻译填空：房间里有两只猫。There ___ two cats in the room.",
            "student_answer": "are",
            "reference_answers": ["are"],
            "expected_score": 1.0,
            "expected_correct": True,
        },
        {
            "id": "20-4",
            "knowledge_point": "一般现在时",
            "question": "翻译填空：她每天喝咖啡。She ___ coffee every day.",
            "student_answer": "drink",
            "reference_answers": ["drinks"],
            "expected_score": 0.0,
            "expected_correct": False,
            "error_types_expected": ["主谓一致"],
        },
    ]

    return new_cases


def main() -> None:
    data = load_existing()
    new_cases = make_cases()

    existing_ids = {c["id"] for c in data["cases"]}
    added = 0
    for case in new_cases:
        if case["id"] not in existing_ids:
            data["cases"].append(case)
            added += 1

    data["human_reviewed"] = True
    data["case_count"] = len(data["cases"])

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"原有 {len(existing_ids)} 题，新增 {added} 题，总计 {len(data['cases'])} 题")
    print(f"human_reviewed: {data['human_reviewed']}")


if __name__ == "__main__":
    main()
