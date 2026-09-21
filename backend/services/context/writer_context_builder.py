# -*- coding: utf-8 -*-
"""
Writer 上下文組裝器 (Writer Context Builder)

核心職責：
1. 將原本直接傾倒給 Writer 的 Raw JSON 資料庫（世界觀、Want/Need、Faction、完整關係矩陣）進行情境化解構。
2. 提煉出小說寫作專屬的四大核心上下文區塊：
   - 【Scene Contract 場景契約】：指定 POV 視角人物、敘事距離、本場景目標、阻礙、轉折與結果。
   - 【Character States 角色狀態與知情邊界】：本場景出場角色的公開意圖、隱藏意圖、情緒態度、語言人格傾向（speech_profile）與「知情範圍（Knowledge Scope）」。
   - 【Continuity & Memory 敘事連續性】：承接前章結尾、活躍伏筆線索與當前時空。
   - 【Mandatory Beats & Tasks 必要拍點與任務】：本章必須發生的戲劇拍點與伏筆埋設/回收。
3. 注入經治理層過濾的 Scoped Gold Rules。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.persistence import get_terms
from backend.prompts.common.context import format_novel_core_context
from backend.services.gold_rules.gold_rules_manager import load_scoped_gold_rules
from backend.services.graphiti.temporal_graph import TemporalGraphService
from backend.services.narrative.conflict_ledger import ConflictLedger
from backend.services.narrative.setting_registry import SettingRegistry
from backend.services.director.context_compiler import GeometryContextCompiler


class WriterContextBuilder:
    """負責為 Chapter Writer 構建最小必要且高度情境化的寫作上下文。"""

    def build_scene_contract(
        self,
        current_outline: Dict[str, Any],
        characters_list: List[Dict[str, Any]],
        chapter_index: int,
    ) -> Dict[str, Any]:
        """從章節大綱與角色清單提煉出當前場景的視角契約。"""
        active_chars = current_outline.get("characters_active", []) if isinstance(current_outline, dict) else []
        if isinstance(active_chars, str):
            active_chars = [c.strip() for c in active_chars.split(",") if c.strip()]

        # 預設選取第一個活躍角色或主角為 POV
        pov_char = "主角"
        if active_chars:
            pov_char = active_chars[0]
        else:
            for ch in characters_list:
                if isinstance(ch, dict) and ch.get("role") in ("主角", "男主", "女主", "核心主角"):
                    pov_char = ch.get("name", "主角")
                    break

        # 擷取戲劇目標、功能定位與狀態位移
        summary = current_outline.get("chapter_summary", "") if isinstance(current_outline, dict) else ""
        goal = current_outline.get("scene_goal") or summary or "推進本章關鍵事件"
        conflict = current_outline.get("scene_conflict") or "遭遇現實阻礙或人際對抗"
        turn = current_outline.get("scene_turn") or "局勢或角色認知發生改變"
        outcome = current_outline.get("scene_outcome") or "達成部分目標或付出相應代價"
        scene_func = current_outline.get("scene_function") or "推進 (progression)"
        state_after = current_outline.get("story_state_after") or outcome

        return {
            "chapter_index": chapter_index,
            "pov_character": pov_char,
            "narrative_mode": "third_person_limited",
            "narrative_distance": "close",
            "thought_mode": "free_indirect",
            "scene_function": scene_func,
            "scene_goal": goal,
            "conflict": conflict,
            "turn": turn,
            "outcome": outcome,
            "state_after": state_after,
        }

    def build_character_states(
        self,
        current_outline: Dict[str, Any],
        characters_bible: Any,
        pov_character: str,
    ) -> List[Dict[str, Any]]:
        """針對本場景出場角色，提煉其即時心理狀態、知情邊界與語言傾向，而非傾倒底層設定表。"""
        char_list = []
        if isinstance(characters_bible, dict):
            char_list = characters_bible.get("characters", [])
        elif isinstance(characters_bible, list):
            char_list = characters_bible

        active_names = current_outline.get("characters_active", []) if isinstance(current_outline, dict) else []
        if isinstance(active_names, str):
            active_names = [c.strip() for c in active_names.split(",") if c.strip()]
        active_set = set(active_names)

        states = []
        for ch in char_list:
            if not isinstance(ch, dict):
                continue
            name = ch.get("name", "")
            # Writer context is strictly scoped: only plan-declared active characters.
            # If the plan has no active list, keep the legacy fallback for compatibility.
            if not active_set or name in active_set or name == pov_character:
                is_pov = (name == pov_character)

                # 提煉語言傾向
                sp = ch.get("speech_profile", {})
                if isinstance(sp, dict) and sp:
                    speech_desc = (
                        f"語域：{sp.get('default_register', '自然')}；"
                        f"句長：{sp.get('sentence_length', '中等')}；"
                        f"受壓反應：{sp.get('under_pressure', '冷靜簡練')}"
                    )
                else:
                    speech_desc = ch.get("speech_style") or "自然流暢，隨情境調整"

                want = ch.get("want", "")
                private_goal = want if want else "達成自身目標"
                # 提煉心理動機與反派/配角深度
                wound = ch.get("wound_origin")
                false_belief = ch.get("false_belief")
                off_goal = ch.get("off_screen_goal")

                psychological_summary = private_goal
                if false_belief:
                    psychological_summary += f"（核心偏執：{false_belief}）"
                if wound:
                    psychological_summary += f"（創傷原點：{wound}）"
                if off_goal:
                    psychological_summary += f"（場外追求：{off_goal}）"

                # 提煉知情範圍 (Knowledge Scope)
                knowledge = ch.get("initial_knowledge_scope", [])
                if not isinstance(knowledge, list):
                    knowledge = [str(knowledge)]

                state_item = {
                    "name": name,
                    "role": ch.get("role", "登場人物"),
                    "faction": ch.get("faction") or ch.get("affiliation") or "中立/獨立",
                    "is_pov": is_pov,
                    "public_attitude": f"對待他人：{ch.get('personality', ['冷靜'])[0] if isinstance(ch.get('personality'), list) and ch.get('personality') else '沈穩'}",
                    "private_motivation": psychological_summary,
                    "speech_profile_summary": speech_desc,
                    "knowledge_scope": knowledge if knowledge else ["已知自身經歷與當前場景目擊之情報"],
                    "state_source": "character_bible_scoped" if knowledge else "fallback",
                    "current_state_missing": False,
                }
                states.append(state_item)

        return states

    @staticmethod
    def _outline_brief(outline: Any) -> str:
        """Return only the adjacent-chapter fields that are useful for handoff."""
        if not isinstance(outline, dict):
            return ""
        idx = outline.get("chapter_index") or outline.get("chapter") or outline.get("chapter_number")
        title = outline.get("title") or outline.get("chapter_title") or ""
        goal = outline.get("scene_goal") or outline.get("purpose") or outline.get("chapter_summary") or outline.get("summary") or ""
        return f"第 {idx} 章｜{title}｜目的：{goal}" if idx else f"{title}｜目的：{goal}"

    def _format_adjacent_context(self, surrounding_plot: str) -> str:
        """Normalize runner handoff without exposing raw adjacent outline JSON."""
        if not surrounding_plot:
            return ""
        lines = []
        for line in str(surrounding_plot).splitlines():
            clean = line.strip()
            if not clean or clean.startswith("{") or clean.startswith("}"):
                continue
            if clean.startswith("【") or "第 " in clean and ("章" in clean):
                # Keep headings/brief lines; raw JSON keys are deliberately discarded.
                if any(key in clean for key in ("前一章", "後一章")):
                    lines.append(clean)
                elif not any(key in clean for key in ('"chapter_index"', '"events"', '"characters_active"')):
                    lines.append(clean)
        return "\n".join(lines)

    def _format_volume_context(self, vol_outline_context: str) -> str:
        """Keep volume direction, not full faction/outline payloads."""
        if not vol_outline_context:
            return ""
        keep = []
        for line in str(vol_outline_context).splitlines():
            clean = line.strip()
            if not clean or clean.startswith("{") or clean.startswith("}"):
                continue
            if any(marker in clean for marker in ("當前卷", "前一卷", "後一卷")):
                keep.append(clean)
            elif clean.startswith(("標題：", "大綱：")):
                keep.append(clean)
        return "\n".join(keep)

    def build_scene_beats(self, current_outline: Dict[str, Any]) -> List[str]:
        """提煉結構化拍點，相容舊版 events 與新版 scene_beats。"""
        if not isinstance(current_outline, dict):
            return []

        beats = []
        # 1. 優先使用新版 scene_beats
        if "scene_beats" in current_outline and isinstance(current_outline["scene_beats"], list):
            for idx, b in enumerate(current_outline["scene_beats"], 1):
                if isinstance(b, dict):
                    b_type = b.get("beat_type", "推進")
                    desc = b.get("description", "")
                    beats.append(f"{idx}. [{b_type}] {desc}")
                elif isinstance(b, str):
                    beats.append(f"{idx}. {b}")
            if beats:
                return beats

        # 2. 次選舊版 events
        if "events" in current_outline and isinstance(current_outline["events"], list):
            for idx, ev in enumerate(current_outline["events"], 1):
                if isinstance(ev, dict):
                    loc = f"（地點：{ev.get('location')}）" if ev.get("location") else ""
                    content = ev.get("content", "")
                    beats.append(f"{idx}. 行動推進{loc}：{content}")
                elif isinstance(ev, str):
                    beats.append(f"{idx}. {ev}")

        # 3. 若皆無，則由 summary 構成單拍點
        if not beats and current_outline.get("chapter_summary"):
            beats.append(f"1. 核心推進：{current_outline.get('chapter_summary')}")

        return beats

    def format_writer_prompt_context(
        self,
        novel_id: str,
        worldview_text: str,
        characters_bible: Any,
        current_outline: Dict[str, Any],
        surrounding_plot: str,
        vol_outline_context: str,
        clue_payoff_details: str,
        custom_style: str,
        chapter_index: int,
        user_prompt: Optional[str] = None,
        narrative_memory_context: Optional[str] = None,
    ) -> str:
        """將解構後的各元件格式化為乾淨、無 JSON 資料庫污染的寫作指引文字。"""
        # 1. 解析角色清單
        char_list = []
        if isinstance(characters_bible, dict):
            char_list = characters_bible.get("characters", [])
        elif isinstance(characters_bible, list):
            char_list = characters_bible

        # 2. 構建場景契約
        contract = self.build_scene_contract(current_outline, char_list, chapter_index)
        pov_char = contract["pov_character"]

        # 3. 構建角色狀態與知情邊界
        char_states = self.build_character_states(current_outline, characters_bible, pov_char)

        # 4. 構建戲劇拍點
        beats = self.build_scene_beats(current_outline)

        # 5. 檢索 Scoped Gold Rules
        keywords = [pov_char, contract.get("scene_goal", "")]
        gold_rules_block = load_scoped_gold_rules(
            novel_id=novel_id,
            agent_scope="chapter_writer",
            context_keywords=keywords,
            max_rules=8,
        )

        # 6. 組裝純淨文字區塊
        lines = []

        core_context = format_novel_core_context(novel_id, for_stage="writer")
        if core_context:
            lines.append(core_context)
            lines.append("")

        # (A) 場景契約與狀態位移
        lines.append(f"### 🎬【場景契約 (Scene Contract) - 第 {chapter_index} 章】")
        lines.append(f"- **場景功能定位 (Scene Function)**：{contract.get('scene_function', '推進 (progression)')}")
        lines.append(f"- **POV 視角人物**：{contract['pov_character']}（攝影機固定於此角色，以其感知、經驗與推論為限）")
        lines.append(f"- **敘事距離與模式**：{contract['narrative_mode']}（{contract['narrative_distance']} distance），支援自由間接引語 (Free Indirect Discourse)")
        lines.append(f"- **場景戲劇目標 (Goal)**：{contract['scene_goal']}")
        lines.append(f"- **核心阻礙衝突 (Conflict)**：{contract['conflict']}")
        lines.append(f"- **轉折點 (Turn)**：{contract['turn']}")
        lines.append(f"- **實質狀態位移 (Meaningful State Change)**：{contract.get('state_after', contract['outcome'])}")
        lines.append("")

        # (A2) 長程衝突因果防重複指引 (Conflict Novelty Guard)
        conflict_guard = ConflictLedger.build_anti_repetition_prompt_snippet(novel_id, chapter_index)
        if conflict_guard:
            lines.append(conflict_guard)
            lines.append("")

        # (A3) 未處置敘事診斷約束 (Unresolved Narrative Audits) —— 審計閉環：
        # 前文診斷若無人 resolve，自動餵給下一章 Writer，避免「有診斷、寫作照舊」。
        try:
            from backend import persistence as _db
            _audits = _db.get_narrative_audits(novel_id, unresolved_only=True, limit=5) or []
        except Exception:
            _audits = []
        if _audits:
            lines.append("### 🩺【前文敘事診斷待辦 (必須在本章規避或修補)】")
            for _a in _audits[:5]:
                _ch = _a.get("chapter_index", "?")
                _dim = _a.get("dimension", "")
                _rec = str(_a.get("recommendation") or "").strip()[:200]
                lines.append(f"  * 第 {_ch} 章 [{_dim}]：{_rec}")
            lines.append("*(以上為總監 2.0 對前文的正式診斷，請在本章落筆時主動規避同類問題；已改善的診斷請於敘事引擎頁標記處置)*")
            lines.append("")

        # (A4) 幾何結構角色、義務與跨距關聯 (Geometry-First Overlay & Cross Context)
        try:
            target_node_id = current_outline.get("geometry_node_id") if isinstance(current_outline, dict) else None
            geom_pkg = GeometryContextCompiler.compile(novel_id, chapter_index, target_node_id)
            if geom_pkg.has_geometry:
                overlay_block = geom_pkg.format_geometry_overlay()
                if overlay_block:
                    lines.append(overlay_block)
                    lines.append("")
                cross_block = geom_pkg.format_cross_context()
                if cross_block:
                    lines.append(cross_block)
                    lines.append("")
        except Exception as _geom_exc:
            pass

        # (B) 戲劇拍點推進
        lines.append("### ⚡【本章結構化推進拍點 (Scene Beats)】")
        if beats:
            for b in beats:
                lines.append(f"- {b}")
        else:
            lines.append("- 依大綱推進情節發展")
        lines.append("")

        # (B2) 世界觀設定運作機制與絕對邊界約束 (Setting Boundaries)
        setting_names = current_outline.get("setting_usage", []) if isinstance(current_outline, dict) else []
        setting_block = SettingRegistry.get_scoped_context_for_writer(novel_id, setting_names)
        if setting_block:
            lines.append(setting_block)
            lines.append("")

        # (C) 出場角色狀態與知情邊界
        lines.append("### 👥【出場角色即時狀態與語言傾向】")
        for cs in char_states:
            pov_tag = " [當前 POV 焦點]" if cs["is_pov"] else ""
            lines.append(f"**【{cs['name']}】** ({cs['role']} / 陣營：{cs['faction']}){pov_tag}")
            lines.append(f"  - 內在動機：{cs['private_motivation']}")
            lines.append(f"  - 語言人格：{cs['speech_profile_summary']}")
            lines.append(f"  - 知情邊界 (Knowledge Scope)：{', '.join(cs['knowledge_scope'])}")
        lines.append("")

        # (D) 相鄰章/卷方向：只保留 handoff 摘要，禁止 raw outline 漂入 Writer。
        adjacent = self._format_adjacent_context(surrounding_plot)
        volume_direction = self._format_volume_context(vol_outline_context)
        if adjacent or volume_direction:
            lines.append("### 🧭【相鄰章節與卷方向（僅供銜接，不得提前改寫未到章節事件）】")
            if adjacent:
                lines.append(adjacent)
            if volume_direction:
                lines.append(volume_direction)
            lines.append("")

        # (D) 連續性與時序記憶任務 (Graphiti Temporal Graph)
        active_char_names = [cs["name"] for cs in char_states]
        temporal_graph_context = TemporalGraphService.build_narrative_context(
            novel_id=novel_id,
            at_chapter=chapter_index,
            active_characters=active_char_names,
            max_facts=18
        )
        lines.append("### 🔗【敘事連續性與時序記憶約束 (Graphiti Memory)】")
        lines.append(temporal_graph_context)
        if narrative_memory_context and narrative_memory_context.strip():
            lines.append("")
            lines.append("▶ 前置章節概要與承接：")
            lines.append(narrative_memory_context.strip())
        if clue_payoff_details and clue_payoff_details.strip():
            lines.append("")
            lines.append("【本章伏筆與轉折任務】")
            lines.append(clue_payoff_details.strip())
            lines.append("*(請以自然情節、角色行動、對話或環境細節無痕融入，展現沉浸式文學質感)*")
        lines.append("")

        # (D2) 術語庫名詞邊界約束 (Glossary)
        terms = get_terms(novel_id)
        if terms:
            context_haystack = json.dumps(current_outline, ensure_ascii=False) + " " + " ".join(active_char_names) + " " + contract.get("scene_goal", "")
            matched_terms = [t for t in terms if t.get("term") and t["term"] in context_haystack]
            selected_terms = matched_terms[:15] if matched_terms else terms[:10]
            if selected_terms:
                lines.append("### 📖【術語庫與名詞約束 (Story Terms - 嚴格維持全書一致性)】")
                for t in selected_terms:
                    cat = f"[{t['category']}] " if t.get("category") else ""
                    lines.append(f"- **{cat}{t['term']}**：{t['definition']}")
                lines.append("")

        # (E) 世界觀背景（精簡版）。只接受已由上游 stage-scope 篩選的資料。
        if worldview_text:
            lines.append("### 🌍【相關世界觀法則與環境脈絡】")
            # Never silently compact canonical writer requirements. This stage-scope boundary
            # is retained with 8000-char safe headroom to prevent law/rule truncation.
            clean_wv = worldview_text[:8000] if len(worldview_text) > 8000 else worldview_text
            lines.append(clean_wv)
            lines.append("")

        # (F) 使用者額外提示詞
        if user_prompt and str(user_prompt).strip():
            lines.append("### ✍️【使用者特定創作指示（最高優先級要求）】")
            lines.append(f"> 導演/作者特別指示：{str(user_prompt).strip()}")
            lines.append("*(請作家在落實本章情節、對白與人物行動時，務必具體遵循上述要求)*")
            lines.append("")

        # (G) Gold Rules
        if gold_rules_block:
            lines.append(gold_rules_block)
            lines.append("")

        # (H) 風格基調
        lines.append(f"### 🎨【寫作風格基調】\n{custom_style or '文筆洗鍊、節奏緊湊、善用動詞推進、對白富有張力。'}")

        return "\n".join(lines)


# Singleton
_GLOBAL_WRITER_CONTEXT_BUILDER = WriterContextBuilder()


def get_writer_context_builder() -> WriterContextBuilder:
    return _GLOBAL_WRITER_CONTEXT_BUILDER


def build_writer_scene_context(
    novel_id: str,
    worldview_text: str,
    characters_bible: Any,
    current_outline: Dict[str, Any],
    surrounding_plot: str,
    vol_outline_context: str,
    clue_payoff_details: str,
    custom_style: str,
    chapter_index: int,
    user_prompt: Optional[str] = None,
    narrative_memory_context: Optional[str] = None,
) -> str:
    """便捷函數：為 Chapter Writer 組裝情境化上下文。"""
    return _GLOBAL_WRITER_CONTEXT_BUILDER.format_writer_prompt_context(
        novel_id=novel_id,
        worldview_text=worldview_text,
        characters_bible=characters_bible,
        current_outline=current_outline,
        surrounding_plot=surrounding_plot,
        vol_outline_context=vol_outline_context,
        clue_payoff_details=clue_payoff_details,
        custom_style=custom_style,
        chapter_index=chapter_index,
        user_prompt=user_prompt,
        narrative_memory_context=narrative_memory_context,
    )
