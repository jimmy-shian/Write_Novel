# -*- coding: utf-8 -*-
"""Macro semantic stage generation handler."""

from __future__ import annotations

from typing import Any, Generator

from backend.agents.macro_semantic.runner import run_macro_semantic
from backend.generation.handlers import resolve_handler_prompt
from backend.generation.routing.schema import GenerationTaskRequest


def run_macro_semantic_task(task: GenerationTaskRequest, context: Any = None) -> Generator[str, None, None]:
    prompt = resolve_handler_prompt(task, default_instruction="請為幾何篇卷與線程填充宏觀故事主題、衝突核心與具體劇本線索")
    return run_macro_semantic(
        novel_id=task.novel_id,
        user_prompt=prompt,
        stream=task.options.stream,
        force_json=True,
    )
