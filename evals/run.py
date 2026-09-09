"""Seed benchmark: deterministic baseline or explicitly requested live isolated grading."""

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field

DEFAULT_DATA = Path(__file__).parent / "data" / "assessment_seed.json"


class Case(BaseModel):
    id: str
    knowledge_point: str
    question: str
    student_answer: str
    reference_answers: list[str] = Field(min_length=1)
    expected_score: float = Field(ge=0, le=1)
    expected_correct: bool


def load_cases(path: Path) -> list[Case]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    cases = [Case.model_validate(item) for item in data["cases"]]
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Duplicate case IDs")
    return cases


def run(mode: str, cases: list[Case]) -> dict:
    agent = None
    prompt_hash = None
    if mode == "live":
        from langgraph.prebuilt import create_react_agent

        from language_tutor.agents.assessor_agent import ASSESSMENT_PROMPT
        from language_tutor.llm.client import get_assessor_llm

        prompt = ASSESSMENT_PROMPT + "\n本次是独立题库评测，不查询学生历史。"
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        agent = create_react_agent(get_assessor_llm(), tools=[], prompt=prompt)
    results = []
    for case in cases:
        started = perf_counter()
        try:
            if mode == "exact-match":
                correct = case.student_answer.strip().casefold() in {
                    answer.casefold() for answer in case.reference_answers
                }
                score = 1.0 if correct else 0.0
            else:
                from language_tutor.llm.outputs import AssessmentOutput, invoke_validated

                output = invoke_validated(
                    agent,
                    [
                        (
                            "user",
                            json.dumps(
                                {
                                    "knowledge_point": case.knowledge_point,
                                    "question": case.question,
                                    "student_answer": case.student_answer,
                                },
                                ensure_ascii=False,
                            ),
                        )
                    ],
                    AssessmentOutput,
                    "benchmark",
                )
                correct, score = output.is_correct, output.score
            results.append(
                {
                    "id": case.id,
                    "valid": True,
                    "correct": correct,
                    "score": score,
                    "expected_correct": case.expected_correct,
                    "expected_score": case.expected_score,
                    "elapsed_ms": (perf_counter() - started) * 1000,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": case.id,
                    "valid": False,
                    "error_type": type(exc).__name__,
                    "elapsed_ms": (perf_counter() - started) * 1000,
                }
            )
    valid = [row for row in results if row["valid"]]
    latencies = sorted(row["elapsed_ms"] for row in results)
    from language_tutor import config

    return {
        "mode": mode,
        "dataset_status": "synthetic seed; human review pending",
        "scope": "isolated grading, no history retrieval",
        "model": config.LLM_MODEL if mode == "live" else None,
        "prompt_sha256": prompt_hash,
        "case_count": len(cases),
        "valid_output_rate": len(valid) / len(cases) if cases else 0,
        "correctness_accuracy": sum(row["correct"] == row["expected_correct"] for row in valid)
        / len(cases)
        if cases
        else 0,
        "score_mae_valid_only": statistics.mean(
            abs(row["score"] - row["expected_score"]) for row in valid
        )
        if valid
        else None,
        "latency_p50_ms": statistics.median(latencies) if latencies else None,
        "latency_p95_ms": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
        if latencies
        else None,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["exact-match", "live"], default="exact-match")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=Path("evals/results/baseline.json"))
    args = parser.parse_args()
    report = run(args.mode, load_cases(args.data))
    report["dataset_sha256"] = hashlib.sha256(args.data.read_bytes()).hexdigest()
    report["created_at"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{report['case_count']} cases; mode={args.mode}; report={args.output}")


if __name__ == "__main__":
    main()
