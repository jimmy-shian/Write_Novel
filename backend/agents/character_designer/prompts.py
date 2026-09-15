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
    JSON_OBJECT_OUTPUT_CONTRACT,
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

def _format_existing_chars_summary(existing_chars_json) -> str:
    """提取既有已確立角色清單摘要，供後續陣營/梯隊生成時建立人物關係張力"""
    if not existing_chars_json:
        return "（尚無已確立角色）"
    try:
        parsed = json.loads(existing_chars_json) if isinstance(existing_chars_json, str) else existing_chars_json
        chars = parsed.get("characters", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
        if not chars:
            return "（尚無已確立角色）"
        lines = []
        for c in chars:
            if not isinstance(c, dict):
                continue
            name = c.get("name", "未命名")
            role = c.get("role", "未知定位")
            faction = c.get("faction") or c.get("affiliation") or "未定"
            want = c.get("want") or c.get("motivation") or ""
            pers = c.get("personality", [])
            pers_str = ", ".join(pers) if isinstance(pers, list) else str(pers)
            lines.append(f"- 【{name}】（陣營: {faction}，定位: {role}，性格: {pers_str}，核心欲求: {want[:50]}）")
        return "\n".join(lines[:35]) + ("\n...(其餘角色略)" if len(lines) > 35 else "")
    except Exception:
        return "（已確立角色資料解析中）"


def _format_factions_summary(worldview_text: str) -> str:
    """提取世界觀中的陣營設定"""
    if not worldview_text:
        return "（世界觀尚未設定具體陣營）"
    try:
        parsed = json.loads(worldview_text) if isinstance(worldview_text, str) and worldview_text.strip().startswith("{") else {}
        if not parsed:
            from backend.models.parsers import extract_json_block
            parsed = extract_json_block(worldview_text) or {}
        factions = parsed.get("factions", [])
        if not factions or not isinstance(factions, list):
            return "（依世界觀正文設定之主要陣營）"
        lines = []
        for f in factions:
            if isinstance(f, dict):
                name = f.get("name", "")
                pos = f.get("position", "")
                res = f.get("resources", "")
                lines.append(f"- 陣營【{name}】：立場利益: {pos}；掌握資源/制度權力: {res}")
        return "\n".join(lines) if lines else "（依世界觀正文設定之主要陣營）"
    except Exception:
        return "（依世界觀正文設定之主要陣營）"


def build_character_designer_messages(worldview_text, existing_chars_json, user_prompt, hint, mode, target_char_index, novel_id=None, faction_info=None, tier=1, target_batch_count=4, wave=None):
    """角色設計師提示詞拼接（支援世界觀陣營梯隊分段生成：每陣營 5-10 人）"""
    schema_snippet = get_json_schema_prompt_snippet("character")
    system_prompt = f"{CHARACTER_DESIGNER_PROMPT}\n\n{schema_snippet}\n{CONTEXT_REQUEST_RULE}\n\n{CHARACTER_DESIGNER_GUIDELINES}\n\n{JSON_OBJECT_OUTPUT_CONTRACT}\n"
    system_prompt += build_agent_context_contract(
        "Character Designer / 角色設計師",
        "- 經後端挑選的世界觀背景與作品核心基石，必須包含 factions / 勢力設定與 progressive_character_plan / 角色登場策略。\n- generate 模式：支援以陣營梯隊（Faction-Driven）分段生成，每個陣營保證生成 5-10 位具備完整深度的角色 Bible。\n- expand/modify 模式：會提供現有角色聖經與總監提示；modify 可能提供被修改角色完整內容。",
        "根據作品核心基石與可見世界觀設計立體深刻的群像角色 Bible。角色要服務於世界觀衝突、勢力格局、登場策略與作者原案需求；不得用空世界觀硬編角色。",
        "輸出完整合法的 characters JSON 物件（{'characters': [...]}）。分段生成時每次只輸出當前批次指定陣營梯隊的角色；expand/modify 應保留既有角色並補充或修正，避免刪除無關角色。"
    )
    
    core_context = f"{format_novel_core_context(novel_id)}\n\n" if novel_id else ""
    existing_summary = _format_existing_chars_summary(existing_chars_json)
    factions_summary = _format_factions_summary(worldview_text)

    if mode == "generate":
        # =========================================================================
        # 模式 A: 陣營梯隊導向分段生成 (Faction-Driven Tiered Generation)
        # =========================================================================
        if faction_info and isinstance(faction_info, dict):
            f_name = faction_info.get("name", "主要勢力")
            f_pos = faction_info.get("position", "")
            f_res = faction_info.get("resources", "")
            f_rel = faction_info.get("relationship_to_protagonist", "")

            if tier == 1:
                tier_label = "第一梯隊：高層核心巨頭、領袖代表與首席宿敵/導師"
                tier_req = f"""請為陣營【{f_name}】設計 {target_batch_count} 位最核心高層角色：
1. 角色規劃（{target_batch_count} 位高層）：
   - 角色 1：該陣營的最高掌權者 / 裁決者 / 精神領袖（若本陣營為主角所在底層陣營，則必須為故事第一核心主角，嚴格落實核心基石能力與反差偽裝）。
   - 角色 2 至 {target_batch_count}：陣營首席執法官、審判司長、核心宿敵、頂尖守護者或引路 Mentor。
2. 反派與敵對高層必填：
   - `wound_origin`: 創傷原點（其極端冷血、專制或追求力量背後的慘痛創傷）
   - `false_belief`: 核心認知偏見（堅信的扭曲真理）
   - `belief_collapse_3beats`: 三階動態信念崩塌節奏（陣列 3 項：認知初裂 -> 體制反噬 -> 致命真相）
3. 必填心理與行動欄位：
   - `name`: 具體姓名（嚴禁代號）
   - `role`: 陣營領袖 / 首席執行官 / 核心宿敵 / 王牌強者 / 導師
   - `faction`: 必須填寫【{f_name}】
   - `want`, `need`, `fatal_flaw`, `want_need_conflict`, `secret`, `speech_profile`, `motivation`, `arc`, `appearance`, `background`, `relationships`
4. ⚠️ 跨角色與跨陣營關係約束：
   - 必須在 `relationships` 中，與【前續已確立角色】（特別是主角及對立勢力代表）建立具體的衝突、同盟、牽制或利益往來！"""
            else:
                tier_label = "第二梯隊：中堅骨幹、內部異見者、雙面間諜與基層代表"
                tier_req = f"""請為陣營【{f_name}】設計 {target_batch_count} 位鮮活的中堅與基層群像角色（使該陣營總角色數充實至 6-10 人）：
1. 角色規劃（{target_batch_count} 位中堅與基層）：
   - 執行隊長、專利審查官、審判隊員、技術專員或情報線人。
   - 內部異見者 / 改革派 / 叛逆者（對高層意志產生質疑與動搖者）。
   - 雙面間諜 / 跨陣營暗線聯絡人 / 灰色交易者。
   - 基層行動人員 / 市井幫手。
2. 配角獨立生命力必填欄位：
   - `independent_arc`: 配角三階段獨立成長線（物件：{{"phase_1": "...", "phase_2": "...", "phase_3": "..."}}），不得淪為傳聲筒！
   - `off_screen_goal`: 場外個人追求（在主線劇情之外的真實生活目標）
3. 必填心理與行動欄位：
   - `name`: 具體姓名
   - `role`: 中堅隊長 / 審查官 / 異見者 / 潛伏間諜 / 技術專家 / 基層幹員
   - `faction`: 必須填寫【{f_name}】
   - `want`, `need`, `fatal_flaw`, `want_need_conflict`, `secret`, `speech_profile`, `motivation`, `arc`, `appearance`, `background`, `relationships`
4. ⚠️ 複雜關係網織造：
   - 必須在 `relationships` 欄位中，與該陣營第一梯隊高層及其他陣營角色建立緊密的暗線關聯（監視、背叛、救命恩情、雙面情報等）。"""

            user_content = f"""{core_context}【世界觀核心背景】
{worldview_text}

【世界觀各大陣營格局】
{factions_summary}

【前續批次已確立之角色 Bible（請與這些角色產生緊密的關係交織）】
{existing_summary}

【本次分段生成任務：陣營【{f_name}】— {tier_label}】
- 陣營名稱：{f_name}
- 陣營立場與利益：{f_pos}
- 掌握資源/制度權力：{f_res}
- 與主角/核心衝突之關係：{f_rel}

{tier_req}

【輸出格式】
最外層必須是合法的單一 JSON 物件 `{{"characters": [...]}}`，列表中「僅」包含本次設計的 {target_batch_count} 位角色。
"""
        else:
            # 兼容模式：無特定陣營傳入時的全量引導
            user_content = f"""{core_context}【世界觀背景】
{worldview_text}

【世界觀各大陣營格局】
{factions_summary}

【前續已確立之角色 Bible】
{existing_summary}

【使用者要求】
{user_prompt or "請根據作品核心基石與世界觀，為各陣營設計豐富立體的角色與配角群像。"}

請為本作品生成符合結構的角色 Bible JSON 設定。
硬性要求：
1. 核心主角群的人設、動機、特殊能力與弱點必須嚴格契合【作品核心基石】（例如主角的專屬能力與原創設定），嚴禁脫離原案瞎編其他設定。
2. 必須讀取並落實世界觀中的 `factions` / 勢力設定，每個陣營至少規劃 5-10 人，為主要角色標明所屬勢力、利益立場、與其他勢力的衝突或合作關係。
3. 必須讀取並落實 `progressive_character_plan` / 角色登場策略，讓角色功能、首次登場階段與群像節奏對齊。
4. 必須建立可供後續 volumes、volume_skeleton、writer 使用的角色關係資料，例如 relationships / relationship_matrix / role / faction / entry_phase 等 schema 允許欄位。
5. 不要只列人物簡介；每位核心角色都要有可寫作的動機、弱點、成長弧線、聲音/行為特徵與關係張力。
6. 反派與敵對人物必須定義 `wound_origin`（創傷原點）與 `false_belief`（偏見執念），拒絕純臉譜化；立場動搖/轉變角色必填 `belief_collapse_3beats`（三階信仰崩塌節奏）；重要配角必填 `independent_arc` 與 `off_screen_goal`。
"""
    elif mode == "expand":
        user_content = f"""{core_context}【世界觀背景】
{worldview_text}

【現有角色聖經】
{existing_chars_json}

【總監批判與擴增提示 (Hint)】
{hint or "請擴增有深度的新角色，補足各陣營中堅與基層人物。"}

【一般提示詞 (Prompt)】
{user_prompt or "請在現有角色基礎上進行增量擴展，追加新角色。"}

請根據作品核心基石與總監提示，追加新角色。
[極重要要求]：
請只生成本次需要「新增/追加」的角色清單，並回傳格式完全合法的 characters JSON（例如 `{{ "characters": [...] }}`），列表中應「僅」包含本次新增的角色，千萬不要重寫、輸出或複製任何未修改的既有角色。
擴增角色時仍必須遵守世界觀勢力設定；新角色的 faction、登場功能與關係網必須能回接既有角色聖經，不能只新增孤立人物。
"""
    else:  # modify
        target_char_content = ""
        if target_char_index is not None:
            try:
                parsed_chars = json.loads(existing_chars_json)
                chars_list = parsed_chars.get("characters", [])
                norm_idx = db.normalize_char_index(int(target_char_index), len(chars_list), source='character_designer')
                target_char_content = f"\n【被修改角色的完整內容 (Index {norm_idx})】\n{json.dumps(chars_list[norm_idx], ensure_ascii=False, indent=2)}"
            except IndexError:
                pass
                
        user_content = f"""【世界觀背景】
{worldview_text}

【現有角色聖經】
{existing_chars_json}
{target_char_content}

【修改指示 (Hint)】
{hint or "請修改角色設定。"}

【一般提示詞 (Prompt)】
{user_prompt or "請對指定角色進行內容調整。"}

請將以上修改與該角色的完整內容融會貫通。
[極重要要求]：
請只生成「受修改後」的角色清單，並回傳格式完全合法的 characters JSON（例如 `{{ "characters": [...] }}`），列表中應「僅」包含本次被修改的角色的全新設定，千萬不要複製或重寫其他無關、未修改的角色。
修改時保留角色既有關係網與勢力一致性；若總監要求補關係或勢力，請同步修正 relationships / relationship_matrix 等相關欄位。
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_missing_character_designer_messages(worldview_summary, existing_chars_json, new_char_name, chapter_outline):
    """
    為首次登場的缺失角色生成獨立設計提示詞訊息列表。
    此函數負責將角色設計 system prompt 與 user prompt 組裝為 LLM messages，
    按照嚴格 JSON Schema 要求生成新角色卡。
    """
    schema = {
        "name": "",
        "role": "",
        "entry_phase": "",
        "personality": [],
        "want": "",
        "need": "",
        "fatal_flaw": "",
        "motivation": "",
        "arc": "",
        "speech_style": "",
        "appearance": "",
        "background": "",
        "relationships": []
    }

    # 僅提取現有角色的名稱與角色定位，節省 Token 並防範衝突
    existing_names_str = "暫無角色"
    if existing_chars_json:
        try:
            names = extract_character_names_list(existing_chars_json)
            if names:
                existing_names_str = ", ".join(names)
        except Exception:
            pass

    schema_snippet = format_json_schema_prompt(schema, label="this missing character schema")
    system_prompt = f"""你是一位頂尖的角色設計大師（Character Designer）。
請根據世界觀背景與新角色首次登場的章節骨架，為新登場的角色【{new_char_name}】設計一個具備深度與心理層次的角色卡設定。

⚠️【剛性約束項目】：
1. 輸出必須符合以下角色 schema：
{schema_snippet}
2. name 欄位必須是角色的具體姓名【{new_char_name}】，絕對禁止填寫無關名稱。
3. 角色的人設、動機 (motivation)、致命缺陷 (fatal_flaw)、發聲風格 (speech_style) 必須與章節大綱的情境完全契合，且不可與現有的其他角色衝突。
4. {JSON_OBJECT_OUTPUT_CONTRACT}
"""
    system_prompt += build_agent_context_contract(
        "Missing Character Designer / 缺失角色補卡師",
        "- 世界觀背景大綱。\n- 既有角色名稱與定位清單。\n- 新角色首次登場的章節大綱。",
        "只為指定新角色生成一張可併入角色庫的角色卡，服務於其首次登場章節。",
        "輸出單一角色 JSON；name 必須等於指定新角色名稱，不得順手新增其他角色。"
    )
    user_content = f"""【世界觀背景大綱】
{worldview_summary}

【現有已登場角色清單 (避免人設重複或名稱衝突)】
{existing_names_str}

【新角色【{new_char_name}】登場的第 {chapter_outline.get('chapter_index')} 章大綱】
{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}

請為新角色【{new_char_name}】生成高品質的完整角色 JSON 卡片。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

