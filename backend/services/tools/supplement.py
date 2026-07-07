# -*- coding: utf-8 -*-
from backend.llm import call_llm_stream
from backend.utils import StreamAccumulator
from backend.services.tools.sub_agent import SubAgentGenerator

def supplement_content(
    stage_name: str,
    original_output: str,
    evaluation_feedback: str,
    novel_id: str,
    stream: bool = True,
    force_json: bool = False,
):
    """
    [Tool 3] 執行部分內容的補強與生成
    當 evaluate_output 回報不合格時，Director 調用此工具進行 content enhancement
    """
    def _run():
        from backend.prompts.prompt_builder import build_supplement_messages

        messages = build_supplement_messages(
            stage_name, original_output, evaluation_feedback, novel_id
        )
        llm_stream = call_llm_stream("copilot", messages, stream=stream, force_json=force_json)
        acc = StreamAccumulator(llm_stream)
        for chunk in acc:
            yield chunk

        return {
            "success": True,
            "enhanced_content": acc.content,
            "stage": stage_name,
        }

    return SubAgentGenerator(_run())
