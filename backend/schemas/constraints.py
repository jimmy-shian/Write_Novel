# -*- coding: utf-8 -*-
"""
Constraints Module (限制規範層)
負責管理所有規則載入、格式化，以及 gold rules 黃金律的讀取。
agents.py 不應該包含任何規則讀取或格式化邏輯，一律交由此模組處理。
"""

import os
from backend import db
from backend.utils import safe_filename


# =============================================================================
# Gold Rules File Naming
# =============================================================================

def gold_rules_filename(title: str) -> str:
    """將小說標題轉換為安全的 gold rules 檔名前綴。"""
    return safe_filename(title)


# =============================================================================
# Gold Rules Loading
# =============================================================================

def load_retrospective_gold_rules(novel_id: str, limit: int = 16000) -> str:
    """
    載入指定小說的 Retrospective Gold Rules（創作金律回顧文件）。
    若無對應檔案則回傳空字串。
    若檔案過長，會保留首尾並插入省略標記以節省 Token。

    Args:
        novel_id: 小說的唯一 ID。
        limit:    回傳內容的最大字元數。

    Returns:
        Gold rules 的文字內容（字串），無則回傳空字串。
    """
    novel = db.get_novel(novel_id)
    if not novel:
        return ""
    gold_rules_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gold_rules")
    if not os.path.isdir(gold_rules_dir):
        return ""

    safe_title = gold_rules_filename(novel.get("title", ""))
    candidates = []
    expected_name = f"{safe_title}_retrospective_gold_rules.md"
    expected_path = os.path.join(gold_rules_dir, expected_name)
    if os.path.isfile(expected_path):
        candidates.append(expected_path)
    else:
        for name in os.listdir(gold_rules_dir):
            if name.endswith("_retrospective_gold_rules.md") and name.startswith(safe_title):
                path = os.path.join(gold_rules_dir, name)
                if os.path.isfile(path):
                    candidates.append(path)

    if not candidates:
        return ""
    latest = max(candidates, key=lambda path: os.path.getmtime(path))
    try:
        with open(latest, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except OSError:
        return ""
    if len(content) <= limit:
        return content
    marker = f"\n\n...[創作金律過長，已省略 {len(content) - limit} 字，保留開頭與結尾]...\n\n"
    head_len = max(1, (limit - len(marker)) * 2 // 3)
    tail_len = max(1, limit - len(marker) - head_len)
    return content[:head_len] + marker + content[-tail_len:]
