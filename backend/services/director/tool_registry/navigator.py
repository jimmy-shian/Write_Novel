# -*- coding: utf-8 -*-
from typing import Optional, Dict, Any

def goto_generation_position(
    target: str,
    novel_id: str,
    volume_index: Optional[int] = None,
    chapter_index: Optional[int] = None,
    reason: str = "",
    agent_prompt: str = "",
    agent_context: str = "",
    **_: Any,
) -> Dict[str, Any]:
    """
    [Tool] Convert a Director navigation intent into a normal executable decision.
    The frontend should not invent this decision; the Director chooses the target.
    """
    return {
        "success": True,
        "decision": {
            "action": "CONTINUE",
            "target": target,
            "volume_index": volume_index,
            "chapter_index": chapter_index,
            "reason": reason or f"總監指定前往 {target}",
            "hint": agent_prompt or reason or "",
            "agent_prompt": agent_prompt or "",
            "agent_context": agent_context or "",
        },
    }
