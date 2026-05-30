import sys
import os
import json

# Add parent directory to path so we can import llm.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import call_llm_stream
from models.parsers import extract_json_block

def call_llm_sync(agent_name: str, messages: list) -> str:
    """
    Calls call_llm_stream synchronously and aggregates the entire content
    returned by the stream, ignoring thinking steps.
    """
    stream = call_llm_stream(agent_name, messages)
    full_content = []
    
    for chunk in stream:
        if chunk.startswith("data:"):
            data_str = chunk[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                data_json = json.loads(data_str)
                t = data_json.get("type")
                delta = data_json.get("delta", "")
                
                # Aggregate only non-thinking content for standard use cases
                if t == "content":
                    full_content.append(delta)
                elif t == "error":
                    print(f"[LLM Client Error] {data_json.get('message')}")
            except:
                continue
                
    return "".join(full_content)

def call_llm_json(agent_name: str, messages: list) -> dict:
    """
    Helper to synchronously call the LLM and parse the output into a dictionary.
    """
    raw_text = call_llm_sync(agent_name, messages)
    return extract_json_block(raw_text)
