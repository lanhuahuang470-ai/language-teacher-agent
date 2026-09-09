"""Extract a JSON object without rewriting content or miscounting quoted braces."""

import json
import re


def extract_json(raw: str) -> dict:
    if not isinstance(raw, str):
        raise ValueError("模型输出必须是文本")
    # Accept literal newlines/tabs inside model-generated JSON strings without altering content.
    candidates = [raw.strip()]
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if match:
        candidates.append(match.group(1).strip())
    for candidate in candidates:
        try:
            value = json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            raise ValueError("模型输出必须是 JSON 对象")
        return value
    # raw_decode handles nested objects, quoted braces and escaped quotes.
    start = raw.find("{")
    if start < 0:
        raise ValueError("模型输出中没有 JSON 对象")
    try:
        value, _ = json.JSONDecoder(strict=False).raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        raise ValueError("无法提取有效 JSON 对象") from exc
    return value
