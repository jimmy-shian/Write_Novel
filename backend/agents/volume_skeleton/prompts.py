# -*- coding: utf-8 -*-
"""
Prompt Builder (隔離的提示詞構建與拼接層)
負責將系統提示詞與執行期資料做字串插值、拼接，確保 agents.py 只有純粹的核心邏輯與資料庫存取。
"""

import json
from backend.schemas import agent_json
from backend import persistence as db
from backend.schemas.agent_json import CHARACTER_BASIC_FIELDS
from backend.prompts.prompt_main import (
    STORY_ARCHITECT_PROMPT,
    STORY_ARCHITECT_GUIDELINES,
    VOLUMES_PLANNER_PROMPT,
    VOLUMES_PLANNER_GUIDELINES,
    VOLUME_SKELETON_PROMPT,
    VOLUME_SKELETON_GUIDELINES,
    CHARACTER_DESIGNER_PROMPT,
    CHARACTER_DESIGNER_GUIDELINES,
    FORESHADOWING_ORCHESTRATOR_PROMPT,
    FORESHADOWING_ORCHESTRATOR_GUIDELINES,
    CHAPTER_WRITER_PROMPT,
    CHAPTER_WRITER_GUIDELINES,
    VOLUME_SKELETON_PROMPT_PLUS,
    CHARACTER_DESIGNER_PROMPT_PLUS
)
from backend.prompts.prompt_detail_modifier import (
    EDITOR_PROMPT,
    INCREMENTAL_CHARACTER_PROMPT,
    INCREMENTAL_CHARACTER_APPEND_PROMPT
)
from backend.prompts.prompt_instructions import (
    CO_PILOT_ORCHESTRATOR_PROMPT,
    DIRECTOR_COMMON_FOOTER
)
from backend.prompts.output_contracts import (
    DIRECTOR_DECISION_KEY_CONTRACT,
    DIRECTOR_HARD_VALIDATION_POLICY,
    DIRECTOR_MANDATORY_INSPECTION_POLICY,
    DIRECTOR_TOOL_CALL_CONTRACT,
    STRICT_JSON_KEY_CONTRACT,
)
from backend.prompts.json_output import format_json_schema_prompt, get_json_schema_prompt_snippet

# --- 世界觀摘要輔助函數 ---
# 用於提取世界觀的關鍵摘要，避免過長的上下文導致 API 失敗
MAX_WORLDVIEW_SUMMARY_LENGTH = 36000
MAX_MACRO_OUTLINE_LENGTH = 12000
MAX_DIRECTOR_WORLDVIEW_LENGTH = 42000
MAX_DIRECTOR_CHARACTERS_LENGTH = 36000
MAX_DIRECTOR_PLOT_LENGTH = 52000
MAX_DIRECTOR_PROSE_LENGTH = 32000
MAX_DIRECTOR_REPORT_LENGTH = 30000
MAX_GOLD_RULES_CONTEXT_LENGTH = 16000

# --- 角色基本設定輔助函數 ---
# 定義角色只需要傳入的基本欄位，過濾掉冗長的背景故事等欄位
# 核心欄位：name 和 personality 是必留的，其他可以過濾
# CHARACTER_BASIC_FIELDS 定義在 agent_json.py 中，供各模組統一引用

MAX_CHARACTERS_SUMMARY_LENGTH = 26000

from backend.prompts.common.context import *

def build_volume_skeleton_planner_messages(
    worldview_text,
    volume_index,
    current_vol,
    start_ch,
    end_ch,
    vol_chapter_count,
    surrounding_context,
    precalc_clues,
    user_prompt,
    novel_id=None,
    total_volume_chapters=None,
    vol_start_ch=None,
    vol_end_ch=None,
    prior_chapters_context="",
    batch_num=1,
    total_batches=1,
):
    """卷骨架大綱規劃師提示詞拼接（支援批次生成 1-8, 9-16 等，附上本卷宏觀大綱與前文既有骨架）"""
    schema_snippet = get_json_schema_prompt_snippet("skeleton")
    system_prompt = f"{VOLUME_SKELETON_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{VOLUME_SKELETON_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Volume Skeleton Planner / 卷章節骨架規劃師",
        "- 經後端挑選的世界觀背景。\n- 指定卷的標題、全卷概要、時間線、序列上下文、適用規則與全卷/當前批次章節範圍。\n- 本卷前文已生成章節脈絡與 Python 預計算的逐章 allocated_tasks 表。",
        f"生成指定批次範圍（第 {start_ch} 至 {end_ch} 章，共 {vol_chapter_count} 章）的章節元素契約與骨架，嚴密承接前文章節脈絡與全卷大綱，並把預計算任務與角色元素填入對應章節。",
        f"輸出 chapters_skeleton JSON；chapter_index 必須完整連續覆蓋指定批次範圍（第 {start_ch} 至 {end_ch} 章）。每章確立完整元素契約（時空、出場角色、拍點與世界觀運作），並支援大綱期新增角色。"
    )

    vol_title = current_vol.get("title", f"第 {volume_index} 卷")
    vol_summary = current_vol.get("summary", "")
    vol_tot = total_volume_chapters or current_vol.get("chapter_count", end_ch)
    v_start = vol_start_ch or start_ch
    v_end = vol_end_ch or end_ch

    total_vol_range = f"第 {v_start} 至 {v_end} 章（全卷共 {vol_tot} 章）"

    volume_macro_context = {
        "volume_index": volume_index,
        "volume_title": vol_title,
        "total_volume_range": total_vol_range,
        "full_volume_chapter_range": [v_start, v_end],
        "full_volume_total_chapters": vol_tot,
        "volume_summary": vol_summary,
        "conflict_archetype": current_vol.get("conflict_archetype", "未指定"),
        "anti_template": current_vol.get("anti_template", "無特定禁用模板"),
        "factions": current_vol.get("factions", []),
        "time_timeline": current_vol.get("time_timeline", ""),
        "sequence_context": current_vol.get("sequence_context", ""),
        "applicable_rules": current_vol.get("applicable_rules", []),
    }

    current_batch_task = {
        "volume_index": volume_index,
        "volume_title": vol_title,
        "current_batch": f"{batch_num}/{total_batches}",
        "batch_chapter_range": [start_ch, end_ch],
        "batch_chapter_count": vol_chapter_count,
        "target_chapter_indexes": list(range(start_ch, end_ch + 1)),
    }
    
    core_context = f"{format_novel_core_context(novel_id)}\n\n" if novel_id else ""
    prior_section = f"\n{prior_chapters_context}\n" if prior_chapters_context else ""

    geom_section = ""
    if novel_id:
        try:
            from backend.persistence import load_geometry_graph
            graph = load_geometry_graph(novel_id)
            if graph:
                # 1. 注入 VolumeContainer.semantic (themes, core conflicts) 到 volume_macro_context
                vol_container = next((v for v in graph.volumes.values() if v.volume_index == volume_index), None)
                if vol_container and vol_container.semantic:
                    vol_theme = vol_container.semantic.get("theme") or vol_container.semantic.get("volume_theme")
                    vol_conflict = vol_container.semantic.get("core_conflict") or vol_container.semantic.get("conflict_core")
                    if vol_theme:
                        volume_macro_context["volume_theme"] = vol_theme
                    if vol_conflict:
                        volume_macro_context["core_conflict"] = vol_conflict
                    volume_macro_context["volume_semantic"] = vol_container.semantic

                # 2. 幾何圖譜節點與邊的語義覆蓋 (Geometry Graph Overlay)
                if graph.nodes:
                    node_lines = ["【幾何圖譜結構角色與前後義務 (Geometry Graph Overlay)】"]
                    for ch_num in range(start_ch, end_ch + 1):
                        ch_nodes = graph.get_chapter_nodes(ch_num)
                        if ch_nodes:
                            n = ch_nodes[0]
                            role = n.structural_role.value if hasattr(n.structural_role, "value") else str(n.structural_role)
                            in_edges = graph.get_incoming_edges(n.node_id)
                            out_edges = graph.get_outgoing_edges(n.node_id)

                            def _edge_desc(e, direction):
                                e_type = e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)
                                causal = (e.semantic.get("causal_link") or e.semantic.get("dramatic_clash")) if isinstance(getattr(e, "semantic", None), dict) else ""
                                link = f"{e_type} 來自節點 {e.source}" if direction == "in" else f"{e_type} 至節點 {e.target}"
                                label = "因果" if direction == "in" else "義務"
                                return link + (f" ({label}: {causal})" if causal else "")

                            in_desc = [_edge_desc(e, "in") for e in in_edges[:2]]
                            out_desc = [_edge_desc(e, "out") for e in out_edges[:2]]

                            node_info = f"- 第 {ch_num} 章（節點 `{n.node_id}`）：結構角色 `{role}` | 線程 `{n.primary_thread}`"

                            # 注入 node.semantic (internal_shift, dramatic_choice, focus_character)
                            if n.semantic and isinstance(n.semantic, dict):
                                focus_c = n.semantic.get("focus_character")
                                shift = n.semantic.get("internal_shift")
                                choice = n.semantic.get("dramatic_choice")
                                if focus_c:
                                    node_info += f" | 焦點角色: {focus_c}"
                                if shift:
                                    node_info += f" | 心境位移: {shift}"
                                if choice:
                                    node_info += f" | 抉擇代價: {choice}"

                            if in_desc:
                                node_info += f" | 前置因果承接: {'; '.join(in_desc)}"
                            if out_desc:
                                node_info += f" | 後續結構義務: {'; '.join(out_desc)}"
                            node_lines.append(node_info)

                    # 3. 注入本批次活躍線程人物綁定 (Active Character Thread Bindings)
                    active_threads = set()
                    for ch_num in range(start_ch, end_ch + 1):
                        for cn in graph.get_chapter_nodes(ch_num):
                            if cn.primary_thread:
                                active_threads.add(cn.primary_thread)

                    thread_binding_lines = []
                    for t_id in sorted(active_threads):
                        t_obj = graph.threads.get(t_id)
                        if t_obj and t_obj.semantic and isinstance(t_obj.semantic, dict):
                            b_data = t_obj.semantic.get("character_binding")
                            if b_data and isinstance(b_data, dict):
                                c_name = b_data.get("character_name") or b_data.get("character") or "未知"
                                arc_t = b_data.get("arc_theme") or ""
                                flaw = b_data.get("flaw_to_overcome") or ""
                                t_line = f"- 線程 `{t_id}`: 綁定角色 `{c_name}`"
                                if arc_t:
                                    t_line += f" | 弧線主題: {arc_t}"
                                if flaw:
                                    t_line += f" | 待克服心魔: {flaw}"
                                thread_binding_lines.append(t_line)

                    if thread_binding_lines:
                        node_lines.append("\n【幾何線程人物綁定與弧線契約 (Active Character Thread Bindings)】")
                        node_lines.extend(thread_binding_lines)

                    if len(node_lines) > 1:
                        geom_section = "\n" + "\n".join(node_lines) + "\n"
        except Exception:
            pass

    user_content = f"""{core_context}【世界觀背景】
{worldview_text}

【第 {volume_index} 卷宏觀全卷大綱與設定 (Volume Outline & Settings)】
{json.dumps(volume_macro_context, ensure_ascii=False, indent=2)}

【本次骨架生成任務：第 {volume_index} 卷分批生成（第 {start_ch} 至 {end_ch} 章）】
{json.dumps(current_batch_task, ensure_ascii=False, indent=2)}

👉 **當前生成目標**：
- 你現在正在規劃第 {volume_index} 卷【{vol_title}】的 **第 {start_ch} 章 至 第 {end_ch} 章**（共 {vol_chapter_count} 章，全卷進度批次：{batch_num}/{total_batches}）。
- 請輸出包含這些 chapter_index 的完整連續輕量章節骨架：{list(range(start_ch, end_ch + 1))}。
- 緊扣上方【第 {volume_index} 卷宏觀全卷大綱】，使本批次情節精準推動該卷的核心主線與高潮。
- 承接前文已規劃之情節進展與人物狀態，確保故事前後連貫。
- 每章短句聚焦戲劇推進拍點 (Scene Beats)，專注於骨架結構。
{prior_section}
{geom_section}
{surrounding_context}
{precalc_clues}

【allocated_tasks 填寫說明】
- 每一章請依據「本卷逐章伏筆/轉折操作表」填寫 allocated_tasks。
- 表中無任務的章節請輸出：foreshadowing_plants: [], foreshadowing_payoffs: [], turning_points: []。
- 若某章安排了 plant/payoff/turning point，請在 chapter_summary 或 events[0].content 中以簡潔語句標註其劇情落點。

【每章細緻元素契約指引 (Chapter Element Contract)】
- 本階段即為章節之完整元素鎖定！請將該章所需之所有元素細緻規劃，讓後續 Writer 僅需按計畫填入故事，不再依賴後期自由膨脹：
- 時空與場景：time_setting 明確標註具體時間點或時段；scene_setting 描寫具體場景空間與環境特徵、光影氣氛，嚴禁模糊籠統。
- 出場角色與知情邊界：characters_active 列出本章真正活躍出場的角色名單（包含核心主角、常駐配角，乃至於路人甲、乙、丙等功能性過場角色）。
  *【細緻角色層次規劃（含路人與單次/常駐標註）】：
    - 請細緻規劃每位出場角色是屬於「核心主角」、「常駐/重複出現配角」，或是「單次過場角色/路人甲乙丙」（如特定掌櫃、守衛、信使、群眾代表等）。
    - 規劃時需定下其在該場景中的具體動機、功能與說話態度，防止正文盲猜。
    - 若情節需要新角色或命名配角/路人，**必須在此大綱階段即做完整角色安排**，於頂層 new_characters 陣列中詳細填入，並標明是一次性還是可能再登場！
    - 當活躍角色發生可持續的心理、立場或關係變化時，填寫 character_state_changes（name、state_change、relationship_change），確保性格隨劇情合理推進，杜絕前後矛盾。
- 世界觀與元素運作機制：setting_usage 列出本章情節運作或涉及的具體世界觀法則、專有名詞、超常機制或專屬道具清單，在寫作前完成全部元素預先裝填。
- 戲劇推進拍點：每章規劃 3-5 個精簡推進拍點（scene_beats 或 events），包含行動起點、意外阻礙、關鍵抉擇與落地後果。
- 章節目標與位移：chapter_summary 概括核心情節；scene_goal 標註戲劇目標；scene_conflict 標註阻礙；cliffhanger 留出懸念鉤子。
- 實質狀態位移：story_state_before 與 story_state_after 清楚標示情報、人際、風險或資源的實質改變。
- emotional_requirement 描述本章必要的情感效果（例如和解、告別、愧疚或信任破裂），僅在大綱確有此需求時填寫。

【章節多樣性與反公式化指引】
- 同卷破局多樣化：交鋒模式注重變化，靈活結合正面博弈、同伴支援、資源周旋與制度借力等多種形式。
- 保持劇情緊湊推進：每 3 章內安排實質的主線推進、角色抉擇或伏筆實質進展。
- 重大轉折前置鋪墊：若某章安排角色立場轉變或重大轉折（turning point），前置章節宜具備動搖或懷疑的過渡鋪墊拍點。

【單章輸出格式示意（抽象通用結構）】
{{
  "chapter_index": {start_ch},
  "chapter_title": "本章主旨標題（依故事簡介與情節自命，體現文學質感）",
  "chapter_summary": "本章核心事件概括，交代人物行動、核心阻礙與衝突推進成果。",
  "time_setting": "具體時間點或時間跨度",
  "scene_setting": "具體場景空間、物理環境與氛圍特質",
  "events": [
    {{"scene_index": 1, "location": "場景空間", "characters": ["出場人物名"], "content": "行動推進 -> 遭遇阻礙/反制 -> 達成結果"}}
  ],
  "characters_active": ["主要出場角色名", "特定配角或路人甲(標註功能)"],
  "emotional_tone": "情境氛圍基調",
  "emotional_requirement": "本章情感要求或留白（若有）",
  "character_state_changes": [
    {{"name": "角色名", "state_change": "心理/立場轉向說明", "relationship_change": "與他人關係變化"}}
  ],
  "setting_usage": ["本章調用之世界觀法則或道具機制"],
  "scene_beats": ["拍點一：起點行動與動機", "拍點二：意外阻礙或交鋒", "拍點三：關鍵抉擇與轉折", "拍點四：落地結果與實質代價"],
  "story_state_before": "本章開始前局勢與情報狀態",
  "story_state_after": "本章結束後實質位移之局勢或情報代價",
  "cliffhanger": "章末具備實質懸念之收尾鉤子",
  "allocated_tasks": {{"foreshadowing_plants": [], "foreshadowing_payoffs": [], "turning_points": []}}
}}

【勢力與角色一致性及增量指引】
- 勢力/組織的定義、立場與背景以世界觀中的設定為準。
- 若章節使用既有角色，characters_active 請使用既有名冊中的名稱。
- 【新登場人物設定】：若本批章節劇情需要引入新命名角色（包含主要配角或重要過場路人），請於 new_characters 中說明其陣營、性格與動機，協助正文作家準確掌握人物：
  - name: 角色全名
  - role: 劇中定位（正派盟友 / 主要反派 / 導師 / 灰色中立 / 地方幹員 / 單次過場配角）
  - faction: 所屬勢力或門派（無勢力則填獨立/平民）
  - personality: 核心性格特徵與說話風格
  - motivation: 核心動機、生存訴求或過場功能
  - first_appearance_chapter: 首次登場章節號
  - is_one_off: 是否為單次過場角色 (true/false)
- 若本批章節解鎖了新地域、專屬法則或新勢力，請一併在頂層 "new_world_rules" 與 "new_factions" 中回傳；若無新增則給予空陣列 []。

【通用小說生成原則】
- 本提示詞為通用小說大綱規劃規範，嚴禁依賴或套用任何特定單一小說之範例情節；所有情節、場景、角色與設定必須 100% 依據當前專案輸入的故事簡介、世界觀與篇卷規劃進行推演。

【完整輸出 JSON 根結構範例】
{{
  "volume_index": {volume_index},
  "chapters_skeleton": [
    ... // 共 {vol_chapter_count} 章節輕量骨架（第 {start_ch} 至第 {end_ch} 章）
  ],
  "new_characters": [
    {{
      "name": "新角色全名",
      "role": "正派盟友 | 主要反派 | 導師 | 灰色中立 | 地方頭目 | 單次過場配角",
      "faction": "所屬勢力或門派名稱",
      "personality": "性格特質與言語風格短句",
      "motivation": "核心訴求或衝突動機",
      "first_appearance_chapter": {start_ch},
      "is_one_off": false
    }}
  ],
  "new_world_rules": [
    {{
      "name": "本卷新增規則或特殊制度名稱",
      "scope": "本卷專屬 | 全域通用",
      "description": "具體規則邏輯、代價與約束"
    }}
  ],
  "new_factions": [
    {{
      "name": "新增勢力名稱",
      "alignment": "敵對 | 友好 | 中立利益導向",
      "summary": "勢力背景與在當前卷的影響力"
    }}
  ]
}}

【使用者額外提示詞 (Prompt)】
{user_prompt or "請為本批章節生成連貫、短句化的輕量章節骨架，並同步申明新角色與新法則。"}

請生成符合上述 JSON 結構的物件。chapters_skeleton 輸出章數必須等於 {vol_chapter_count}，chapter_index 必須從 {start_ch} 到 {end_ch} 連續且不可缺漏。不要因追求細節導致輸出中斷。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_volume_skeleton_completion_messages(
    worldview_text, volume_index, current_vol, start_ch, end_ch, batch_count,
    surrounding_context, precalc_clues, user_prompt, prior_segment_json, novel_id=None
):
    """
    卷骨架「分段補全」提示詞拼接（completion 模式）。
    要求 LLM 接續前段章節脈絡，產出指定補全範圍 (start_ch ~ end_ch) 的獨立完整 JSON。
    """
    schema_snippet = get_json_schema_prompt_snippet("skeleton")
    system_prompt = f"{VOLUME_SKELETON_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{VOLUME_SKELETON_GUIDELINES}\n"
    system_prompt += build_agent_context_contract(
        "Volume Skeleton Completion / 卷骨架補全師",
        "- 經後端挑選的世界觀背景。\n- 指定卷的標題、概要、已完成前段章節與本次補全範圍。\n- Python 預計算的 allocated_tasks。",
        "只接續前段，補全本次指定章節範圍；不得重寫已完成章節。",
        "輸出只包含補全範圍的 chapters_skeleton 元素；必須延續前段脈絡並保持 JSON 可解析。"
    )

    core_context = f"{format_novel_core_context(novel_id)}\n\n" if novel_id else ""
    user_content = f"""{core_context}【世界觀背景】
{worldview_text}

【當前特定篇卷任務 — 分段補全 (Completion)】
- 當前篇卷序號：第 {volume_index} 卷
- 篇卷標題：{current_vol.get('title', f'第 {volume_index} 卷')}
- 篇卷概要：{current_vol.get('summary', '')}
- 已完成前段章節：第 {start_ch - 1} 章及之前（請勿重寫此前段章節）
- 本次需補全章節範圍：第 {start_ch} 章至第 {end_ch} 章（共 {batch_count} 章，序號必須為 {start_ch} 到 {end_ch} 連續編號）

{surrounding_context}
{precalc_clues}

【前段已生成之章節骨架參考】
{prior_segment_json}

【補全輸出要求】
1. 請只輸出純 JSON，包含本次補全範圍（第 {start_ch} 至第 {end_ch} 章）的完整 JSON 物件，格式如下：
{{
  "volume_index": {volume_index},
  "chapters_skeleton": [
    {{
      "chapter_index": {start_ch},
      "chapter_title": "章節標題",
      "chapter_summary": "本章概要",
      "time_setting": "時間設定",
      "scene_setting": "主要場景",
      "scene_goal": "核心目標",
      "scene_conflict": "阻礙與衝突",
      "scene_beats": [{{"beat_index": 1, "beat_type": "setup", "description": "行動與結果", "involved_characters": []}}],
      "characters_active": ["活躍角色名稱"],
      "emotional_tone": "",
      "emotional_requirement": "",
      "character_state_changes": [{{"name": "角色名稱", "state_change": "心理或立場變化", "relationship_change": "與另一角色關係變化"}}],
      "scene_turn": "",
      "scene_outcome": "",
      "cliffhanger": "",
      "allocated_tasks": {{"foreshadowing_plants": [], "foreshadowing_payoffs": [], "turning_points": []}}
    }}
  ],
  "new_characters": [
    {{
      "name": "本段新登場角色全名",
      "role": "正派盟友 | 主要反派 | 導師 | 灰色中立 | 地方頭目",
      "faction": "所屬門派勢力",
      "personality": "性格特質與言語風格短句",
      "motivation": "利益訴求或矛盾",
      "first_appearance_chapter": {start_ch}
    }}
  ],
  "new_world_rules": [],
  "new_factions": []
}}
2. 輸出章數必須等於 {batch_count}，chapter_index 必須從 {start_ch} 到 {end_ch} 連續且不可缺漏。
3. 延續前段章節的標題風格與情節因果。
4. 凡本段登場之新命名人物，請於 new_characters 中明確其陣營、性格與動機，協助正文寫作維持角色一致性。

【使用者額外提示詞 (Prompt)】
{user_prompt or "請接續前段內容，為本卷剩餘章節補全骨架大綱，並申明新角色。"}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    return messages


def build_incremental_skeleton_messages(worldview_text, volume_index, existing_skeleton, user_hint, novel_id=None):
    """卷骨架增量修正提示詞拼接"""
    patch_schema = {
        "volume_index": volume_index,
        "chapters_skeleton": [
            {
                "chapter_index": "必填：要修改的絕對章節序號",
                "chapter_title": "可省略未修改欄位",
                "chapter_summary": "可省略未修改欄位",
                "time_setting": "可省略未修改欄位",
                "scene_setting": "可省略未修改欄位",
                "events": "若修改事件，回傳完整的新 events 陣列",
                "characters_active": "可省略未修改欄位",
                "emotional_tone": "可省略未修改欄位",
                "cliffhanger": "可省略未修改欄位",
                "allocated_tasks": "除非明確要求修改伏筆/轉折，否則省略"
            }
        ]
    }
    schema_snippet = format_json_schema_prompt(patch_schema, label="this incremental skeleton patch schema")
    system_prompt = VOLUME_SKELETON_PROMPT_PLUS.format(hints=user_hint) + f"\n\n{schema_snippet}"
    system_prompt += build_agent_context_contract(
        "Incremental Skeleton / 卷骨架增量修正師",
        "- 世界觀摘要。\n- 指定卷索引。\n- 現有該卷章節骨架。\n- 總監或使用者的局部修改要求。",
        "只修補指定卷中被要求修改或補全的章節。",
        "輸出 chapters_skeleton patch JSON；每個回傳章節必須含 chapter_index。未修改章節不要回傳。"
    )
    
    core_context = f"{format_novel_core_context(novel_id)}\n\n" if novel_id else ""
    user_content = f"""{core_context}【世界觀背景】
{worldview_text}

【當前篇卷】
- 卷索引: {volume_index}

【現有骨架大綱】
{existing_skeleton}

【修改要求】
{user_hint}

請僅針對第 {volume_index} 卷的章節大綱骨架進行修改，並回傳格式完全合法的 chapters_skeleton JSON。
只回傳被修改或新增補全的章節物件；每個物件必須包含 chapter_index。未修改章節不要回傳，未修改欄位請省略，後端會按 chapter_index 深度合併。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

