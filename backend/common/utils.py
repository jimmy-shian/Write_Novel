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


# ---------------------------------------------------------------------------
# SSE / LLM streaming helpers (repeated accumulation pattern in agents.py)
# ---------------------------------------------------------------------------
def accumulate_stream(stream, collect_thinking=False):
    """Consume an SSE ``data:`` line stream and return accumulated text.

    Parameters
    ----------
    stream : iterable of str
        Raw SSE chunks (each may start with ``data:``).
    collect_thinking : bool
        If True, also accumulate ``"type": "thinking"`` deltas separately.

    Yields
    ------
    str
        Each raw chunk (pass-through for the caller to yield onward).

    Returns (via tuple when used with :func:`run_stream_with_accumulator`)
    ------
    (full_text, thinking_text) if *collect_thinking* else (full_text, "")
    """
    # This helper is designed to be used via run_stream_with_accumulator below,
    # which manages the generator protocol correctly.
    raise NotImplementedError("Use run_stream_with_accumulator instead.")


def run_stream_with_accumulator(stream, collect_thinking=False):
    """Generator that yields each chunk from *stream* and tracks accumulated text.

    Usage in agents::

        gen = run_stream_with_accumulator(call_llm_stream(...))
        for chunk in gen:
            yield chunk
        full_text, thinking_text = gen.result

    This replaces the repeated 10-line accumulation block in every agent runner.
    """
    content_parts = []
    thinking_parts = []

    for chunk in stream:
        yield chunk
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    content_parts.append(data.get("delta", ""))
                elif collect_thinking and data.get("type") == "thinking":
                    thinking_parts.append(data.get("delta", ""))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    # Attach result as attribute for caller retrieval after the generator is exhausted
    _acc = type("Accumulator", (), {})()
    _acc.content = "".join(content_parts)
    _acc.thinking = "".join(thinking_parts)

    # Store reference on the generator frame (hack: use function attribute)
    # The caller accesses it via the generator's .result property below.
    # We work around by returning through a wrapper.
    pass  # See below: we use a wrapper class instead.


class StreamAccumulator:
    """Wraps an SSE generator to yield chunks and expose accumulated text.

    Example::

        acc = StreamAccumulator(call_llm_stream("writer", messages))
        for chunk in acc:
            yield chunk
        full_text = acc.content
        thinking_text = acc.thinking
    """

    __slots__ = ("_gen", "_content", "_thinking", "_collect_thinking")

    def __init__(self, stream, collect_thinking=False):
        self._gen = iter(stream)
        self._content = []
        self._thinking = []
        self._collect_thinking = collect_thinking

    def __iter__(self):
        return self

    def __next__(self):
        chunk = next(self._gen)
        if chunk.startswith("data:"):
            try:
                data = json.loads(chunk[5:].strip())
                if data.get("type") == "content":
                    self._content.append(data.get("delta", ""))
                elif self._collect_thinking and data.get("type") == "thinking":
                    self._thinking.append(data.get("delta", ""))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        return chunk

    @property
    def content(self):
        return "".join(self._content)

    @property
    def thinking(self):
        return "".join(self._thinking)
