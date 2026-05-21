import requests
import json
import os
import re
from db import get_agent_configs, AGENT_DEFAULTS
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Nvidia Model Presets ---
NVIDIA_MODEL_PRESETS = {
    "google/gemma-3n-e4b-it": {
        "temperature": 0.20,
        "top_p": 0.70,
        "frequency_penalty": 0.00,
        "presence_penalty": 0.00
    },
    "nvidia/nemotron-3-super-120b-a12b": {
        "chat_template_kwargs": {"enable_thinking": True},
        "reasoning_budget": 16384
    },
    "openai/gpt-oss-120b": {},
    "minimaxai/minimax-m2.7": {},
    "mistralai/mistral-small-4-119b-2603": {
        "reasoning_effort": "high"
    },
    "stepfun-ai/step-3.5-flash": {}
}

# --- Agent API Key Mapping from .env ---
def get_agent_api_key(agent_name):
    """Get API key from environment variables."""
    key_map = {
        "global": os.getenv("NVIDIA_API_KEY_GLOBAL"),
        "architect": os.getenv("NVIDIA_API_KEY_ARCHITECT"),
        "character": os.getenv("NVIDIA_API_KEY_CHARACTER"),
        "plot": os.getenv("NVIDIA_API_KEY_PLOT"),
        "writer": os.getenv("NVIDIA_API_KEY_WRITER"),
        "editor": os.getenv("NVIDIA_API_KEY_EDITOR"),
        "copilot": os.getenv("NVIDIA_API_KEY_COPILOT")
    }
    return key_map.get(agent_name, key_map.get("global"))

# --- Agent Model Mapping from .env ---
def get_agent_model(agent_name):
    """Get default model from environment variables.
    If specific agent model is not set, falls back to MODEL_GLOBAL."""
    global_default = os.getenv("MODEL_GLOBAL", "qwen/qwen3.5-122b-a10b")
    model_map = {
        "global": global_default,
        "architect": os.getenv("MODEL_ARCHITECT") or global_default,
        "character": os.getenv("MODEL_CHARACTER") or global_default,
        "plot": os.getenv("MODEL_PLOT") or global_default,
        "writer": os.getenv("MODEL_WRITER") or global_default,
        "editor": os.getenv("MODEL_EDITOR") or global_default,
        "copilot": os.getenv("MODEL_COPILOT") or global_default
    }
    return model_map.get(agent_name, global_default)

def get_default_config():
    """Get default config values from .env."""
    return {
        "base_url": os.getenv("DEFAULT_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        "temperature": float(os.getenv("DEFAULT_TEMPERATURE", 0.7)),
        "top_p": float(os.getenv("DEFAULT_TOP_P", 0.95)),
        "max_tokens": int(os.getenv("DEFAULT_MAX_TOKENS", 16384)),
        "enable_thinking": int(os.getenv("DEFAULT_ENABLE_THINKING", 1))
    }

def get_config_for_agent(agent_name):
    """
    Fetches the configuration for a specific agent.
    Priority: Database settings > AGENT_DEFAULTS > .env globals
    """
    configs = get_agent_configs()
    
    agent_cfg = configs.get(agent_name)
    global_cfg = configs.get("global")
    
    # Get agent-specific defaults from AGENT_DEFAULTS (reads from .env for models)
    agent_defaults = AGENT_DEFAULTS.get(agent_name, AGENT_DEFAULTS["global"])
    
    # Base fallback from agent-specific AGENT_DEFAULTS
    config = {
        "api_key": get_agent_api_key(agent_name) or "",
        "base_url": agent_defaults.get("base_url", "https://integrate.api.nvidia.com/v1"),
        "model": get_agent_model(agent_name),
        "temperature": agent_defaults["temperature"],
        "top_p": agent_defaults["top_p"],
        "max_tokens": agent_defaults["max_tokens"],
        "enable_thinking": agent_defaults["enable_thinking"]
    }
    
    # Override with global database values if present and not empty
    if global_cfg:
        for k in config:
            if k in global_cfg and global_cfg[k] not in [None, ""]:
                config[k] = global_cfg[k]
                
    # Override with specific agent database values if present and not empty
    if agent_cfg and agent_name != "global":
        for k in config:
            if k in agent_cfg and agent_cfg[k] not in [None, ""]:
                config[k] = agent_cfg[k]
                
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
        
    # Auto-inject preset parameters if model matches
    model_name = config["model"]
    if model_name in NVIDIA_MODEL_PRESETS:
        payload.update(NVIDIA_MODEL_PRESETS[model_name])
        
    if custom_payload_overrides:
        payload.update(custom_payload_overrides)
        
    try:
        # Ensure proper endpoint path for NVIDIA API
        base_url = config["base_url"].rstrip("/")
        if not base_url.endswith("/chat/completions"):
            base_url += "/chat/completions"
        
        response = requests.post(
            base_url,
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
                    
                    # Check for thinking model reasoning field
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    content = delta.get("content") or ""
                    
                    if reasoning:
                        yield "data: " + json.dumps({
                            "type": "thinking",
                            "delta": reasoning
                        }, ensure_ascii=False) + "\n\n"
                        continue
                        
                    if content:
                        # Detect inline think blocks (some models use <think> tags)
                        think_start = "<think>"
                        think_end = "</think>"
                        
                        if think_start in content:
                            in_think_block = True
                            parts = content.split(think_start)
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
                            
                        if think_end in content:
                            in_think_block = False
                            parts = content.split(think_end)
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
                    # Ignore JSON parsing errors for partial chunks
                    continue
                    
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        
    except requests.exceptions.RequestException as e:
        yield "data: " + json.dumps({
            "type": "error",
            "message": f"Request Failed: {str(e)}"
        }, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"