# -*- coding: utf-8 -*-
"""
Standalone HTML Novel Reader Generator.
Creates a portable, zero-dependency, single-file HTML novel reader
with local progress saving (localStorage), reading settings (font size,
themes, width, line height), TOC navigation, and responsive mobile support.
"""

import html
import json
from typing import Any, Dict, List, Optional


def escape_text(text: Optional[str]) -> str:
    """Safely escape text for HTML output."""
    if not text:
        return ""
    return html.escape(str(text))


def format_paragraphs(text: Optional[str]) -> str:
    """Format novel chapter content into clean HTML paragraphs."""
    if not text:
        return "<p class=\"reader-empty-chapter\">（本章暫無內容）</p>"
    
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraphs = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        paragraphs.append(f"<p>{html.escape(stripped)}</p>")
        
    if not paragraphs:
        return "<p class=\"reader-empty-chapter\">（本章暫無內容）</p>"
        
    return "\n".join(paragraphs)


def build_novel_html(
    novel: Dict[str, Any],
    chapters: List[Dict[str, Any]],
    wb: Optional[Dict[str, Any]] = None,
    char: Optional[Dict[str, Any]] = None,
    plot: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate a standalone single-file HTML document for the novel.
    """
    novel_id = str(novel.get("id", "novel-export"))
    title = novel.get("title", "未命名小說")
    genre = novel.get("genre", "未分類")
    style = novel.get("style", "預設風格")
    summary = novel.get("summary", "") or novel.get("pipeline_prompt", "")
    
    # Process chapter titles from plot if available
    chapter_titles = {}
    if plot and plot.get("parsed_data") and "chapters" in plot["parsed_data"]:
        for c in plot["parsed_data"]["chapters"]:
            if "chapter_index" in c:
                chapter_titles[c["chapter_index"]] = str(c.get("chapter_title", "")).strip()

    sorted_chapters = sorted(chapters or [], key=lambda x: x.get("chapter_index", 0))
    total_chapters = len(sorted_chapters)
    total_words = sum(len(ch.get("content", "") or "") for ch in sorted_chapters)
    
    # Process Worldbuilding and Character data for Lore Tab
    wb_content = wb.get("content", "") if wb else ""
    char_data = char.get("json_data", "") if char else ""
    char_list = []
    if isinstance(char_data, list):
        char_list = char_data
    elif isinstance(char_data, str) and char_data.strip():
        try:
            parsed = json.loads(char_data)
            if isinstance(parsed, list):
                char_list = parsed
            elif isinstance(parsed, dict) and "characters" in parsed:
                char_list = parsed["characters"]
        except Exception:
            char_list = []

    # Build Chapter Items for TOC and Reader Articles
    toc_items_html = []
    chapters_content_html = []

    for idx, ch in enumerate(sorted_chapters, start=1):
        ch_idx = ch.get("chapter_index", idx)
        raw_title = chapter_titles.get(ch_idx, "") or ch.get("title", "")
        if raw_title and raw_title != f"第 {ch_idx} 章" and raw_title != f"第{ch_idx}章":
            display_title = f"第 {ch_idx} 章：{raw_title}"
        else:
            display_title = f"第 {ch_idx} 章"

        ch_content = ch.get("content", "") or ""
        word_count = len(ch_content)
        formatted_body = format_paragraphs(ch_content)
        
        # TOC Item
        toc_items_html.append(f"""
            <div class="toc-item" data-chapter-index="{ch_idx}" onclick="reader.jumpToChapter({ch_idx})">
                <div class="toc-item-left">
                    <span class="toc-chapter-badge">第 {ch_idx} 章</span>
                    <span class="toc-chapter-title">{escape_text(raw_title or display_title)}</span>
                </div>
                <span class="toc-chapter-words">{word_count:,} 字</span>
            </div>
        """)
        
        # Prev/Next chapter pointers
        prev_btn = f'<button class="nav-btn prev-btn" onclick="reader.jumpToChapter({ch_idx - 1})"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"></polyline></svg> 上一章</button>' if idx > 1 else '<button class="nav-btn disabled" disabled>已是第一章</button>'
        next_btn = f'<button class="nav-btn next-btn" onclick="reader.jumpToChapter({ch_idx + 1})">下一章 <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg></button>' if idx < total_chapters else '<button class="nav-btn disabled" disabled>已是最新章節</button>'

        # Chapter Article
        chapters_content_html.append(f"""
        <article class="chapter-container" id="chapter-{ch_idx}" data-chapter-index="{ch_idx}">
            <header class="chapter-header">
                <div class="chapter-meta">
                    <span class="chapter-badge">Chapter {ch_idx}</span>
                    <span class="chapter-words-count">約 {word_count:,} 字</span>
                </div>
                <h2 class="chapter-title">{escape_text(display_title)}</h2>
            </header>
            
            <div class="chapter-body">
                {formatted_body}
            </div>
            
            <footer class="chapter-footer">
                <div class="chapter-nav-actions">
                    {prev_btn}
                    <button class="nav-btn toc-trigger-btn" onclick="reader.openDrawer('toc')">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
                        目錄
                    </button>
                    {next_btn}
                </div>
                <button class="btn-back-top-chapter" onclick="reader.scrollToTop()">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>
                    返回頂部
                </button>
            </footer>
        </article>
        """)

    # Characters Card list for Lore tab
    char_cards_html = []
    for c in char_list:
        if isinstance(c, dict):
            c_name = c.get("name", "未命名角色")
            c_role = c.get("role", "主角/配角")
            c_desc = c.get("description", "") or c.get("personality", "") or c.get("background", "")
            c_arc = c.get("arc", "") or c.get("goal", "")
            char_cards_html.append(f"""
            <div class="character-card">
                <div class="char-header">
                    <span class="char-name">{escape_text(c_name)}</span>
                    <span class="char-role-badge">{escape_text(c_role)}</span>
                </div>
                {f'<p class="char-desc">{escape_text(c_desc)}</p>' if c_desc else ''}
                {f'<div class="char-meta-row"><strong>成長弧光/目標：</strong>{escape_text(c_arc)}</div>' if c_arc else ''}
            </div>
            """)

    chapters_joined = "\n".join(chapters_content_html) if chapters_content_html else '<div class="empty-novel-notice"><p>本作品正文尚無章節內容。</p></div>'
    toc_joined = "\n".join(toc_items_html) if toc_items_html else '<p class="empty-toc">無章節目錄</p>'
    char_cards_joined = "\n".join(char_cards_html) if char_cards_html else '<p class="empty-data-text">尚無結構化角色資料</p>'

    html_content = f"""<!DOCTYPE html>
<html lang="zh-TW" data-theme="parchment" data-font="serif" data-size="24" data-width="standard" data-spacing="standard">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="icon" href="data:image/x-icon;base64,AAABAAQAEBAAAAAAIAAoBAAARgAAACAgAAAAACAAKBAAAG4EAAAwMAAAAAAgACgkAACWFAAAQEAAAAAAIAAoQAAAvjgAACgAAAAQAAAAIAAAAAEAIAAAAAAAAAQAAMQOAADEDgAAAAAAAAAAAAAfDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hg0G/x4NBv8eDQb/Hg0G/x4NBv8eDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQb/IA0H/yEOB/8gDQf/JA8I/yQPCP8hDQf/Ig4H/yEOB/8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8eDQb/LxIN/zITD/8xFA//NhcT/1soJ/9dKSn/OBgU/zMVEP8zFA//LxIN/x4NBv8fDQb/Hw0G/x8NBv8gDQb/HQwF/ywTDf9KHx3/SyAe/1onJ/9iKCn/Yikq/1YmJ/9NIiH/SyAd/y0TDf8cDAX/IA0G/x8NBv8fDQb/Hw0G/x8NBv8eDAX/aDEy/1MgIP9MFhb/ejlA/4Q9Rv9kJSn/VCIi/2szNf8eDAX/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDgf/GQoC/0EgHv9xOD//m01a/18yOP9dMTb/oFZk/30/Sf88Hhv/GgoC/yAOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x0MBf8pEAr/Oxwa/1UtMP9oV2D/WVFX/18uM/9fMTX/NxoX/xsKBP8gDQf/Hw0G/x8NBv8fDQb/Hw0G/yANBv8bCwT/OhcT/zkXEv8uDw7/i4WS/4+Hlv9PJin/UCcn/1QqLP8XCAL/IQ4H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA0H/xoLBP9FGhf/dzk//zccHf9MLTH/d0RL/1UqLP8XCAD/IQ4H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/MhQQ/x0KBf9cLTD/Vyst/y4UEv9ZLC7/HQsE/x8NB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/xwMBf8aCwT/OBkW/zkaF/8YCQL/FggA/yAOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA4H/xoKA/8aCgL/IQ4H/yEOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQf/IA0H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/KAAAACAAAABAAAAAAQAgAAAAAAAAEAAAxA4AAMQOAAAAAAAAAAAAAB8NBv8fDQb/Hw0G/x8NBv8gDQb/Hw0G/x8NBv8fDQb/IA4H/x8NBv8fDQb/IA0H/yANB/8gDQf/Hw0G/x8NBv8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQb/IA0G/yAOB/8fDQb/Hw0G/x8NB/8gDgf/IA4H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8N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Bv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8eDQb/Jg4I/y8SDf81FxT/PxsZ/0ojJf9hT1j/dHCA/357i/9eSVP/RiIk/z4gHv8+IB3/Qh4c/y4QDP8eDAX/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8cDAX/LhIN/zETDv9lKi7/332U/1gzOP88Jyz/OB8k/5dodv/al63/PRcW/zAUEP8zGRT/GwwE/yANB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA4H/xkKA/9JHBn/kjtC/zsWE/9GGxr/PRwa/yQSDP8lEgz/WSwv/2EwNP9GHh7/uWyA/1kqLf8XCAH/IA4H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/HQwF/y8SDf9GGxj/LRMN/ysTDf8/Hx3/PhoZ/z4cGv81GRX/JRAL/0giIv+/anz/XCks/xcIAf8hDgf/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/HQwF/xkKA/8dDAX/JBAK/y0QDf/BbH//vm6B/zEUEv8tFhH/HwwF/xsGAP8eCwT/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA4H/yANBv8eDQb/GAgB/1ooKf9bKCr/GAgB/x0MBP8fDQb/IA4H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDgf/GAgB/xgIAP8gDgf/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDgf/IA4H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8oAAAAMAAAAGAAAAABACAAAAAAAAAkAADEDgAAxA4AAAAAAAAAAAAAHw0G/x8NBv8gDQf/IA4H/yAOB/8fDQf/IA0G/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDQf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/Hw4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA0G/x8NBv8gDQf/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8fDQb/Hw0G/yANB/8fDQb/Hw0G/x8NBv8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA0G/yAOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/HwwG/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQf/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8eDQb/Hg0G/yANBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8N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H/84GBb/PR8c/0chIf90Nz3/fTtD/zMRDv8eDAX/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x4NBv8cCwT/MRMP/yANBv8/HBr/RR4d/0YcHP9bKzD/bFVe/1xRXP9VS1//V05i/3Vsef9dP0j/WiYs/0glJf9IJif/SyYn/x8MBv9GIiH/HQkC/x4MBf8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8cDAX/LxMO/ykQC/8uEw7/OxUS/85qfv/vmbP/YzY8/zQfIf9DLzX/Pi0x/z4dI/+wgpT/6LjO/3k9Rv8tFA//OR0a/zAXEf9CIh//GQoC/yEOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8eDQb/Iw0H/2MnKP9gJyn/PBUS/4o7RP+sVGP/TyYo/z4mJf9LLzH/SS8y/0UiIv+eYG//5p20/3s7Q/8oDwr/VCUo/1wrLv8nEAv/HQwF/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8dDAX/LxAM/5U8Qf+dQUv/NxQR/xoHAP8iCQT/SiMi/xwJAv8ZCAD/FwcA/ycQC/9TJSf/OA0L/yoPCv9XJin/y32V/8ZziP8yDgv/Hg0G/yANBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8eDQb/JQ4I/1IfHf9NHRv/NhUR/z4bGP8uFQ//KRIO/0klJf8eCAH/IgoE/0woKf8aCgT/IhAJ/zQaFv9ZJyv/4Yee/9x6jP85EhH/HQ0F/yAOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x0LBP8dCwT/GwsE/yQPCf86Ghf/QR8d/2IwNP+LR1X/jExY/1EnKP9EIyP/SSYm/zgdGv8rEQz/RBcW/0UZGP8jDQf/Hg0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8gDQb/IA0G/x4MBf8aCgP/Hw0G/1EcH//4l7H/+J24/1UiJf8nEgz/HAoE/xkJAv8dDAX/HQwE/xwLBP8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8hDgf/HQwF/yoMB/+BOUD/gjhB/ykLBv8bCwP/IQ4H/yAOB/8fDQb/IA4H/yANB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yAOB/8gCQP/IAoD/yAOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDgf/Hw4H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8MBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDgb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQf/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8fDQb/Hw0G/x8NBv8fDQb/IA4G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQf/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/KAAAAEAAAACAAAAAAQAgAAAAAAAAQAAAxA4AAMQOAAAAAAAAAAAAAB8NBv8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yANB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDgf/IA4H/yAOB/8gDQb/Hw0G/yAOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA4H/yAOB/8fDQb/Hw0G/x8NBv8gDQb/IA0G/x8NBv8fDQb/IA0G/yANB/8gDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDgf/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDgf/IA4H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA0G/x8NBv8gDgf/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA4H/yAOB/8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA4H/yAOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yAOB/8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/HwwG/x8NBv8fDQb/Hw0G/x8MBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQf/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8MBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA0H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw4H/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA0G/yANBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDgb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8MBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8MBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8MBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/HwwG/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQb/IA4G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8fDQb/GwsE/xsMBP8fDQb/IA0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8gDQb/IA0G/yANBv8gDQb/IA0G/yANB/8gDQf/IA0H/yANB/8gDQf/IA4H/yAOB/8gDgf/IA0H/yEOB/8dDAX/HwwF/zIUD/8yFBD/HwwF/xwMBf8hDgf/IA0H/yEOB/8gDgf/IA4H/yANB/8gDQf/IA4H/yAOB/8gDQf/IA0G/yANBv8gDQf/IA0G/yANBv8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8cDAT/GwsE/xsLBP8bDAT/GwsE/xoLBP8aCwP/GgsD/xkLA/8ZCgP/GQoD/xgKAv8YCgL/GAoC/xgJAv8UBwD/Jg8J/1klJP9IHRr/SR0b/1smJf8oEAr/FAgA/xgJAv8XCQL/GAoC/xgKAv8YCgL/GQoC/xkKA/8ZCgP/GgsD/xoKA/8aCgP/GwsE/xsLBP8bDAT/GwsE/x8MBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x4NBv8iDgf/NhQQ/zgUEf84FBH/ORUS/zsWEv88FxP/PRgU/z8ZFf9CGhf/RBwY/0cdGf9JHhv/TB8c/04gHv9PIR//UCEf/2csLf8nDwv/JQ4I/yYOCP8nDgv/aS0u/1EjIP9QIh//TyEf/00gHv9LHxz/SR4b/0YdGf9EGxj/QhoX/z8ZFv8+GBT/PBcT/zoVEv84FRH/OBYR/zYUEP8jDgf/Hg0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8N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Ov/Hkqf//9fx/818kP8vCgf/EQQA/1wwMv8yFBD/Vy0u/x0MBP8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IgwG/1UgH/+bQEj/dTA1/0cbGf89FRL/WiAk/20tNP9KHyD/GAkB/ysVEP8uGBT/MBkW/ywXEv80ExD/kEpX/6ldbf93NT3/ZzU5/0IdHf9gKTD/j0lW/1cmKv8dCQL/IA4H/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/HwwG/yYNB/9uKiz/qUVN/5c/Sf81Eg//GwoC/x0JAv8aCAH/WC0t/zcZFv8UBgD/HQoD/x0KA/8SBAD/SSUm/0cgIP8qBwP/JwsG/x8LBP9kKzD/yH2V//inxf+MQU7/KwwJ/x8OB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8iDQb/QxgV/20qLP9NHRz/QhoX/0MdGv83GBP/IA0F/xMFAP9ZLTD/LBQP/x4LBP8ZCQH/PyAe/1IrLf8PAwD/GQoC/x8NB/82Ghb/ZSwy/+OMpf//qsP/p1Jf/ywLCf8gDgf/IA0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yINBv8lDQf/Ig0G/xsLA/8kDwn/PxwZ/08mJv8/Hh3/MhYT/2w4Pf9EExT/Shkb/2IyNv8eCgT/MxgV/0onKP9WLjD/TSko/0IbGv9nKS7/kkdP/00cHf8mDgj/Hg0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDgf/Hg0F/xkJAv8fDAb/Oxwa/1orLf+IQE7/0H6W/9SJoP98PEb/WS4x/1IsLf82Ghj/IA0H/xcIAP8cCwP/Jw0I/ycKBv8lDgj/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/HwwG/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8MBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8gDgf/IA0G/xgJAv8jCQT/fjU+//+owv//rcn/hD5J/ygMCP8XCAD/GgoC/x8MBv8hDgf/Hw0G/x8NBv8fDgf/Hg0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8MBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQf/JA0I/0cWFv+iTVj/pE1Z/0UUFf8jDAb/IA4H/yAOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x4NBv8nDwn/MQ0K/zENCv8oDwn/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hg0G/yAOB/8hDgf/Hg0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/HwwG/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8MBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8MBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/HwwG/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/HwwG/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQf/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw4G/x8NBv8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA0G/yANBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/HwwG/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDAb/Hw0G/x8NBv8fDQb/Hw0G/x8MBv8fDQb/Hw0G/x8NB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8gDQf/IA0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA0G/yANBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANBv8gDgf/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yAOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANB/8gDQf/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yANB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/IA4H/yANBv8fDQb/Hw0G/x8NBv8fDQb/IA4H/yANBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/yAOB/8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8fDQb/Hw0G/x8NBv8="><link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>📖</text></svg>">
    <title>《{escape_text(title)}》- 便攜式離線閱讀器</title>
    <style>
        /* ==========================================================================
           CSS RESET & MODERN CSS VARIABLES (Themes & Layout)
           ========================================================================== */
        *, *::before, *::after {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        :root {{
            /* Theme Variables Default: Parchment */
            --bg-page: #f7f1e3;
            --bg-surface: #eee5d3;
            --bg-surface-trans: rgba(238, 229, 211, 0.88);
            --bg-card: #fdfbf7;
            --text-primary: #2d2926;
            --text-secondary: #6e6659;
            --text-muted: #9c9281;
            --border-color: #ded2bc;
            --border-light: rgba(142, 126, 99, 0.18);
            --accent-color: #8b5a2b;
            --accent-hover: #70441d;
            --accent-light: rgba(139, 90, 43, 0.12);
            --accent-text: #ffffff;
            --shadow-sm: 0 2px 6px rgba(45, 41, 38, 0.06);
            --shadow-md: 0 8px 20px rgba(45, 41, 38, 0.1);
            --shadow-lg: 0 16px 36px rgba(45, 41, 38, 0.16);
            --radius-sm: 6px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --radius-full: 9999px;
            
            /* Reader Dimensions */
            --reader-max-width: 840px;
            --reader-font-size: 18px;
            --reader-line-height: 1.85;
            --reader-paragraph-gap: 1.25em;
            --reader-font-family: "Noto Serif CJK TC", "Source Han Serif TC", "Songti SC", "SimSun", "PMingLiU", Georgia, serif;
            
            /* Header / Bar heights */
            --topbar-height: 48px;
            --fab-size: 48px;
        }}

        /* Theme: Eye-Care Green (護眼豆沙綠) */
        [data-theme="eyecare"] {{
            --bg-page: #eaf4ec;
            --bg-surface: #dbeadc;
            --bg-surface-trans: rgba(219, 234, 220, 0.88);
            --bg-card: #f2f8f3;
            --text-primary: #1e382b;
            --text-secondary: #4d705c;
            --text-muted: #799a86;
            --border-color: #c4dec7;
            --border-light: rgba(77, 112, 92, 0.18);
            --accent-color: #2e7d32;
            --accent-hover: #1b5e20;
            --accent-light: rgba(46, 125, 50, 0.12);
            --accent-text: #ffffff;
            --shadow-sm: 0 2px 6px rgba(30, 56, 43, 0.06);
            --shadow-md: 0 8px 20px rgba(30, 56, 43, 0.1);
            --shadow-lg: 0 16px 36px rgba(30, 56, 43, 0.16);
        }}

        /* Theme: Clean White (雅致純白) */
        [data-theme="light"] {{
            --bg-page: #f8fafc;
            --bg-surface: #ffffff;
            --bg-surface-trans: rgba(255, 255, 255, 0.9);
            --bg-card: #ffffff;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-muted: #94a3b8;
            --border-color: #e2e8f0;
            --border-light: rgba(226, 232, 240, 0.8);
            --accent-color: #2563eb;
            --accent-hover: #1d4ed8;
            --accent-light: rgba(37, 99, 235, 0.1);
            --accent-text: #ffffff;
            --shadow-sm: 0 2px 6px rgba(15, 23, 42, 0.05);
            --shadow-md: 0 8px 20px rgba(15, 23, 42, 0.08);
            --shadow-lg: 0 16px 36px rgba(15, 23, 42, 0.12);
        }}

        /* Theme: Midnight Slate (沉夜星藍) */
        [data-theme="midnight"] {{
            --bg-page: #0b1329;
            --bg-surface: #131f3f;
            --bg-surface-trans: rgba(19, 31, 63, 0.9);
            --bg-card: #17264e;
            --text-primary: #e2e8f0;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --border-color: #233562;
            --border-light: rgba(148, 163, 184, 0.14);
            --accent-color: #38bdf8;
            --accent-hover: #0ea5e9;
            --accent-light: rgba(56, 189, 248, 0.16);
            --accent-text: #0b1329;
            --shadow-sm: 0 2px 6px rgba(0, 0, 0, 0.3);
            --shadow-md: 0 8px 20px rgba(0, 0, 0, 0.4);
            --shadow-lg: 0 16px 36px rgba(0, 0, 0, 0.6);
        }}

        /* Theme: OLED Black (極致墨曜) */
        [data-theme="oled"] {{
            --bg-page: #000000;
            --bg-surface: #121212;
            --bg-surface-trans: rgba(18, 18, 18, 0.92);
            --bg-card: #181818;
            --text-primary: #d6d6d6;
            --text-secondary: #8c8c8c;
            --text-muted: #5a5a5a;
            --border-color: #272727;
            --border-light: rgba(255, 255, 255, 0.08);
            --accent-color: #eab308;
            --accent-hover: #ca8a04;
            --accent-light: rgba(234, 179, 8, 0.14);
            --accent-text: #000000;
            --shadow-sm: 0 2px 6px rgba(0, 0, 0, 0.5);
            --shadow-md: 0 8px 20px rgba(0, 0, 0, 0.7);
            --shadow-lg: 0 16px 36px rgba(0, 0, 0, 0.9);
        }}

        /* Font Family Variants */
        [data-font="serif"] {{
            --reader-font-family: "Noto Serif CJK TC", "Source Han Serif TC", "Songti SC", "SimSun", "PMingLiU", Georgia, serif;
        }}
        [data-font="sans"] {{
            --reader-font-family: system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Heiti SC", sans-serif;
        }}
        [data-font="kaiti"] {{
            --reader-font-family: "Kaiti SC", "STKaiti", "KaiTi", "DFKai-SB", "BiauKai", serif;
        }}

        /* Page Width Variants */
        [data-width="narrow"] {{
            --reader-max-width: 680px;
        }}
        [data-width="standard"] {{
            --reader-max-width: 840px;
        }}
        [data-width="wide"] {{
            --reader-max-width: 1020px;
        }}

        /* Spacing Variants */
        [data-spacing="compact"] {{
            --reader-line-height: 1.6;
            --reader-paragraph-gap: 1em;
        }}
        [data-spacing="standard"] {{
            --reader-line-height: 1.85;
            --reader-paragraph-gap: 1.3em;
        }}
        [data-spacing="loose"] {{
            --reader-line-height: 2.2;
            --reader-paragraph-gap: 1.6em;
        }}

        /* Base Body */
        html, body {{
            width: 100%;
            min-height: 100vh;
            background-color: var(--bg-page);
            color: var(--text-primary);
            font-family: var(--reader-font-family);
            font-size: var(--reader-font-size);
            line-height: var(--reader-line-height);
            transition: background-color 0.25s ease, color 0.25s ease;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            text-rendering: optimizeLegibility;
            overflow-x: hidden;
        }}

        /* Top Progress Bar */
        #top-progress-container {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 3px;
            background: transparent;
            z-index: 100;
            pointer-events: none;
        }}
        #top-progress-bar {{
            height: 100%;
            width: 0%;
            background: var(--accent-color);
            transition: width 0.1s linear;
        }}

        /* Floating Top Bar (Sticky header with book title & status) */
        .reader-top-nav {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: var(--topbar-height);
            background-color: var(--bg-surface-trans);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border-light);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 16px;
            z-index: 90;
            transform: translateY(0);
            transition: transform 0.3s ease, background-color 0.25s ease;
        }}
        .reader-top-nav.hidden-nav {{
            transform: translateY(-100%);
        }}
        .top-nav-left {{
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
        }}
        .top-book-icon {{
            color: var(--accent-color);
            display: flex;
            align-items: center;
        }}
        .top-book-title {{
            font-size: 0.9rem;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            color: var(--text-primary);
        }}
        .top-chapter-current {{
            font-size: 0.8rem;
            color: var(--text-muted);
            white-space: nowrap;
            display: none;
        }}
        @media (min-width: 640px) {{
            .top-chapter-current {{
                display: inline-block;
            }}
        }}
        .top-nav-right {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .top-action-btn {{
            background: transparent;
            border: none;
            color: var(--text-secondary);
            width: 36px;
            height: 36px;
            border-radius: var(--radius-sm);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .top-action-btn:hover {{
            background-color: var(--accent-light);
            color: var(--accent-color);
        }}
        .top-progress-text {{
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--accent-color);
            padding: 4px 8px;
            background: var(--accent-light);
            border-radius: var(--radius-full);
            font-variant-numeric: tabular-nums;
        }}

        /* Main Reader Layout */
        .reader-app {{
            width: 100%;
            min-height: 100vh;
            padding-top: calc(var(--topbar-height) + 24px);
            padding-bottom: 120px;
        }}
        .reader-content-wrapper {{
            max-width: var(--reader-max-width);
            margin: 0 auto;
            padding: 0 20px;
            transition: max-width 0.25s ease;
        }}

        /* Hero / Novel Cover Header */
        .novel-hero-header {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 32px 28px;
            margin-bottom: 40px;
            box-shadow: var(--shadow-sm);
            position: relative;
            overflow: hidden;
        }}
        .novel-hero-header::before {{
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 6px;
            height: 100%;
            background: var(--accent-color);
        }}
        .novel-title-tag {{
            display: inline-block;
            font-size: 0.8rem;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--accent-color);
            background: var(--accent-light);
            padding: 4px 12px;
            border-radius: var(--radius-full);
            margin-bottom: 14px;
        }}
        .novel-main-title {{
            font-size: 1.8rem;
            font-weight: 700;
            line-height: 1.3;
            color: var(--text-primary);
            margin-bottom: 12px;
        }}
        .novel-meta-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            font-size: 0.88rem;
            color: var(--text-secondary);
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px dashed var(--border-light);
        }}
        .novel-meta-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .novel-summary-box {{
            font-size: 0.92rem;
            line-height: 1.7;
            color: var(--text-secondary);
            background: var(--bg-surface);
            padding: 16px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border-light);
        }}
        .novel-hero-actions {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-top: 20px;
        }}
        .btn-hero {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 20px;
            border-radius: var(--radius-md);
            font-size: 0.92rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            border: 1px solid transparent;
        }}
        .btn-hero-primary {{
            background-color: var(--accent-color);
            color: var(--accent-text);
        }}
        .btn-hero-primary:hover {{
            background-color: var(--accent-hover);
            transform: translateY(-1px);
        }}
        .btn-hero-secondary {{
            background-color: var(--bg-surface);
            color: var(--text-primary);
            border-color: var(--border-color);
        }}
        .btn-hero-secondary:hover {{
            background-color: var(--accent-light);
            border-color: var(--accent-color);
            color: var(--accent-color);
        }}

        /* Chapter Article */
        .chapter-container {{
            margin-bottom: 64px;
            padding-top: 32px;
            position: relative;
            content-visibility: auto;
            contain-intrinsic-size: 0 800px;
            contain: layout style;
        }}
        .chapter-container:not(:last-child)::after {{
            content: "❖ ❖ ❖";
            display: block;
            text-align: center;
            font-size: 1.1rem;
            letter-spacing: 0.4em;
            color: var(--text-muted);
            margin: 64px 0 32px 0;
            opacity: 0.6;
        }}
        .chapter-header {{
            margin-bottom: 28px;
            padding-bottom: 16px;
            border-bottom: 2px solid var(--border-light);
        }}
        .chapter-meta {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }}
        .chapter-badge {{
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--accent-color);
        }}
        .chapter-words-count {{
            font-size: 0.8rem;
            color: var(--text-muted);
        }}
        .chapter-title {{
            font-size: 1.45rem;
            font-weight: 700;
            color: var(--text-primary);
            line-height: 1.4;
        }}
        .chapter-body {{
            font-size: var(--reader-font-size);
            line-height: var(--reader-line-height);
            color: var(--text-primary);
            letter-spacing: 0.02em;
            contain: layout style;
        }}
        .chapter-body p {{
            margin-bottom: var(--reader-paragraph-gap);
            text-indent: 2em;
            text-align: justify;
            word-break: break-word;
        }}
        .reader-empty-chapter {{
            color: var(--text-muted);
            font-style: italic;
            text-align: center !important;
            text-indent: 0 !important;
            padding: 32px 0;
        }}
        .chapter-footer {{
            margin-top: 36px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            align-items: center;
        }}
        .chapter-nav-actions {{
            display: flex;
            align-items: center;
            justify-content: center;
            flex-wrap: wrap;
            gap: 12px;
            width: 100%;
        }}
        .nav-btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            min-height: 44px;
            padding: 0 18px;
            border-radius: var(--radius-full);
            font-size: 0.88rem;
            font-weight: 500;
            background-color: var(--bg-surface);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .nav-btn:hover:not(.disabled) {{
            background-color: var(--accent-light);
            border-color: var(--accent-color);
            color: var(--accent-color);
        }}
        .nav-btn.disabled {{
            opacity: 0.45;
            cursor: not-allowed;
        }}
        .btn-back-top-chapter {{
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 0.8rem;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            cursor: pointer;
            padding: 6px 12px;
            border-radius: var(--radius-sm);
            transition: color 0.2s;
        }}
        .btn-back-top-chapter:hover {{
            color: var(--accent-color);
        }}

        /* Floating Action Menu (FAB Control Bar) */
        .fab-control-container {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 10px;
            z-index: 95;
        }}
        .fab-menu-group {{
            display: flex;
            flex-direction: column;
            gap: 10px;
            transform: scale(0.9);
            opacity: 0;
            pointer-events: none;
            transform-origin: bottom right;
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        .fab-control-container.open .fab-menu-group {{
            transform: scale(1);
            opacity: 1;
            pointer-events: auto;
        }}
        .fab-btn {{
            width: var(--fab-size);
            height: var(--fab-size);
            border-radius: var(--radius-full);
            background-color: var(--bg-surface);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            box-shadow: var(--shadow-md);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s ease;
            position: relative;
        }}
        .fab-btn:hover {{
            background-color: var(--accent-light);
            border-color: var(--accent-color);
            color: var(--accent-color);
            transform: translateY(-2px);
        }}
        .fab-btn-main {{
            background-color: var(--accent-color);
            color: var(--accent-text);
            border: none;
        }}
        .fab-btn-main:hover {{
            background-color: var(--accent-hover);
            color: var(--accent-text);
        }}
        .fab-btn-main .icon-close {{
            display: none;
        }}
        .fab-control-container.open .fab-btn-main .icon-menu {{
            display: none;
        }}
        .fab-control-container.open .fab-btn-main .icon-close {{
            display: block;
        }}
        .fab-tooltip {{
            position: absolute;
            right: calc(100% + 10px);
            top: 50%;
            transform: translateY(-50%);
            background: var(--bg-surface);
            color: var(--text-primary);
            padding: 4px 10px;
            font-size: 0.75rem;
            font-weight: 500;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border-color);
            box-shadow: var(--shadow-sm);
            white-space: nowrap;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.2s;
        }}
        .fab-btn:hover .fab-tooltip {{
            opacity: 1;
        }}

        /* Modal & Drawer Overlays */
        .reader-modal-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: rgba(0, 0, 0, 0.45);
            backdrop-filter: blur(4px);
            -webkit-backdrop-filter: blur(4px);
            z-index: 110;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.25s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .reader-modal-overlay.active {{
            opacity: 1;
            pointer-events: auto;
        }}

        /* Settings Modal (小視窗) */
        .settings-modal {{
            background-color: var(--bg-surface);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-lg);
            width: 100%;
            max-width: 440px;
            max-height: 90vh;
            overflow-y: auto;
            padding: 24px;
            transform: translateY(20px) scale(0.96);
            transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        .reader-modal-overlay.active .settings-modal {{
            transform: translateY(0) scale(1);
        }}
        .modal-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border-light);
        }}
        .modal-title {{
            font-size: 1.1rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-primary);
        }}
        .modal-close-btn {{
            background: transparent;
            border: none;
            color: var(--text-secondary);
            width: 32px;
            height: 32px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
        }}
        .modal-close-btn:hover {{
            background-color: var(--accent-light);
            color: var(--accent-color);
        }}

        /* Settings Sections */
        .setting-group {{
            margin-bottom: 20px;
        }}
        .setting-label {{
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .setting-value-badge {{
            color: var(--accent-color);
            font-weight: 700;
        }}

        /* Theme Selector */
        .theme-grid {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 8px;
        }}
        .theme-pill {{
            height: 48px;
            border-radius: var(--radius-md);
            border: 2px solid transparent;
            cursor: pointer;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 2px;
            font-size: 0.72rem;
            font-weight: 600;
            transition: all 0.2s ease;
            box-shadow: var(--shadow-sm);
            padding: 4px;
        }}
        .theme-pill.active {{
            border-color: var(--accent-color);
            transform: scale(1.04);
        }}
        .theme-parchment-pill {{ background: #f7f1e3; color: #2d2926; }}
        .theme-eyecare-pill {{ background: #eaf4ec; color: #1e382b; }}
        .theme-light-pill {{ background: #ffffff; color: #0f172a; border-color: #e2e8f0; }}
        .theme-midnight-pill {{ background: #0b1329; color: #e2e8f0; }}
        .theme-oled-pill {{ background: #000000; color: #e5e7eb; }}

        /* Segmented Buttons (Fonts, Widths, Spacing) */
        .segmented-btn-group {{
            display: flex;
            background: var(--bg-card);
            padding: 4px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border-color);
            gap: 4px;
        }}
        .segment-btn {{
            flex: 1;
            min-height: 38px;
            border: none;
            border-radius: var(--radius-sm);
            background: transparent;
            color: var(--text-secondary);
            font-size: 0.82rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .segment-btn.active {{
            background: var(--accent-color);
            color: var(--accent-text);
            font-weight: 600;
            box-shadow: var(--shadow-sm);
        }}

        /* TOC & Lore Drawer (側欄/抽屜) */
        .reader-drawer-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: rgba(0, 0, 0, 0.45);
            backdrop-filter: blur(4px);
            -webkit-backdrop-filter: blur(4px);
            z-index: 115;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.25s ease;
        }}
        .reader-drawer-overlay.active {{
            opacity: 1;
            pointer-events: auto;
        }}
        .reader-drawer {{
            position: fixed;
            top: 0;
            right: 0;
            width: 100%;
            max-width: 400px;
            height: 100%;
            background-color: var(--bg-surface);
            color: var(--text-primary);
            border-left: 1px solid var(--border-color);
            box-shadow: var(--shadow-lg);
            z-index: 120;
            transform: translateX(100%);
            transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            flex-direction: column;
        }}
        .reader-drawer-overlay.active .reader-drawer {{
            transform: translateX(0);
        }}
        .drawer-header {{
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-light);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .drawer-tabs {{
            display: flex;
            background: var(--bg-card);
            border-radius: var(--radius-md);
            padding: 4px;
            border: 1px solid var(--border-color);
            margin: 12px 20px 8px 20px;
            gap: 4px;
        }}
        .drawer-tab-btn {{
            flex: 1;
            padding: 8px;
            border: none;
            background: transparent;
            color: var(--text-secondary);
            font-size: 0.85rem;
            font-weight: 500;
            border-radius: var(--radius-sm);
            cursor: pointer;
            transition: all 0.2s;
        }}
        .drawer-tab-btn.active {{
            background: var(--accent-color);
            color: var(--accent-text);
            font-weight: 600;
        }}
        .drawer-search-box {{
            padding: 8px 20px;
            position: relative;
        }}
        .drawer-search-input {{
            width: 100%;
            height: 38px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: 0 12px 0 36px;
            font-size: 0.85rem;
            color: var(--text-primary);
            outline: none;
            transition: border-color 0.2s;
        }}
        .drawer-search-input:focus {{
            border-color: var(--accent-color);
        }}
        .search-icon-pos {{
            position: absolute;
            left: 32px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            pointer-events: none;
        }}
        .drawer-body {{
            flex: 1;
            overflow-y: auto;
            padding: 10px 20px 24px 20px;
        }}
        .toc-list {{
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}
        .toc-item {{
            padding: 12px 14px;
            border-radius: var(--radius-md);
            background: var(--bg-card);
            border: 1px solid var(--border-light);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .toc-item:hover {{
            background: var(--accent-light);
            border-color: var(--accent-color);
            color: var(--accent-color);
            transform: translateX(-2px);
        }}
        .toc-item.current-reading {{
            border-color: var(--accent-color);
            background: var(--accent-light);
            font-weight: 600;
        }}
        .toc-item-left {{
            display: flex;
            align-items: baseline;
            gap: 8px;
            min-width: 0;
        }}
        .toc-chapter-badge {{
            font-size: 0.75rem;
            font-weight: 700;
            color: var(--accent-color);
            white-space: nowrap;
        }}
        .toc-chapter-title {{
            font-size: 0.88rem;
            color: var(--text-primary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .toc-chapter-words {{
            font-size: 0.75rem;
            color: var(--text-muted);
            white-space: nowrap;
        }}

        /* Lore Tab Items in Drawer */
        .lore-container {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        .lore-section-title {{
            font-size: 0.95rem;
            font-weight: 700;
            color: var(--text-primary);
            border-left: 3px solid var(--accent-color);
            padding-left: 8px;
            margin-top: 8px;
        }}
        .lore-text-box {{
            font-size: 0.85rem;
            line-height: 1.7;
            color: var(--text-secondary);
            background: var(--bg-card);
            padding: 14px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border-light);
            white-space: pre-wrap;
        }}
        .character-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-light);
            border-radius: var(--radius-md);
            padding: 14px;
        }}
        .char-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 6px;
        }}
        .char-name {{
            font-weight: 700;
            font-size: 0.92rem;
            color: var(--text-primary);
        }}
        .char-role-badge {{
            font-size: 0.72rem;
            background: var(--accent-light);
            color: var(--accent-color);
            padding: 2px 8px;
            border-radius: var(--radius-full);
            font-weight: 600;
        }}
        .char-desc {{
            font-size: 0.82rem;
            line-height: 1.6;
            color: var(--text-secondary);
            margin-bottom: 6px;
        }}
        .char-meta-row {{
            font-size: 0.78rem;
            color: var(--text-muted);
        }}

        /* Toast Notification */
        #reader-toast {{
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: var(--bg-surface);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            box-shadow: var(--shadow-lg);
            padding: 12px 20px;
            border-radius: var(--radius-full);
            font-size: 0.88rem;
            display: flex;
            align-items: center;
            gap: 12px;
            z-index: 150;
            opacity: 0;
            pointer-events: none;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            max-width: 90vw;
        }}
        #reader-toast.show {{
            transform: translateX(-50%) translateY(0);
            opacity: 1;
            pointer-events: auto;
        }}
        .toast-action-btn {{
            background: var(--accent-light);
            color: var(--accent-color);
            border: none;
            padding: 4px 10px;
            border-radius: var(--radius-full);
            font-size: 0.78rem;
            font-weight: 600;
            cursor: pointer;
        }}

        /* RWD Breakpoints */
        @media (max-width: 640px) {{
            :root {{
                --topbar-height: 44px;
            }}
            .novel-hero-header {{
                padding: 20px 16px;
            }}
            .novel-main-title {{
                font-size: 1.4rem;
            }}
            .reader-content-wrapper {{
                padding: 0 16px;
            }}
            .chapter-container {{
                padding-top: 20px;
                margin-bottom: 48px;
            }}
            .chapter-title {{
                font-size: 1.25rem;
            }}
            .chapter-body p {{
                text-indent: 2em;
            }}
            .fab-control-container {{
                bottom: 16px;
                right: 16px;
            }}
            .reader-drawer {{
                max-width: 100%;
            }}
        }}

        @media print {{
            .reader-top-nav,
            .fab-control-container,
            .chapter-footer,
            #top-progress-container {{
                display: none !important;
            }}
            body {{
                background: #ffffff !important;
                color: #000000 !important;
            }}
            .chapter-container {{
                page-break-after: always;
                content-visibility: visible !important;
                contain: none !important;
            }}
        }}
    </style>
</head>
<body>
    <!-- Top Progress Indicator -->
    <div id="top-progress-container">
        <div id="top-progress-bar"></div>
    </div>

    <!-- Sticky Top Navigation -->
    <nav class="reader-top-nav" id="reader-top-nav">
        <div class="top-nav-left">
            <span class="top-book-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
            </span>
            <span class="top-book-title">{escape_text(title)}</span>
            <span class="top-chapter-current" id="nav-current-chapter">· 正文開始</span>
        </div>
        <div class="top-nav-right">
            <span class="top-progress-text" id="nav-progress-percent">0%</span>
            <button class="top-action-btn" onclick="reader.openDrawer('toc')" title="目錄">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
            </button>
            <button class="top-action-btn" onclick="reader.openModal('settings')" title="閱讀設定">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
            </button>
        </div>
    </nav>

    <!-- Main Reader Application Container -->
    <main class="reader-app">
        <div class="reader-content-wrapper">
            
            <!-- Book Cover / Hero Section -->
            <header class="novel-hero-header" id="novel-cover">
                <span class="novel-title-tag">AI Factory 便攜小說</span>
                <h1 class="novel-main-title">《{escape_text(title)}》</h1>
                
                <div class="novel-meta-grid">
                    <div class="novel-meta-item">
                        <strong>題材：</strong><span>{escape_text(genre)}</span>
                    </div>
                    <div class="novel-meta-item">
                        <strong>風格基調：</strong><span>{escape_text(style)}</span>
                    </div>
                    <div class="novel-meta-item">
                        <strong>全書章節：</strong><span>{total_chapters} 章</span>
                    </div>
                    <div class="novel-meta-item">
                        <strong>總字數：</strong><span>約 {total_words:,} 字</span>
                    </div>
                </div>

                {f'<div class="novel-summary-box"><strong>故事簡介：</strong><br>{escape_text(summary)}</div>' if summary else ''}

                <div class="novel-hero-actions">
                    <button class="btn-hero btn-hero-primary" onclick="reader.startReading()">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                        開始閱讀
                    </button>
                    <button class="btn-hero btn-hero-secondary" onclick="reader.openDrawer('toc')">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
                        章節目錄
                    </button>
                    <button class="btn-hero btn-hero-secondary" onclick="reader.openDrawer('lore')">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon></svg>
                        設定資料庫
                    </button>
                </div>
            </header>

            <!-- Chapters Articles -->
            <section class="chapters-wrapper" id="chapters-wrapper">
                {chapters_joined}
            </section>
        </div>
    </main>

    <!-- Floating Action Button Menu (FAB) -->
    <div class="fab-control-container" id="fab-container">
        <div class="fab-menu-group" id="fab-menu-group">
            <button class="fab-btn" onclick="reader.scrollToTop()" title="回到頂部">
                <span class="fab-tooltip">回到頂部</span>
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>
            </button>
            <button class="fab-btn" onclick="reader.toggleThemeQuick()" title="切換日夜模式">
                <span class="fab-tooltip">切換日/夜</span>
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
            </button>
            <button class="fab-btn" onclick="reader.openModal('settings')" title="閱讀設定">
                <span class="fab-tooltip">閱讀設定</span>
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
            </button>
            <button class="fab-btn" onclick="reader.openDrawer('toc')" title="章節目錄">
                <span class="fab-tooltip">目錄跳轉</span>
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
            </button>
        </div>
        <button class="fab-btn fab-btn-main" onclick="reader.toggleFabMenu()" title="展開選單">
            <svg class="icon-menu" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
            <svg class="icon-close" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
    </div>

    <!-- Reading Settings Modal (小視窗) -->
    <div class="reader-modal-overlay" id="modal-settings-overlay" onclick="reader.handleOverlayClick(event, 'modal-settings-overlay')">
        <div class="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
            <div class="modal-header">
                <h3 class="modal-title" id="settings-title">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                    閱讀偏好設定
                </h3>
                <button class="modal-close-btn" onclick="reader.closeModal('settings')" aria-label="關閉">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            </div>

            <!-- Theme Color Presets -->
            <div class="setting-group">
                <div class="setting-label">
                    <span>背景主題色彩</span>
                    <span class="setting-value-badge" id="lbl-current-theme">羊皮紙</span>
                </div>
                <div class="theme-grid">
                    <button class="theme-pill theme-parchment-pill active" data-theme-val="parchment" onclick="reader.setTheme('parchment')">
                        <span>暖柔</span>
                        <span style="font-size:0.65rem;">羊皮紙</span>
                    </button>
                    <button class="theme-pill theme-eyecare-pill" data-theme-val="eyecare" onclick="reader.setTheme('eyecare')">
                        <span>護眼</span>
                        <span style="font-size:0.65rem;">豆沙綠</span>
                    </button>
                    <button class="theme-pill theme-light-pill" data-theme-val="light" onclick="reader.setTheme('light')">
                        <span>雅致</span>
                        <span style="font-size:0.65rem;">晨曦白</span>
                    </button>
                    <button class="theme-pill theme-midnight-pill" data-theme-val="midnight" onclick="reader.setTheme('midnight')">
                        <span>謐夜</span>
                        <span style="font-size:0.65rem;">星空藍</span>
                    </button>
                    <button class="theme-pill theme-oled-pill" data-theme-val="oled" onclick="reader.setTheme('oled')">
                        <span>極致</span>
                        <span style="font-size:0.65rem;">墨曜黑</span>
                    </button>
                </div>
            </div>

            <!-- Font Size -->
            <div class="setting-group">
                <div class="setting-label">
                    <span>字體大小</span>
                    <span class="setting-value-badge" id="lbl-font-size">中</span>
                </div>
                <div class="segmented-btn-group">
                    <button class="segment-btn" data-size-val="xs" onclick="reader.setFontSize(16)">小小</button>
                    <button class="segment-btn" data-size-val="s" onclick="reader.setFontSize(20)">小</button>
                    <button class="segment-btn active" data-size-val="m" onclick="reader.setFontSize(24)">中</button>
                    <button class="segment-btn" data-size-val="l" onclick="reader.setFontSize(28)">大</button>
                    <button class="segment-btn" data-size-val="xl" onclick="reader.setFontSize(32)">大大</button>
                </div>
            </div>

            <!-- Font Family -->
            <div class="setting-group">
                <div class="setting-label">
                    <span>字體風格</span>
                </div>
                <div class="segmented-btn-group">
                    <button class="segment-btn active" data-font-val="serif" onclick="reader.setFontFamily('serif')">明體/宋體</button>
                    <button class="segment-btn" data-font-val="sans" onclick="reader.setFontFamily('sans')">黑體/現代</button>
                    <button class="segment-btn" data-font-val="kaiti" onclick="reader.setFontFamily('kaiti')">文雅楷體</button>
                </div>
            </div>

            <!-- Line Height / Spacing -->
            <div class="setting-group">
                <div class="setting-label">
                    <span>行距排版</span>
                </div>
                <div class="segmented-btn-group">
                    <button class="segment-btn" data-spacing-val="compact" onclick="reader.setSpacing('compact')">緊湊</button>
                    <button class="segment-btn active" data-spacing-val="standard" onclick="reader.setSpacing('standard')">標準</button>
                    <button class="segment-btn" data-spacing-val="loose" onclick="reader.setSpacing('loose')">寬鬆</button>
                </div>
            </div>

            <!-- Page Width -->
            <div class="setting-group">
                <div class="setting-label">
                    <span>閱讀欄寬</span>
                </div>
                <div class="segmented-btn-group">
                    <button class="segment-btn" data-width-val="narrow" onclick="reader.setPageWidth('narrow')">舒適 (680)</button>
                    <button class="segment-btn active" data-width-val="standard" onclick="reader.setPageWidth('standard')">標準 (840)</button>
                    <button class="segment-btn" data-width-val="wide" onclick="reader.setPageWidth('wide')">寬版 (1020)</button>
                </div>
            </div>
            
            <!-- Reset Button -->
            <div style="margin-top: 24px; text-align: center;">
                <button class="nav-btn" style="width: 100%; border-radius: var(--radius-md);" onclick="reader.resetSettings()">
                    恢復預設閱讀設定
                </button>
            </div>
        </div>
    </div>

    <!-- TOC / Lore Drawer (側欄抽屜) -->
    <div class="reader-drawer-overlay" id="drawer-overlay" onclick="reader.handleOverlayClick(event, 'drawer-overlay')">
        <aside class="reader-drawer" role="complementary" aria-label="小說目錄與設定">
            <div class="drawer-header">
                <h3 class="modal-title">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
                    全書目錄與設定
                </h3>
                <button class="modal-close-btn" onclick="reader.closeDrawer()" aria-label="關閉抽屜">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            </div>

            <!-- Drawer Tabs -->
            <div class="drawer-tabs">
                <button class="drawer-tab-btn active" id="tab-btn-toc" onclick="reader.switchDrawerTab('toc')">章節目錄 ({total_chapters})</button>
                <button class="drawer-tab-btn" id="tab-btn-lore" onclick="reader.switchDrawerTab('lore')">世界觀與角色</button>
            </div>

            <!-- Search Filter for TOC -->
            <div class="drawer-search-box" id="drawer-search-container">
                <span class="search-icon-pos">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                </span>
                <input type="text" class="drawer-search-input" id="toc-search-input" placeholder="搜尋章節名稱或編號..." oninput="reader.filterToc(this.value)">
            </div>

            <!-- Drawer Body -->
            <div class="drawer-body">
                <!-- TOC Panel -->
                <div class="toc-list" id="drawer-toc-panel">
                    {toc_joined}
                </div>

                <!-- Lore Panel -->
                <div class="lore-container" id="drawer-lore-panel" style="display: none;">
                    <div class="lore-section-title">世界觀與核心設定</div>
                    <div class="lore-text-box">{escape_text(wb_content) if wb_content else "尚無世界觀設定資料"}</div>

                    <div class="lore-section-title">主要角色設定 ({len(char_list)})</div>
                    {char_cards_joined}
                </div>
            </div>
        </aside>
    </div>

    <!-- Floating Toast for Progress Restoration -->
    <div id="reader-toast">
        <span id="toast-message">已恢復至上次閱讀進度</span>
        <button class="toast-action-btn" id="toast-action-btn" onclick="reader.scrollToTop()">回頂部</button>
    </div>

    <!-- ==========================================================================
       EMBEDDED READER JAVASCRIPT LOGIC (Offline, LocalStorage, TOC, Settings)
       ========================================================================== -->
    <script>
        (function() {{
            'use strict';

            const NOVEL_KEY = 'novel_reader_{escape_text(novel_id)}';
            
            const DEFAULT_SETTINGS = {{
                theme: 'parchment',
                fontSize: 24,
                fontFamily: 'serif',
                spacing: 'standard',
                pageWidth: 'standard',
                scrollY: 0,
                lastChapter: 1,
                lastReadTime: Date.now()
            }};

            class NovelReader {{
                constructor() {{
                    this.state = Object.assign({{}}, DEFAULT_SETTINGS);
                    this.chapterElements = [];
                    this.currentChapterIndex = 1;
                    this.isScrollingProgrammatically = false;
                    this.scrollDebounceTimer = null;
                    this.init();
                }}

                init() {{
                    this.loadStoredState();
                    this.bindChapterElements();
                    this.applyAllSettings();
                    this.setupScrollTracker();
                    this.setupKeyboardShortcuts();
                    
                    // Attempt progress restoration after paint
                    window.addEventListener('DOMContentLoaded', () => {{
                        setTimeout(() => this.restoreReadingProgress(), 150);
                    }});
                }}

                loadStoredState() {{
                    try {{
                        const raw = localStorage.getItem(NOVEL_KEY);
                        if (raw) {{
                            const parsed = JSON.parse(raw);
                            this.state = Object.assign({{}}, DEFAULT_SETTINGS, parsed);
                        }}
                    }} catch (e) {{
                        console.warn('Unable to read localStorage:', e);
                    }}
                }}

                saveState() {{
                    try {{
                        this.state.lastReadTime = Date.now();
                        localStorage.setItem(NOVEL_KEY, JSON.stringify(this.state));
                    }} catch (e) {{
                        console.warn('Unable to write to localStorage:', e);
                    }}
                }}

                bindChapterElements() {{
                    this.chapterElements = Array.from(document.querySelectorAll('.chapter-container'));
                }}

                applyAllSettings() {{
                    this.setTheme(this.state.theme, false);
                    this.setFontSize(this.state.fontSize, false);
                    this.setFontFamily(this.state.fontFamily, false);
                    this.setSpacing(this.state.spacing, false);
                    this.setPageWidth(this.state.pageWidth, false);
                }}

                /* ================= UI Toggles & Modals ================= */
                toggleFabMenu() {{
                    const container = document.getElementById('fab-container');
                    if (container) container.classList.toggle('open');
                }}

                openModal(name) {{
                    this.closeFabMenu();
                    const el = document.getElementById(`modal-${{name}}-overlay`);
                    if (el) el.classList.add('active');
                }}

                closeModal(name) {{
                    const el = document.getElementById(`modal-${{name}}-overlay`);
                    if (el) el.classList.remove('active');
                }}

                openDrawer(defaultTab = 'toc') {{
                    this.closeFabMenu();
                    const el = document.getElementById('drawer-overlay');
                    if (el) {{
                        el.classList.add('active');
                        this.switchDrawerTab(defaultTab);
                    }}
                }}

                closeDrawer() {{
                    const el = document.getElementById('drawer-overlay');
                    if (el) el.classList.remove('active');
                }}

                closeFabMenu() {{
                    const container = document.getElementById('fab-container');
                    if (container) container.classList.remove('open');
                }}

                handleOverlayClick(e, overlayId) {{
                    if (e.target.id === overlayId) {{
                        if (overlayId === 'drawer-overlay') this.closeDrawer();
                        else if (overlayId === 'modal-settings-overlay') this.closeModal('settings');
                    }}
                }}

                switchDrawerTab(tab) {{
                    const tocPanel = document.getElementById('drawer-toc-panel');
                    const lorePanel = document.getElementById('drawer-lore-panel');
                    const searchContainer = document.getElementById('drawer-search-container');
                    const tabBtnToc = document.getElementById('tab-btn-toc');
                    const tabBtnLore = document.getElementById('tab-btn-lore');

                    if (tab === 'toc') {{
                        if (tocPanel) tocPanel.style.display = 'flex';
                        if (lorePanel) lorePanel.style.display = 'none';
                        if (searchContainer) searchContainer.style.display = 'block';
                        if (tabBtnToc) tabBtnToc.classList.add('active');
                        if (tabBtnLore) tabBtnLore.classList.remove('active');
                    }} else {{
                        if (tocPanel) tocPanel.style.display = 'none';
                        if (lorePanel) lorePanel.style.display = 'flex';
                        if (searchContainer) searchContainer.style.display = 'none';
                        if (tabBtnToc) tabBtnToc.classList.remove('active');
                        if (tabBtnLore) tabBtnLore.classList.add('active');
                    }}
                }}

                filterToc(query) {{
                    const items = document.querySelectorAll('.toc-item');
                    const q = (query || '').trim().toLowerCase();
                    items.forEach(item => {{
                        const title = item.textContent.toLowerCase();
                        if (!q || title.includes(q)) {{
                            item.style.display = 'flex';
                        }} else {{
                            item.style.display = 'none';
                        }}
                    }});
                }}

                /* ================= Settings Controllers ================= */
                setTheme(theme, save = true) {{
                    const themeNames = {{
                        parchment: '羊皮紙',
                        eyecare: '豆沙綠',
                        light: '晨曦白',
                        midnight: '星空藍',
                        oled: '墨曜黑'
                    }};
                    document.documentElement.setAttribute('data-theme', theme);
                    this.state.theme = theme;
                    
                    const lbl = document.getElementById('lbl-current-theme');
                    if (lbl) lbl.textContent = themeNames[theme] || theme;

                    document.querySelectorAll('.theme-pill').forEach(pill => {{
                        if (pill.dataset.themeVal === theme) pill.classList.add('active');
                        else pill.classList.remove('active');
                    }});

                    if (save) this.saveState();
                }}

                toggleThemeQuick() {{
                    const cur = this.state.theme;
                    if (cur === 'midnight' || cur === 'oled') {{
                        this.setTheme('parchment');
                    }} else {{
                        this.setTheme('midnight');
                    }}
                }}

                setFontSize(size, save = true) {{
                    const s = Math.max(14, Math.min(32, parseInt(size, 10) || 24));
                    this.state.fontSize = s;

                    const sizeLabels = {{ 16: '小小', 20: '小', 24: '中', 28: '大', 32: '大大' }};
                    const lbl = document.getElementById('lbl-font-size');
                    if (lbl) lbl.textContent = sizeLabels[s] || `${{s}}px`;

                    document.querySelectorAll('[data-size-val]').forEach(btn => {{
                        const btnSize = {{ xs: 16, s: 20, m: 24, l: 28, xl: 32 }};
                        const val = Object.keys(btnSize).find(k => btnSize[k] === s);
                        if (btn.dataset.sizeVal === val) btn.classList.add('active');
                        else btn.classList.remove('active');
                    }});

                    if (this._fontRaf) cancelAnimationFrame(this._fontRaf);
                    this._fontRaf = requestAnimationFrame(() => {{
                        document.documentElement.style.setProperty('--reader-font-size', `${{s}}px`);
                        if (save) this.saveState();
                    }});
                }}

                setFontFamily(font, save = true) {{
                    document.documentElement.setAttribute('data-font', font);
                    this.state.fontFamily = font;

                    document.querySelectorAll('[data-font-val]').forEach(btn => {{
                        if (btn.dataset.fontVal === font) btn.classList.add('active');
                        else btn.classList.remove('active');
                    }});

                    if (save) this.saveState();
                }}

                setSpacing(spacing, save = true) {{
                    document.documentElement.setAttribute('data-spacing', spacing);
                    this.state.spacing = spacing;

                    document.querySelectorAll('[data-spacing-val]').forEach(btn => {{
                        if (btn.dataset.spacingVal === spacing) btn.classList.add('active');
                        else btn.classList.remove('active');
                    }});

                    if (save) this.saveState();
                }}

                setPageWidth(width, save = true) {{
                    document.documentElement.setAttribute('data-width', width);
                    this.state.pageWidth = width;

                    document.querySelectorAll('[data-width-val]').forEach(btn => {{
                        if (btn.dataset.widthVal === width) btn.classList.add('active');
                        else btn.classList.remove('active');
                    }});

                    if (save) this.saveState();
                }}

                resetSettings() {{
                    this.state.theme = DEFAULT_SETTINGS.theme;
                    this.state.fontSize = DEFAULT_SETTINGS.fontSize;
                    this.state.fontFamily = DEFAULT_SETTINGS.fontFamily;
                    this.state.spacing = DEFAULT_SETTINGS.spacing;
                    this.state.pageWidth = DEFAULT_SETTINGS.pageWidth;
                    this.applyAllSettings();
                    this.saveState();
                    this.showToast('已恢復預設閱讀設定');
                }}

                /* ================= Navigation & Progress ================= */
                startReading() {{
                    const firstChapter = document.querySelector('.chapter-container');
                    if (firstChapter) {{
                        this.scrollToElement(firstChapter);
                    }}
                }}

                jumpToChapter(idx) {{
                    const target = document.getElementById(`chapter-${{idx}}`);
                    if (target) {{
                        this.closeDrawer();
                        this.closeModal('settings');
                        this.scrollToElement(target);
                    }} else {{
                        this.showToast(`查無第 ${{idx}} 章`);
                    }}
                }}

                scrollToElement(element) {{
                    this.isScrollingProgrammatically = true;
                    const topOffset = element.getBoundingClientRect().top + window.pageYOffset - 60;
                    window.scrollTo({{
                        top: Math.max(0, topOffset),
                        behavior: 'smooth'
                    }});
                    setTimeout(() => {{
                        this.isScrollingProgrammatically = false;
                        this.updateProgress();
                    }}, 600);
                }}

                scrollToTop() {{
                    window.scrollTo({{ top: 0, behavior: 'smooth' }});
                }}

                setupScrollTracker() {{
                    let lastScrollY = window.pageYOffset;
                    const topNav = document.getElementById('reader-top-nav');

                    window.addEventListener('scroll', () => {{
                        const curScrollY = window.pageYOffset;
                        
                        // Top nav hide on scroll down, reveal on scroll up
                        if (topNav) {{
                            if (curScrollY > 180 && curScrollY > lastScrollY + 10) {{
                                topNav.classList.add('hidden-nav');
                            }} else if (curScrollY < lastScrollY - 10 || curScrollY <= 80) {{
                                topNav.classList.remove('hidden-nav');
                            }}
                        }}
                        lastScrollY = curScrollY;

                        // Debounce progress saving
                        if (this.scrollDebounceTimer) clearTimeout(this.scrollDebounceTimer);
                        this.scrollDebounceTimer = setTimeout(() => {{
                            this.updateProgress();
                        }}, 150);
                    }}, {{ passive: true }});
                }}

                updateProgress() {{
                    const scrollY = window.pageYOffset;
                    const totalDocHeight = document.documentElement.scrollHeight - window.innerHeight;
                    const percent = totalDocHeight > 0 ? Math.min(100, Math.max(0, Math.round((scrollY / totalDocHeight) * 100))) : 0;

                    // Update Top Progress Bar
                    const bar = document.getElementById('top-progress-bar');
                    if (bar) bar.style.width = `${{percent}}%`;

                    const percentLabel = document.getElementById('nav-progress-percent');
                    if (percentLabel) percentLabel.textContent = `${{percent}}%`;

                    // Detect active chapter
                    let activeIdx = 1;
                    const viewportMiddle = window.innerHeight * 0.35;
                    
                    for (const chEl of this.chapterElements) {{
                        const rect = chEl.getBoundingClientRect();
                        if (rect.top <= viewportMiddle && rect.bottom >= 0) {{
                            activeIdx = parseInt(chEl.dataset.chapterIndex, 10) || 1;
                        }}
                    }}

                    this.currentChapterIndex = activeIdx;
                    this.state.scrollY = scrollY;
                    this.state.lastChapter = activeIdx;
                    this.saveState();

                    // Update top current chapter label
                    const curChapterTitleEl = document.querySelector(`#chapter-${{activeIdx}} .chapter-title`);
                    const navChapterLabel = document.getElementById('nav-current-chapter');
                    if (navChapterLabel && curChapterTitleEl) {{
                        navChapterLabel.textContent = `· ${{curChapterTitleEl.textContent.trim()}}`;
                    }}

                    // Highlight TOC current reading item
                    document.querySelectorAll('.toc-item').forEach(item => {{
                        const chIdx = parseInt(item.dataset.chapterIndex, 10);
                        if (chIdx === activeIdx) item.classList.add('current-reading');
                        else item.classList.remove('current-reading');
                    }});
                }}

                restoreReadingProgress() {{
                    if (this.state.scrollY && this.state.scrollY > 150) {{
                        window.scrollTo({{ top: this.state.scrollY, behavior: 'smooth' }});
                        const chTitle = document.querySelector(`#chapter-${{this.state.lastChapter}} .chapter-title`);
                        const titleText = chTitle ? chTitle.textContent.trim() : `第 ${{this.state.lastChapter}} 章`;
                        this.showToast(`已為您恢復閱讀進度：${{titleText}}`, true);
                    }}
                }}

                showToast(msg, showTopAction = false) {{
                    const toast = document.getElementById('reader-toast');
                    const msgEl = document.getElementById('toast-message');
                    const btn = document.getElementById('toast-action-btn');
                    if (!toast || !msgEl) return;

                    msgEl.textContent = msg;
                    if (btn) btn.style.display = showTopAction ? 'inline-block' : 'none';

                    toast.classList.add('show');
                    setTimeout(() => {{
                        toast.classList.remove('show');
                    }}, 4000);
                }}

                setupKeyboardShortcuts() {{
                    window.addEventListener('keydown', (e) => {{
                        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
                        
                        if (e.key === 'Escape') {{
                            this.closeDrawer();
                            this.closeModal('settings');
                            this.closeFabMenu();
                        }} else if (e.key === 't' || e.key === 'T') {{
                            e.preventDefault();
                            this.openDrawer('toc');
                        }} else if (e.key === 's' || e.key === 'S') {{
                            e.preventDefault();
                            this.openModal('settings');
                        }} else if (e.key === '[' || e.key === 'ArrowLeft') {{
                            if (this.currentChapterIndex > 1) {{
                                e.preventDefault();
                                this.jumpToChapter(this.currentChapterIndex - 1);
                            }}
                        }} else if (e.key === ']' || e.key === 'ArrowRight') {{
                            if (this.currentChapterIndex < {total_chapters}) {{
                                e.preventDefault();
                                this.jumpToChapter(this.currentChapterIndex + 1);
                            }}
                        }}
                    }});
                }}
            }}

            window.reader = new NovelReader();
        }})();
    </script>
</body>
</html>
"""
    return html_content
