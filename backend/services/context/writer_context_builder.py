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
        time_setting = current_outline.get("time_setting") or "承接前章時間線"
        scene_setting = current_outline.get("scene_setting") or current_outline.get("location") or "依大綱指定場景"

        return {
            "chapter_index": chapter_index,
            "pov_character": pov_char,
            "narrative_mode": "third_person_limited",
            "narrative_distance": "close",
            "thought_mode": "free_indirect",
            "scene_function": scene_func,
            "time_setting": time_setting,
            "scene_setting": scene_setting,
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

        found_names = {s["name"] for s in states}
        for aname in active_names:
            if aname and aname not in found_names:
                is_one_off = any(k in aname for k in ("路人", "侍衛", "掌櫃", "小二", "店員", "乘客", "士兵", "隨從", "弟子", "刺客", "管家", "守衛"))
                role_label = "單次過場角色/路人" if is_one_off else "大綱出場配角"
                states.append({
                    "name": aname,
                    "role": role_label,
                    "faction": "中立/環境人物",
                    "is_pov": (aname == pov_character),
                    "public_attitude": "對待他人：言行專注當前現場互動，依情境做出自然反應",
                    "private_motivation": "履行當前場景情節功能與日常生存動機",
                    "speech_profile_summary": "自然簡練，貼合身份",
                    "knowledge_scope": ["僅知當前現場目擊之事"],
                    "state_source": "scene_outline_scoped",
                    "current_state_missing": False,
                })

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

    def _format_narrative_continuity_context(self, raw_packet: Dict[str, Any], chapter_index: int = 1) -> str:
        """
        Converts narrative memory packet into clean, literary continuity prose without raw JSON dumps.
        """
        if not raw_packet or not isinstance(raw_packet, dict):
            if chapter_index <= 1:
                return "▶ 本章為故事開篇第一章，請建立核心世界觀質感與人物初始處境。"
            return ""

        lines = []
        if chapter_index <= 1:
            lines.append("▶ 本章為故事開篇第一章，請建立核心世界觀質感與人物初始處境。")
            return "\n".join(lines)

        tail = raw_packet.get("previous_chapter_tail")
        if tail and str(tail).strip():
            lines.append(f"▶ 前章結尾現場場景留白（請自然承接情緒餘波與動作流向）：\n{str(tail).strip()}")

        active_chars = raw_packet.get("active_characters") or []
        if isinstance(active_chars, list) and active_chars:
            char_lines = []
            for ac in active_chars:
                if isinstance(ac, dict) and ac.get("name"):
                    st = ac.get("state") or ac.get("state_change") or "維持警備狀態"
                    char_lines.append(f"  - **{ac['name']}**：{st}")
                elif isinstance(ac, str):
                    char_lines.append(f"  - {ac}")
            if char_lines:
                lines.append("▶ 出場人物當前身心狀態：\n" + "\n".join(char_lines))

        recent_memories = raw_packet.get("recent_chapter_memories") or []
        if isinstance(recent_memories, list) and recent_memories:
            mem_lines = []
            # 固定預算精煉：保留最近 3 章情勢演變（單章限制 150 字），既確保前文連貫，又杜絕歷史無節制堆疊
            scoped_memories = recent_memories[-3:]
            for m in scoped_memories:
                if isinstance(m, dict):
                    idx = m.get("chapter_index", "")
                    summ = m.get("chapter_summary") or m.get("summary") or ""
                    if summ:
                        clean_summ = str(summ).strip()[:150]
                        mem_lines.append(f"  - 第 {idx} 章情勢演變：{clean_summ}")
            if mem_lines:
                lines.append("▶ 近期情勢演進脈絡（固定預算銜接）：\n" + "\n".join(mem_lines))

        long_range = raw_packet.get("long_range_arc_retrospective") or []
        if isinstance(long_range, list) and long_range:
            # 長程回顧收斂至核心 3 條重要進展
            recap_lines = [f"  - {str(item).strip()[:120]}" for item in long_range if str(item).strip()]
            if recap_lines:
                lines.append("▶ 長程關鍵主線進展：\n" + "\n".join(recap_lines[-3:]))

        character_history = raw_packet.get("character_emotional_and_relationship_history") or []
        if isinstance(character_history, list) and character_history:
            history_lines = []
            for record in character_history:
                if not isinstance(record, dict) or not record.get("character"):
                    continue
                name = str(record["character"])
                events = record.get("recorded_moments") or []
                if not events:
                    continue
                history_lines.append(f"  - **{name}** 的過往重要轉變：")
                # 每個角色僅保留最近 2 筆核心變化
                for event in events[-2:]:
                    if not isinstance(event, dict):
                        continue
                    details = []
                    if event.get("state_change"):
                        details.append(f"心理／立場：{event['state_change']}")
                    if event.get("relationship_change"):
                        details.append(f"關係：{event['relationship_change']}")
                    if details:
                        history_lines.append(f"    · 第 {event.get('chapter_index', '?')} 章：" + "；".join(details))
            if history_lines:
                lines.append("▶ 本章活躍角色動態情感與關係記憶（不可覆寫既定事實）：\n" + "\n".join(history_lines))

        arc_summary = raw_packet.get("current_arc_summary")
        if isinstance(arc_summary, str) and arc_summary.strip():
            lines.append(f"▶ 當前階段主線大勢：{arc_summary.strip()}")
        elif isinstance(arc_summary, dict):
            arc_text = str(arc_summary.get("arc_summary") or "").strip()
            if arc_text:
                lines.append(f"▶ 近階段主線大勢（已寫正文的跨章回顧）：{arc_text}")
            progress = arc_summary.get("character_arc_progress") or []
            progress_lines = []
            if isinstance(progress, list):
                for item in progress:
                    if not isinstance(item, dict):
                        continue
                    changes = [
                        str(item.get(field)).strip()
                        for field in ("latest_state_change", "latest_relationship_change")
                        if item.get(field) and str(item.get(field)).strip()
                    ]
                    if changes:
                        progress_lines.append(f"  - {item.get('name', '角色')}：" + "；".join(changes))
            if progress_lines:
                lines.append("▶ 階段內角色狀態變化：\n" + "\n".join(progress_lines))

        return "\n\n".join(lines).strip()

    def _format_clue_payoff_details(self, details: Any) -> str:
        """將伏筆藍圖與轉折任務格式化為沉浸式自然指示，避免 JSON 原始結構洩漏。"""
        if not details:
            return ""
        if isinstance(details, str):
            try:
                data = json.loads(details)
            except Exception:
                return details.strip()
        else:
            data = details
        if isinstance(data, list):
            lines = []
            for item in data:
                if isinstance(item, dict):
                    name = item.get("clue_name") or item.get("seed_text") or item.get("name") or "伏筆"
                    inst = item.get("instruction") or item.get("clue_instruction") or item.get("payoff_event") or item.get("desc") or ""
                    lines.append(f"- 伏筆/任務「{name}」：{inst}")
                elif isinstance(item, str):
                    lines.append(f"- {item}")
            return "\n".join(lines)
        return str(data).strip()

    def format_writer_prompt_context(
        self,
        novel_id: str = "",
        worldview_text: str = "",
        characters_bible: Any = None,
        current_outline: Optional[Dict[str, Any]] = None,
        surrounding_plot: str = "",
        vol_outline_context: str = "",
        clue_payoff_details: str = "",
        custom_style: str = "",
        chapter_index: int = 1,
        user_prompt: Optional[str] = None,
        narrative_memory_context: Optional[str] = None,
        fix_mode: bool = False,
        fix_targets: Optional[List[Dict[str, Any]]] = None,
        banned_hits: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """將解構後的各元件格式化為乾淨、無 JSON 資料庫污染的寫作指引文字。"""
        current_outline = current_outline or {}
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

        # (Top) 修正輪最高指令置頂與禁用原文清單
        if fix_mode and user_prompt and str(user_prompt).strip():
            lines.append("### 🚨【本次修正最高指令：覆寫其他風格要求】")
            lines.append(f"> 導演/作者特別指示：\n{str(user_prompt).strip()}")
            lines.append("")

        if fix_mode and banned_hits:
            lines.append("### 🚫【本次禁用原文：出現即判失敗】")
            lines.append("> 以下為正文已偵測到的嚴重公式化套路句/口癖，本輪生成必須徹底重寫或定點消除，出現任一條即視為失敗：")
            for h in banned_hits:
                p_idx = h.get("paragraph_index", 1)
                sent = h.get("matched_sentence", "")
                lbl = h.get("pattern_label", "")
                ctx = h.get("context_20chars", "")
                ctx_str = f"（前後文：…{ctx}…）" if ctx else ""
                lines.append(f"- 第 {p_idx} 段：『{sent}』[{lbl}]{ctx_str}")
            lines.append("")

        # (A0) 紅線禁令：嚴禁元敘事與開篇套路
        lines.append("### 🚫【紅線禁令：嚴禁元敘事與開篇套路】")
        lines.append("- **嚴禁元敘事洩漏**：正文嚴禁出現「那是上一章...」、「正如前一章所述」、「承接上一章情節」等破壁敘事詞彙；小說必須 100% 維持在沉浸式故事世界內部，禁止旁白對讀者或寫作大綱進行元評論。")
        lines.append("- **開篇切入去重**：嚴禁連續跨章復用相同的開頭場景（如反覆以網咖、霓虹燈光、夜雨等定型意象開局）；每一章開篇必須更換全新的感官切入點、對白或突發行動。")
        lines.append("")

        core_context = format_novel_core_context(novel_id, for_stage="writer")
        if core_context:
            lines.append(core_context)
            lines.append("")

        # (A) 場景契約與時空邊界
        lines.append(f"### 🎬【場景契約 (Scene Contract) - 第 {chapter_index} 章】")
        lines.append(f"- **本章指定時間 (Time)**：【{contract.get('time_setting', '承接前章時間線')}】")
        lines.append(f"- **本章指定地點 (Location)**：【{contract.get('scene_setting', '依大綱指定場景')}】")
        lines.append(f"- **POV 視角人物**：{contract['pov_character']}（攝影機固定於此角色，以其感知、經驗與推論為限）")
        lines.append(f"- **場景功能定位 (Scene Function)**：{contract.get('scene_function', '推進 (progression)')}")
        lines.append(f"- **敘事距離與模式**：{contract['narrative_mode']}（{contract['narrative_distance']} distance），支援自由間接引語 (Free Indirect Discourse)")
        lines.append(f"- **場景戲劇目標 (Goal)**：{contract['scene_goal']}")
        lines.append(f"- **核心阻礙衝突 (Conflict)**：{contract['conflict']}")
        lines.append(f"- **轉折點 (Turn)**：{contract['turn']}")
        lines.append(f"- **實質狀態位移 (Meaningful State Change)**：{contract.get('state_after', contract['outcome'])}")
        lines.append("")

        if fix_mode:
            lines.append("### 🔓【本輪允許偏離】")
            lines.append("- 允許更換破局手段、代價場景、微動作描寫與心理博弈細節，不視為偏離大綱；以打破套路與解決診斷為最高準則。")
            lines.append("")

        lines.append("### 🏛️【不可違背之場景時空公理（剛性約束）】")
        lines.append(f"- **嚴格鎖定指定地點**：全章核心情節必須在【{contract.get('scene_setting', '依大綱指定場景')}】展開，嚴禁擅自更換至其他無關地點或延用前章已結束之舊場景。")
        lines.append(f"- **嚴格鎖定時間流向**：本章時間為【{contract.get('time_setting', '承接前章時間線')}】。若大綱註明經過數小時或數天，開篇必須體現時間流逝與情境切換，嚴禁無縫秒接上一秒動作（例如前章已吃完或放下的食物、已結束的現場對話）。")
        lines.append("")

        # (A2) 長程衝突因果防重複指引 (Conflict Novelty Guard)
        conflict_guard = ConflictLedger.build_anti_repetition_prompt_snippet(novel_id, chapter_index)
        if conflict_guard:
            lines.append(conflict_guard)
            lines.append("")

        # (A3) 未處置敘事診斷約束 (Unresolved Narrative Audits) —— 審計閉環：
        # 前文診斷若無人 resolve，自動餵給下一章 Writer，避免「有診斷、寫作照舊」。
        # 修正輪直接傳入本次待修 targets；正常輪嚴格過濾：僅載入當前章之前的真實歷史診斷 (chapter_index < 當前章)，杜絕未來未寫章節之審計反向倒灌。
        try:
            from backend import persistence as _db
            if fix_mode and fix_targets:
                _audits = fix_targets
            elif chapter_index and chapter_index > 1:
                _audits = _db.get_narrative_audits(
                    novel_id, unresolved_only=True, limit=5, max_chapter=chapter_index - 1
                ) or []
            else:
                _audits = []
        except Exception:
            _audits = []

        # (A3-b) 前章代價欠帳警報：若上一章存在零代價破局的未處置診斷，強制注入提醒
        _cost_debt_alerts = []
        try:
            if chapter_index > 1:
                from backend import persistence as _db2
                _prev_audits = _db2.get_narrative_audits(
                    novel_id, chapter_index=chapter_index - 1, unresolved_only=True, limit=10
                ) or []
                _cost_debt_alerts = [
                    a for a in _prev_audits
                    if a.get("dimension") in ("ability_constraints", "conflict_novelty")
                ]
        except Exception:
            _cost_debt_alerts = []

        if _cost_debt_alerts:
            lines.append("### 🚨【前章代價欠帳警報（剛性約束）】")
            lines.append(
                "主角在上一章動用了高位能力或高階策略破局，但尚未支付實質代價。"
                "本章情節**必須**體現該行動的代價引力（後遺症、追查壓力、資源匱乏或社會關係損耗），"
                "不得連續兩章零代價推進。"
            )
            for _ca in _cost_debt_alerts[:3]:
                _rec = str(_ca.get("recommendation") or "").strip()[:200]
                lines.append(f"  * 前章未償診斷 [{_ca.get('dimension', '')}]：{_rec}")
            lines.append("")

        if _audits:
            lines.append("### 🩺【前文歷史敘事診斷待辦 (必須在本章規避或修補)】")
            for _a in _audits[:5]:
                _ch = _a.get("chapter_index", "?")
                _dim = _a.get("dimension", "")
                _rec = str(_a.get("recommendation") or "").strip()[:200]
                lines.append(f"  * 第 {_ch} 章 [{_dim}]：{_rec}")
            lines.append("*(以上為總監對歷史前文的正式診斷，請在本章落筆時主動規避同類問題)*")
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
        # (D) 連續性與時序記憶任務 (Graphiti Temporal Graph - 聚焦本章活躍元素)
        active_char_names = [cs["name"] for cs in char_states]
        temporal_graph_context = TemporalGraphService.build_narrative_context(
            novel_id=novel_id,
            at_chapter=chapter_index,
            active_characters=active_char_names,
            max_facts=8
        )
        lines.append("### 🔗【敘事連續性與時序記憶約束 (Graphiti Memory)】")
        lines.append(temporal_graph_context)
        if narrative_memory_context:
            if isinstance(narrative_memory_context, dict):
                formatted_mem = self._format_narrative_continuity_context(narrative_memory_context, chapter_index)
                if formatted_mem.strip():
                    lines.append("")
                    lines.append(formatted_mem)
            elif isinstance(narrative_memory_context, str) and narrative_memory_context.strip():
                try:
                    parsed = json.loads(narrative_memory_context)
                    if isinstance(parsed, dict):
                        formatted_mem = self._format_narrative_continuity_context(parsed, chapter_index)
                        if formatted_mem.strip():
                            lines.append("")
                            lines.append(formatted_mem)
                    else:
                        lines.append("")
                        lines.append("▶ 前置章節概要與承接：")
                        lines.append(narrative_memory_context.strip())
                except Exception:
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
            chapter_haystack = (
                json.dumps(current_outline, ensure_ascii=False) + " " + " ".join(active_char_names) + " " +
                contract.get("scene_goal", "") + " " + (clue_payoff_details or "")
            )
            broader_haystack = " ".join(((worldview_text or "")[:8000], narrative_memory_context or ""))
            directly_relevant = [t for t in terms if t.get("term") and t["term"] in chapter_haystack]
            context_relevant = [
                t for t in terms
                if t.get("term") and t["term"] in broader_haystack and t not in directly_relevant
            ]
            selected_terms = (directly_relevant + context_relevant)[:15]
            if not selected_terms:
                # Prefer hand-curated entries and terms recently updated near this chapter,
                # rather than an arbitrary alphabetical slice of a large glossary.
                selected_terms = sorted(
                    terms,
                    key=lambda t: (
                        0 if t.get("source_chapter") is None else 1,
                        abs(int(t.get("updated_chapter") or chapter_index) - int(chapter_index)),
                    ),
                )[:10]
            if selected_terms:
                lines.append("### 📖【術語庫與名詞約束 (Story Terms - 剛性約束與唯一性)】")
                lines.append("> 剛性約束：以下專有名詞為唯一標準名稱。嚴禁自造替代名詞或進行近義詞替換，行文中涉及相關概念時必須強制沿用。")
                lines.append("> 備註若以「禁用別稱：」標記別稱，正文不得使用該稱呼；其他備註僅作參考，不得推定為禁用詞。")
                for t in selected_terms:
                    cat = f"[{t['category']}] " if t.get("category") else ""
                    note = f" (備註/約束：{t['notes']})" if t.get("notes") else ""
                    lines.append(f"- **{cat}{t['term']}**：{t['definition']}{note}")
                lines.append("")

        # (E) 世界觀背景（精簡版）。只接受已由上游 stage-scope 篩選的資料。
        if worldview_text:
            lines.append("### 🌍【相關世界觀法則與環境脈絡】")
            # Never silently compact canonical writer requirements. This stage-scope boundary
            # is retained with 8000-char safe headroom to prevent law/rule truncation.
            clean_wv = worldview_text[:8000] if len(worldview_text) > 8000 else worldview_text
            lines.append(clean_wv)
            lines.append("")

        # (F) 使用者額外提示詞（正常輪保留，修正輪已置頂）
        if not fix_mode and user_prompt and str(user_prompt).strip():
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
    fix_mode: bool = False,
    fix_targets: Optional[List[Dict[str, Any]]] = None,
    banned_hits: Optional[List[Dict[str, Any]]] = None,
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
        fix_mode=fix_mode,
        fix_targets=fix_targets,
        banned_hits=banned_hits,
    )
