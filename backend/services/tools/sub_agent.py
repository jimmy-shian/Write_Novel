# -*- coding: utf-8 -*-
import json
import time
from typing import Dict, Any

from backend.llm import call_llm_stream
from backend.utils import StreamAccumulator
from backend.models.parsers import extract_json_block

MAX_RETRIES = 10

class SubAgentGenerator:
    """包裝子代理人執行的生成器，以便外部獲取最終解析結果"""
    def __init__(self, gen):
        self.gen = gen
        self.result = None

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self.gen)
        except StopIteration as e:
            self.result = e.value
            raise

def invoke_sub_agent(
    agent_name: str,
    task_description: str,
    context: Dict[str, Any],
    novel_id: str,
    stream: bool = True,
    force_json: bool = False,
    max_retries: int = MAX_RETRIES,
):
    """
    [Tool 1] 總監呼叫其他代理人
    支援自動 retry，最大 10 次，若格式錯誤則退回重新呼叫
    """
    def _run():
        from backend.prompts.prompt_builder import build_director_sub_agent_messages

        retries = 0
        last_error = ""

        while retries < max_retries:
            retries += 1
            try:
                messages = build_director_sub_agent_messages(
                    agent_name, task_description, context,
                    retry_hint=last_error if last_error else None,
                    retry_count=retries,
                )
                llm_stream = call_llm_stream(agent_name, messages, stream=stream, force_json=force_json)
                acc = StreamAccumulator(llm_stream)
                for chunk in acc:
                    yield chunk

                full_text = acc.content
                parsed = extract_json_block(full_text)
                if parsed:
                    return {
                        "success": True,
                        "result": parsed,
                        "agent_name": agent_name,
                        "retries_used": retries,
                    }

                last_error = "JSON block extraction failed, raw output payload: " + json.dumps({
                    "director_payload_view": "collapsed_json",
                    "payload_kind": "sub_agent_invalid_json_output",
                    "char_count": len(full_text or ""),
                    "data": full_text if len(full_text or "") <= 800 else {
                        "__collapsed_text__": True,
                        "message": "子代理人輸出無法解析，原文已收合；請依錯誤重新輸出合法 JSON。",
                    },
                }, ensure_ascii=False)
                time.sleep(1)

            except Exception as e:
                last_error = str(e)
                time.sleep(min(2 ** (retries - 1), 30))

        return {
            "success": False,
            "error": last_error,
            "agent_name": agent_name,
            "retries_used": retries,
        }

    return SubAgentGenerator(_run())
