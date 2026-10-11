"""Load the project-level writing skill used by the Editor pipeline."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


_SKILL_PATH = (
    Path(__file__).resolve().parents[3]
    / "skills"
    / "editor-natural-novel-editing"
    / "SKILL.md"
)
_FRONTMATTER_SEPARATOR = "---"


def _strip_frontmatter(text: str) -> str:
    """Return the instruction body without YAML metadata."""
    normalized = text.lstrip("\ufeff")
    if not normalized.startswith(f"{_FRONTMATTER_SEPARATOR}\n"):
        return normalized.strip()

    end = normalized.find(
        f"\n{_FRONTMATTER_SEPARATOR}\n",
        len(_FRONTMATTER_SEPARATOR) + 1,
    )
    if end < 0:
        raise ValueError(f"Invalid editor writing skill frontmatter: {_SKILL_PATH}")
    return normalized[end + len(f"\n{_FRONTMATTER_SEPARATOR}\n") :].strip()


@lru_cache(maxsize=1)
def load_editor_writing_skill() -> str:
    """Load and validate the Editor writing skill from the project."""
    if not _SKILL_PATH.is_file():
        raise FileNotFoundError(f"Editor writing skill not found: {_SKILL_PATH}")

    body = _strip_frontmatter(_SKILL_PATH.read_text(encoding="utf-8"))
    if not body:
        raise ValueError(f"Editor writing skill is empty: {_SKILL_PATH}")
    return body


def format_editor_writing_skill_context() -> str:
    """Format the skill as a clearly scoped Editor-only context block."""
    return (
        "【Editor 寫作 Skill：自然小說編修】\n"
        "以下內容只規範文字表達與編修方式。Story Canon、時間線、章節劇情契約、"
        "預定事件與驗證 Gate 的硬性約束優先於本 skill。\n\n"
        f"{load_editor_writing_skill()}"
    )


__all__ = ["load_editor_writing_skill", "format_editor_writing_skill_context"]
