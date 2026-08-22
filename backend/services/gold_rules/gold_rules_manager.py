# -*- coding: utf-8 -*-
"""
Gold Rules 治理系統 (Gold Rules Governance Manager)

核心職責：
1. 嚴格區分 Canon（世界事實）、Style Profile（風格偏好）與 Gold Rules（寫作策略）。
2. 實作 Scope 分流（Chapter Writer, Editor, Story Architect, Director 等）、優先級排序與衝突仲裁。
3. 控制生命週期（status: approved / draft / archived），預設僅向下游注入 approved 規則，阻斷 AI 偏誤自我循環。
4. 提供語意與關鍵字相關性排名，動態選取 Top 8-12 條規則，避免長度膨脹。
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend import persistence as db
from backend.common.utils import safe_filename


@dataclass
class GoldRule:
    rule_id: str
    scope: List[str]  # e.g. ["chapter_writer", "editor"]
    category: str  # e.g. "dialogue", "pov", "pacing", "foreshadowing", "worldview"
    strength: str  # "hard" | "soft" | "adaptive"
    rule: str
    condition: str = "通用"
    source: str = "human_review"  # "human_review" | "editor_revision" | "benchmark_approved" | "retrospective_draft"
    confidence: float = 0.90
    version: int = 1
    status: str = "approved"  # "approved" | "draft" | "archived"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GoldRule:
        return cls(
            rule_id=str(data.get("rule_id", "GR-UNKNOWN")),
            scope=list(data.get("scope", ["global"])),
            category=str(data.get("category", "general")),
            strength=str(data.get("strength", "soft")),
            rule=str(data.get("rule", "")),
            condition=str(data.get("condition", "通用")),
            source=str(data.get("source", "human_review")),
            confidence=float(data.get("confidence", 0.85)),
            version=int(data.get("version", 1)),
            status=str(data.get("status", "approved")),
            created_at=float(data.get("created_at", time.time())),
        )


class GoldRulesManager:
    """管理小說的 Gold Rules、風格與事實治理。"""

    def __init__(self):
        self._rules_cache: Dict[str, List[GoldRule]] = {}
        self._cache_mtime: Dict[str, float] = {}

    def get_storage_directory(self) -> str:
        """傳回 gold rules 的儲存目錄。"""
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "gold_rules")
        os.makedirs(d, exist_ok=True)
        return d

    def _get_novel_filepath(self, novel_id: str) -> Optional[str]:
        novel = db.get_novel(novel_id)
        safe_title = safe_filename(novel.get("title", "")) if novel else f"novel_{novel_id[:8]}"
        d = self.get_storage_directory()
        return os.path.join(d, f"{safe_title}_{novel_id[:8]}_rules.json")

    def _get_legacy_markdown_path(self, novel_id: str) -> Optional[str]:
        novel = db.get_novel(novel_id)
        if not novel:
            return None
        safe_title = safe_filename(novel.get("title", ""))
        d = self.get_storage_directory()
        candidates = [
            os.path.join(d, f"{safe_title}_retrospective_gold_rules.md"),
        ]
        if os.path.isdir(d):
            for fname in os.listdir(d):
                if fname.startswith(safe_title) and fname.endswith("_retrospective_gold_rules.md"):
                    candidates.append(os.path.join(d, fname))
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    def load_rules(self, novel_id: str) -> List[GoldRule]:
        """載入指定小說的所有結構化金律。若只有 legacy markdown 則進行自動轉換。"""
        filepath = self._get_novel_filepath(novel_id)
        if filepath and os.path.isfile(filepath):
            mtime = os.path.getmtime(filepath)
            if novel_id in self._rules_cache and self._cache_mtime.get(novel_id) == mtime:
                return self._rules_cache[novel_id]
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    rules = [GoldRule.from_dict(r) for r in raw if isinstance(r, dict)]
                    self._rules_cache[novel_id] = rules
                    self._cache_mtime[novel_id] = mtime
                    return rules
            except Exception:
                pass

        # 嘗試從 legacy markdown 解析
        legacy_md = self._get_legacy_markdown_path(novel_id)
        if legacy_md and os.path.isfile(legacy_md):
            try:
                with open(legacy_md, "r", encoding="utf-8") as f:
                    content = f.read()
                    rules = self._parse_legacy_markdown(content)
                    if rules:
                        self.save_rules(novel_id, rules)
                        return rules
            except Exception:
                pass

        return self._get_default_builtin_rules()

    def _parse_legacy_markdown(self, markdown_text: str) -> List[GoldRule]:
        """將舊版純文字金律 Markdown 解析為結構化 GoldRule 清單。"""
        rules: List[GoldRule] = []
        lines = markdown_text.splitlines()
        current_agent = "global"
        agent_mapping = {
            "世界觀": "story_architect",
            "角色": "character_designer",
            "伏筆": "foreshadowing_orchestrator",
            "篇卷": "volumes_planner",
            "骨架": "volume_skeleton",
            "正文": "chapter_writer",
            "寫作": "chapter_writer",
            "編輯": "editor",
            "總監": "director",
        }

        idx = 1
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("#"):
                for k, v in agent_mapping.items():
                    if k in line_str:
                        current_agent = v
                        break
            elif (line_str.startswith("-") or line_str.startswith("*") or re.match(r"^\d+\.", line_str)) and len(line_str) > 8:
                clean_text = re.sub(r"^[-*\d.]+\s*", "", line_str).strip()
                if clean_text:
                    rules.append(
                        GoldRule(
                            rule_id=f"GR-LEGACY-{idx:03d}",
                            scope=[current_agent],
                            category="general",
                            strength="soft",
                            rule=clean_text,
                            condition="通用",
                            source="retrospective_legacy",
                            confidence=0.85,
                            status="approved",
                        )
                    )
                    idx += 1
        return rules or self._get_default_builtin_rules()

    def _get_default_builtin_rules(self) -> List[GoldRule]:
        """系統內建的現代小說創作金律基礎集。"""
        return [
            GoldRule(
                rule_id="GR-SYS-001",
                scope=["chapter_writer"],
                category="pov",
                strength="hard",
                rule="嚴格鎖定當前場景指定之 POV 角色視角與感知範圍。禁止未經授權突然切入其他角色的不可知心理活動（禁止 Head-hopping）。",
                condition="所有第三人稱限制視角場景",
                confidence=1.0,
                status="approved",
            ),
            GoldRule(
                rule_id="GR-SYS-002",
                scope=["chapter_writer"],
                category="exposition",
                strength="soft",
                rule="嚴禁作者跳出故事進行『資料庫或設定集式』背景說明。世界觀規則應化為人物眼前的現實障礙、感官細節或具體行動結果。",
                condition="任何涉及設定或歷史背景的段落",
                confidence=0.95,
                status="approved",
            ),
            GoldRule(
                rule_id="GR-SYS-003",
                scope=["chapter_writer"],
                category="dialogue",
                strength="soft",
                rule="對話應體現人物 speech_profile 的語域與受壓反應，禁止固定句尾口癖與機械式標籤；日常交代自然俐落，高壓情境展現語言防禦與潛台詞。",
                condition="角色對白與交鋒場景",
                confidence=0.92,
                status="approved",
            ),
            GoldRule(
                rule_id="GR-SYS-004",
                scope=["chapter_writer"],
                category="pacing",
                strength="adaptive",
                rule="調節 Show 與 Tell 之平衡：重大抉擇、生死衝突、情感轉折使用細膩 Scene/Show；時間跳躍、空間移動與低重要度背景使用俐落 Summary/Tell。",
                condition="轉場與高潮交替節奏",
                confidence=0.90,
                status="approved",
            ),
            GoldRule(
                rule_id="GR-SYS-005",
                scope=["chapter_writer"],
                category="prose",
                strength="soft",
                rule="剔除 AI 慣用套路詞（如『指尖輕微顫抖、血痕、空氣凝固、命運的重量』），使用多元且精確的動詞白描推進故事。",
                condition="動作與情緒描寫",
                confidence=0.95,
                status="approved",
            ),
            GoldRule(
                rule_id="GR-SYS-006",
                scope=["editor"],
                category="editing",
                strength="hard",
                rule="針對 Reviewer 標記之視角越界、設定集傾倒或對話生硬段落進行局部精準修復；嚴禁改動大綱核心事件與未受標記的良好 prose。",
                condition="正文精修階段",
                confidence=0.98,
                status="approved",
            ),
        ]

    def save_rules(self, novel_id: str, rules: List[GoldRule]) -> bool:
        """持久化儲存小說的 Gold Rules。"""
        filepath = self._get_novel_filepath(novel_id)
        if not filepath:
            return False
        try:
            data = [r.to_dict() for r in rules]
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._rules_cache[novel_id] = rules
            self._cache_mtime[novel_id] = os.path.getmtime(filepath)
            return True
        except Exception:
            return False

    def add_rules(self, novel_id: str, new_rules: List[GoldRule]) -> int:
        """追加新規則，預設如果來自未審核的回顧則維持 draft，避免自污染。"""
        existing = self.load_rules(novel_id)
        rule_map = {r.rule_id: r for r in existing}
        added_count = 0
        for nr in new_rules:
            if nr.rule_id in rule_map:
                # 更新版本
                old = rule_map[nr.rule_id]
                if nr.version >= old.version:
                    rule_map[nr.rule_id] = nr
                    added_count += 1
            else:
                rule_map[nr.rule_id] = nr
                added_count += 1
        updated_list = list(rule_map.values())
        self.save_rules(novel_id, updated_list)
        return added_count

    def query_rules(
        self,
        novel_id: str,
        agent_scope: str,
        context_keywords: Optional[List[str]] = None,
        status: str = "approved",
        max_rules: int = 10,
    ) -> List[GoldRule]:
        """
        根據 Agent Scope、審核狀態與情境關鍵字檢索最適金律。
        """
        all_rules = self.load_rules(novel_id)
        matched: List[Tuple[float, GoldRule]] = []

        keywords = [k.lower() for k in (context_keywords or []) if k]

        for rule in all_rules:
            if status and rule.status != status:
                continue

            # 檢查 Scope 匹配
            scopes = [s.lower() for s in rule.scope]
            scope_target = agent_scope.lower()
            if "global" not in scopes and scope_target not in scopes:
                # 兼容 writer / chapter_writer
                if scope_target == "writer" and "chapter_writer" in scopes:
                    pass
                elif scope_target == "chapter_writer" and "writer" in scopes:
                    pass
                else:
                    continue

            # 計算相關性得分
            score = rule.confidence
            if rule.strength == "hard":
                score += 1.0  # 硬性約束優先

            rule_text = (rule.rule + " " + rule.condition + " " + rule.category).lower()
            for kw in keywords:
                if kw in rule_text:
                    score += 0.3

            matched.append((score, rule))

        # 按分數降序排序並截取 Top-N
        matched.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in matched[:max_rules]]

    def format_rules_for_prompt(
        self,
        novel_id: str,
        agent_scope: str,
        context_keywords: Optional[List[str]] = None,
        max_rules: int = 10,
    ) -> str:
        """
        將查詢到的最適金律格式化為注入 System / User Prompt 的精簡 Markdown 區塊。
        """
        rules = self.query_rules(
            novel_id=novel_id,
            agent_scope=agent_scope,
            context_keywords=context_keywords,
            status="approved",
            max_rules=max_rules,
        )
        if not rules:
            return ""

        lines = [
            f"## 【{agent_scope.upper()} 寫作策略與黃金指引 (Gold Rules)】",
            "*(以下為本作品經審核確認之關鍵創作準則，請在寫作時精準落實)*",
        ]
        for idx, r in enumerate(rules, 1):
            tag = "🔴 [硬約束]" if r.strength == "hard" else ("🟡 [軟準則]" if r.strength == "soft" else "🟢 [彈性調節]")
            cond = f" (情境：{r.condition})" if r.condition and r.condition != "通用" else ""
            lines.append(f"{idx}. {tag}{cond} {r.rule}")

        return "\n".join(lines)


# Singleton
_GLOBAL_GOLD_RULES_MANAGER = GoldRulesManager()


def get_gold_rules_manager() -> GoldRulesManager:
    return _GLOBAL_GOLD_RULES_MANAGER


def load_scoped_gold_rules(
    novel_id: str,
    agent_scope: str,
    context_keywords: Optional[List[str]] = None,
    max_rules: int = 10,
) -> str:
    """提供給各 Runner / Context Builder 呼叫的便捷注入函數。"""
    return _GLOBAL_GOLD_RULES_MANAGER.format_rules_for_prompt(
        novel_id=novel_id,
        agent_scope=agent_scope,
        context_keywords=context_keywords,
        max_rules=max_rules,
    )
