# -*- coding: utf-8 -*-
"""
格式錯誤重試處理機制
最大重試次數: 10 次
支援: progressive backoff, incremental prompt refinement, escalation to Director
"""

import json
import time
import traceback
from typing import Any, Callable, Dict, Generator, Optional

from backend.llm import call_llm_stream
from backend.utils import StreamAccumulator
from backend.models.parsers import extract_json_block

MAX_RETRIES = 10
BASE_BACKOFF = 1.0


class RetryContext:
    """追蹤每次 retry 的 context"""

    def __init__(self, max_retries: int = MAX_RETRIES):
        self.max_retries = max_retries
        self.attempt = 0
        self.errors: list = []
        self.accumulated_outputs: list = []
        self.escalated_to_director = False

    @property
    def remaining(self) -> int:
        return max(0, self.max_retries - self.attempt)

    def record_attempt(self, output: str, error: str):
        self.attempt += 1
        self.accumulated_outputs.append(output[:500])
        if error:
            self.errors.append(error)

    def backoff_seconds(self) -> float:
        return min(BASE_BACKOFF * (2 ** (self.attempt - 1)), 60.0)


def json_format_validator(content: str) -> tuple[bool, str]:
    """校驗 LLM output 是否為合法 JSON 格式"""
    try:
        parsed = extract_json_block(content)
        if not parsed:
            return False, "無法從輸出中提取 JSON block"
        if isinstance(parsed, (dict, list)):
            return True, ""
        return False, f"提取結果型別不符: {type(parsed).__name__}, 期望 dict/list"
    except Exception as e:
        return False, f"JSON 解析失敗: {str(e)}"


def execute_with_retry(
    agent_name: str,
    messages: list,
    validator: Callable[[str], tuple[bool, str]],
    novel_id: str,
    max_retries: int = MAX_RETRIES,
    on_retry: Optional[Callable[[int, str], None]] = None,
) -> Generator[str, None, tuple[bool, str, str]]:
    """
    執行 LLM 呼叫 + JSON 格式校驗 + auto-retry

    Yields SSE chunks, returns (success, output, error_message)
    """
    ctx = RetryContext(max_retries=max_retries)

    for attempt in range(1, max_retries + 1):
        ctx.attempt = attempt
        try:
            llm_stream = call_llm_stream(agent_name, messages)
            acc = StreamAccumulator(llm_stream)
            for chunk in acc:
                yield chunk

            full_output = acc.content

            is_valid, err_msg = validator(full_output)
            if is_valid:
                return True, full_output, ""

            ctx.record_attempt(full_output, err_msg)
            if on_retry:
                on_retry(attempt, err_msg)

            messages = _inject_retry_feedback(messages, err_msg, attempt, full_output[:300])

        except Exception as e:
            err_msg = f"呼叫異常: {str(e)}"
            ctx.record_attempt("", err_msg)
            if on_retry:
                on_retry(attempt, err_msg)

            messages = _inject_retry_feedback(messages, err_msg, attempt, "")

        backoff = ctx.backoff_seconds()
        time.sleep(backoff)

    return False, "", f"已達最大重試次數 ({max_retries})，所有嘗試均失敗"


def _inject_retry_feedback(messages: list, error: str, attempt: int, last_output: str) -> list:
    """將 retry feedback 注入 messages"""
    feedback = {
        "role": "user",
        "content": (
            f"【系統回報 - 第 {attempt} 次重試】\n"
            f"上次輸出格式不符要求：{error}\n"
            f"請嚴格遵守 JSON 輸出格式，使用 ```json ... ``` 包裹。\n"
            + (f"上次輸出節錄：{last_output}" if last_output else "")
        ),
    }
    return messages + [feedback]
