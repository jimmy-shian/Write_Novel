import requests
import json
import os
import re
import sys
import types
from collections.abc import Mapping
from backend.persistence import get_agent_configs, AGENT_DEFAULTS
from dotenv import load_dotenv
import time


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)


# --- Agent API Key Mapping from .env & Space Secrets ---
def get_agent_api_key(agent_name):
    """Get API key from environment variables (including Hugging Face Space Secrets)."""
    global_fallback = (
        os.getenv("NVIDIA_API_KEY_GLOBAL")
        or os.getenv("GLOBAL_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("API_KEY")
        or ""
    )
    key_map = {
        "global": global_fallback,
        "architect": os.getenv("NVIDIA_API_KEY_ARCHITECT") or global_fallback,
        "character": os.getenv("NVIDIA_API_KEY_CHARACTER") or global_fallback,
        "volumes": os.getenv("NVIDIA_API_KEY_VOLUMES") or os.getenv("NVIDIA_API_KEY_ARCHITECT") or global_fallback,
        "volume_skeleton": os.getenv("NVIDIA_API_KEY_VOLUME_SKELETON") or os.getenv("NVIDIA_API_KEY_PLOT") or global_fallback,
        "plot": os.getenv("NVIDIA_API_KEY_PLOT") or global_fallback,
        "writer": os.getenv("NVIDIA_API_KEY_WRITER") or global_fallback,
        "editor": os.getenv("NVIDIA_API_KEY_EDITOR") or global_fallback,
        "copilot": os.getenv("NVIDIA_API_KEY_COPILOT") or global_fallback
    }
    return key_map.get(agent_name, global_fallback) or global_fallback

# --- Agent Model Mapping from .env ---
def get_agent_model(agent_name):
    """Get default model from environment variables.
    If specific agent model is not set, falls back to MODEL_GLOBAL."""
    global_default = os.getenv("MODEL_GLOBAL", "nvidia/nemotron-3-super-120b-a12b")
    model_map = {
        "global": global_default,
        "architect": os.getenv("MODEL_ARCHITECT") or global_default,
        "character": os.getenv("MODEL_CHARACTER") or os.getenv("MODEL_STORY") or global_default,
        "volumes": os.getenv("MODEL_VOLUMES") or os.getenv("MODEL_ARCHITECT") or global_default,
        "volume_skeleton": os.getenv("MODEL_VOLUME_SKELETON") or os.getenv("MODEL_PLOT") or global_default,
        "plot": os.getenv("MODEL_PLOT") or os.getenv("MODEL_CRITIC") or global_default,
        "writer": os.getenv("MODEL_WRITER") or global_default,
        "editor": os.getenv("MODEL_EDITOR") or global_default,
        "copilot": os.getenv("MODEL_COPILOT") or global_default,
    }
    return model_map.get(agent_name, global_default)

def get_agent_base_url(agent_name):
    """Get base URL for agent from environment variables."""
    global_default = os.getenv("BASE_URL_GLOBAL") or os.getenv("DEFAULT_BASE_URL", "https://integrate.api.nvidia.com/v1")
    url_map = {
        "global": global_default,
        "architect": os.getenv("BASE_URL_ARCHITECT") or global_default,
        "character": os.getenv("BASE_URL_CHARACTER") or global_default,
        "volumes": os.getenv("BASE_URL_VOLUMES") or os.getenv("BASE_URL_ARCHITECT") or global_default,
        "volume_skeleton": os.getenv("BASE_URL_VOLUME_SKELETON") or os.getenv("BASE_URL_PLOT") or global_default,
        "plot": os.getenv("BASE_URL_PLOT") or global_default,
        "writer": os.getenv("BASE_URL_WRITER") or global_default,
        "editor": os.getenv("BASE_URL_EDITOR") or global_default,
        "copilot": os.getenv("BASE_URL_COPILOT") or global_default,
    }
    return url_map.get(agent_name, global_default)

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
    Priority: Database agent config > Database global config > Baseline fallback.
    (.env is deprecated; SQLite agent_configs is the sole source of truth)
    """
    configs = get_agent_configs()
    
    agent_cfg = configs.get(agent_name) or {}
    global_cfg = configs.get("global") or {}
    
    # 1. Baseline baseline defaults (only used if DB has no record)
    config = {
        "api_key": "",
        "base_url": "http://127.0.0.1:8765/v1",
        "model": "gemini-web/pro",
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 1,
    }
    
    # 2. Inherit from global database config if present
    if global_cfg:
        for k in ("api_key", "base_url", "model", "temperature", "top_p", "max_tokens", "enable_thinking"):
            if k in global_cfg and global_cfg[k] not in [None, ""]:
                config[k] = global_cfg[k]
                
    # 3. Override with specific agent database values if present and not empty
    if agent_name != "global" and agent_cfg:
        for k in ("api_key", "base_url", "model", "temperature", "top_p", "max_tokens", "enable_thinking"):
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
        content = _message_content_to_text(msg.get("content") or "")
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


def _message_content_to_text(content):
    """Keep chat message content JSON-serializable and printable."""
    if isinstance(content, str):
        return content
    if isinstance(content, (dict, list, tuple)):
        try:
            return json.dumps(_make_json_safe(content), ensure_ascii=False, indent=2)
        except Exception:
            return str(content)
    if isinstance(content, types.GeneratorType):
        return f"[non-serializable generator omitted: {content!r}]"
    return str(content)


def _make_json_safe(value, path="$", seen=None):
    """Recursively convert accidental non-JSON values before API payload serialization."""
    if seen is None:
        seen = set()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, types.GeneratorType):
        return f"[non-serializable generator omitted at {path}: {value!r}]"

    obj_id = id(value)
    if obj_id in seen:
        return f"[circular reference omitted at {path}]"
    seen.add(obj_id)

    if isinstance(value, Mapping):
        return {
            str(key): _make_json_safe(item, f"{path}.{key}", seen)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [
            _make_json_safe(item, f"{path}[{idx}]", seen)
            for idx, item in enumerate(value)
        ]
    if callable(value):
        return f"[non-serializable callable omitted at {path}: {value!r}]"
    return str(value)


def _find_non_json_values(value, path="$", seen=None):
    if seen is None:
        seen = set()
    try:
        json.dumps(value, ensure_ascii=False)
        return []
    except TypeError:
        pass

    hits = []
    if isinstance(value, types.GeneratorType):
        return [(path, "generator", repr(value))]
    obj_id = id(value)
    if obj_id in seen:
        return []
    seen.add(obj_id)
    if isinstance(value, Mapping):
        for key, item in value.items():
            hits.extend(_find_non_json_values(item, f"{path}.{key}", seen))
    elif isinstance(value, (list, tuple, set)):
        for idx, item in enumerate(value):
            hits.extend(_find_non_json_values(item, f"{path}[{idx}]", seen))
    else:
        hits.append((path, type(value).__name__, repr(value)[:200]))
    return hits


def _safe_debug_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(str(text).encode(encoding, errors="replace").decode(encoding, errors="replace"))

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
    
    is_local_url = any(h in config.get("base_url", "") for h in ("127.0.0.1", "localhost", "0.0.0.0"))
    if not config["api_key"]:
        if is_local_url:
            config["api_key"] = "local-key"
        else:
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

    if not isinstance(stream, bool):
        print(f"[LLM PAYLOAD WARNING] Invalid stream flag type {type(stream).__name__}; coercing to False.")
        stream = False

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

    non_json_values = _find_non_json_values(payload_base)
    if non_json_values:
        print(f"[LLM PAYLOAD WARNING] Non-JSON values detected before API call: {non_json_values}")
        payload_base = _make_json_safe(payload_base)

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
            for line in str(content).split("\n"):
                _safe_debug_print(line)
    print("\n" + "=" * 80)
    print("【API 請求即將發送】", agent_name, " | Model:", actual_model_string, " | ", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
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
            if force_json and agent_name in ["architect", "character", "plot", "volumes", "volume_skeleton"]:
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
        
        # If we reached here, the call succeeded!
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        return
        
    except Exception as e:
        print(f"[AGENT ERROR] Agent '{agent_name}' failed: {e}")
        err_str = str(e)
        base_url = config.get("base_url", "")
        if ("127.0.0.1" in base_url or "localhost" in base_url) and os.getenv("SPACE_ID"):
            diag = " (⚠️ 注意：當前伺服器在雲端容器環境運行，無法直接連線至您個人電腦的本機 127.0.0.1。若欲使用本機 WebChat2Local，請於本機執行 start.bat 並使用本機頁面 http://127.0.0.1:8000)"
        elif "401" in err_str or "Unauthorized" in err_str:
            diag = " (⚠️ HTTP 401 Unauthorized：API Key 無效或未授權，請至系統設定檢查 API Key)"
        elif "410" in err_str or "Gone" in err_str:
            diag = f" (⚠️ HTTP 410 Gone：模型 [{config.get('model')}] 已下線過期停用，請至系統設定重新選取可用模型)"
        elif "404" in err_str:
            diag = f" (⚠️ HTTP 404 Not Found：找不到模型 [{config.get('model')}] 或 Base URL 路徑錯誤)"
        elif "Connection refused" in err_str or "NewConnectionError" in err_str:
            diag = f" (⚠️ 連線被拒：無法連線至 {base_url}，請確認該連接埠之服務已啟動)"
        else:
            diag = ""
        yield "data: " + json.dumps({"type": "error", "message": f"API 呼叫失敗。錯誤訊息: {err_str}{diag}"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"


def call_llm(agent_name: str, system_prompt: str, user_prompt: str, force_json: bool = False, **kwargs) -> str:
    """Synchronously executes LLM call and returns accumulated content string."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    accumulated = []
    for chunk in call_llm_stream(agent_name, messages, force_json=force_json, stream=False):
        if chunk.startswith("data: "):
            try:
                data = json.loads(chunk[6:].strip())
                if data.get("type") == "content":
                    accumulated.append(data.get("delta", ""))
                elif data.get("type") == "error":
                    print(f"[LLM ERROR] {data.get('message')}")
            except Exception:
                pass
    return "".join(accumulated)


