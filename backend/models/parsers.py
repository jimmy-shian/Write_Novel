import json
import re

def _try_parse_json_with_repair(json_str: str) -> dict:
    """Attempts to parse JSON, and if it fails, tries to close open brackets/braces."""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # Very simple repair for truncated generation
    for suffix in ["]}", "}", "]}", "]", "\"}"]:
        try:
            return json.loads(json_str + suffix)
        except json.JSONDecodeError:
            pass
            
    return None

def _unwrap_single_nested_key(parsed: any) -> any:
    if isinstance(parsed, dict) and len(parsed) == 1:
        key = list(parsed.keys())[0]
        if key.strip() == "":
            val = parsed[key]
            if isinstance(val, dict):
                return _unwrap_single_nested_key(val)
    return parsed


def _parse_last_json_value(text: str):
    decoder = json.JSONDecoder()
    last_value = None
    for match in re.finditer(r"[\{\[]", text or ""):
        candidate = text[match.start():].lstrip()
        try:
            value, _ = decoder.raw_decode(candidate)
            last_value = value
        except json.JSONDecodeError:
            repaired = _try_parse_json_with_repair(candidate)
            if repaired is not None:
                last_value = repaired
    return last_value

def extract_json_block(text: str) -> dict:
    """
    Robustly extracts a JSON object or array from response text.
    Handles markdown blocks (```json ... ```), removes inline thinking tags (<think>...</think>),
    and attempts to parse the content. Supports truncated responses.
    """
    if not text:
        return {}

    # 1. Strip thinking blocks
    cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    parsed_result = None

    # 2. Match markdown codeblocks if they exist (can be array or dict).
    # Director prompts promise that the last JSON block is authoritative; earlier
    # blocks may be examples, tool calls, or tool results.
    json_matches = list(re.finditer(r"```(?:json)?\s*([\{\[].*?)\s*```", cleaned_text, flags=re.DOTALL))
    for json_match in reversed(json_matches):
        parsed_result = _try_parse_json_with_repair(json_match.group(1).strip())
        if parsed_result is not None:
            break

    if parsed_result is None:
        # 3. Fallback: scan for the last standalone JSON value. Using first "{"
        # through last "}" breaks when Director output contains tool JSON plus
        # tool-result JSON in one transcript.
        parsed_result = _parse_last_json_value(cleaned_text)

    if parsed_result is None:
        # 4. Fallback: try standard raw loads
        parsed_result = _try_parse_json_with_repair(cleaned_text)

    if parsed_result is not None:
        return _unwrap_single_nested_key(parsed_result)

    return {}

def validate_plot_quality(plot_data: dict) -> bool:
    """
    Quality checking equation:
    Verifies that for every event in the micro plot, both 'scene' and 'consequence'
    are at least 5 characters long to ensure compliance with the strict quality engine.
    """
    if not plot_data or "events" not in plot_data:
        return False
    
    events = plot_data.get("events", [])
    if not isinstance(events, list) or len(events) == 0:
        return False

    for ev in events:
        scene = ev.get("scene", "")
        consequence = ev.get("consequence", "")
        
        if not isinstance(scene, str) or len(scene.strip()) < 5:
            return False
        if not isinstance(consequence, str) or len(consequence.strip()) < 5:
            return False

    return True
