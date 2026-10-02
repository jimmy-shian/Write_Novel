import sys
import os

# Add parent directory to path so we can import llm.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.common.llm import call_llm_stream
from backend.common.utils import StreamAccumulator
from backend.models.parsers import extract_json_block

def call_llm_sync(agent_name: str, messages: list) -> str:
    """
    Calls call_llm_stream synchronously and aggregates the entire content
    returned by the stream, ignoring thinking steps.
    """
    acc = StreamAccumulator(call_llm_stream(agent_name, messages))
    for _ in acc:
        pass
    if acc.error:
        print(f"[LLM Client Error] {acc.error}")
    return acc.content

def call_llm_json(agent_name: str, messages: list) -> dict:
    """
    Helper to synchronously call the LLM and parse the output into a dictionary.
    """
    raw_text = call_llm_sync(agent_name, messages)
    return extract_json_block(raw_text)
