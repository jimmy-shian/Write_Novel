# -*- coding: utf-8 -*-
"""
backend.services.retry_handler 單元測試：
- json_format_validator
- RetryContext 狀態機（紀錄、收合、退避）
- execute_with_retry：成功即回、失敗重試、注入 feedback、達上限停止
"""
import json

from backend.services.retry_handler import (
    RetryContext,
    json_format_validator,
    execute_with_retry,
)


def _sse(delta: str) -> str:
    return f"data: {json.dumps({'type': 'content', 'delta': delta}, ensure_ascii=False)}\n\n"


def _drain(gen):
    """消耗 SSE 產生器，回傳 (chunks, return_value)。"""
    chunks = []
    while True:
        try:
            chunks.append(next(gen))
        except StopIteration as stop:
            return chunks, stop.value


def test_json_format_validator():
    ok, err = json_format_validator('```json\n{"a": 1}\n```')
    assert ok is True and err == ""

    ok, err = json_format_validator("[1, 2, 3]")
    assert ok is True

    ok, err = json_format_validator("這不是 JSON")
    assert ok is False and err


def test_retry_context_records_and_backoff():
    ctx = RetryContext(max_retries=3)
    assert ctx.remaining == 3

    ctx.record_attempt("short output", "格式錯誤")
    assert ctx.attempt == 1
    assert ctx.errors == ["格式錯誤"]
    assert ctx.remaining == 2
    # 短輸出原樣保留
    assert ctx.accumulated_outputs[0]["data"] == "short output"
    assert ctx.backoff_seconds() == 1.0

    # 長輸出應被收合為 collapsed payload
    ctx.record_attempt("x" * 600, "")
    assert ctx.accumulated_outputs[1]["data"]["__collapsed_text__"] is True
    assert ctx.backoff_seconds() == 2.0

    # 退避上限 60 秒
    ctx.attempt = 10
    assert ctx.backoff_seconds() == 60.0
    assert ctx.remaining == 0


def test_execute_with_retry_success_first_attempt(monkeypatch):
    import backend.services.retry_handler as rh

    def fake_stream(agent_name, messages):
        yield _sse('```json\n{"ok": true}\n```')

    monkeypatch.setattr(rh, "call_llm_stream", fake_stream)

    chunks, (success, output, err) = _drain(
        execute_with_retry("writer", [], json_format_validator, "novel_x")
    )
    assert success is True
    assert '"ok"' in output
    assert err == ""
    assert len(chunks) == 1


def test_execute_with_retry_retries_then_succeeds(monkeypatch):
    import backend.services.retry_handler as rh

    calls = {"n": 0}
    retries = []

    def fake_stream(agent_name, messages):
        calls["n"] += 1
        if calls["n"] == 2:
            # 第二次呼叫必須已注入 retry feedback
            assert any(
                isinstance(m, dict) and "系統回報" in m.get("content", "")
                for m in messages
            )
            yield _sse('```json\n{"ok": true}\n```')
        else:
            yield _sse("不是 JSON 的輸出")

    monkeypatch.setattr(rh, "call_llm_stream", fake_stream)
    monkeypatch.setattr("backend.services.retry_handler.time.sleep", lambda s: None)

    chunks, (success, output, err) = _drain(
        execute_with_retry(
            "writer", [{"role": "user", "content": "hi"}],
            json_format_validator, "novel_x",
            max_retries=3,
            on_retry=lambda a, e: retries.append((a, e)),
        )
    )
    assert success is True
    assert calls["n"] == 2
    assert len(retries) == 1
    assert retries[0][0] == 1 and retries[0][1]


def test_execute_with_retry_stops_at_max_retries(monkeypatch):
    import backend.services.retry_handler as rh

    calls = {"n": 0}

    def fake_stream(agent_name, messages):
        calls["n"] += 1
        yield _sse("永遠不是 JSON")

    monkeypatch.setattr(rh, "call_llm_stream", fake_stream)
    monkeypatch.setattr("backend.services.retry_handler.time.sleep", lambda s: None)

    chunks, (success, output, err) = _drain(
        execute_with_retry("writer", [], json_format_validator, "novel_x", max_retries=2)
    )
    assert success is False
    assert calls["n"] == 2
    assert "最大重試次數" in err