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

from backend import persistence as db
from backend.services.gold_rules.gold_rules_manager import load_scoped_gold_rules


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

        # 擷取戲劇目標與衝突
        summary = current_outline.get("chapter_summary", "") if isinstance(current_outline, dict) else ""
        goal = current_outline.get("scene_goal") or summary or "推進本章關鍵事件"
        conflict = current_outline.get("scene_conflict") or "遭遇現實阻礙或人際對抗"
        turn = current_outline.get("scene_turn") or "局勢或角色認知發生改變"
        outcome = current_outline.get("scene_outcome") or "達成部分目標或付出相應代價"

        return {
            "chapter_index": chapter_index,
            "pov_character": pov_char,
            "narrative_mode": "third_person_limited",
            "narrative_distance": "close",
            "thought_mode": "free_indirect",
            "scene_goal": goal,
            "conflict": conflict,
            "turn": turn,
            "outcome": outcome,
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
            # 若無明確指定活躍清單，或該角色在活躍名單內，或該角色為 POV
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

                # 提煉目標
                want = ch.get("want", "")
                need = ch.get("need", "")
                private_goal = want if want else "達成自身目標"

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
                    "private_motivation": private_goal,
                    "speech_profile_summary": speech_desc,
                    "knowledge_scope": knowledge if knowledge else ["已知自身經歷與當前場景目擊之情報"],
                }
                states.append(state_item)

        return states

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

        # (A) 場景契約
        lines.append(f"### 🎬【場景契約 (Scene Contract) - 第 {chapter_index} 章】")
        lines.append(f"- **POV 視角人物**：{contract['pov_character']}（攝影機固定於此角色，以其感知、經驗與推論為限）")
        lines.append(f"- **敘事距離與模式**：{contract['narrative_mode']}（{contract['narrative_distance']} distance），支援自由間接引語 (Free Indirect Discourse)")
        lines.append(f"- **場景戲劇目標 (Goal)**：{contract['scene_goal']}")
        lines.append(f"- **核心阻礙衝突 (Conflict)**：{contract['conflict']}")
        lines.append(f"- **轉折點 (Turn)**：{contract['turn']}")
        lines.append(f"- **結果與狀態改變 (Outcome)**：{contract['outcome']}")
        lines.append("")

        # (B) 戲劇拍點推進
        lines.append("### ⚡【本章結構化推進拍點 (Scene Beats)】")
        if beats:
            for b in beats:
                lines.append(f"- {b}")
        else:
            lines.append("- 依大綱推進情節發展")
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

        # (D) 連續性與伏筆任務
        lines.append("### 🔗【敘事連續性與記憶約束】")
        lines.append(narrative_memory_context or "（第一章開篇或無前置章節記憶）")
        if clue_payoff_details and clue_payoff_details.strip():
            lines.append("")
            lines.append("【本章伏筆與轉折任務】")
            lines.append(clue_payoff_details.strip())
            lines.append("*(請以自然情節、角色行動、對話或環境細節無痕融入，嚴禁抽離故事刻意說明)*")
        lines.append("")

        # (E) 世界觀背景（精簡版）
        if worldview_text:
            lines.append("### 🌍【相關世界觀法則與環境脈絡】")
            # 限制長度，避免世界觀傾倒
            clean_wv = worldview_text[:4000] if len(worldview_text) > 4000 else worldview_text
            lines.append(clean_wv)
            lines.append("")

        # (F) 使用者額外提示詞
        if user_prompt and str(user_prompt).strip():
            lines.append("### ✍️【使用者特定創作指示】")
            lines.append(str(user_prompt).strip())
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
