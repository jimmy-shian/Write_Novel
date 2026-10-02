# -*- coding: utf-8 -*-
"""
Shared utility functions for the AI Novel Factory.

Eliminates cross-module duplication of:
- _normalize_outlines (was in diagnostics.py and director_context.py)
- _safe_filename (was in agents.py, app.py, export_novel.py)
- deep_merge_dict (was in db.py and incremental_patch_engine.py)
- SSE event helpers for LLM stream accumulation
"""

import json
import re


# ---------------------------------------------------------------------------
# Outline normalization (duplicated in diagnostics.py + director_context.py)
# ---------------------------------------------------------------------------
def normalize_outlines(plot_data):
    """
    Normalize a list of chapter outlines so every item has an integer
    ``chapter_index`` and the result is sorted by it.
    """
    chapters = plot_data.get("chapters", []) if isinstance(plot_data, dict) else []
    normalized = []
    for idx, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        item = dict(chapter)
        try:
            raw_idx = (
                item.get("chapter_index")
                or item.get("chapter")
                or item.get("chapter_number")
                or item.get("index")
                or (idx + 1)
            )
            item["chapter_index"] = int(raw_idx)
        except Exception:
            item["chapter_index"] = idx + 1
        normalized.append(item)
    normalized.sort(key=lambda c: c["chapter_index"])
    return normalized


# ---------------------------------------------------------------------------
# Filename sanitization (duplicated in agents.py, app.py, export_novel.py)
# ---------------------------------------------------------------------------
_FILENAME_RE = re.compile(r'[\\/*?:"<>|]')


def safe_filename(title, fallback="novel"):
    """Strip filesystem-unsafe characters from *title*.

    Replaces ``\\ / * ? : " < > |`` with empty string.
    Returns *fallback* when the result is empty.
    """
    if not title:
        return fallback
    cleaned = _FILENAME_RE.sub("", title)
    return cleaned or fallback


# ---------------------------------------------------------------------------
# Deep merge (duplicated in db.py + incremental_patch_engine.py)
# ---------------------------------------------------------------------------
def deep_merge_dict(base, patch):
    """Recursively merge *patch* into *base* (non-destructive).

    - ``dict`` values are merged recursively.
    - ``None`` values in *patch* are skipped (not written into result).
    - All other values in *patch* overwrite *base*.
    """
    if not isinstance(base, dict):
        base = {}
    if not isinstance(patch, dict):
        return patch
    merged = dict(base)
    for key, value in patch.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


class StreamAccumulator:
    """Wraps an SSE generator to yield chunks and expose accumulated text.

    Example::

        acc = StreamAccumulator(call_llm_stream("writer", messages))
        for chunk in acc:
            yield chunk
        full_text = acc.content
        thinking_text = acc.thinking
    """

    __slots__ = ("_gen", "_content", "_thinking", "_collect_thinking", "_error", "_finish_reason")

    def __init__(self, stream, collect_thinking=False):
        self._gen = iter(stream)
        self._content = []
        self._thinking = []
        self._collect_thinking = collect_thinking
        self._error = None
        self._finish_reason = None

    def __iter__(self):
        return self

    def __next__(self):
        chunk = next(self._gen)
        if isinstance(chunk, str) and chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    self._content.append(data.get("delta", ""))
                elif self._collect_thinking and data.get("type") == "thinking":
                    self._thinking.append(data.get("delta", ""))
                elif data.get("type") == "error":
                    self._error = data.get("message") or "LLM API Error"
                if data.get("finish_reason"):
                    self._finish_reason = data["finish_reason"]
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        elif isinstance(chunk, dict):
            if "text" in chunk:
                self._content.append(str(chunk["text"]))
            elif "delta" in chunk:
                self._content.append(str(chunk["delta"]))
            elif "content" in chunk:
                self._content.append(str(chunk["content"]))
            if chunk.get("type") == "error":
                self._error = chunk.get("message") or "LLM API Error"
            if chunk.get("finish_reason"):
                self._finish_reason = chunk["finish_reason"]
        return chunk

    @property
    def content(self):
        return "".join(self._content)

    @property
    def thinking(self):
        return "".join(self._thinking)

    @property
    def error(self):
        return self._error

    @property
    def finish_reason(self):
        return self._finish_reason
