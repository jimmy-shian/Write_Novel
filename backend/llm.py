import requests
import json
import os
import re
from backend.db import get_agent_configs, AGENT_DEFAULTS
from dotenv import load_dotenv
import time
# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)



# --- Agent API Key Mapping from .env ---
def get_agent_api_key(agent_name):
    """Get API key from environment variables."""
    key_map = {
        "global": os.getenv("NVIDIA_API_KEY_GLOBAL"),
        "architect": os.getenv("NVIDIA_API_KEY_ARCHITECT"),
        "character": os.getenv("NVIDIA_API_KEY_CHARACTER"),
        "volumes": os.getenv("NVIDIA_API_KEY_VOLUMES") or os.getenv("NVIDIA_API_KEY_ARCHITECT"),
        "volume_skeleton": os.getenv("NVIDIA_API_KEY_VOLUME_SKELETON") or os.getenv("NVIDIA_API_KEY_PLOT"),
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
    global_default = os.getenv("MODEL_GLOBAL", "patcher-main")
    model_map = {
        "global": global_default,
        "architect": os.getenv("MODEL_ARCHITECT") or global_default,
        "character": os.getenv("MODEL_CHARACTER") or os.getenv("MODEL_STORY") or global_default,
        "volumes": os.getenv("MODEL_VOLUMES") or os.getenv("MODEL_ARCHITECT") or global_default,
        "volume_skeleton": os.getenv("MODEL_VOLUME_SKELETON") or os.getenv("MODEL_PLOT") or global_default,
        "plot": os.getenv("MODEL_PLOT") or os.getenv("MODEL_CRITIC") or global_default,
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
                # Only override model if agent doesn't have a specialized default model in .env
                if k == "model" and agent_name != "global":
                    if get_agent_model(agent_name) != get_agent_model("global"):
                        continue
                # Do not override if the agent has a specialized default that differs from global
                if agent_name != "global" and k in agent_defaults and k in AGENT_DEFAULTS["global"]:
                    if agent_defaults[k] != AGENT_DEFAULTS["global"][k]:
                        continue
                config[k] = global_cfg[k]
                
    # Override with specific agent database values if present and not empty
    if agent_cfg and agent_name != "global":
        for k in config:
            if k in agent_cfg and agent_cfg[k] not in [None, ""]:
                config[k] = agent_cfg[k]
                
    return config

def normalize_messages(messages):
    """
    Normalizes the messages list to guarantee:
    1. A single 'system' message at the very beginning (combining multiple if present).
    2. Roles strictly alternate between 'user' and 'assistant'.
    3. The first message after 'system' is always 'user'.
    """
    if not messages:
        return []
        
    system_content = []
    other_messages = []
    
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            system_content.append(content)
        else:
            other_messages.append({"role": role, "content": content})
            
    normalized = []
    system_text = "使用繁體中文 zh-TW\n"
    if system_content:
        system_text += "\n".join(system_content)
    normalized.append({"role": "system", "content": system_text})
        
    if not other_messages:
        return normalized
        
    # Merge consecutive messages of the same role
    merged_others = []
    for msg in other_messages:
        if not merged_others:
            merged_others.append(msg)
        else:
            last_msg = merged_others[-1]
            if last_msg["role"] == msg["role"]:
                last_msg["content"] = (last_msg["content"] + "\n\n" + msg["content"]).strip()
            else:
                merged_others.append(msg)
                
    # Ensure the first non-system message is 'user'
    if merged_others and merged_others[0]["role"] == "assistant":
        merged_others.insert(0, {"role": "user", "content": "請開始小說寫作、分析與指導："})
        
    normalized.extend(merged_others)
    return normalized

def call_llm_stream(agent_name, messages, custom_payload_overrides=None, stream=False, force_json=False):
    """
    Calls the LLM API using standard streaming or non-streaming.
    On JSON validation failure for structured agents (architect, character, plot, volumes, volume_skeleton),
    automatically redirects the conversation + error to the director (copilot) agent.
    Yields custom SSE formatted chunks:
    - {"type": "thinking", "delta": "..."}
    - {"type": "content", "delta": "..."}
    - {"type": "error", "message": "..."}
    - {"type": "reset"}
    - {"type": "done"}
    """
    import time
    import random
    from backend.models.parsers import extract_json_block

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
    
    normalized_msgs = normalize_messages(messages)
    print(f"[LLM PATCH] Normalized {len(messages)} messages to {len(normalized_msgs)} to guarantee alternating roles.")
    
    model_id = config["model"]
    try:
        models_config_str = os.getenv("MODELS_CONFIG", "{}")
        models_config = json.loads(models_config_str)
    except Exception:
        models_config = {}

    preset_overrides = {}
    actual_model_string = model_id

    if model_id in models_config:
        model_data = models_config[model_id]
        actual_model_string = model_data.get("model", model_id)
        preset_overrides = {k: v for k, v in model_data.items() if k not in ("name", "model")}

    if "gpt-oss" in actual_model_string and normalized_msgs and normalized_msgs[0]["role"] == "system":
        normalized_msgs[0]["content"] = "Reasoning: high\n" + normalized_msgs[0]["content"]
        
    if custom_payload_overrides:
        custom_payload_overrides = dict(custom_payload_overrides)
        if "stream" in custom_payload_overrides:
            stream = custom_payload_overrides.pop("stream")
        if "force_json" in custom_payload_overrides:
            force_json = custom_payload_overrides.pop("force_json")

    payload_base = {
        "model": actual_model_string,
        "messages": normalized_msgs,
        "max_tokens": int(config["max_tokens"]),
        "temperature": float(config["temperature"]),
        "top_p": float(config["top_p"]),
        "stream": stream,
    }
    
    if config["enable_thinking"]:
        payload_base["chat_template_kwargs"] = {"enable_thinking": True}

    if force_json and "gpt-oss" not in actual_model_string:
        payload_base["response_format"] = {"type": "json_object"}
        
    # Auto-inject preset parameters from MODELS_CONFIG
    payload_base.update(preset_overrides)
        
    if custom_payload_overrides:
        payload_base.update(custom_payload_overrides)

    # === Debug: 列印 system prompt 和 user prompt ===
    print("\n" + "=" * 80)
    print(f"【API 傳送提示詞】Agent: {agent_name} | Model ID: {model_id} | Resolved Model: {actual_model_string}")
    print("=" * 80)
    for i, msg in enumerate(normalized_msgs):
        role_label = msg.get("role", "unknown")
        content = msg.get("content", "")
        print(f"\n--- [{i}] role: {role_label} ---")
        # 解析 JSON 格式化輸出，處理換行
        try:
            parsed = json.loads(content)
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
        except (json.JSONDecodeError, TypeError):
            # 非 JSON 內容，直接顯示，處理換行
            for line in content.split("\n"):
                print(line)
    print("\n" + "=" * 80)
    print("【API 請求即將發送】", agent_name, " | ", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    print("=" * 80 + "\n")
    # ==========================================

    accumulated_content = []
    has_yielded_anything = False
    in_think_block = False
    
    try:
        base_url = config["base_url"].rstrip("/")
        if not base_url.endswith("/chat/completions"):
            base_url += "/chat/completions"
        
        if not stream:
            # Non-streaming request
            response = requests.post(
                base_url,
                headers=headers,
                json=payload_base,
                timeout=300
            )
            if response.status_code != 200:
                error_text = response.text
                try:
                    err_json = response.json()
                    error_msg = err_json.get("error", {}).get("message", error_text)
                except:
                    error_msg = error_text
                raise RuntimeError(f"HTTP Error ({response.status_code}): {error_msg}")
                
            res_json = response.json()
            choice = res_json.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content") or ""
            reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
            
            if reasoning:
                yield "data: " + json.dumps({"type": "thinking", "delta": reasoning}, ensure_ascii=False) + "\n\n"
            if content:
                accumulated_content.append(content)
                yield "data: " + json.dumps({"type": "content", "delta": content}, ensure_ascii=False) + "\n\n"
            
            # --- Validations (before yielding done) ---
            if agent_name in ["architect", "character", "plot", "volumes", "volume_skeleton"]:
                parsed_json = extract_json_block(content)
                if not parsed_json or len(parsed_json) == 0:
                    raise ValueError("JSON validation failed: LLM output is not a valid JSON structure or is empty.")
            
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return

        response = requests.post(
            base_url,
            headers=headers,
            json=payload_base,
            stream=True,
            timeout=300
        )
        
        if response.status_code != 200:
            error_text = response.text
            try:
                err_json = response.json()
                error_msg = err_json.get("error", {}).get("message", error_text)
            except:
                error_msg = error_text
            raise RuntimeError(f"HTTP Error ({response.status_code}): {error_msg}")
            
        try:
            line_iter = response.iter_lines()
        except Exception as e:
            print(f"[LLM] Failed to create line iterator: {e}")
            raise
        
        for line in line_iter:
            try:
                if not line:
                    continue
                    
                decoded_line = line.decode("utf-8").strip()
                
                if not decoded_line.startswith("data:"):
                    continue
                    
                data_str = decoded_line[5:].strip()
                
                if data_str == "[DONE]":
                    break
                    
                data_json = json.loads(data_str)
                choices = data_json.get("choices", [])
                if not choices:
                    continue
                    
                delta = choices[0].get("delta", {})
                
                # Check for reasoning fields (Nvidia/Nemotron reasoning stream fields)
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                content = delta.get("content") or ""
                
                if reasoning:
                    has_yielded_anything = True
                    yield "data: " + json.dumps({
                        "type": "thinking",
                        "delta": reasoning
                    }, ensure_ascii=False) + "\n\n"
                    continue
                    
                if content:
                    has_yielded_anything = True
                    
                    # Detect inline think blocks (some models use <think> tags)
                    think_start = "<think>"
                    think_end = "</think>"
                    
                    if think_start in content:
                        in_think_block = True
                        parts = content.split(think_start)
                        if parts[0]:
                            accumulated_content.append(parts[0])
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
                            accumulated_content.append(parts[1])
                            yield "data: " + json.dumps({
                                "type": "content",
                                "delta": parts[1]
                            }, ensure_ascii=False) + "\n\n"
                        continue
                        
                    if in_think_block:
                        yield "data: " + json.dumps({
                            "type": "thinking",
                            "delta": content
                        }, ensure_ascii=False) + "\n\n"
                    else:
                        accumulated_content.append(content)
                        yield "data: " + json.dumps({
                            "type": "content",
                            "delta": content
                        }, ensure_ascii=False) + "\n\n"
            except Exception as e:
                print(f"[LLM] Line processing error (non-fatal): {e}")
                continue
        
        # --- Validations (before yielding done) ---
        full_text = "".join(accumulated_content)
        
        # If JSON is expected, validate it
        if agent_name in ["architect", "character", "plot", "volumes", "volume_skeleton"]:
            parsed_json = extract_json_block(full_text)
            if not parsed_json or len(parsed_json) == 0:
                raise ValueError("JSON validation failed: LLM output is not a valid JSON structure or is empty.")
                
        # If we reached here, the call succeeded!
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        return
        
    except Exception as e:
        print(f"[AGENT ERROR] Agent '{agent_name}' failed: {e}")
        
        # For JSON-structural agents, redirect to director (copilot) with error context
        if agent_name in ["architect", "character", "plot", "volumes", "volume_skeleton"]:
            error_msg = str(e)
            failed_output = "".join(accumulated_content)
            director_content = f"【系統通知】代理人「{agent_name}」在執行創作任務時發生錯誤。錯誤訊息：\n{error_msg}"
            if failed_output.strip():
                failed_payload = {
                    "director_payload_view": "collapsed_json",
                    "payload_kind": "agent_failed_output",
                    "agent_name": agent_name,
                    "char_count": len(failed_output),
                    "data": failed_output if len(failed_output) <= 2000 else {
                        "__collapsed_text__": True,
                        "message": "代理人失敗輸出已收合為 metadata；請總監依錯誤、完整對話紀錄與後續工具結果決定是否重發指令。",
                    },
                }
                director_content += f"\n\n【該代理人的失敗輸出 JSON 收合封包】\n{json.dumps(failed_payload, ensure_ascii=False, indent=2)}"
            director_content += f"\n\n以下是該代理人的完整對話紀錄。請你（創意總監）根據這些資訊判斷下一步該如何處理。"
            
            director_msgs = [{"role": "system", "content": director_content}]
            director_msgs.extend(normalized_msgs)
            
            yield "data: " + json.dumps({"type": "reset"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "retrying", "message": f"⚠️ 代理人「{agent_name}」輸出格式異常，正在轉呈創意總監代理判斷與處理..."}, ensure_ascii=False) + "\n\n"
            
            yield from call_llm_stream("copilot", director_msgs)
            return
        
        # For other agents, yield error + done
        if has_yielded_anything:
            yield "data: " + json.dumps({"type": "error", "message": f"API 呼叫失敗。錯誤訊息: {str(e)}"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        else:
            yield "data: " + json.dumps({"type": "error", "message": f"API 呼叫失敗。錯誤訊息: {str(e)}"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
