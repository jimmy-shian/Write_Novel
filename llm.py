import requests
import json
import os
import re
from db import get_agent_configs

def get_config_for_agent(agent_name):
    """
    Fetches the configuration for a specific agent.
    If the agent's API key is empty, falls back to the 'global' configuration.
    If 'global' API key is also empty, checks the environment variable.
    """
    configs = get_agent_configs()
    
    agent_cfg = configs.get(agent_name)
    global_cfg = configs.get("global")
    
    # Base fallback logic
    config = {
        "api_key": "",
        "base_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model": "qwen/qwen3.5-122b-a10b",
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 4096,
        "enable_thinking": 1
    }
    
    # Populate with global values first
    if global_cfg:
        for k in config:
            if k in global_cfg and global_cfg[k] not in [None, ""]:
                config[k] = global_cfg[k]
                
    # Override with specific agent values if present and not empty
    if agent_cfg and agent_name != "global":
        for k in config:
            if k in agent_cfg and agent_cfg[k] not in [None, ""]:
                config[k] = agent_cfg[k]
                
    # Environment fallback if still empty
    if not config["api_key"]:
        config["api_key"] = os.environ.get("NVIDIA_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        
    return config

def call_llm_stream(agent_name, messages, custom_payload_overrides=None):
    """
    Calls the LLM API using standard streaming and yields custom SSE formatted chunks.
    Yielded structure:
    - {"type": "thinking", "delta": "..."}
    - {"type": "content", "delta": "..."}
    - {"type": "error", "message": "..."}
    - {"type": "done"}
    """
    config = get_config_for_agent(agent_name)
    
    if not config["api_key"]:
        yield "data: " + json.dumps({
            "type": "error", 
            "message": f"API Key for agent '{agent_name}' (or Global) is not set. Please set it in Settings."
        }, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        return
        
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }
    
    payload = {
        "model": config["model"],
        "messages": messages,
        "max_tokens": int(config["max_tokens"]),
        "temperature": float(config["temperature"]),
        "top_p": float(config["top_p"]),
        "stream": True
    }
    
    if config["enable_thinking"]:
        payload["chat_template_kwargs"] = {"enable_thinking": True}
        
    if custom_payload_overrides:
        payload.update(custom_payload_overrides)
        
    try:
        response = requests.post(
            config["base_url"],
            headers=headers,
            json=payload,
            stream=True,
            timeout=60
        )
        
        if response.status_code != 200:
            error_text = response.text
            try:
                err_json = response.json()
                error_msg = err_json.get("error", {}).get("message", error_text)
            except:
                error_msg = error_text
                
            yield "data: " + json.dumps({
                "type": "error",
                "message": f"API Error ({response.status_code}): {error_msg}"
            }, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
            return
            
        in_think_block = False
        
        for line in response.iter_lines():
            if not line:
                continue
                
            decoded_line = line.decode("utf-8").strip()
            
            if decoded_line.startswith("data:"):
                data_str = decoded_line[5:].strip()
                
                if data_str == "[DONE]":
                    break
                    
                try:
                    data_json = json.loads(data_str)
                    choices = data_json.get("choices", [])
                    if not choices:
                        continue
                        
                    delta = choices[0].get("delta", {})
                    
                    # 1. Check for thinking model reasoning field
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    content = delta.get("content") or ""
                    
                    if reasoning:
                        yield "data: " + json.dumps({
                            "type": "thinking",
                            "delta": reasoning
                        }, ensure_ascii=False) + "\n\n"
                        continue
                        
                    if content:
                        # Some models put think blocks directly inside content, e.g. <think>...</think>
                        # Let's detect these inline tags
                        if "<think>" in content:
                            in_think_block = True
                            parts = content.split("<think>")
                            if parts[0]:
                                yield "data: " + json.dumps({
                                    "type": "content",
                                    "delta": parts[0]
                                }, ensure_ascii=False) + "\n\n"
                            if len(parts) > 1 and parts[1]:
                                yield "data: " + json.dumps({
                                    "type": "thinking",
                                    "delta": parts[1]
                                }, ensure_ascii=False) + "\n\n"
                            continue
                            
                        if "</think>" in content:
                            in_think_block = False
                            parts = content.split("</think>")
                            if parts[0]:
                                yield "data: " + json.dumps({
                                    "type": "thinking",
                                    "delta": parts[0]
                                }, ensure_ascii=False) + "\n\n"
                            if len(parts) > 1 and parts[1]:
                                yield "data: " + json.dumps({
                                    "type": "content",
                                    "delta": parts[1]
                                }, ensure_ascii=False) + "\n\n"
                            continue
                            
                        # Standard stream forwarding
                        yield "data: " + json.dumps({
                            "type": "thinking" if in_think_block else "content",
                            "delta": content
                        }, ensure_ascii=False) + "\n\n"
                        
                except Exception as e:
                    # Ignore JSON parsing errors for weird lines
                    continue
                    
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        
    except requests.exceptions.RequestException as e:
        yield "data: " + json.dumps({
            "type": "error",
            "message": f"Request Failed: {str(e)}"
        }, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"
