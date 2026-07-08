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
from backend.prompts.output_contracts import (
    JSON_OBJECT_OUTPUT_CONTRACT,
    STRICT_JSON_KEY_CONTRACT,
    format_json_schema_prompt,
)
from backend.agents.director.prompt_sections import (
    FINAL_USER_INSTRUCTION,
    build_director_decision_contract,
)

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
from backend.prompts.common.context import _context_query_text, _parse_jsonish

def build_director_decision_messages(
    novel_id,
    current_stage,
    worldview_text,
    characters_text,
    plot_text,
    written_chapters_text,
    user_prompt,
    validation_report,
    character_review_mode=None,
    character_review_hint=None,
    character_review_target_content=None,
    suggested_next_chapter=None,
    chapter_index=None,
    director_context_block=None,
    gold_rules_context=None
):
    """總監決策評判提示詞
    
    根據不同階段傳入對應的審查內容：
    - worldview: 完整世界觀內容 + 評斷提示詞
    - characters: 完整角色列表
    - volumes: 完整卷列表 + 世界觀的 macro_outline
    - volume_skeleton: 完整骨架(每2卷一組) + 世界觀的 macro_outline
    - writer: 該章的完整內容(正文+大綱+角色聖經+伏筆)
    - editor: 該章的完整潤色內容
    """
    from backend.services.diagnostics import diagnose_all_phases
    from backend import persistence as db
    diags = diagnose_all_phases(novel_id)
    novel = db.get_novel(novel_id)
    raw_worldview_text = worldview_text
    raw_characters_text = characters_text
    context_query = _context_query_text(plot_text, written_chapters_text, user_prompt, character_review_hint, character_review_target_content, director_context_block)
    worldview_text = select_worldview_context(raw_worldview_text, current_stage, query_text=context_query, force_full=(current_stage == "worldview"))
    characters_text = build_relevant_character_context_text(
        raw_characters_text,
        query_text=context_query,
        include_all_full=(current_stage == "characters"),
    )
    plot_text = compact_context_text(plot_text, MAX_DIRECTOR_PLOT_LENGTH, "大綱/卷骨架")
    written_chapters_text = compact_context_text(written_chapters_text, MAX_DIRECTOR_PROSE_LENGTH, "正文")
    validation_report = compact_context_text(validation_report, MAX_DIRECTOR_REPORT_LENGTH, "校驗報告")
    gold_rules_context = compact_context_text(gold_rules_context, MAX_GOLD_RULES_CONTEXT_LENGTH, "創作金律")

    pipeline_prompt = compact_context_text((novel.get("pipeline_prompt") or "").strip() if novel else "", 12000, "原始需求")
    user_prompt_clean = compact_context_text((user_prompt or "").strip(), 12000, "當前指示")
    is_only_bg = (not user_prompt_clean) or (user_prompt_clean == pipeline_prompt)

    # Prepare prompt blocks
    bg_prompt_block = f"""【使用者建書初期原始需求（僅作為整體背景與大綱風格參考，非當前修改指令）】
{pipeline_prompt}"""

    if is_only_bg:
        active_instruction_block = ""
        worldview_user_prompt_section = bg_prompt_block
        default_user_prompt_section = bg_prompt_block
    else:
        active_instruction_block = f"""【當前步驟修改指示 / 系統錯誤自癒回報（請優先滿足此要求）】
{user_prompt_clean}"""
        worldview_user_prompt_section = f"{active_instruction_block}\n\n{bg_prompt_block}"
        default_user_prompt_section = f"{active_instruction_block}\n\n{bg_prompt_block}"

    # 取得該階段的通過標準
    from backend.schemas.agent_json import format_criteria_for_prompt
    stage_criteria = format_criteria_for_prompt(current_stage)
    director_contract = build_director_decision_contract(current_stage, stage_criteria)
    
    # 取得世界觀的 macro_outline
    macro_outline = ""
    if raw_worldview_text:
        try:
            parsed = _parse_jsonish(raw_worldview_text)
            macro_outline = parsed.get("macro_outline", "") if isinstance(parsed, dict) else ""
        except:
            # 嘗試從文本提取
            if "【整體故事大綱】" in str(raw_worldview_text):
                parts = str(raw_worldview_text).split("【整體故事大綱】")
                if len(parts) > 1:
                    macro_outline = parts[1].strip()
    macro_outline = compact_context_text(macro_outline, MAX_MACRO_OUTLINE_LENGTH, "整體故事大綱")
    if character_review_target_content:
        character_review_target_content = compact_context_text(character_review_target_content, 12000, "目標角色")
    if character_review_hint:
        character_review_hint = compact_context_text(character_review_hint, 8000, "角色修改提示")
    if director_context_block:
        director_context_block = compact_context_text(director_context_block, 16000, "總監補充上下文")

    director_input_policy = """

## Director 輸入與展開政策
1. 本輪輸入可能包含「硬指標計數」與「預設視圖」。硬指標由 Python 校驗報告直接計算；預設視圖只用於定位，不可把未展開項目當成已審查。
2. 對上一個 Agent 輸出可用 `TOOL_CALL evaluate_output` 做硬性檢查；若需要展開內容，必須使用完整 Tool envelope。
3. 只要本階段包含長列表、完整角色表、卷骨架或正文，放行前需有足夠內容檢閱依據；不能只因 Python 硬性校驗通過就宣稱內容品質通過。
4. 若遇到前端回報的 system_event（錯誤、阻斷、索引缺失、執行失敗），請把它當作事實封包，根據 validation_report 與工具檢視結果決定下一步；前端不負責判斷流程。
"""
                    
    # 總監評斷世界觀與進行伏筆審查時需要完整傳入，而其他階段已經通過審核，將其內部的伏筆與轉折欄位改為 "此區塊通過審核不需評判"
    if current_stage not in ("worldview", "foreshadowing"):
        worldview_text = mask_worldview_seeds_and_turns(worldview_text)

    # 根據 current_stage 構建不同的審查內容
    if current_stage == "worldview":
        # 世界觀階段：只傳世界觀完整內容 + 評斷提示詞
        system_prompt = f"""{director_contract}

你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前世界觀的創作質量，並決定下一步的最佳動作。
 
【審查原則與柔軟語調指南】
1. 當前階段是「current_stage = {current_stage}」（世界觀架構師）。
2. 評估語氣可溫和、細心且富有建設性，但所有評估文字只能寫在 JSON 的 `reason`、`hint`、`agent_prompt` 或 `agent_context` value 中。
3. **【拆解評判要求】** 你必須單獨評估以下三個獨立區塊；若需要說明，請寫入 `reason`，不得輸出 JSON 以外的報告文字：
   - **核心世界觀設定**（主題深度、多陣營衝突、宏觀大綱）。
   - **🎭多幕式劇情起伏結構**（劇情起伏與功能）。
   - **👥角色漸進登場規劃策略**（人物登場波次與群像鋪陳）。
4. **【格式與 ID 的絕對強硬要求】** 
   - 幕次標題必須嚴格遵循『第一幕 (自擬階段名稱)』、『第二幕 (自擬階段名稱)』等標準命名格式。
   - 角色波次標題必須嚴格遵循『第一波 (自擬登場群體或主題)』、『第二波 (自擬登場群體或主題)』等標準命名格式。
   - **絕對禁止**出現『1.』、『1-01』、『1-0XX』等不一致或隨意的標號，這會影響後續與系統其他部分溝通參數的統一！
 
"""
        user_content = f"""{worldview_user_prompt_section}
 
【完整世界觀設定（包含核心、多幕起伏結構與角色漸進規劃）】
{worldview_text}
 
{FINAL_USER_INSTRUCTION}
"""
    
    elif current_stage == "characters":
        # 角色階段：完整角色列表
        system_prompt = f"""{director_contract}

你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前角色設計的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（角色設計師）。
2. 角色關係網是否邏輯連貫。
3. 確認角色的心理深度、成長弧線是否完整。
 
"""
        character_extra_context = ""
        if character_review_mode in ("modify", "expand") and character_review_hint:
            character_extra_context += f"\n\n【本次修改/新增的總監指示 (Hint)】\n{character_review_hint}"
        if character_review_mode in ("modify", "expand") and character_review_target_content:
            character_extra_context += f"\n\n【被修改/新增角色的完整內容】\n{character_review_target_content}"
        if character_review_mode == "generate":
            character_extra_context = "\n\n【重要】此為世界觀生成後的首次角色生成，請確認角色陣容是否完整且與世界觀設定契合。"
        
        user_content = f"""{default_user_prompt_section}
 
【世界觀背景】
{worldview_text}
 
【完整角色列表（完整設定）】
{characters_text}
{character_extra_context}
 
{FINAL_USER_INSTRUCTION}
"""
    
    elif current_stage == "volumes":
        # 卷階段：完整卷列表 + 世界觀的 macro_outline
        system_prompt = f"""{director_contract}

你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前篇卷規劃的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（篇卷規劃師）。
2. 檢查卷結構是否與世界觀的 multi_act_structure 呼應。
3. 確認每卷的功能定位是否明確，情節銜接是否連貫。
 
"""
        user_content = f"""{default_user_prompt_section}
 
【世界觀的整體故事大綱 (macro_outline)】
{macro_outline}
 
【完整篇卷列表（完整設定）】
{plot_text}
 
{FINAL_USER_INSTRUCTION}
"""
    
    elif current_stage == "volume_skeleton":
        # 骨架階段：完整骨架 + 世界觀的 macro_outline + Python 分配表
        system_prompt = f"""{director_contract}

你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前卷骨架的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（篇卷骨架規劃師）。
2. 檢查骨架是否和該卷標題、概要、時間線、序列上下文與適用規則一致。
3. 檢查各章是否依「Python 預計算本卷伏筆/轉折分配表」自然埋設、回收或承載 turning point；沒有分配任務的章節不可要求硬塞伏筆。
4. 通過標準：劇情能完整根據該卷伏筆/轉折分配自然鋪陳與回收，章節之間沒有內容跳痛，角色行為與卷設定不衝突，即可放行。
5. 骨架階段只需輕量脈絡，不負責正文細節。若每章已點出承接/推進、時間、地點、活躍角色/勢力與 allocated_tasks 落點，不得因細節量少或場景未展開而退回；正文展開交給 writer。
6. 合理的非線性時間敘事可以接受，例如穿越、回憶、夢境、異界時間差或其他劇情設定明確支持的時間跳躍；不要只因時間不是線性遞進就退回。
7. 若需要繼續生成缺失卷，必須輸出 `CONTINUE` + `target: "volume_skeleton"` + 明確 `volume_index`，且 `agent_prompt` 必須要求一次生成該卷完整「輕量」章節骨架；不得輸出 SEGMENT_GENERATE、SEGMENT_COMPLETE 或要求分段生成。
8. 若骨架使用了角色 Bible 中不存在的命名角色，優先輸出 `INCREMENTAL_APPEND_CHARACTER` 補角色卡；補卡完成後再回到該卷骨架或原章節，不得跳到下一卷。
9. 勢力/組織設定以世界觀 factions 為準；若骨架中的勢力立場、制度、目標與世界觀不一致，指出具體不一致並要求修正，不要讓下游臨時改寫勢力設定。
 
"""
        user_content = f"""{default_user_prompt_section}
 
【世界觀的整體故事大綱 (macro_outline)】
{macro_outline}
 
【完整卷骨架列表（完整設定）】
{plot_text}
 
{FINAL_USER_INSTRUCTION}
"""
    

    elif current_stage == "writer":
        # 寫作階段：該章的完整內容(正文+大綱+角色聖經+伏筆+後三章伏筆回收預告)
        system_prompt = f"""{director_contract}

你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前章節正文的創作質量，並決定下一步的最佳動作。

【審查原則】
1. 當前階段是「current_stage = {current_stage}」（正文寫作作家）。
2. 檢查角色台詞、語氣、動作是否100%符合角色聖經。
3. 確認伏筆是否自然融入，轉折點是否有足夠鋪陳。
4. ⚠️【後三章伏筆預埋審查】：請特別注意檢查「clue_payoff_upcoming_3_chapters」中預告的後三章即將回收之伏筆，是否已在本章正文中有合理的前置鋪墊與自然埋入。
5. 角色聖經的配角欄位缺失不是 writer 階段阻斷理由；除非主角資料缺失已明顯造成正文無法寫作，否則不得改派角色修補，應繼續 writer/editor 流程。
6. 但若正文或章節大綱使用了角色 Bible 中不存在的命名角色，必須先 `INCREMENTAL_APPEND_CHARACTER` 追加角色卡，再回到本章 writer；不得讓 writer 硬寫無角色卡人物。
7. 勢力/組織描寫必須以世界觀 factions 與當前卷 factions 為準；若正文把勢力立場、制度、敵友關係寫錯，應退回 writer 修正或回 worldview 修正源資料。

"""
        user_content = f"""{default_user_prompt_section}

【世界觀背景】
{worldview_text}

【角色 Bible 聖經（命中角色完整設定；其他角色名稱與基本關係）】
{characters_text}

【當前章節大綱】
{plot_text}

【本章正文（完整內容）】
{written_chapters_text}

{FINAL_USER_INSTRUCTION}
"""
    
    elif current_stage == "editor":
        # 編輯階段：該章的完整潤色內容
        system_prompt = f"""{director_contract}

你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前潤色後正文的質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（編輯姬）。
2. 檢查潤色後是否比原版有明顯提升。
3. 確認角色人設、大綱走向、伏筆完整性是否保持。
4. 角色聖經的配角欄位缺失不是 editor 階段阻斷理由；若本章正文與大綱可正常審核，應放行到下一章 writer。
 
"""
        extra_guideline = ""
        current_ch = chapter_index if chapter_index is not None else 1
        if suggested_next_chapter is not None:
            # 檢查是否為非常規（如補寫、補充缺漏章節）
            is_supplementary = (suggested_next_chapter != current_ch + 1)
            supp_msg = "（⚠️ 此為補充/填補缺漏章節）" if is_supplementary else ""
            extra_guideline = f"\n\n💡【編輯姬審核後前往下一章指引】{supp_msg}：當前審查的章節為第 {current_ch} 章。本系統建議的下一章計畫前往：第 {suggested_next_chapter} 章。若此章為補齊先前缺漏的章節或繼續推展，請優先在 JSON 決策中將 `chapter_index` 設為 {suggested_next_chapter}，並將 `target` 設為 `writer`，以利全自動管線能無縫銜接到正確的章節位置。"

        user_content = f"""{default_user_prompt_section}
 
【世界觀背景】
{worldview_text}
 
【原章節大綱】
{plot_text}
 
【潤色後正文（完整內容）】
{written_chapters_text}{extra_guideline}
 
{FINAL_USER_INSTRUCTION}
"""
    
    elif current_stage == "foreshadowing":
        # 伏筆審查階段
        system_prompt = f"""{director_contract}

你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前伏筆與轉折點的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」（伏筆與轉折編織師）。
2. 請核對「世界觀背景」以及「剛性校驗報告」。
3. 確認伏筆種子（foreshadowing_seeds）是否包含必要欄位，且數量是否達到 50 個。
4. 確認關鍵轉折點（key_turning_points）是否包含必要欄位，且數量是否達到 50 個。
5. **重要審查指引（分步展開審查）**：
   - 審查應分步進行（例如先確認伏筆種子，再確認轉折點）。
   - 你可以使用 `expand_collapsed_json` 工具來分頁展開查看資料庫中的完整伏筆列表。
   - 例如，你可以呼叫 `expand_collapsed_json` 展開 1~10，在下一輪呼叫展開 11~20，依此類推。
   - **檢查-1, 2, 3 的步驟狀態**：若需要說明目前檢查到哪一步，只能寫在 JSON 的 `reason` value 中，例如「Step 1: 伏筆種子 1-10 審查」。
   - 如果某部分不合格，你可以使用 `supplement_content` 工具進行部分修改與補強。
   - 只有當伏筆種子與轉折點皆確認合格且數量足夠後，才能下達 `CONTINUE` 進入 `characters` 階段。

"""
        user_content = f"""{default_user_prompt_section}
 
【完整世界觀背景】
{worldview_text}
 
{FINAL_USER_INSTRUCTION}
"""
    
    else:
        # 默認通用格式
        system_prompt = f"""{director_contract}

你是 AI 小說創作系統的最高決策創意總監。你的任務是評審當前階段的創作質量，並決定下一步的最佳動作。
 
【審查原則】
1. 當前階段是「current_stage = {current_stage}」。
2. 對比使用者的原始意圖，檢查是否有邏輯跳躍、設定穿幫、或者是套用流水帳的情形。
3. ⚠️ 【Plot / Outline 階段強制放行】：若當前階段是 `plot` 或 `plot_review`，除非有嚴重人物缺失需要 `GO_BACK_TO_CHARACTERS`，否則必須直接給出 `CONTINUE`，不得故意阻斷。
 
"""
        user_content = f"""{default_user_prompt_section}
 
【當前各板塊數據】
- 世界觀設定：{worldview_text if worldview_text else "（空）"}
- 角色設定：{characters_text if characters_text else "（空）"}
- 大綱設定：{plot_text if plot_text else "（空）"}
- 正文：{written_chapters_text if written_chapters_text else "（空）"}
 
{FINAL_USER_INSTRUCTION}
"""
    
    system_prompt += director_input_policy

    if gold_rules_context:
        user_content += f"""

## 既有會議討論聖經 / 創作金律
以下內容來自本作品先前輸出的 retrospective gold rules。它是總監下指令時的參考規則，應用於判斷風格、避坑與流程建議；若與系統底層剛性校驗報告衝突，仍以 Python 校驗報告為準。
{gold_rules_context}
"""

    if current_stage in ("volumes", "volume_skeleton", "writer", "editor"):
        system_prompt += """

## 伏筆/轉折審核紅線
1. 伏筆與轉折的硬性位置，以 Python 預計算分配表與章節大綱 allocated_tasks 為唯一依據。
2. 世界觀 foreshadowing_seeds / key_turning_points 內的 act、stage、volume、chapter 等欄位，只是早期草稿參考，不得當成本階段硬性任務。
3. 你不得在審核時臨時發明新的伏筆/轉折義務，也不得要求 Agent 隨意新增未分配的伏筆。
4. 若某章/某卷沒有被分配 plant、payoff 或 turning point，請只做一般品質審核，不得因「應該有伏筆感」而退回。
5. 若要退回修改，必須引用分配表中的 seed_id / turn_id、指定章節與缺失位置。
"""

    if suggested_next_chapter is not None:
        if current_stage in ("writer", "editor"):
            user_content += f"\n\n💡【系統寫作計畫指引】：若本次審核放行並準備繼續正文寫作，系統建請下一章前往：第 {suggested_next_chapter} 章（這可能是一般的順序下一章，或是為了補齊斷檔/缺漏的章節）。請在輸出 JSON 決策時，優先將 `chapter_index` 設為 {suggested_next_chapter}，並將 `target` 設為 `writer`。\n"
        elif current_stage == "volume_skeleton":
            user_content += f"\n\n💡【系統寫作計畫指引】：若剛性校驗報告確認【所有卷】的骨架皆已完全生成且無缺漏，準備放行進入正文寫作階段時，系統建請從第 {suggested_next_chapter} 章開始寫作。請在決策放行且 target 為 writer 時，將 `chapter_index` 設為 {suggested_next_chapter}。\n"

    system_prompt += f"\n\n{DIRECTOR_CONTEXT_REQUEST_RULE}\n"
    
    last_run_block = ""
    last_run = db.get_last_agent_run(novel_id)
    if last_run:
        _last_input = last_run.get('input_data', '') or ''
        _last_output = last_run.get('output_data', '') or ''
        _last_stage = last_run.get('agent_name', '')
        _user_content_summary = ''
        try:
            _input_msgs = json.loads(_last_input) if _last_input else []
            if isinstance(_input_msgs, list):
                _user_parts = []
                for _m in _input_msgs:
                    if isinstance(_m, dict) and _m.get('role') == 'user':
                        _c = compact_context_text(_m.get('content') or '', 8000, "上一輪 Agent user input")
                        _user_parts.append(_c)
                _user_content_summary = '\n---\n'.join(_user_parts) if _user_parts else '(無 user 訊息)'
            else:
                _user_content_summary = compact_context_text(str(_input_msgs), 8000, "上一輪 Agent input")
        except Exception:
            _user_content_summary = compact_context_text(_last_input, 8000, "上一輪 Agent input")
        # 清理思考過程標記 (不放入思考)
        import re
        clean_last_output = re.sub(r"<think>.*?</think>", "", _last_output, flags=re.DOTALL).strip()
        # 一律使用收合函數：JSON list 欄位「前5項展示 + 其餘收合 + 工具指令」
        # 純文字輸出時自動 fallback 截斷 6000 字元
        _output_summary = collapse_json_output_for_director(
            clean_last_output,
            stage_name=_last_stage,
            preview_count=5
        )

        last_run_block = f"""

【上一個運行的 Agent 執行記錄 (Last Agent Run)】
- 階段名稱 (Stage)：{_last_stage}
- 該 Agent 接收到的使用者指示摘要 (User Content)：
{_user_content_summary}

- 該 Agent 產生的原始輸出內容 (Output)：
{_output_summary}
"""
        system_prompt += """
## ⚠️ 【上一個運行的 Agent 審核核對指令】 (🔥 核心職責)
你在進行本次評審時，請特別核對使用者內容中的【上一個運行的 Agent 執行記錄 (Last Agent Run)】。
1. 對比上個 Agent 接收到的輸入與指示，評審該 Agent 產生的原始輸出是否正確且完整地完成了要求。
2. 總監的判斷不應自己重組要求。如果該 Agent 的輸出已經正確完成了生成，沒有嚴重缺失，請放行前進。
3. 若該 Agent 的輸出有缺失、格式錯誤、欄位缺失或不足量，請在 JSON 決策中將其退回至該 Agent，並在 `reason` 與 `hint` 中明確指出其原始輸出的不足之處，供其重新生成。
"""

    system_prompt += """

## 檢查報告解讀規則
1. 「待生成」「待補」「佇列」「缺少章節」代表流程進度尚未完成，不等於上一輪 Agent 內容品質不合格。
2. 只有格式無法解析、必填欄位缺失、章節索引錯誤、allocated_tasks 與 Python 分配表不一致、角色/勢力設定明顯衝突，才屬於需要退回修正的內容問題。
3. 若報告同時列出多個未完成卷，請依報告中的「下一步建議」或最早未完整卷前進；不要因後續卷完全缺失而跳過較早的缺章卷。
4. 若上一輪輸出本身合格但全書仍有缺卷/缺章，請用 CONTINUE 派發下一個正確生成目標，不要把流程未完成寫成內容不合格或中止理由。
"""

    user_content += f"""

## 系統底層結構/進度檢查報告（Python 計算事實，請以此為準）
{validation_report}
"""
    
    if director_context_block:
        user_content += f"\n\n{director_context_block}"
        
    if last_run_block:
        user_content += f"\n\n{last_run_block}"

    # 統一在 user_content 尾端附加額外的說明
    if not is_only_bg:
        if "【當前步驟修改指示" not in user_content:
            user_content += f"\n\n{active_instruction_block}"
    else:
        if "【使用者建書初期原始需求" not in user_content:
            user_content += f"\n\n{bg_prompt_block}"
    
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_director_decision_help_messages(help_reason, target_data):
    """總監調閱輔助決策提示詞"""
    system_prompt = f"""{build_director_decision_contract("help", "")}

你是一位小說創作流程總監。你剛剛調閱了完整的詳細板塊數據。
你的任務是根據調閱資料輸出下一步可執行總監決策。
"""
    user_content = f"""【總監調閱原因】
{help_reason}

【被調閱板塊數據】
{target_data}

{FINAL_USER_INSTRUCTION}
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

def build_director_sub_agent_messages(
    agent_name: str,
    task_description: str,
    context: dict,
    retry_hint: str = None,
    retry_count: int = 1
) -> list:
    """
    為總監呼叫子代理人構建提示詞訊息
    """
    system_prompt = f"""你是一位負責執行具體寫作任務的專業子代理人（Sub-Agent: {agent_name}）。
你的任務是根據總監 Agent 下達的指令，完成特定章節或設定的生成/修改。

⚠️【剛性約束項目】：
1. 必須完全遵守上下文中的世界觀設定與角色人設，禁止胡編亂造。
{JSON_OBJECT_OUTPUT_CONTRACT}
"""
    system_prompt += build_agent_context_contract(
        f"Director Sub-Agent / 總監子代理人 {agent_name}",
        "- 總監指派之生成任務。\n- 總監提供的 context 物件。\n- 可能包含上次錯誤與重試提示。",
        "只完成總監 task_description 指定的工作；不要自行擴大任務範圍。",
        "輸出 JSON，且必須能被後端解析。若 context 不足以完成，回傳 context request JSON。"
    )
    user_content = f"""【總監指派之生成任務】
{task_description}

【參考上下文 context】
{json.dumps(context, ensure_ascii=False, indent=2)}
"""
    if retry_hint:
        user_content += f"\n\n【系統錯誤自癒回報 - 第 {retry_count} 次重試】\n上次生成失敗原因：{retry_hint}\n請針對此錯誤修正後重新輸出 JSON。"

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]


def build_supplement_messages(
    stage_name: str,
    original_output: str,
    evaluation_feedback: str,
    novel_id: str
) -> list:
    """
    為不合格的輸出進行補強生成或局部修正
    """
    system_prompt = f"""你是一位資深的內容編輯（Content Editor）。
你的任務是根據總監對當前階段【{stage_name}】的評判回饋，對先前生成的內容進行補強、修復與生成。

⚠️【剛性約束項目】：
1. 請只針對缺失的欄位或不合格的部分進行增刪補強，確保最終輸出的 JSON 結構正確且內容符合評估要求。
{JSON_OBJECT_OUTPUT_CONTRACT}
"""
    system_prompt += build_agent_context_contract(
        "Supplement Content / 內容補強修正師",
        "- 原先生成內容。\n- 總監指出的不合格回饋與具體問題。\n- stage_name 決定應符合哪個階段 schema。",
        "只補強或修復不合格部分，保留原內容中已合格的設定與結構。",
        "輸出修正後完整且合法的 JSON；不要輸出與 schema 無關的說明。"
    )
    user_content = f"""【原先生成的內容】
{original_output}

【總監評估之不合格回饋與問題】
{evaluation_feedback}

請根據以上回饋，修正並補強上述內容，重新生成一份完整且合格的 JSON 輸出。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]


