import json
import re

def extract_json_block(text: str) -> dict:
    """
    Robustly extracts a JSON object from response text.
    Handles markdown blocks (```json ... ```), removes inline thinking tags (<think>...</think>),
    and attempts to parse the content.
    """
    if not text:
        return {}

    # 1. Strip thinking blocks
    cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # 2. Match markdown codeblocks if they exist
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned_text, flags=re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Fallback: try finding first '{' and last '}'
    first_brace = cleaned_text.find("{")
    last_brace = cleaned_text.rfind("}")
    if first_brace != -1 and last_brace != -1:
        json_str = cleaned_text[first_brace:last_brace + 1].strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # 4. Fallback: try standard raw loads
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        pass

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
