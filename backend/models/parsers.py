import json
import re

def _salvage_truncated_candidate(candidate: str) -> any:
    """
    Attempts to parse a JSON candidate string.
    1. Direct json.loads
    2. Try simple bracket/brace closures
    3. Truncated array / object auto-salvage: backtrack to the last complete item ending in '}'
       and close brackets/braces.
    """
    if not candidate:
        return None

    try:
        return json.loads(candidate)
    except Exception:
        pass

    # Simple closures (e.g. if only missing closing bracket or brace)
    for suffix in ["]}", "}", "]", "\"\n}\n]", "\"\n}\n}\n]", "\"\n}\n}"]:
        try:
            return json.loads(candidate + suffix)
        except Exception:
            pass

    # Backtracking salvage for truncated arrays/objects
    idx = len(candidate)
    attempts = 0
    while attempts < 150:
        attempts += 1
        last_brace = candidate.rfind("}", 0, idx)
        if last_brace == -1:
            break
        prefix = candidate[:last_brace + 1].rstrip()
        if prefix.endswith(","):
            prefix = prefix[:-1].rstrip()

        for suffix in ["]}", "]", "}", "\n]\n}", "\n}\n}", "\n}"]:
            try:
                val = json.loads(prefix + suffix)
                return val
            except Exception:
                pass
        idx = last_brace

    return None

def _try_parse_json_with_repair(json_str: str) -> any:
    """Attempts to parse JSON with salvage fallback."""
    return _salvage_truncated_candidate(json_str)

def _unwrap_single_nested_key(parsed: any) -> any:
    if isinstance(parsed, dict) and len(parsed) == 1:
        key = list(parsed.keys())[0]
        if key.strip() == "":
            val = parsed[key]
            if isinstance(val, (dict, list)):
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
            repaired = _salvage_truncated_candidate(candidate)
            if repaired is not None:
                last_value = repaired
    return last_value

def extract_json_block(text: str) -> any:
    """
    Robustly extracts a JSON object or array from response text.
    Handles markdown blocks (```json ... ```), removes inline thinking tags (<think>...</think>),
    and attempts to parse the content. Supports truncated responses via array auto-salvage.
    """
    if not text:
        return {}

    # 1. Strip thinking blocks
    cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    candidates = []

    # 2. Extract codeblocks from last to first (authoritative block is usually the final one)
    codeblock_starts = [m.end() for m in re.finditer(r"```(?:json)?", cleaned_text, flags=re.IGNORECASE)]
    if codeblock_starts:
        for start_idx in reversed(codeblock_starts):
            snippet = cleaned_text[start_idx:]
            end_idx = snippet.find("```")
            if end_idx != -1:
                content = snippet[:end_idx].strip()
            else:
                content = snippet.strip()
            if content.startswith("{") or content.startswith("["):
                candidates.append(content)

    # 3. Fallback: extract from first '{' or '[' to end
    first_brace = cleaned_text.find("{")
    if first_brace != -1:
        candidates.append(cleaned_text[first_brace:].strip())
    first_bracket = cleaned_text.find("[")
    if first_bracket != -1:
        candidates.append(cleaned_text[first_bracket:].strip())

    # 4. Fallback: entire cleaned text
    candidates.append(cleaned_text)

    for candidate in candidates:
        parsed = _salvage_truncated_candidate(candidate)
        if parsed is not None:
            return _unwrap_single_nested_key(parsed)

    # 5. Last resort: scan for last standalone value
    last_val = _parse_last_json_value(cleaned_text)
    if last_val is not None:
        return _unwrap_single_nested_key(last_val)

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
