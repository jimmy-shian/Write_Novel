"""Stage-specific handler wrappers for unified generation-task routing."""

from __future__ import annotations

def resolve_handler_prompt(task, default_instruction: str = "") -> str:
    """
    智能解析並拼接 Handler 層的提示詞，避免 task.instruction 覆蓋 user_prompt 或 pipeline_prompt。
    """
    from backend import persistence as db

    user_prompt = (task.user_prompt or getattr(task, "prompt", None) or "").strip()
    instruction = (task.instruction or "").strip()
    hint = (task.hint or "").strip()

    # 只有當使用者完全未提供任何自訂提示詞或指示時，才嘗試讀取小說的 pipeline_prompt (大綱靈感)
    if not user_prompt and not instruction and getattr(task, "novel_id", None):
        try:
            novel = db.get_novel(task.novel_id)
            if novel and novel.get("pipeline_prompt"):
                user_prompt = (novel.get("pipeline_prompt") or "").strip()
        except Exception:
            pass

    parts = []
    # 如果 user_prompt 和 instruction 內容相同，只保留一份
    if user_prompt and instruction and user_prompt != instruction:
        parts.append(f"【作者創作原案與要求】\n{user_prompt}")
        parts.append(f"【本階段執行目標】\n{instruction}")
    elif user_prompt:
        parts.append(user_prompt)
    elif instruction:
        parts.append(instruction)
    elif default_instruction:
        parts.append(default_instruction)

    if hint and hint not in parts and hint != user_prompt and hint != instruction:
        parts.append(f"【修改與微調指示】\n{hint}")

    return "\n\n".join(parts).strip()


from .characters_handler import run_characters_task
from .director_handler import run_director_task
from .editor_handler import run_editor_task
from .foreshadowing_handler import run_foreshadowing_task
from .volumes_handler import run_volumes_task
from .volume_skeleton_handler import run_volume_skeleton_task
from .worldview_handler import run_worldview_task
from .writer_handler import run_writer_task

HANDLER_REGISTRY = {
    "worldview": run_worldview_task,
    "characters": run_characters_task,
    "foreshadowing": run_foreshadowing_task,
    "volumes": run_volumes_task,
    "volume_skeleton": run_volume_skeleton_task,
    "writer": run_writer_task,
    "editor": run_editor_task,
    "evaluate": run_director_task,
}



