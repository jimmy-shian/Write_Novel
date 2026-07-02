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

    # 2. Match markdown codeblocks if they exist (can be array or dict)
    json_match = re.search(r"```(?:json)?\s*([\{\[].*?)\s*```", cleaned_text, flags=re.DOTALL)
    if json_match:
        parsed = _try_parse_json_with_repair(json_match.group(1).strip())
        if parsed is not None:
            return parsed

    # 3. Fallback: try finding first '{' or '[' and last '}' or ']'
    first_brace = cleaned_text.find("{")
    first_bracket = cleaned_text.find("[")
    
    # Determine the start based on whichever comes first (and exists)
    start_idx = -1
    if first_brace != -1 and first_bracket != -1:
        start_idx = min(first_brace, first_bracket)
    else:
        start_idx = max(first_brace, first_bracket)
        
    if start_idx != -1:
        # Check matching end character based on what we started with
        if cleaned_text[start_idx] == "{":
            end_idx = cleaned_text.rfind("}")
        else:
            end_idx = cleaned_text.rfind("]")
            
        if end_idx != -1 and end_idx >= start_idx:
            json_str = cleaned_text[start_idx:end_idx + 1].strip()
            parsed = _try_parse_json_with_repair(json_str)
            if parsed is not None:
                return parsed
        else:
            # Maybe it was truncated, try parsing from start to end of string with repair
            json_str = cleaned_text[start_idx:].strip()
            parsed = _try_parse_json_with_repair(json_str)
            if parsed is not None:
                return parsed

    # 4. Fallback: try standard raw loads
    parsed = _try_parse_json_with_repair(cleaned_text)
    if parsed is not None:
        return parsed

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
