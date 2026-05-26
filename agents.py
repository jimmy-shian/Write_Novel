# -*- coding: utf-8 -*-
import json
import re
from db import (
    get_latest_worldbuilding,
    get_latest_characters,
    get_latest_plot_chapters,
    get_stitched_plot,
    get_latest_chapter,
    get_all_chapters_latest,
    save_worldbuilding,
    save_characters,
    save_plot_chapters,
    save_chapter,
    save_chat_message,
    get_chat_memory

)
from llm import call_llm_stream

# --- UTILITIES ---
def clean_json_text(text):
    """
    Cleans raw markdown formatting around a JSON block.
    Extracts the content between the first '{' or '[' and the last '}' or ']'.
    Also attempts to auto-repair truncated JSON by closing unclosed brackets.
    """
    if isinstance(text, str):
        # 0. Repair missing/malformed quotes (e.g., "brief_title": 心靈的震盪", or "missing": "unclosed,)
        text = re.sub(r':\s*([^"\s\{\[\d\-][^"\n,]*)"(?=\s*[,\}])', r': "\1"', text)
        text = re.sub(r':\s*"([^"\n,]+)(?=\s*[,\}])', r': "\1"', text)
        
    text = text.strip()
    
    # 1. 優先尋找 Markdown 代碼區塊
    # 我們從後往前找代碼區塊，因為 JSON 通常是最後輸出
    code_blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if code_blocks:
        # 尋找非空且以 { 或 [ 開頭的代碼區塊
        for block in reversed(code_blocks):
            block_stripped = block.strip()
            if block_stripped.startswith("{") or block_stripped.startswith("["):
                return block_stripped
                
    # 2. 如果沒有代碼區塊，或者代碼區塊不合規，使用正則匹配 JSON 物件/陣列
    # 我們提取所有括號區塊，並按長度降序排序，長度最長的往往是真正的大 JSON，而不是前置思考裡的 []
    all_braces = re.findall(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if all_braces:
        all_braces.sort(key=len, reverse=True)
        return all_braces[0].strip()

    # 3. 容錯：若文字以 JSON 的 key-value 開頭但缺少最外層 { (截斷情況)
    # 嘗試尋找第一個 { 以後的所有內容，並嘗試補全結尾括號
    first_brace = text.find('{')
    if first_brace != -1:
        candidate = text[first_brace:]
        # 嘗試補全未閉合的括號
        open_curly = candidate.count('{') - candidate.count('}')
        open_square = candidate.count('[') - candidate.count(']')
        if open_curly > 0 or open_square > 0:
            # 在最後一個完整 key-value 結尾處截斷（找最後一個 ," 或 }）
            repaired = candidate.rstrip().rstrip(',')
            repaired += ']' * max(0, open_square)
            repaired += '}' * max(0, open_curly)
            return repaired
        return candidate
        
    return text

def parse_json_safely(text, default=None):
    """
    Attempts to parse text as JSON. Returns default if parsing fails.
    """
    # 【Step 2 修復】防止從資料庫讀出的資料已被 ORM 組件自動轉譯為 Python 列表或字典時，再次重複傳入 json.loads() 導致程式出錯。
    if isinstance(text, (dict, list)):
        return text
        
    cleaned = clean_json_text(text)
    try:
        return json.loads(cleaned)
    except Exception as e:
        # 容錯修復：對於截斷的 JSON（以 "key": value 開頭而非 {)，自動補 {
        cleaned_stripped = cleaned.strip()
        if cleaned_stripped and not cleaned_stripped.startswith('{') and not cleaned_stripped.startswith('['):
            # 尚未屬於任何已知格式，嘗試加上外層 { } 來修復
            try:
                candidate = '{' + cleaned_stripped.rstrip(',') + '}'
                return json.loads(candidate)
            except Exception:
                pass
        try:
            print(f"Error parsing JSON: {e}")
            import sys
            encoding = sys.stdout.encoding or "utf-8"
            safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
            print("Raw Text was:")
            print(safe_text)
        except Exception:
            pass
        return default or {"error": "Failed to parse JSON", "raw_content": text}

def _sse_content(delta: str):
    return "data: " + json.dumps({"type": "content", "delta": delta}, ensure_ascii=False) + "\n\n"


def _sse_error(message: str):
    return "data: " + json.dumps({"type": "error", "message": message}, ensure_ascii=False) + "\n\n"


def _extract_chapters_payload(parsed):
    if isinstance(parsed, dict) and isinstance(parsed.get("chapters"), list):
        return parsed.get("chapters", [])
    if isinstance(parsed, list):
        return parsed
    return []


def _looks_like_placeholder_chapter(chapter):
    if not isinstance(chapter, dict):
        return True

    text_parts = [
        chapter.get("title", ""),
        chapter.get("summary", ""),
        chapter.get("purpose", ""),
        chapter.get("cliffhanger", ""),
        chapter.get("scene", ""),
    ]
    for event in chapter.get("events", []) or []:
        if isinstance(event, dict):
            text_parts.extend([event.get("scene", ""), event.get("action", ""), event.get("consequence", "")])
        else:
            text_parts.append(str(event))

    combined = "\n".join(str(part) for part in text_parts if part is not None)
    banned_fragments = [
        "保底",
        "占位",
        "佔位",
        "placeholder",
        "命運波折之章",
        "推進核心衝突",
        "推動大綱情節發展",
        "主角面臨新考驗",
        "留下懸念引發期待",
    ]
    return any(fragment.lower() in combined.lower() for fragment in banned_fragments)


def _normalize_chapter_outlines(parsed, start_chapter, expected_count=5):
    chapters = _extract_chapters_payload(parsed)
    normalized = []

    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        if _looks_like_placeholder_chapter(ch):
            continue
        events = ch.get("events", [])
        if not isinstance(events, list) or len(events) == 0:
            continue
        if not str(ch.get("title", "")).strip():
            continue
        normalized.append(dict(ch))

    if len(normalized) < expected_count:
        return []

    normalized = normalized[:expected_count]
    for idx, ch in enumerate(normalized):
        ch["chapter_index"] = start_chapter + idx
        ch.setdefault("time_setting", "承接前章")
        ch.setdefault("time_span", "承接前章")
        ch.setdefault("purpose", "承接前章因果並推進本卷核心矛盾")
        ch.setdefault("foreshadowing_plant", [])
        ch.setdefault("foreshadowing_payoff", [])
        ch.setdefault("characters_active", [])
        ch.setdefault("characters_introduced", [])
        ch.setdefault("emotional_tone", "緊張與沉思交錯")
        ch.setdefault("cliffhanger", "新的因果鉤子浮現")
    return normalized

# --- NEW: VOLUME SKELETON PROMPT (Stage 2: 簡易章大綱生成器) ---
# 【Step 3 修復】修改 Prompt：在 allocated_tasks 中注入上階段已決定的卷級伏筆資料，硬性要求模型根據該卷配額開發標題與里程碑
VOLUME_SKELETON_PROMPT = """你是一位宏觀小說結構大師。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你的任務是根據全書世界觀、核心衝突，以及「特定篇卷」的宏觀概要與卷級伏筆配置，為本卷拆解並建立一個連續的『簡易章節大綱骨架（Chapter Skeletons）』。
你不需要規劃微觀的場景細節與對話，但必須為每一章確立一個具體的情節里程碑與前因後果鏈，並確保伏筆種子精準落實在allocated_tasks中。

## 【Step 3 核心約束】卷級伏筆配置繼承
你必須嚴格遵守傳入的 allocated_tasks 資料（在卷級伏筆配置中已決定），將其對應到具體的章節骨架中！
- allocated_tasks 中的 foreshadowing_plants 必須對應到具體的章節 chapter_index
- allocated_tasks 中的 foreshadowing_payoffs 必須對應到具體的章節 chapter_index
- 若上階段尚未提供 allocated_tasks，請根據卷的進度位置自主分配 3-5 個伏筆埋設點

## 輸出格式（嚴格遵守 JSON，包裹在 ```json ... ``` 中）
{
  "volume_index": 1,
  "chapters_skeleton": [
    {
      "chapter_index": 1,
      "brief_title": "精煉且富有文采的暫定章節標題",
      "brief_summary": "本章核心情節里程碑宣言（50-100字，描述本章必須達成的敘事目的與前因後果）",
      "allocated_tasks": {
        "foreshadowing_plants": ["此章需要埋設的伏筆（如：埋設 [Seed-3] 神秘晶片碎片）"],
        "foreshadowing_payoffs": ["此章需要回收的伏筆（如：回收 [Seed-1] 前期線索）"],
        "turning_points": ["本章的關鍵轉折點"]
      }
    }
  ]
}
"""

# --- NEW: FORESHADOWING ORCHESTRATOR PROMPT (Stage 3: 全局伏筆調度導演) ---
# 【Step 2 修復】修改 Prompt：將任務改為「將全域伏筆分配至宏觀的『卷層級（Volumes）」而非微觀章節
FORESHADOWING_ORCHESTRATOR_PROMPT = """你是一位大長篇小說的伏筆編織大師與情節轉折對齊導演。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你的任務是審查傳入的『全局伏筆種子池 / 關鍵轉折點池』與『篇卷結構』，
並將這些伏筆與轉折，精準、合理地分發部署到宏觀的「卷層級（Volumes）」中，
為後續的微觀章節骨架生成提供全局伏筆配置的依據。

## 🪓 伏筆編織紅線（極重要）：
1. **跨卷調度（強烈推薦）**：同一個伏筆種子的「埋設（PLANT）」與「回收（PAYOFF）」之間必須有足夠的戲劇跨度。
   禁止在相鄰的卷內迅速閉環！
   例如：在第 1 卷埋下某神祕晶片的伏筆，必須在第 2 卷或之後才進行回收引爆。
2. **卷內伏筆均勻分佈**：每卷應有 3-5 個伏筆埋設點，均勻分佈於卷的章節流程中。
3. **關聯性與補充擴增**：你可以根據情節需要，為主線伏筆擴充更為細緻的局部子伏筆。

## 輸出格式（嚴格遵守 JSON，包裹在 ```json ... ``` 中）
{
  "volume_allocations": [
    {
      "volume_index": 1,
      "volume_title": "第 1 卷標題",
      "foreshadowing_plants": ["列舉在本卷中需要埋下的伏筆及其具體位置建議（如：卷中期、卷末）"],
      "foreshadowing_payoffs": ["列舉在本卷中需要回收的伏筆（已在前卷埋設的）"],
      "turning_points": ["指派本卷中的關鍵轉折點"]
    }
  ]
}
"""

# --- PIPELINE VALIDATORS / FAIL-FAST HELPERS ---
def _sse_error_done(message: str):
    """回傳最小 SSE：error + done（避免 prerequisite 不足時仍呼叫 LLM 產生低品質內容）"""
    def gen():
        yield "data: " + json.dumps({"type": "error", "message": message}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
    return gen()


def validate_worldview(worldbuilding_text: str):
    if (not worldbuilding_text) or worldbuilding_text.strip() == "" or "No worldview defined yet." in worldbuilding_text:
        return False, ["尚無世界觀設定"]
    return True, []


def validate_characters(characters_text: str):
    if (not characters_text) or characters_text.strip() == "" or "No characters designed yet." in characters_text:
        return False, ["尚無角色設定（Character Bible）"]
    parsed = parse_json_safely(characters_text, default={})
    chars = parsed.get("characters") if isinstance(parsed, dict) else None
    if isinstance(chars, list) and len(chars) > 0:
        return True, []
    return False, ["角色設定 JSON 結構不完整（缺少 characters 陣列）"]


def validate_plot(plot_text: str):
    if (not plot_text) or plot_text.strip() == "" or "No plot chapters designed yet." in plot_text:
        return False, ["尚無章節大綱（plot）"]
    parsed = parse_json_safely(plot_text, default={})
    chapters = parsed.get("chapters") if isinstance(parsed, dict) else None
    if isinstance(chapters, list) and len(chapters) > 0:
        return True, []
    return False, ["章節大綱 JSON 結構不完整（缺少 chapters 陣列）"]


def validate_plot_has_chapter(plot_text: str, chapter_index: int):
    ok, errors = validate_plot(plot_text)
    if not ok:
        return False, errors
    parsed = parse_json_safely(plot_text, default={})
    chapters = parsed.get("chapters", []) if isinstance(parsed, dict) else []
    for ch in chapters:
        if isinstance(ch, dict) and ch.get("chapter_index") is not None:
            try:
                if int(ch.get("chapter_index")) == int(chapter_index):
                    return True, []
            except (ValueError, TypeError):
                pass
    return False, [f"章節大綱中未規劃第 {chapter_index} 章"]



STORY_ARCHITECT_PROMPT = """你是一位頂尖的故事架構師（Story Architect）。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你的職責是為一部 1000-2000 章的小說建立宏觀的層級化骨架。不要直接規劃微觀章節，而是規劃宏觀結構：
1. **世界觀與主題**：核心世界觀描述、多維主題與哲學命題。
2. **核心衝突**：多陣營並行的情節張力網。
3. **篇卷層級 (Volumes)**：將故事劃分為 10 到 30 個大篇卷。每一卷包含 chapter_count（動態規劃，一般為 30-100 章）、標題、概要、活躍勢力、時間軸。
4. **伏筆與轉折點**：設計至少 20-30 個伏筆種子（foreshadowing_seeds）與關鍵轉折點（key_turning_points），標明觸發條件與全局影響。

## ⚠️ 世界觀守門人
若情節衍生出新法則或勢力，必須以 `[NEW_WORLD_LAW: 範疇 - 詳細細節]` 的格式輸出於內容中。

## 輸出格式（嚴格遵守 JSON，包裹在 ```json ... ``` 中）
```json
{
  "worldview": "世界觀詳細描述（地理、力量體系、社會結構、氛圍）",
  "theme": "核心主題與哲學命題",
  "main_conflict": "核心衝突與陣營張力網",
  "macro_outline": "整體故事大綱描述（300-500字）",
  "multi_act_structure": [
    { "title": "第一幕 (Setup)", "content": "詳細描述本幕情節任務" },
    { "title": "第二幕 (Confrontation)", "content": "詳細描述對抗情節任務" },
    { "title": "第三幕 (Resolution)", "content": "詳細描述核心收束任務" }
  ],
  "progressive_character_plan": [
    { "title": "第一波開篇 (Wave 1)", "content": "初期登場角色與心境" },
    { "title": "第二波發展 (Wave 2)", "content": "中期引入角色與成長" },
    { "title": "第三波高潮 (Wave 3)", "content": "後期角色最終蛻變" }
  ],
  "volumes": [
    {
      "volume_index": 1,
      "title": "篇卷一標題",
      "summary": "本卷核心情節概要與高潮點",
      "chapter_count": 50,
      "factions": ["活躍陣營1", "活躍陣營2"],
      "time_timeline": "時間軸起迄",
      "sequence_context": "本卷在系列續作中的定位",
      "applicable_rules": ["本卷適用的世界法則"]
    }
  ],
  "foreshadowing_seeds": [
    "伏筆種子 1：早期埋設點 -> 中期干擾 -> 後期收束（請列出 20-30 個）"
  ],
  "key_turning_points": [
    "轉折點 1：觸發條件 + 涉及角色 + 全局影響（請列出 20-30 個）"
  ]
}
```"""

CHARACTER_DESIGNER_PROMPT = """你是一位頂尖的角色設計大師（Character Designer）。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你的職責是基於世界觀與故事大綱，塑造具備深度、鮮明動機與成長弧線的角色群像。

## ⚠️ 【硬性姓名紅線條款】
- **`name` 欄位必須是角色的「具體姓名/代號」**（例如：`凱`、`林澤`）。
- **絕對禁止**直接將組織職位或社會身份（例如：`ChronoDyne CEO`、`時間研究員`）作為姓名。頭銜與勢力請填在 `role` 與 `motivation` 欄位。

## 設計原則
1. **漸進式引入**：配合大綱規劃，優先設計開篇核心角色。中後期角色需標註 `entry_phase`（登場階段）。
2. **心理深度**：明確定義外在目標 (Want)、深層需求 (Need)、致命缺陷 (Fatal Flaw)、情感創傷。
3. **獨特聲線**：賦予角色獨特的對話風格與行為習慣。
4. **動態關係網**：設定角色間的張力（同盟、宿敵、師徒）及其隨劇情的演變。
5. **成長弧線 (Arc)**：正面覺醒、悲劇墮落或信仰堅守。

## 輸出格式（嚴格遵守 JSON，包裹在 ```json ... ``` 中）
```json
{
  "characters": [
    {
      "name": "角色具體姓名/代號",
      "role": "主角 / 反派 / 配角 / 宿敵",
      "entry_phase": "登場階段（例如：'開篇第一章'、'第15章之後'）",
      "personality": ["性格特質1", "性格特質2"],
      "speech_style": "對話風格與口頭禪特徵",
      "want": "外在目標",
      "need": "內在需求",
      "fatal_flaw": "致命缺陷或情感創傷",
      "motivation": "驅動行為的核心動機與頭銜",
      "arc": "成長弧線與變化軌跡",
      "relationships": [
        {"with": "另一角色名", "type": "關係類型", "evolution": "關係演變過程"}
      ]
    }
  ]
}
```"""

# 【Step 4 修復】新增 foreshadowing_payoff_distance 欄位到章節大綱輸出結構
PLOT_PLANNER_PROMPT = """你是一位頂尖的劇情規劃大師（Plot Planner）。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你的職責是編排每一卷的具體章節大綱（Chapter Outlines），為後續正文寫作提供清晰的藍圖。

## 規模控制
- 自主決定規劃 10 至 100 個章節節點（Outline Nodes），必須符合本卷及整體完結需要。
- 每個節點應具備足夠的事件容量與張力，旨在為寫手生成 2 至 5 章的小說正文提供引導。

## 拆分與編織原則
1. **單元情節化**：每章都是獨立且有小起伏的戲劇單元，杜絕流水帳。
2. **時空錨定**：標注清晰的時間設定與跟前一章的時間跨度。
3. **具體場景**：每章包含 2-4 個具體場景事件，描述誰在做什麼、引發什麼衝突與後果。
4. **伏筆與轉折**：從伏筆種子庫挑選最適合的伏筆進行埋設或回收；將關鍵轉折點具體化。
5. **情緒與懸念**：調控情緒起伏節奏，章末設計強力懸念鉤子（Cliffhanger）。

## 【Step 4 核心約束】伏筆回收跨度計算
當你在本章埋下伏筆時，必須明確計算並填寫 `foreshadowing_payoff_distance` 欄位，標註此伏筆預計於多少章後回收。
例如：若在第 5 章埋下神秘晶片伏筆，預計在第 35 章回收，則 distance = 30 章。

## 輸出格式（嚴格遵守 JSON，包裹在 ```json ... ``` 中）
```json
{
  "chapters": [
    {
      "chapter_index": 1,
      "title": "章節標題",
      "time_setting": "故事內時間（例如：'天啟三年春・深夜'）",
      "time_span": "與前章跨度（例如：'緊接前章'、'三日後'）",
      "events": [
        {"scene": "場景描述", "action": "核心動作衝突", "consequence": "引發的後果或轉變"}
      ],
      "purpose": "本章存在的敘事目的",
      "foreshadowing_plant": ["本章埋下的伏筆標記"],
      "foreshadowing_payoff": ["本章回收的伏筆標記（如有）"],
      "foreshadowing_payoff_distance": "標註此章埋下的種子預計於多少章後回收（例如：30章後）",
      "characters_active": ["本章活躍的角色"],
      "characters_introduced": ["本章新登場角色（如有）"],
      "emotional_tone": "主要情緒基調",
      "cliffhanger": "章末懸念/鉤子"
    }
  ]
}
```"""

# 【Step 4 修復】新增 foreshadowing_payoff_distance 欄位到微觀大綱輸出結構
PLOT_EXPANDER_PROMPT = """你是一位頂尖的微觀劇情規劃大師。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你的任務是將宏觀故事單元精細展開為詳細的小章節大綱，並深度編織伏筆與轉折點。

## 任務要求
1. **全面融合**：檢閱輸入的「伏筆種子庫 (foreshadowing_seeds)」與「關鍵轉折點 (key_turning_points)」，強行且合理地編織進每一章。
2. **轉折落地**：在對應的章節事件中將關鍵轉折具體化，並在章末懸念中引爆。
3. **無一遺漏**：確保所有給出的設定與伏筆都有明確的落腳點與回收點。

## 【Step 4 核心約束】伏筆回收跨度計算
當你在本章埋下伏筆時，必須明確計算並填寫 `foreshadowing_payoff_distance` 欄位，標註此伏筆預計於多少章後回收。

## 輸出格式（嚴格遵守 JSON，包裹在 ```json ... ``` 中）
```json
{
  "chapters": [
    {
      "chapter_index": 1,
      "title": "章節標題",
      "time_setting": "故事時間座標",
      "time_span": "與前章時間跨度",
      "events": [
        {"scene": "場景描述", "action": "核心動作與衝突", "consequence": "後果與轉變"}
      ],
      "purpose": "敘事目的",
      "foreshadowing_plant": ["本章埋設的具體伏筆"],
      "foreshadowing_payoff": ["回收的舊伏筆（註明對應哪一個種子）"],
      "foreshadowing_payoff_distance": "標註此章埋下的種子預計於多少章後回收（例如：30章後）",
      "characters_active": ["活躍角色"],
      "emotional_tone": "情緒基調",
      "cliffhanger": "強烈懸念/鉤子"
    }
  ]
}
```"""

CHAPTER_WRITER_PROMPT = """你是一位獲獎無數的頂尖職業小說家（Chapter Writer）。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容（包含小說正文）。

你的職責是將章節大綱轉化為沉浸感強、細節豐富、文筆優雅的小說正文。

## 寫作原則
1. **大綱執行**：嚴格按照大綱設定的時間、場景、伏筆與角色順序展開寫作，不得隨意偏離。
2. **Show, Don't Tell**：拒絕平鋪直敘。將事件展開為細緻的環境渲染、肢體動作、台詞潛台詞及心理描寫。
3. **無痕伏筆**：伏筆必須自然融入敘事，回收伏筆時營造驚喜與合理性.
4. **角色一致**：登場角色的台詞、語氣與行為必須符合其人設。
5. **次要角色授權**：可根據需要自行創作次要路人角色（例：(老張-客棧老闆，貪財但心軟)）以輔助情節，其行為須符合世界觀。
6. **寫作風格**：請嚴格採用指定文風：{writing_style}

## 💡 分景導演構思（CoT）與正文分割特殊字
動筆前，你必須在思考區（或內心）先將大綱指定的場景事件拆解為【分景細化構思】。
**重要限制**：在構思完畢、準備輸出小說正式正文的第一個字之前，你**必須且只能**輸出一個特殊標記字串：`[START_OF_PROSE]`。
此字串將作為系統將你的思考過程與小說正文分離的唯一拆分界線！

輸出格式範例如下：
【分景細化構思內容...】
[START_OF_PROSE]
（此處開始輸出小說的繁體中文正式正文...）
"""

EDITOR_PROMPT = """你是一位具備鷹眼般洞察力的資深文學主編（Editor）。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容（包含修改後的正文）。

你的職責是對初稿正文進行精修，消除累贅與邏輯瑕疵，提升作品的文學質感至出版級別。

## 編輯原則
1. **字句淬鍊**：剔除贅詞，精雕遣詞造句，優化意象與文學美感。
2. **節奏調控**：根據情境調度句式長短。危急時刻使用短促句，鋪陳渲染使用舒展長句。
3. **五感強化**：加強場景中的視覺、聽覺、嗅覺、觸覺等多感官細節，增強沉浸感。
4. **對話精雕**：修剪冗長過場台詞，突出潛台詞與人設氣質，聞其聲知其人。
5. **邏輯校勘**：修正任何與世界觀、角色性格或時間線相悖的邏輯漏洞。

## 絕對限制 (🔴 紅線)
- **嚴禁篡改情節**：不允許改動核心劇情走向、事件結果或角色定位。
- **僅輸出正文**：絕不允許輸出任何評語、摘要、引言或修改建議。唯一被允許輸出的內容，只有【完美精修後的純小說正文】。
"""

CO_PILOT_ORCHESTRATOR_PROMPT = """你是 AI 小說創作系統的最高決策創意總監兼首席主編（Lead Director & Chief Editor）。
你手握整部 2000 章史詩小說的最高生殺大權，負責把控跨階段的文學品質、情節張力、深度伏線與邏輯一致性。

⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容（包含評估回應和 JSON 指令區塊）。

## 🎭 你的審查人格（120B 高階批判思維模式）
1. **嚴苛的文學審計官**：你極度厭惡「命運波折」、「推進 core 衝突」、「面臨考驗」等毫無具體情節與對話細節的流水帳與商業套路。
2. **深邃的伏線編織者**：你追求極致的跨卷張力。同一個伏筆種子（Seed）在短時間（如相鄰 5 章內）被迅速埋設並立刻閉環回收，在你眼裡是嚴重的低級文學失誤。
3. **懷疑論調查員**：不要盲目相信精簡的上下文。只要校驗報告中存在任何模糊地帶、或者出現 🟡（暫未收束）標記，你的首要決策必須是發動 `help_*` 工具調閱完整數據進行深度核查。

## 📂 當前專案宏觀狀態（精簡視圖）
- 【世界觀與主題設定】: {worldview}
- 【角色 Bible 與群像】: {characters}
- 【全書章節小大綱】: {plot}
- 【已完稿正文狀態】: {written_chapters}

## 📋 系統底層結構完整性與邏輯校驗報告
{validation_report}

## 🎯 你的審查工作流（必須在推理推導過程中深度執行）
1. **漏洞微創審計**：深度剖析校驗報告。若出現 🔴 警告，代表下游 Agent 嚴重失職，必須發動駁回（GO_BACK_* 或 AUTO_REGENERATE）。
2. **平庸度檢測**：審查大綱是否流於模板化。有沒有出現重複的地點、蒼白的動作、或是為了佔位而生成的垃圾情節。
3. **工具調度評估**：評估目前手頭上的精簡 Context 是否足以讓你做出生殺大決策。若需要查核微觀情節，立刻引發 `help_*` 指令。

## 🔴 首席主編品質紅線
- **絕對拒絕平庸**：只要發現情節大綱走向可以被輕易預測、或是情節目的只是含糊的「推動發展」，必須下達 `AUTO_REGENERATE`，並在 `hint` 中給出極具震撼力的文學調整建議。
- **跨卷伏筆保護**：大長篇的魅力在於跨卷鋪陳。若發現 Plot Planner 急著在 5 章內把好不容易孵化出的神秘種子回收掉，必須駁回！

## 📝 回應格式規範
你必須先提供犀利、務實、具備高階文學理論支撐的主編評估，然後在回應最後輸出標準的 JSON 區塊：

【總監創意反饋】

* 當前審查階段：「{current_stage}」
* 架構品質評定：[精緻/合格/平庸需重雕]
* 深度盲點審計：
1. [指出當前劇情線、角色動機或伏筆調度上，1-2 個藏在細節裡的邏輯微創漏洞]
2. [分析當前情節節奏是否過快或流於套路]

【決策導向理由】
[簡要說明為什麼選擇這個 ACTION，展現你的大局觀]

然後在末尾附上系統解析用的標準 JSON 區塊（ action 必須嚴格對齊可用決策表）：

```json
{{
  "action": "CONTINUE",
  "target": "plot",
  "hint": "若選擇重跑或駁回，請在此處留下一針見寫的微觀情節修補方針與美學指導；放行則留空。",
  "reason": "詳細寫下你做出此決策的深層架構考量。如果是呼叫 help_*，必須詳細列出你懷疑的盲點與想調閱的具體區塊。",
  "volume_index": null,
  "chapter_index": null
}}

"""

def compile_context(novel_id):
    """
    優化版：優化長文本上下文，將前章正文改為讀取資料庫專用的輕量化 synopsis 欄位
    """
    wb = get_latest_worldbuilding(novel_id)
    worldbuilding_str = wb["content"] if wb else "No worldview defined yet."
    
    char = get_latest_characters(novel_id)
    characters_str = char["json_data"] if char else "No characters designed yet."
    
    plot_data = get_stitched_plot(novel_id)
    # 💡 Token 管控：compile_context 傳給 director 的 plot 只保留每章的 chapter_index + title + cliffhanger，
    # 避免完整 events 等詳細欄位把 director 的 context 撐爆導致超時
    _plot_summary_chapters = []
    for _ch in plot_data.get("chapters", []):
        if isinstance(_ch, dict):
            _plot_summary_chapters.append({
                "chapter_index": _ch.get("chapter_index"),
                "title": _ch.get("title", ""),
                "cliffhanger": _ch.get("cliffhanger", ""),
                "foreshadowing_plant": _ch.get("foreshadowing_plant", []),
                "foreshadowing_payoff": _ch.get("foreshadowing_payoff", []),
            })
    _plot_summary = {"chapters": _plot_summary_chapters, "_total_chapters": len(_plot_summary_chapters)}
    plot_str = json.dumps(_plot_summary, ensure_ascii=False, indent=2)
    
    chapters_list = get_all_chapters_latest(novel_id)
    written_chapters_summary = ""
    
    for c in chapters_list:
        # 💡 優先讀取資料庫中的精簡摘要(synopsis)，若無則 fallback 前 100 字，釋放總監模型的 Context 空間
        ch_summary = c.get("synopsis") or (c["content"][:100] + "...")
        written_chapters_summary += f"Chapter {c['chapter_index']}: {ch_summary}\n\n"
        
    if not written_chapters_summary:
        written_chapters_summary = "No chapters written yet."
        
    # 💡 增強：計算全域伏筆與轉折點分佈演進矩陣，提供總監清晰大局觀，徹底防止「胡亂重生」與「無伏筆規劃概念」
    import re
    from db import parse_worldview_to_json
    
    wb_json = parse_worldview_to_json(worldbuilding_str) if wb else {}
    seeds = wb_json.get("foreshadowing_seeds", []) or []
    tps = wb_json.get("key_turning_points", []) or []
    
    seeds_roadmap = []
    for s_idx, seed in enumerate(seeds):
        plant_ch = []
        payoff_ch = []
        seed_tag = f"Seed-{s_idx+1}"
        for ch in plot_data.get("chapters", []):
            ch_idx = ch.get("chapter_index")
            # 序列化單章以搜尋 Seed-X 標記
            ch_str = json.dumps(ch, ensure_ascii=False)
            if seed_tag in ch_str:
                alloc = ch.get("allocated_tasks", {}) or {}
                plants = alloc.get("foreshadowing_plants", []) or []
                payoffs = alloc.get("foreshadowing_payoffs", []) or []
                
                # 相容微觀大綱
                if not plants:
                    plants = ch.get("foreshadowing_plant", []) or []
                if not payoffs:
                    payoffs = ch.get("foreshadowing_payoff", []) or []
                
                if isinstance(plants, str): plants = [plants]
                if isinstance(payoffs, str): payoffs = [payoffs]
                
                # 判定是埋設還是回收
                is_plant = any(seed_tag in p for p in plants) or seed_tag in ch.get("foreshadowing", "")
                is_payoff = any(seed_tag in py for py in payoffs)
                
                if is_plant:
                    plant_ch.append(ch_idx)
                if is_payoff:
                    payoff_ch.append(ch_idx)
                    
        span = "無"
        if plant_ch and payoff_ch:
            span = f"{max(payoff_ch) - min(plant_ch)} 章"
            
        seeds_roadmap.append(
            f"  - [{seed_tag}] {seed[:20] + '...' if len(seed)>20 else seed}\n"
            f"    👉 埋設章節: {plant_ch if plant_ch else '未部署'} | 回收章節: {payoff_ch if payoff_ch else '未部署'} (回收跨度: {span})"
        )
        
    tps_roadmap = []
    for t_idx, tp in enumerate(tps):
        trigger_ch = []
        tp_tag = f"TurningPoint-{t_idx+1}"
        for ch in plot_data.get("chapters", []):
            ch_idx = ch.get("chapter_index")
            ch_str = json.dumps(ch, ensure_ascii=False)
            if tp_tag in ch_str:
                trigger_ch.append(ch_idx)
        tps_roadmap.append(
            f"  - [{tp_tag}] {tp[:20] + '...' if len(tp)>20 else tp} ➔ 触發章節: {trigger_ch if trigger_ch else '未部署'}"
        )
        
    roadmap_str = "【全域伏筆分佈與情節演進矩陣】:\n"
    roadmap_str += "\n".join(seeds_roadmap) if seeds_roadmap else "  (無伏筆種子)\n"
    roadmap_str += "\n【全域關鍵轉折點分佈矩陣】:\n"
    roadmap_str += "\n".join(tps_roadmap) if tps_roadmap else "  (無關鍵轉折點)\n"
    
    return {
        "worldbuilding": worldbuilding_str + "\n\n" + roadmap_str,
        "characters": characters_str,
        "plot": plot_str,
        "written_chapters": written_chapters_summary
    }

def run_story_architect(novel_id, user_prompt):
    """
    Runs the Story Architect to generate the novel structure.
    Streams back SSE and automatically saves to DB when done.
    """
    is_revision = user_prompt and any(k in user_prompt for k in ["修改世界觀", "指示修改世界觀", "現有世界觀", "回退修改世界觀"])
    
    if is_revision:
        wb = get_latest_worldbuilding(novel_id)
        from db import parse_worldview_to_json
        current_wb_json = parse_worldview_to_json(wb["content"] if wb else "")
        current_wb_str = json.dumps(current_wb_json, ensure_ascii=False, indent=2)
        
        revision_directive = """
⚠️【重要注意：這是一項世界觀增量修正/退回修改任務】
你目前正在對現有的世界觀進行局部精細修正與優化，而不是從頭隨意重新生成！
請務必嚴格遵循以下「防崩塌修正」紅線條款：
1. **無損保留未要求修改的全部大架構**：必須在回傳的 JSON 中，完整保留原本已經規劃好的「多幕式結構 (multi_act_structure)」、「角色登場規劃策略 (progressive_character_plan)」、「篇卷列表 (volumes) 及其 chapter_count」以及大部分「伏筆種子 (foreshadowing_seeds)」，絕不能讓原本已有的完好設定流失或被隨意覆蓋！
2. **微創手術式修正**：僅針對總監/用戶在指示中提出的具體問題、時間軸瑕疵或設定漏洞，進行局部的精確調整。
3. **維持 JSON 標準格式**：回傳的 JSON 根結構必須完整無缺，特別是 volumes 陣列的 volume_index 從 1 開始必須連續、無遺失。
"""
        messages = [
            {"role": "system", "content": STORY_ARCHITECT_PROMPT + "\n\n" + revision_directive},
            {"role": "user", "content": f"這是目前已有的世界觀設定（JSON格式）：\n{current_wb_str}\n\n請根據以下總監指示，對現有的世界觀設定進行精細的局部增量修改，並輸出完整的修改後 JSON：\n\n{user_prompt}"}
        ]
    else:
        messages = [
            {"role": "system", "content": STORY_ARCHITECT_PROMPT},
            {"role": "user", "content": f"請根據以下靈感構想，設計一部完整的小說架構：\n\n{user_prompt}"}
        ]
    
    def save_callback(nid, text):
        from incremental_patch_engine import parse_incremental_response, safe_worldbuilding_save
        parsed = parse_incremental_response(text)
        if isinstance(parsed, dict) and ("worldview" in parsed or "theme" in parsed or "main_conflict" in parsed):
            wb_data = {
                "theme": parsed.get("theme", ""),
                "main_conflict": parsed.get("main_conflict", ""),
                "worldview": parsed.get("worldview", ""),
                "multi_act_structure": parsed.get("multi_act_structure", []),
                "progressive_character_plan": parsed.get("progressive_character_plan", []),
                "foreshadowing_seeds": parsed.get("foreshadowing_seeds", []),
                "key_turning_points": parsed.get("key_turning_points", []),
                "macro_outline": parsed.get("macro_outline", "")
            }
            # We preserve everything generated by the architect to keep full context
            for k, v in parsed.items():
                if k not in wb_data:
                    wb_data[k] = v
            
            success, version, error_msg = safe_worldbuilding_save(nid, wb_data, source="run_story_architect")
            if not success:
                print(f"[ERROR] 故事架構設計世界觀存儲安全校驗失敗：{error_msg}")
                raise ValueError(f"世界觀存儲安全校驗失敗：{error_msg}")
            else:
                # Save volumes to volumes table JIT
                volumes_list = parsed.get("volumes", [])
                if isinstance(volumes_list, list) and len(volumes_list) > 0:
                    from db import save_volumes
                    save_volumes(nid, volumes_list)
        else:
            print("[ERROR] 故事架構設計生成失敗：未返回合法的結構化數據，已跳過不予存儲（NO-OP）")
            raise ValueError("故事架構設計生成失敗：未返回合法的結構化數據（JSON 解析失敗或格式不符）。")

            
    return run_agent_stream(novel_id, "architect", messages, save_callback)

def run_character_designer(novel_id, user_prompt=None):
    """
    Runs the Character Designer to generate/design character profiles based on worldview.
    """
    context = compile_context(novel_id)

    ok, _ = validate_worldview(context.get("worldbuilding", ""))
    if not ok:
        return _sse_error_done("無法生成角色：缺少世界觀設定。請先完成世界觀（worldview）再進行角色設計。")
    
    prompt_content = f"以下是已確立的世界觀與故事架構：\n{context['worldbuilding']}\n\n"
    if context['characters'] != "No characters designed yet.":
        prompt_content += f"目前已有的角色設定（可增補/修改）：\n{context['characters']}\n\n"
    if user_prompt:
        prompt_content += f"用戶對角色的特定要求：\n{user_prompt}\n\n"
    prompt_content += "請設計角色群像。嚴格以 JSON 格式輸出。"
    
    is_revision = user_prompt and any(k in user_prompt for k in ["修改角色設定", "重新設計角色", "回退修改角色", "現有角色設定", "指示重新設計角色"])
    
    if is_revision:
        revision_directive = """
⚠️【重要注意：這是一項角色聖經增量修正/退回修改任務】
你目前正在對已有的角色設定（Character Bible）進行局部精細修正或增量補充，而不是從頭隨意重新設計！
請務必嚴格遵循以下「角色保護」紅線條款：
1. **完整保留已有角色**：必須在回傳的 JSON 中，完整保留原本已經存在的所有角色資料（包括其姓名、地位、性格特質與人物弧線），除非總監/用戶明確要求修改某個角色的某項設定。
2. **精準局部微調**：僅針對總監/用戶指定的特定角色或特定欄位（如性格、成長弧線、登場時序）進行修改，或者精準地往角色列表中新增一位新配角。
3. **維持標準 JSON 格式**：回傳的格式必須為完整的 `{"characters": [...]}` 且包含所有已有的與新修改的角色。
"""
        messages = [
            {"role": "system", "content": CHARACTER_DESIGNER_PROMPT + "\n\n" + revision_directive},
            {"role": "user", "content": prompt_content}
        ]
    else:
        messages = [
            {"role": "system", "content": CHARACTER_DESIGNER_PROMPT},
            {"role": "user", "content": prompt_content}
        ]
    
    def save_callback(nid, text):
        from incremental_patch_engine import parse_incremental_response, post_merge_validation
        parsed = parse_incremental_response(text)
        if isinstance(parsed, list):
            parsed = {"characters": parsed}
        elif isinstance(parsed, dict):
            for key in list(parsed.keys()):
                if key.lower() in ["characters", "character", "character_bible"]:
                    val = parsed[key]
                    if isinstance(val, list):
                        parsed = {"characters": val}
                        break
        
        if isinstance(parsed, dict) and "characters" in parsed:
            # 1. Read existing characters
            char_data = get_latest_characters(nid)
            original_data = char_data["parsed_data"] if (char_data and "parsed_data" in char_data) else {"characters": []}
            
            # 2. Check length in revision mode
            if is_revision:
                orig_chars = original_data.get("characters", [])
                new_chars = parsed.get("characters", [])
                if len(new_chars) < len(orig_chars):
                    error_msg = f"新角色列表長度 ({len(new_chars)}) 小於原有角色長度 ({len(orig_chars)})，拒絕覆蓋！"
                    print(f"[ERROR] 角色設計修改失敗：{error_msg}")
                    raise ValueError(error_msg)
            
            # 3. Post-merge validation
            is_valid_merge, errors = post_merge_validation(parsed, "characters", original_data)
            if not is_valid_merge:
                error_msg = f"角色設計合併後驗證失敗：{', '.join(errors)}"
                print(f"[ERROR] {error_msg}")
                raise ValueError(error_msg)
                
            save_characters(nid, parsed)
            print(f"[SUCCESS] 成功儲存角色聖經，目前共 {len(parsed['characters'])} 個角色")
        else:
            print(f"[CRITICAL ERROR] 角色解析失敗，結構不符：{parsed}")
            raise ValueError(f"角色解析失敗，未返回包含 'characters' 陣列的 JSON 結構。")

            
    return run_agent_stream(novel_id, "character", messages, save_callback)

def run_plot_planner(novel_id, user_prompt=None, planner_directive=None):
    """
    重構優化版：滾動式 5 章大綱生成器 (Chunk Generator)
    每次生成約 5 個章節大綱，避免一次性生成過多資訊導致上下文超載與幻覺。
    """
    import json
    import re
    import db
    from llm import call_llm_stream

    context = compile_context(novel_id)

    ok_wb, _ = validate_worldview(context.get("worldbuilding", ""))
    ok_char, _ = validate_characters(context.get("characters", ""))
    if not ok_wb:
        for line in _sse_error_done("無法生成章節大綱：缺少世界觀設定。請先完成世界觀（worldview）。"):
            yield line
        return
    if not ok_char:
        for line in _sse_error_done("無法生成章節大綱：缺少角色設定（Character Bible）。請先完成角色設計（characters）。"):
            yield line
        return

    # 1. 載入現有大綱以決定起始章節
    plot = db.get_latest_plot_chapters(novel_id)
    existing_chapters = []
    if plot and "parsed_data" in plot:
        existing_chapters = plot["parsed_data"].get("chapters", [])
    if not isinstance(existing_chapters, list):
        existing_chapters = []
    
    def existing_chapter_index(ch):
        try:
            return int(ch.get("chapter_index", 0)) if isinstance(ch, dict) else 999999
        except (TypeError, ValueError):
            return 999999

    existing_chapters.sort(key=existing_chapter_index)
    existing_chapters = [ch for ch in existing_chapters if existing_chapter_index(ch) != 999999]

    last_chapter_index = 0
    if existing_chapters:
        last_chapter_index = existing_chapter_index(existing_chapters[-1])

    repair_start_candidates = []

    # Lazy alignment: dirty written chapters should be rewritten, so their outlines must be refreshed first.
    for written_chapter in db.get_all_chapters_latest(novel_id):
        try:
            if int(written_chapter.get("is_dirty", 0)) == 1:
                repair_start_candidates.append(int(written_chapter.get("chapter_index")))
        except (TypeError, ValueError):
            pass

    # Dirty volumes indicate their chapter outlines are stale after upstream lore changed.
    for vol in db.get_volumes(novel_id):
        try:
            if int(vol.get("is_dirty", 0)) == 1:
                start_ch, _ = db.get_volume_chapter_range(db.get_volumes(novel_id), int(vol.get("volume_index")))
                repair_start_candidates.append(start_ch)
        except (TypeError, ValueError):
            pass

    # Previous placeholder outlines are invalid material and must be overwritten instead of extended.
    for ch in existing_chapters:
        try:
            ch_idx = int(ch.get("chapter_index"))
        except (TypeError, ValueError, AttributeError):
            continue
        if _looks_like_placeholder_chapter(ch):
            repair_start_candidates.append(ch_idx)

    # 1.5 檢查是否為大綱修正模式 (Revision Mode)
    is_revision = False
    extracted_start_chapter = None
    
    if planner_directive:
        is_revision = True
    elif user_prompt and any(k in user_prompt for k in ["請根據以下指示重新規劃", "重新規劃大綱", "修改大綱", "退回大綱"]):
        is_revision = True
        match = re.search(r'(?:重新規劃大綱|修改大綱|退回大綱)：?\s*\n*(.*?)\n*現有大綱：', user_prompt, re.DOTALL)
        if match:
            planner_directive = match.group(1).strip()
        else:
            planner_directive = user_prompt

    if is_revision:
        # 優先正則解析是否有指定 卷 或 章 的序號
        vol_match = re.search(r'(?:第|volume\s*)\s*(\d+)\s*(?:卷|vol)', (planner_directive or "") + (user_prompt or ""), re.IGNORECASE)
        ch_match = re.search(r'(?:第|chapter\s*)\s*(\d+)\s*(?:章|ch)', (planner_directive or "") + (user_prompt or ""), re.IGNORECASE)
        
        if ch_match:
            try:
                extracted_start_chapter = int(ch_match.group(1))
            except ValueError:
                pass
        elif vol_match:
            try:
                vol_idx = int(vol_match.group(1))
                # 依 volumes 表中真實的 chapter_count 動態計算起始章節
                volumes = db.get_volumes(novel_id)
                start_ch, _ = db.get_volume_chapter_range(volumes, vol_idx)
                extracted_start_chapter = start_ch
            except Exception:
                pass
                
        if extracted_start_chapter is not None:
            repair_start_candidates.append(extracted_start_chapter)
        else:
            # 預設回退至當前大綱最新一個生成批次 (5章大綱) 的起點
            if existing_chapters:
                repair_start_candidates.append(max(1, last_chapter_index - 4))
            else:
                repair_start_candidates.append(1)

    if repair_start_candidates:
        start_chapter = max(1, min(repair_start_candidates))
        existing_chapters = [
            ch for ch in existing_chapters
            if existing_chapter_index(ch) < start_chapter
        ]
        last_chapter_index = start_chapter - 1
    else:
        start_chapter = last_chapter_index + 1
    # 【Step 1 修復】將單次生成章節數從 5 減少為 4，降低 Token 長度避免小模型上下文超載或超時而無法正確輸出完整的 JSON 結束標籤
    end_chapter = start_chapter + 3 # 每次生成剛好 4 章
    
    yield "data: " + json.dumps({"type": "content", "delta": f"=== [滾動式大綱生成] ===\n目前已規劃 {last_chapter_index} 章。正在規劃接下來的第 {start_chapter} 章至第 {end_chapter} 章大綱...\n\n"}, ensure_ascii=False) + "\n\n"

    # 2. 構建前文銜接上下文 (最後 3 章)
    prev_chapters_context = ""
    if existing_chapters:
        last_few = existing_chapters[-3:]
        prev_chapters_context = "【前文已生成的章節大綱銜接參考】:\n"
        for ch in last_few:
            prev_chapters_context += f"- 第 {ch.get('chapter_index')} 章《{ch.get('title')}》: {ch.get('summary')} (懸念: {ch.get('cliffhanger')})\n"

    # 2.5 構建精簡且滾動聚焦的世界觀設定 (Sliding-window Worldview Context)，避免資訊過載與幻覺
    worldview_json = db.parse_worldview_to_json(context.get("worldbuilding", ""))
    
    # 💡 比例映射演算法 (Proportional Mapping Algorithm) -> 適用於 1000 - 2000 章大長篇
    volumes = db.get_volumes(novel_id)
    total_chapters = db.get_total_chapter_count(volumes)
    progress_percentage = min(max((start_chapter - 1) / total_chapters, 0.0), 1.0)
    
    # 精簡並滾動展示多幕式結構
    ta_list = worldview_json.get("multi_act_structure", [])
    active_act_index = min(int(progress_percentage * len(ta_list)), len(ta_list) - 1) if ta_list else 0
    ta_text = ""
    for idx, act in enumerate(ta_list):
        title = act.get("title", f"項目 #{idx + 1}")
        content = act.get("content", "").strip()
        if idx < active_act_index:
            ta_text += f"- [已完成前文結構] 第 {idx + 1} 幕: {title}\n"
        elif idx == active_act_index:
            ta_text += f"- [🌟 當前主攻幕] 第 {idx + 1} 幕: {title}\n  【核心劇情與情節任務】：{content}\n"
        else:
            ta_text += f"- [未來預告結構] 第 {idx + 1} 幕: {title} (後續大綱的鋪墊方向，當前僅供伏線參考，暫勿在此展開)\n"

    # 精簡並滾動展示角色漸進策略
    cp_list = worldview_json.get("progressive_character_plan", [])
    active_stage_index = min(int(progress_percentage * len(cp_list)), len(cp_list) - 1) if cp_list else 0
    cp_text = ""
    for idx, stage in enumerate(cp_list):
        title = stage.get("title", f"階段 #{idx + 1}")
        content = stage.get("content", "").strip()
        if idx < active_stage_index:
            cp_text += f"- [已歷經成長階段] 階段 {idx + 1}: {title}\n"
        elif idx == active_stage_index:
            cp_text += f"- [🌟 當前主要成長重點] 階段 {idx + 1}: {title}\n  【心境成長與核心轉變】：{content}\n"
        else:
            cp_text += f"- [未來成長預告] 階段 {idx + 1}: {title} (後續轉變方向，當前僅作細微暗示，暫勿完全爆發)\n"

    seeds_list = worldview_json.get("foreshadowing_seeds", [])
    turning_points = worldview_json.get("key_turning_points", [])

    # 💡 增強：動態比例滑動視窗池調度機制 (Sliding-window Proportional Pool Mechanism)
    # 根據當前故事在全書的進度百分比，精確篩選出位於進度 +/- 25% 區間內的伏筆種子與轉折點，並保底輸出至少 4 個最接近的項目
    focused_seeds = []
    if isinstance(seeds_list, list) and seeds_list:
        S = len(seeds_list)
        for idx, seed in enumerate(seeds_list):
            seed_pos = idx / S if S > 1 else 0.0
            if abs(seed_pos - progress_percentage) <= 0.25:
                focused_seeds.append(f"[Seed-{idx + 1}] {seed}")
        # 保底機制：若篩選為空，選取最接近當前進度比例的 4 個種子
        if not focused_seeds:
            sorted_seeds = sorted(enumerate(seeds_list), key=lambda x: abs((x[0] / S if S > 1 else 0.0) - progress_percentage))
            focused_seeds = [f"[Seed-{x[0] + 1}] {x[1]}" for x in sorted_seeds[:4]]
    else:
        focused_seeds = seeds_list

    focused_turning_points = []
    if isinstance(turning_points, list) and turning_points:
        T = len(turning_points)
        for idx, tp in enumerate(turning_points):
            tp_pos = idx / T if T > 1 else 0.0
            if abs(tp_pos - progress_percentage) <= 0.25:
                focused_turning_points.append(f"[TurningPoint-{idx + 1}] {tp}")
        # 保底機制：若篩選為空，選取最接近當前進度比例的 4 個轉折點
        if not focused_turning_points:
            sorted_tps = sorted(enumerate(turning_points), key=lambda x: abs((x[0] / T if T > 1 else 0.0) - progress_percentage))
            focused_turning_points = [f"[TurningPoint-{x[0] + 1}] {x[1]}" for x in sorted_tps[:4]]
    else:
        focused_turning_points = turning_points

    seeds_text = "\n".join(focused_seeds) if isinstance(focused_seeds, list) else str(focused_seeds)
    turning_points_text = "\n".join(focused_turning_points) if isinstance(focused_turning_points, list) else str(focused_turning_points)

    focused_worldview_context = f"""主題：{worldview_json.get("theme", "未設定")}
核心衝突：{worldview_json.get("main_conflict", "未設定")}
世界觀設定：{worldview_json.get("worldview", "未設定")}
宏觀大綱：{worldview_json.get("macro_outline", "未設定")}

【多幕式結構 (當前滾動聚焦於第 {active_act_index + 1} 幕，全書進度約 {int(progress_percentage * 100)}%)】：
{ta_text or "（無結構設定）"}

【角色成長漸進策略 (當前滾動聚焦於階段 {active_stage_index + 1})】：
{cp_text or "（無成長策略）"}

【當前故事階段可調度之伏筆故事線池 (已篩選最相關種子，供選擇性使用)】：
{seeds_text or "（無相關伏筆故事線）"}

【當前故事階段可調度之關鍵轉折點池】：
{turning_points_text or "（無相關關鍵轉折點）"}"""

    # 3. 呼叫大綱設計大師
    # 💡 Token 管控：只傳角色的精簡摘要（name/role/want/fatal_flaw），避免完整 Character Bible 撐爆 plot LLM 的 context
    _chars_parsed = parse_json_safely(context.get('characters', '{}'), default={})
    _chars_list = _chars_parsed.get('characters', []) if isinstance(_chars_parsed, dict) else []
    _chars_brief = [
        {"name": c.get("name", "?"), "role": c.get("role", "?"),
         "want": c.get("want", ""), "fatal_flaw": c.get("fatal_flaw", "")}
        for c in _chars_list if isinstance(c, dict)
    ]
    _chars_brief_str = json.dumps(_chars_brief, ensure_ascii=False)

    planner_prompt = f"""⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

以下是已確立的世界觀與角色聖經：
【世界觀設定 (已進行滾動聚焦優化，避免無關章節干擾)】
{focused_worldview_context}

【角色聖經（精簡版：name/role/want/fatal_flaw）】
{_chars_brief_str}

{prev_chapters_context or "這是整部小說的前 5 章，為開篇大綱。"}

現在，請繼續為這部小說精細規劃**接下來的 4 個章節大綱**（項目數量必須精確為 4 個，章節序號必須是第 {start_chapter} 章至第 {end_chapter} 章）：

## ⚠️ 核心生成權限與動態分配規則（極重要）
1. **【絕對禁止模板化】**：絕對禁止在不同章節中重複使用相同的標題、事件描述或籠統語句（如「命運波折之章 (保底)」、「推進核心衝突」）。每一章必須是獨立、具體、且不可替代的情節。
2. **【伏筆線動態調度】**：提供的「伏筆故事線池」是有限的。這是一部高達 1500 章左右的大小說，伏筆應該在不同卷、章之間進行慢速的、合理的跨卷鋪陳與跨卷回收。你【不需要】也不應該在每一章都塞入伏筆，更【絕對禁止】在同一個 5 章大綱中急著把所有伏筆全部鋪設並立刻回收！請依據劇情節奏隨機且合理地決定是否在本章：
   - 鋪設（Planting）：從池中挑選種子，並在 `foreshadowing_plant` 中寫入具體如何鋪設（例：`"鋪設 [Seed-1]：主角無意中在廢墟發現刻有古神電路紋路的晶片"`）。
   - 回收（Payoff）：從池中挑選已有的舊伏筆，並在 `foreshadowing_payoff` 中寫入具體如何回收。
   - 若本章不適合處理伏筆，這兩欄必須回傳空陣列 `[]`。專注於編織具體的日常生活、調查、戰鬥或台詞對話。
3. **【事件具體落地】**：每一個章節大綱必須是可被執行的寫作藍圖。`events` 陣列中的每一個場景都必須具體描述「誰、在哪裡、做了什麼、面臨什麼新考驗（至少包含一個具體的對話或衝突動作點）」。
4. **【自主配角生成】**：允許並鼓勵你在具體場景中自由創造符合霓虹城世界觀的工具人/路人（如：特定情報販子、路邊小販、打手），並在首次出現時用括號標註：(姓名-身份簡述)。

請裝飾在 ```json ... ``` 區塊中輸出，格式如下：
```json
{{
  "chapters": [
    {{
      "chapter_index": {start_chapter},
      "title": "具體且富有文采的章節標題（拒絕模板化）",
      "time_setting": "故事內時間座標",
      "time_span": "距前章時間跨度",
      "events": [
        {{"scene": "具體發生的地點與場景", "action": "核心動作/衝突 (新登場的次要角色請括號簡述，例如：(老張-客棧老闆，貪財但心軟) 做某事)", "consequence": "帶來的後果或轉變"}}
      ],
      "purpose": "本章敘事目的",
      "foreshadowing_plant": ["具體埋設的伏筆內容，如使用池中種子請註明 Seed ID"],
      "foreshadowing_payoff": ["具體回收的舊伏筆內容，如使用池中種子請註明 Seed ID"],
      "characters_active": ["活躍主要或次要角色"],
      "characters_introduced": ["本章新登場的主要或次要角色 (若有，如 老張)"],
      "scene": "主要場景名稱",
      "emotional_tone": "情緒基調",
      "cliffhanger": "強烈懸念鉤子"
    }}
  ]
}}
```
"""
    messages_expander = [
        {"role": "system", "content": "你是一位頂尖的微觀劇情規劃大師。你只輸出嚴格、合法、無多餘寒暄的標準 JSON 數據。"},
        {"role": "user", "content": planner_prompt}
    ]

    expanded_output = ""
    for sse_line in call_llm_stream("plot", messages_expander):
        yield sse_line
        if sse_line.startswith("data:"):
            try:
                data_str = sse_line[5:].strip()
                if data_str == "[DONE]":
                    continue
                data = json.loads(data_str)
                if data.get("type") == "content":
                    expanded_output += data.get("delta", "")
            except:
                pass

    # 4. 解析生成的微觀章節
    parsed_node = parse_json_safely(expanded_output)
    if isinstance(parsed_node, dict) and "error" in parsed_node:
        parsed_node = parse_json_safely(clean_json_text(expanded_output))

    node_chapters = _normalize_chapter_outlines(parsed_node, start_chapter)

    if not node_chapters:
        yield "data: " + json.dumps({"type": "content", "delta": f"\n  ⚠️ 檢測到章節素材耗盡或大綱解析失敗！正在啟動「創意膨脹與自我修復循環 (Creative Swelling Loop)」...\n"}, ensure_ascii=False) + "\n\n"
        
        # 1. 取得現有資料
        from db import get_volumes, save_volumes
        volumes = get_volumes(novel_id)
        worldview_json = db.parse_worldview_to_json(context.get("worldbuilding", ""))
        char_bible = db.get_latest_characters(novel_id)
        char_list = char_bible["parsed_data"].get("characters", []) if char_bible else []
        
        volume_index = (start_chapter - 1) // 50 + 1
        need_expand_volume = volume_index > len(volumes)
        
        if need_expand_volume:
            yield "data: " + json.dumps({"type": "content", "delta": f"  📚 當前章節大綱已超出原有篇卷規劃（共 {len(volumes)} 卷），即將自動增量擴增新一卷大綱...\n"}, ensure_ascii=False) + "\n\n"
        else:
            yield "data: " + json.dumps({"type": "content", "delta": f"  📚 當前篇卷規劃充足，將專注於世界觀底層擴張...\n"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "content", "delta": f"  🌍 正在為您擴充世界觀：催生新的地下勢力、神秘法則、以及對立衝突線...\n"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "content", "delta": f"  👥 正在增量人物卡：為新勢力注入全新的主要人物與配角設定...\n"}, ensure_ascii=False) + "\n\n"
        
        # 2. 建構創意膨脹 LLM Prompt
        volume_instruction = ""
        volume_json_fragment = ""
        if need_expand_volume:
            volume_instruction = f"4. 規劃第 {volume_index} 卷的卷設定 (標題、核心概要、登場陣營)，因為目前的章節已超出原有篇卷。"
            volume_json_fragment = f''',
  "new_volume": {{
    "title": "第 {volume_index} 卷標題",
    "summary": "第 {volume_index} 卷概要",
    "factions": ["陣營名稱1", "陣營名稱2"]
  }}'''
        swell_prompt = f"""你是一位小說「設定膨脹與自我對齊大師」。
目前我們正在規劃第 {start_chapter} 章之後的大綱，但發現素材（組織、角色、卷規劃）已經耗盡，大綱規劃師出現幻覺。
你需要為這部小說進行【增量創意膨脹】，主動產生新的勢力組織、新角色、新伏筆，以及必要的篇卷大綱。

【現有世界觀設定】
主題：{worldview_json.get("theme", "")}
核心衝突：{worldview_json.get("main_conflict", "")}
世界觀背景：{worldview_json.get("worldview", "")}

【現有組織/勢力與伏筆】
伏筆種子：{json.dumps(worldview_json.get("foreshadowing_seeds", []), ensure_ascii=False)}
關鍵轉折：{json.dumps(worldview_json.get("key_turning_points", []), ensure_ascii=False)}

【現有角色】
{json.dumps([c.get("name") for c in char_list], ensure_ascii=False)}

【當前篇卷】
{json.dumps([v.get("title") for v in volumes], ensure_ascii=False)}

請嚴格以 JSON 格式進行以下增量膨脹：
1. 設計 1 個全新的勢力/組織 (Faction) 及其核心陰謀/動機。
2. 設計 1-2 個全新的角色 (與新勢力相關，包含姓名、身份、動機、性格特質)。
3. 設計 2-3 個全新的伏筆種子與關鍵轉折點。
{volume_instruction}

嚴格輸出 ```json ... ``` 包裹的合法 JSON 物件，格式如下：
{{
  "new_faction": {{
    "name": "新勢力名稱",
    "description": "勢力描述與核心動機"
  }},
  "new_characters": [
    {{
      "name": "姓名 (中文/英文)",
      "role": "身份",
      "personality": ["性格1", "性格2"],
      "speech_style": "說話風格",
      "want": "欲求",
      "need": "內在需求",
      "fatal_flaw": "致命缺陷",
      "motivation": "動機",
      "arc": "人物成長軌跡"
    }}
  ],
  "new_seeds": [
    "伏筆種子1",
    "伏筆種子2"
  ],
  "new_turning_points": [
    "轉折點1"
  ]{volume_json_fragment}
}}
"""
        swell_messages = [
            {"role": "system", "content": "你是一位專精於小說背景世界觀與人物設計的膨脹大師。你只輸出無廢話的標準 JSON 數據。"},
            {"role": "user", "content": swell_prompt}
        ]
        
        # 3. 呼叫 LLM 獲取膨脹數據
        swell_text = ""
        for sse_line in call_llm_stream("copilot", swell_messages):
            if sse_line.startswith("data:"):
                try:
                    data_str = sse_line[5:].strip()
                    if data_str != "[DONE]":
                        data = json.loads(data_str)
                        if data.get("type") == "content":
                            swell_text += data.get("delta", "")
                except:
                    pass
                    
        # 4. 解析與縫合新設定
        parsed_swell = parse_json_safely(swell_text)
        if isinstance(parsed_swell, dict) and "error" in parsed_swell:
            parsed_swell = parse_json_safely(clean_json_text(swell_text))
            
        if isinstance(parsed_swell, dict) and "error" not in parsed_swell:
            new_faction = parsed_swell.get("new_faction")
            new_seeds = parsed_swell.get("new_seeds", [])
            new_tps = parsed_swell.get("new_turning_points", [])
            
            # 縫合勢力與伏筆到世界觀
            if new_faction:
                worldview_json["worldview"] += f"\n\n[增量擴展勢力] {new_faction.get('name')}：{new_faction.get('description')}"
                yield "data: " + json.dumps({"type": "content", "delta": f"  ✅ 成功孵化新勢力：【{new_faction.get('name')}】\n"}, ensure_ascii=False) + "\n\n"
            if isinstance(new_seeds, list) and new_seeds:
                worldview_json["foreshadowing_seeds"].extend(new_seeds)
                yield "data: " + json.dumps({"type": "content", "delta": f"  🌱 新埋設 {len(new_seeds)} 個伏筆種子到故事線中。\n"}, ensure_ascii=False) + "\n\n"
            if isinstance(new_tps, list) and new_tps:
                worldview_json["key_turning_points"].extend(new_tps)
                
            from incremental_patch_engine import safe_worldbuilding_save
            success, version, error_msg = safe_worldbuilding_save(novel_id, worldview_json, source="creative_swelling")
            if not success:
                yield "data: " + json.dumps({"type": "content", "delta": f"  ⚠️ 世界觀合併安全防護已攔截寫入：{error_msg}\n"}, ensure_ascii=False) + "\n\n"
            
            # 縫合新角色到角色 Bible
            new_chars = parsed_swell.get("new_characters", [])
            if isinstance(new_chars, list) and new_chars:
                for c in new_chars:
                    char_list.append({
                        "name": c.get("name", "未命名角色"),
                        "role": c.get("role", "配角"),
                        "entry_phase": f"第 {start_chapter} 章登場",
                        "personality": c.get("personality", ["普通"]),
                        "speech_style": c.get("speech_style", "符合人設"),
                        "want": c.get("want", ""),
                        "need": c.get("need", ""),
                        "fatal_flaw": c.get("fatal_flaw", ""),
                        "motivation": c.get("motivation", ""),
                        "arc": c.get("arc", ""),
                        "relationships": []
                    })
                    yield "data: " + json.dumps({"type": "content", "delta": f"  👤 成功塑造全新角色：【{c.get('name')}】({c.get('role')})\n"}, ensure_ascii=False) + "\n\n"
                
                # 角色聖經保護：防縮短，防寫入損壞
                orig_char_data = get_latest_characters(novel_id)
                orig_chars = orig_char_data["parsed_data"].get("characters", []) if (orig_char_data and "parsed_data" in orig_char_data) else []
                if len(char_list) >= len(orig_chars):
                    from incremental_patch_engine import post_merge_validation
                    is_valid, errors = post_merge_validation({"characters": char_list}, "characters", orig_char_data["parsed_data"] if orig_char_data else None)
                    if is_valid:
                        db.save_characters(novel_id, {"characters": char_list})
                    else:
                        yield "data: " + json.dumps({"type": "content", "delta": f"  ⚠️ 角色設定安全校驗攔截寫入：{', '.join(errors)}\n"}, ensure_ascii=False) + "\n\n"
                else:
                    yield "data: " + json.dumps({"type": "content", "delta": f"  ⚠️ 角色列表長度安全檢測未通過，已攔截覆蓋！\n"}, ensure_ascii=False) + "\n\n"

                
            # 縫合新卷
            new_vol = parsed_swell.get("new_volume")
            if need_expand_volume and new_vol:
                v_list = list(volumes)
                v_list.append({
                    "novel_id": novel_id,
                    "volume_index": volume_index,
                    "title": new_vol.get("title", f"第 {volume_index} 卷"),
                    "summary": new_vol.get("summary", ""),
                    "factions": json.dumps(new_vol.get("factions", []), ensure_ascii=False),
                    "is_dirty": 0
                })
                db.save_volumes(novel_id, v_list)
                yield "data: " + json.dumps({"type": "content", "delta": f"  📘 成功規劃並增設卷級新篇章：【{new_vol.get('title')}】\n"}, ensure_ascii=False) + "\n\n"
                
            yield "data: " + json.dumps({"type": "content", "delta": f"  ⚡ 創意素材增強完畢。正在利用全新資料庫上下文重新生成大綱...\n\n"}, ensure_ascii=False) + "\n\n"
            
            # 重新加載 compile_context
            context = compile_context(novel_id)
            worldview_json = db.parse_worldview_to_json(context.get("worldbuilding", ""))
            
            # 重新計算比例滑動視窗
            volumes = db.get_volumes(novel_id)
            total_chapters = db.get_total_chapter_count(volumes)
            progress_percentage = min(max((start_chapter - 1) / total_chapters, 0.0), 1.0)
            
            # 精簡並滾動展示多幕式結構
            ta_list = worldview_json.get("multi_act_structure", [])
            active_act_index = min(int(progress_percentage * len(ta_list)), len(ta_list) - 1) if ta_list else 0
            ta_text = ""
            for idx, act in enumerate(ta_list):
                title = act.get("title", f"項目 #{idx + 1}")
                content = act.get("content", "").strip()
                if idx < active_act_index:
                    ta_text += f"- [已完成前文結構] 第 {idx + 1} 幕: {title}\n"
                elif idx == active_act_index:
                    ta_text += f"- [🌟 當前主攻幕] 第 {idx + 1} 幕: {title}\n  【核心劇情與情節任務】：{content}\n"
                else:
                    ta_text += f"- [未來預告結構] 第 {idx + 1} 幕: {title} (後續大綱的鋪墊方向，當前僅供伏線參考，暫勿在此展開)\n"

            # 精簡並滾動展示角色漸進策略
            cp_list = worldview_json.get("progressive_character_plan", [])
            active_stage_index = min(int(progress_percentage * len(cp_list)), len(cp_list) - 1) if cp_list else 0
            cp_text = ""
            for idx, stage in enumerate(cp_list):
                title = stage.get("title", f"階段 #{idx + 1}")
                content = stage.get("content", "").strip()
                if idx < active_stage_index:
                    cp_text += f"- [已歷經成長階段] 階段 {idx + 1}: {title}\n"
                elif idx == active_stage_index:
                    cp_text += f"- [🌟 當前主要成長重點] 階段 {idx + 1}: {title}\n  【心境成長與核心轉變】：{content}\n"
                else:
                    cp_text += f"- [未來成長預告] 階段 {idx + 1}: {title} (後續轉變方向，當前僅作細微暗示，暫勿完全爆發)\n"

            seeds_list = worldview_json.get("foreshadowing_seeds", [])
            turning_points = worldview_json.get("key_turning_points", [])

            focused_seeds = []
            if isinstance(seeds_list, list) and seeds_list:
                S = len(seeds_list)
                for idx, seed in enumerate(seeds_list):
                    seed_pos = idx / S if S > 1 else 0.0
                    if abs(seed_pos - progress_percentage) <= 0.25:
                        focused_seeds.append(f"[Seed-{idx + 1}] {seed}")
                if not focused_seeds:
                    sorted_seeds = sorted(enumerate(seeds_list), key=lambda x: abs((x[0] / S if S > 1 else 0.0) - progress_percentage))
                    focused_seeds = [f"[Seed-{x[0] + 1}] {x[1]}" for x in sorted_seeds[:4]]
            else:
                focused_seeds = seeds_list

            focused_turning_points = []
            if isinstance(turning_points, list) and turning_points:
                T = len(turning_points)
                for idx, tp in enumerate(turning_points):
                    tp_pos = idx / T if T > 1 else 0.0
                    if abs(tp_pos - progress_percentage) <= 0.25:
                        focused_turning_points.append(f"[TurningPoint-{idx + 1}] {tp}")
                if not focused_turning_points:
                    sorted_tps = sorted(enumerate(turning_points), key=lambda x: abs((x[0] / T if T > 1 else 0.0) - progress_percentage))
                    focused_turning_points = [f"[TurningPoint-{x[0] + 1}] {x[1]}" for x in sorted_tps[:4]]
            else:
                focused_turning_points = turning_points

            seeds_text = "\n".join(focused_seeds) if isinstance(focused_seeds, list) else str(focused_seeds)
            turning_points_text = "\n".join(focused_turning_points) if isinstance(focused_turning_points, list) else str(focused_turning_points)

            focused_worldview_context = f"""主題：{worldview_json.get("theme", "未設定")}
核心衝突：{worldview_json.get("main_conflict", "未設定")}
世界觀設定：{worldview_json.get("worldview", "未設定")}
宏觀大綱：{worldview_json.get("macro_outline", "未設定")}

【多幕式結構 (當前滾動聚焦於第 {active_act_index + 1} 幕，全書進度約 {int(progress_percentage * 100)}%)】：
{ta_text or "（無結構設定）"}

【角色成長漸進策略 (當前滾動聚焦於階段 {active_stage_index + 1})】：
{cp_text or "（無成長策略）"}

【當前故事階段可調度之伏筆故事線池 (已篩選最相關種子，供選擇性使用)】：
{seeds_text or "（無相關伏筆故事線）"}

【當前故事階段可調度之關鍵轉折點池】：
{turning_points_text or "（無相關關鍵轉折點）"}"""

            planner_prompt = f"""⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

以下是已確立的世界觀與角色聖經：
【世界觀設定 (已進行滾動聚焦優化，避免無關章節干擾)】
{focused_worldview_context}

【角色聖經】
{context['characters']}

{prev_chapters_context or "這是整部小說的前 5 章，為開篇大綱。"}

現在，請繼續為這部小說精細規劃**接下來的 4 個章節大綱**（項目數量必須精確為 4 個，章節序號必須是第 {start_chapter} 章至第 {end_chapter} 章）：

## ⚠️ 核心生成權限與動態分配規則（極重要）
1. **【絕對禁止模板化】**：絕對禁止在不同章節中重複使用相同的標題、事件描述或籠統語句（如「命運波折之章 (保底)」、「推進核心衝突」）。每一章必須是獨立、具體、且不可替代的情節。
2. **【伏筆線動態調度】**：提供的「伏筆故事線池」是有限的。你【不需要】也不應該在每一章都塞入伏筆。請依據劇情節奏隨機且合理地決定是否在本章：
   - 鋪設（Planting）：從池中挑選種子，並在 `foreshadowing_plant` 中寫入具體如何鋪設。
   - 回收（Payoff）：從池中挑選已有的舊伏筆，並在 `foreshadowing_payoff` 中寫入具體如何回收。
   - 若本章不適合處理伏筆，這兩欄必須回傳空陣列 `[]`。專注於編織具體的日常生活、調查、戰鬥或台詞對話。
3. **【事件具體落地】**：每一個章節大綱必須是可被執行的寫作藍圖。`events` 陣列中的每一個場景都必須具體描述「誰、在哪裡、做了什麼、面臨什麼新考驗（至少包含一個具體的對話或衝突動作點）」。
4. **【自主配角生成】**：允許並鼓勵你在具體場景中自由創造符合霓虹城世界觀的工具人/路人，並在首次出現時用括號標註：(姓名-身份簡述)。

請裝飾在 ```json ... ``` 區塊中輸出，格式如下：
```json
{{
  "chapters": [
    {{
      "chapter_index": {start_chapter},
      "title": "具體且富有文采的章節標題",
      "time_setting": "故事內時間座標",
      "time_span": "距前章時間跨度",
      "events": [
        {{"scene": "具體發生的地點與場景", "action": "核心動作/衝突 (新登場的次要角色請括號簡述，例如：(老張-客棧老闆，貪財但心軟) 做某事)", "consequence": "帶來的後果或轉變"}}
      ],
      "purpose": "本章敘事目的",
      "foreshadowing_plant": ["具體埋設的伏筆內容，如使用池中種子請註明 Seed ID"],
      "foreshadowing_payoff": ["具體回收 of 舊伏筆內容，如使用池中種子請註明 Seed ID"],
      "characters_active": ["活躍主要或次要角色"],
      "characters_introduced": ["本章新登場的主要或次要角色"],
      "scene": "主要場景名稱",
      "emotional_tone": "情緒基調",
      "cliffhanger": "強烈懸念鉤子"
    }}
  ]
}}
```
"""
            messages_expander = [
                {"role": "system", "content": "你是一位頂尖的微觀劇情規劃大師。你只輸出嚴格、合法、無多餘寒暄的標準 JSON 數據。"},
                {"role": "user", "content": planner_prompt}
            ]
            
            expanded_output = ""
            for sse_line in call_llm_stream("plot", messages_expander):
                yield sse_line
                if sse_line.startswith("data:"):
                    try:
                        data_str = sse_line[5:].strip()
                        if data_str != "[DONE]":
                            data = json.loads(data_str)
                            if data.get("type") == "content":
                                expanded_output += data.get("delta", "")
                    except:
                        pass
                        
            parsed_node = parse_json_safely(expanded_output)
            if isinstance(parsed_node, dict) and "error" in parsed_node:
                parsed_node = parse_json_safely(clean_json_text(expanded_output))
                
            node_chapters = _normalize_chapter_outlines(parsed_node, start_chapter)
                
        # Director rescue loop: the last line of defense must not save placeholder outlines.
        if not node_chapters:
            yield _sse_content("  ⚠️ 膨脹後重試仍未取得合法大綱。停止保底佔位，改向 AI 總監請求救援診斷與再操作方案...\n")

            rescue_failure_report = (
                "Plot Planner 初次輸出無法解析或章節不足；Creative Swelling 已嘗試補充勢力、角色、伏筆與篇卷後再次重試，"
                "但仍未產出 5 個合法、具體、非模板化章節大綱。"
            )

            for rescue_attempt in range(1, 3):
                rescue_context = compile_context(novel_id)
                rescue_prompt = f"""你是 AI Novel Factory 的首席創意總監與流程救援官。

目前一鍵創作流程在第 {start_chapter} 章至第 {end_chapter} 章的大綱生成處連續失敗。
你不能放棄，也不能生成「保底」「占位」「推進核心衝突」這類模板章。

【失敗報告】
{rescue_failure_report}

【目前世界觀】
{rescue_context['worldbuilding']}

【目前角色 Bible】
{rescue_context['characters']}

【前文大綱銜接】
{prev_chapters_context or "這是本段故事的開端，沒有可用前文。"}

請先診斷失敗原因，再選擇一個救援動作：
1. `PATCH_AND_RETRY`：補充世界觀/角色/伏筆/篇卷，並給 Plot Planner 一段精準 retry 指令。
2. `DIRECT_OUTLINE`：你親自產出第 {start_chapter} 章至第 {end_chapter} 章的 5 個具體章節大綱。

嚴格輸出 ```json ... ``` 包裹的合法 JSON。格式如下：
{{
  "action": "PATCH_AND_RETRY",
  "diagnosis": "失敗原因與下一步策略",
  "planner_directive": "給 Plot Planner 的具體再操作指令，必須包含本段核心衝突、場景方向、角色調度與禁用模板提醒",
  "worldbuilding_patches": [
    {{"title": "新設定標題", "details": "可直接追加到世界觀的具體設定"}}
  ],
  "new_characters": [
    {{
      "name": "具體姓名",
      "role": "身份",
      "personality": ["性格1", "性格2"],
      "speech_style": "說話風格",
      "want": "外在目標",
      "need": "內在需求",
      "fatal_flaw": "致命缺陷",
      "motivation": "動機",
      "arc": "弧線"
    }}
  ],
  "foreshadowing_seeds": ["新增伏筆種子"],
  "key_turning_points": ["新增關鍵轉折"],
  "new_volume": {{
    "title": "需要新增篇卷時才填",
    "summary": "篇卷概要",
    "factions": ["活躍陣營"]
  }},
  "chapters": [
    {{
      "chapter_index": {start_chapter},
      "title": "具體且不可替代的章節標題",
      "time_setting": "故事內時間座標",
      "time_span": "距前章時間跨度",
      "events": [
        {{"scene": "具體地點", "action": "誰做了什麼、遇到什麼衝突", "consequence": "造成的後果"}}
      ],
      "purpose": "本章敘事目的",
      "foreshadowing_plant": [],
      "foreshadowing_payoff": [],
      "characters_active": [],
      "characters_introduced": [],
      "scene": "主要場景",
      "emotional_tone": "情緒基調",
      "cliffhanger": "章末具體鉤子"
    }}
  ]
}}

注意：
- 若 action 是 `DIRECT_OUTLINE`，`chapters` 必須精確給出 5 章。
- 若 action 是 `PATCH_AND_RETRY`，也可以在 `chapters` 先給空陣列，系統會根據你的補丁與 planner_directive 再請 Plot Planner 重試。
- 任何章節都必須有具體地點、人物、動作、後果與鉤子。
"""
                rescue_messages = [
                    {"role": "system", "content": "你是嚴格的創意總監與流程救援官。你只輸出可解析 JSON，不輸出寒暄。"},
                    {"role": "user", "content": rescue_prompt}
                ]

                yield _sse_content(f"  🎬 總監救援第 {rescue_attempt} 輪：正在診斷大綱失敗原因並制定再操作方案...\n")
                rescue_text = ""
                for sse_line in call_llm_stream("copilot", rescue_messages):
                    yield sse_line
                    if sse_line.startswith("data:"):
                        try:
                            data_str = sse_line[5:].strip()
                            if data_str != "[DONE]":
                                data = json.loads(data_str)
                                if data.get("type") == "content":
                                    rescue_text += data.get("delta", "")
                        except:
                            pass

                save_chat_message(novel_id, "assistant", f"[Plot Planner Rescue Attempt {rescue_attempt}]\n{rescue_text}", message_type="director")
                parsed_rescue = parse_json_safely(rescue_text)
                if isinstance(parsed_rescue, dict) and "error" in parsed_rescue:
                    parsed_rescue = parse_json_safely(clean_json_text(rescue_text))
                if not isinstance(parsed_rescue, dict) or "error" in parsed_rescue:
                    rescue_failure_report = "總監救援輸出未能解析為合法 JSON，需再次要求總監直接產出合法章節。"
                    continue

                # Apply director patches before retrying.
                wb_latest = get_latest_worldbuilding(novel_id)
                worldview_json = db.parse_worldview_to_json(wb_latest["content"] if wb_latest else "")
                world_patches = parsed_rescue.get("worldbuilding_patches", [])
                if isinstance(world_patches, list) and world_patches:
                    for patch in world_patches:
                        if isinstance(patch, dict):
                            title = patch.get("title", "總監救援補丁")
                            details = patch.get("details", "")
                            worldview_json["worldview"] += f"\n\n[總監救援補丁] {title}：{details}"
                    yield _sse_content(f"  🧭 已縫合 {len(world_patches)} 條總監救援世界觀補丁。\n")

                rescue_seeds = parsed_rescue.get("foreshadowing_seeds", [])
                if isinstance(rescue_seeds, list) and rescue_seeds:
                    worldview_json.setdefault("foreshadowing_seeds", []).extend(rescue_seeds)
                    yield _sse_content(f"  🌱 已追加 {len(rescue_seeds)} 條總監救援伏筆種子。\n")

                rescue_tps = parsed_rescue.get("key_turning_points", [])
                if isinstance(rescue_tps, list) and rescue_tps:
                    worldview_json.setdefault("key_turning_points", []).extend(rescue_tps)
                    yield _sse_content(f"  🔀 已追加 {len(rescue_tps)} 條總監救援轉折點。\n")

                if world_patches or rescue_seeds or rescue_tps:
                    from incremental_patch_engine import safe_worldbuilding_save
                    success, version, error_msg = safe_worldbuilding_save(novel_id, worldview_json, source="rescue_PATCH_AND_RETRY")
                    if not success:
                        yield _sse_content(f"  ⚠️ 總監救援世界觀合併安全防護已攔截寫入：{error_msg}\n")

                rescue_chars = parsed_rescue.get("new_characters", [])
                if isinstance(rescue_chars, list) and rescue_chars:
                    char_bible = db.get_latest_characters(novel_id)
                    char_pd = char_bible["parsed_data"] if char_bible else {"characters": []}
                    char_pd.setdefault("characters", [])
                    existing_names = {c.get("name") for c in char_pd["characters"] if isinstance(c, dict)}
                    added_chars = 0
                    for c in rescue_chars:
                        if not isinstance(c, dict):
                            continue
                        name = c.get("name", "未命名角色")
                        if name in existing_names:
                            continue
                        char_pd["characters"].append({
                            "name": name,
                            "role": c.get("role", "配角"),
                            "entry_phase": f"第 {start_chapter} 章救援引入",
                            "personality": c.get("personality", ["複雜"]),
                            "speech_style": c.get("speech_style", "符合人設"),
                            "want": c.get("want", ""),
                            "need": c.get("need", ""),
                            "fatal_flaw": c.get("fatal_flaw", ""),
                            "motivation": c.get("motivation", ""),
                            "arc": c.get("arc", ""),
                            "relationships": c.get("relationships", [])
                        })
                        added_chars += 1
                    if added_chars:
                        orig_char_data = db.get_latest_characters(novel_id)
                        orig_chars = orig_char_data["parsed_data"].get("characters", []) if (orig_char_data and "parsed_data" in orig_char_data) else []
                        if len(char_pd.get("characters", [])) >= len(orig_chars):
                            from incremental_patch_engine import post_merge_validation
                            is_valid, errors = post_merge_validation(char_pd, "characters", orig_char_data["parsed_data"] if orig_char_data else None)
                            if is_valid:
                                db.save_characters(novel_id, char_pd)
                                yield _sse_content(f"  👥 已縫合 {added_chars} 位總監救援角色。\n")
                            else:
                                yield _sse_content(f"  ⚠️ 總監救援角色設定安全校驗攔截寫入：{', '.join(errors)}\n")
                        else:
                            yield _sse_content("  ⚠️ 總監救援角色列表長度安全檢測未通過，已攔截覆蓋！\n")


                rescue_volume = parsed_rescue.get("new_volume")
                if need_expand_volume and isinstance(rescue_volume, dict):
                    volumes_now = get_volumes(novel_id)
                    if not any(int(v.get("volume_index", 0)) == int(volume_index) for v in volumes_now):
                        v_list = list(volumes_now)
                        v_list.append({
                            "volume_index": volume_index,
                            "title": rescue_volume.get("title", f"第 {volume_index} 卷"),
                            "summary": rescue_volume.get("summary", ""),
                            "factions": rescue_volume.get("factions", []),
                            "is_dirty": 0
                        })
                        db.save_volumes(novel_id, v_list)
                        yield _sse_content(f"  📘 已依總監方案新增第 {volume_index} 卷：《{rescue_volume.get('title', f'第 {volume_index} 卷')}》。\n")

                node_chapters = _normalize_chapter_outlines(parsed_rescue, start_chapter)
                if node_chapters:
                    yield _sse_content("  ✅ 總監已直接給出合法救援大綱，將接管保存流程。\n")
                    break

                planner_directive = parsed_rescue.get("planner_directive", "").strip()
                if not planner_directive:
                    planner_directive = parsed_rescue.get("diagnosis", "").strip()

                yield _sse_content("  🔁 總監已給出補救策略，正在以最新上下文再次請 Plot Planner 生成真實大綱...\n")
                rescue_context = compile_context(novel_id)
                rescue_retry_prompt = f"""⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你正在執行總監救援指令。前兩次大綱生成已失敗，這次必須根據總監診斷產出精確 5 章合法 JSON 大綱。

【總監診斷與再操作指令】
{planner_directive}

【世界觀設定】
{rescue_context['worldbuilding']}

【角色聖經】
{rescue_context['characters']}

{prev_chapters_context or "這是本段故事的開端，沒有可用前文。"}

請規劃第 {start_chapter} 章至第 {end_chapter} 章。嚴禁模板化、保底、占位、泛稱「推進核心衝突」。
每章都必須包含具體場景、人物、動作、後果、敘事目的、伏筆欄位、活躍角色、情緒基調與章末鉤子。

嚴格輸出 ```json ... ``` 包裹的合法 JSON：
{{
  "chapters": [
    {{
      "chapter_index": {start_chapter},
      "title": "具體章節標題",
      "time_setting": "故事內時間座標",
      "time_span": "距前章時間跨度",
      "events": [
        {{"scene": "具體地點", "action": "誰做了什麼與衝突", "consequence": "後果"}}
      ],
      "purpose": "敘事目的",
      "foreshadowing_plant": [],
      "foreshadowing_payoff": [],
      "characters_active": [],
      "characters_introduced": [],
      "scene": "主要場景",
      "emotional_tone": "情緒基調",
      "cliffhanger": "具體鉤子"
    }}
  ]
}}
"""
                retry_messages = [
                    {"role": "system", "content": "你是一位被總監接管指令的微觀劇情規劃師。你只輸出嚴格合法 JSON。"},
                    {"role": "user", "content": rescue_retry_prompt}
                ]
                retry_output = ""
                for sse_line in call_llm_stream("plot", retry_messages):
                    yield sse_line
                    if sse_line.startswith("data:"):
                        try:
                            data_str = sse_line[5:].strip()
                            if data_str != "[DONE]":
                                data = json.loads(data_str)
                                if data.get("type") == "content":
                                    retry_output += data.get("delta", "")
                        except:
                            pass

                parsed_retry = parse_json_safely(retry_output)
                if isinstance(parsed_retry, dict) and "error" in parsed_retry:
                    parsed_retry = parse_json_safely(clean_json_text(retry_output))
                node_chapters = _normalize_chapter_outlines(parsed_retry, start_chapter)
                if node_chapters:
                    yield _sse_content("  ✅ 總監救援後 Plot Planner 已恢復，成功生成合法大綱。\n")
                    break

                rescue_failure_report = "總監補丁與 retry 指令已執行，但 Plot Planner 仍未輸出精確 5 個合法章節。下一輪請總監改用 DIRECT_OUTLINE 親自產出。"

        if not node_chapters:
            yield _sse_error("總監救援仍未產出合法大綱；已停止保存，避免寫入保底佔位章。請檢查總監輸出或稍後重跑一鍵流程。")
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return

    # 5. 確保 chapter_index 的連續性與正確性
    for idx, ch in enumerate(node_chapters):
        ch["chapter_index"] = start_chapter + idx

    # 6. 👥 反向增量動態縫合 (Lore Unbounded) - 檢查新角色並縫合回資料庫
    newly_emerged_characters = []
    worldview_content = context["worldbuilding"]
    worldview_json = db.parse_worldview_to_json(worldview_content)
    
    for ch in node_chapters:
        introduced = ch.get("characters_introduced") or ch.get("characters_active", [])
        for c in introduced:
            if isinstance(c, str) and c:
                char_bible = db.get_latest_characters(novel_id)
                char_list = char_bible["parsed_data"].get("characters", []) if char_bible else []
                if not any(x.get("name") == c for x in char_list):
                    newly_emerged_characters.append(c)

    if newly_emerged_characters:
        newly_emerged_characters = list(set(newly_emerged_characters))
        yield "data: " + json.dumps({"type": "content", "delta": f"  🧵 [反向縫合] 偵測到新湧現的次要角色 {', '.join(newly_emerged_characters)}，精準增量追加回角色 Bible 設定末尾...\n"}, ensure_ascii=False) + "\n\n"
        
        char_bible = db.get_latest_characters(novel_id)
        pd = char_bible["parsed_data"] if char_bible else {"characters": []}
        if "characters" not in pd:
            pd["characters"] = []
            
        for nc in newly_emerged_characters:
            desc = "新登場的次要角色"
            for ch in node_chapters:
                for ev in ch.get("events", []):
                    action_text = ev.get("action", "")
                    match = re.search(r'[\(（]' + re.escape(nc) + r'[-－:：\s]+([^）\)]+)[\)）]', action_text)
                    if match:
                        desc = match.group(1).strip()
                        break
            
            pd["characters"].append({
                "name": nc,
                "role": "配角",
                "entry_phase": f"第 {start_chapter} 章登場",
                "personality": [desc.split("，")[0] if "，" in desc else desc],
                "speech_style": "符合人設說話風格",
                "want": "隨劇情展開的外在目標",
                "need": "隨劇情展開的內在需求",
                "fatal_flaw": "未知缺陷",
                "motivation": desc,
                "arc": "待演變的弧線",
                "relationships": []
            })
        db.save_characters(novel_id, pd)

    # 7. 合併並保存整本大綱到 SQLite
    all_micro_chapters = list(existing_chapters)
    
    for new_ch in node_chapters:
        ch_idx = new_ch["chapter_index"]
        all_micro_chapters = [
            c for c in all_micro_chapters
            if existing_chapter_index(c) != int(ch_idx)
        ]
        all_micro_chapters.append(new_ch)
        
    all_micro_chapters.sort(key=existing_chapter_index)

    final_dict = {"chapters": all_micro_chapters}
    
    from incremental_patch_engine import post_merge_validation
    is_valid, errors = post_merge_validation(final_dict, "plot")
    if is_valid:
        db.save_plot_chapters(novel_id, final_dict)
        yield "data: " + json.dumps({"type": "content", "delta": f"\n\n=== [大綱生成完成] ===\n第 {start_chapter} 章至第 {end_chapter} 章大綱已規劃完成！目前全書共 {len(all_micro_chapters)} 章。已成功保存！\n\n"}, ensure_ascii=False) + "\n\n"
    else:
        err_msg = f"[ERROR] 大綱保存驗證失敗：{', '.join(errors)}"
        print(err_msg)
        yield "data: " + json.dumps({"type": "error", "message": err_msg}, ensure_ascii=False) + "\n\n"

    yield "data: " + json.dumps({"type": "done"}) + "\n\n"


def generate_chapter_synopsis(content):
    """
    Calls the copilot (director) model to compress the written chapter into a 50-character/word plot summary.
    """
    prompt = f"""⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

請將以下小說章節正文壓縮為一段精簡的劇情概要（約 50 字左右）。
注意：
1. 僅包含最核心的劇情事實（發生了什麼事件、什麼反轉或進展）。
2. 不要包含任何過渡、解釋、寒暄或前言，只輸出這段概要本身。

章節正文：
{content}
"""
    messages = [
        {"role": "user", "content": prompt}
    ]
    synopsis = ""
    # call_llm_stream generates SSE chunks. Let's consume it and get only the content.
    for chunk in call_llm_stream("copilot", messages):
        if chunk.startswith("data:"):
            try:
                data_str = chunk[5:].strip()
                if data_str == "[DONE]":
                    continue
                data = json.loads(data_str)
                if data.get("type") == "content":
                    synopsis += data.get("delta", "")
            except:
                pass
    return synopsis.strip()

def run_chapter_writer(novel_id, chapter_index, custom_style="Swiss Modernism 2.0 (Elegant, polished, sensory, dramatic)"):
    """
    Runs the Chapter Writer to write the actual prose for the specified chapter index.
    """
    import db
    
    context = compile_context(novel_id)

    ok_wb, _ = validate_worldview(context.get("worldbuilding", ""))
    ok_char, _ = validate_characters(context.get("characters", ""))
    ok_plot_ch, _ = validate_plot_has_chapter(context.get("plot", ""), int(chapter_index))
    if not ok_wb:
        return _sse_error_done("無法撰寫正文：缺少世界觀設定。請先完成世界觀（worldview）。")
    if not ok_char:
        return _sse_error_done("無法撰寫正文：缺少角色設定（Character Bible）。請先完成角色設計（characters）。")
    if not ok_plot_ch:
        return _sse_error_done(f"無法撰寫正文：缺少第 {chapter_index} 章的大綱（outline）。請先完成章節大綱（plot）。")
    
    # Extract specific chapter details if we have plot chapter data
    plot_json = parse_json_safely(context["plot"])
    specified_chapter_outline = "No outline found for this chapter index."
    
    if "chapters" in plot_json:
        for ch in plot_json["chapters"]:
            if ch.get("chapter_index") is not None and int(ch.get("chapter_index")) == int(chapter_index):
                specified_chapter_outline = json.dumps(ch, ensure_ascii=False, indent=2)
                break
    
    # 【Step 5 修復】動態計算並注入伏筆追蹤資訊
    all_chapters = plot_json.get("chapters", []) if isinstance(plot_json, dict) else []
    
    # 統計所有伏筆埋設與回收
    all_plants = {}  # seed_id -> [chapter_indices]
    all_payoffs = {}  # seed_id -> [chapter_indices]
    current_ch_idx = int(chapter_index)
    
    for ch in all_chapters:
        ch_idx = ch.get("chapter_index")
        if ch_idx is None:
            continue
        try:
            ch_idx = int(ch_idx)
        except (ValueError, TypeError):
            continue
        
        # 收集埋設
        plants = ch.get("foreshadowing_plant", []) or []
        if isinstance(plants, str):
            plants = [plants]
        for p in plants:
            if not isinstance(p, str):
                continue
            # 嘗試解析 Seed ID
            matches = re.findall(r'(?:[Ss]eed)\s*[-\s]?\s*(\d+)', p)
            for m in matches:
                seed_id = int(m)
                all_plants.setdefault(seed_id, []).append(ch_idx)
        
        # 收集回收
        payoffs = ch.get("foreshadowing_payoff", []) or []
        if isinstance(payoffs, str):
            payoffs = [payoffs]
        for py in payoffs:
            if not isinstance(py, str):
                continue
            matches = re.findall(r'(?:[Ss]eed)\s*[-\s]?\s*(\d+)', py)
            for m in matches:
                seed_id = int(m)
                all_payoffs.setdefault(seed_id, []).append(ch_idx)
    
    # 計算當前進行的伏筆組數量
    active_seeds = []
    ending_soon_seeds = []
    for seed_id, plant_chapters in all_plants.items():
        if not plant_chapters:
            continue
        earliest_plant = min(plant_chapters)
        # 找出這個 seed 的回收章節
        payoff_chapters = all_payoffs.get(seed_id, [])
        if not payoff_chapters:
            # 仍在進行中
            active_seeds.append({
                "seed_id": seed_id,
                "planted_at": earliest_plant,
                "distance": current_ch_idx - earliest_plant
            })
            # 即將在近期（5章內）回收
            if payoff_chapters:
                nearest_payoff = min(payoff_chapters)
                if 0 < nearest_payoff - current_ch_idx <= 5:
                    ending_soon_seeds.append({
                        "seed_id": seed_id,
                        "payoff_at": nearest_payoff,
                        "distance": nearest_payoff - current_ch_idx
                    })
    
    # 計算即將回收的伏筆（未來的伏筆回收）
    upcoming_payoffs = []
    for seed_id, payoff_chapters in all_payoffs.items():
        for payoff_ch in payoff_chapters:
            if current_ch_idx < payoff_ch <= current_ch_idx + 10:
                upcoming_payoffs.append({
                    "seed_id": seed_id,
                    "payoff_at": payoff_ch,
                    "distance": payoff_ch - current_ch_idx
                })
    
    active_count = len(active_seeds)
    ending_soon_count = len(ending_soon_seeds)
    upcoming_count = len(upcoming_payoffs)
    
    # 生成伏筆追蹤描述
    foreshadowing_tracking = f"""【當前伏筆動態追蹤】
- 進行中伏筆：{active_count} 組
- 即將於本章或近期（5章內）結束的伏筆：{ending_soon_count} 組
- 預計在接下來10章內回收的伏筆：{upcoming_count} 組"""
    
    if ending_soon_seeds:
        foreshadowing_tracking += f"\n即將回收的伏筆："
        for s in ending_soon_seeds[:3]:  # 最多顯示3個
            foreshadowing_tracking += f"\n  - [Seed-{s['seed_id']}] 預計於第 {s['payoff_at']} 章回收（距離 {s['distance']} 章）"
    
    if upcoming_payoffs:
        foreshadowing_tracking += f"\n未來10章內的伏筆回收："
        for s in sorted(upcoming_payoffs, key=lambda x: x['distance'])[:5]:  # 距離最近的5個
            foreshadowing_tracking += f"\n  - [Seed-{s['seed_id']}] 將於第 {s['payoff_at']} 章回收（距離 {s['distance']} 章）"
                
    # Also fetch previous chapters to maintain continuity
    previous_chapters_text = ""
    for idx in range(1, int(chapter_index)):
        old_ch = get_latest_chapter(novel_id, idx)
        if old_ch:
            summary = old_ch["content"][:800] + "..." if len(old_ch["content"]) > 800 else old_ch["content"]
            previous_chapters_text += f"--- CHAPTER {idx} (PREVIEW) ---\n{summary}\n\n"
            
    prompt_content = f"""【世界觀設定】
{context['worldbuilding']}
 
【角色聖經】
{context['characters']}
 
【本章小大綱（精細規劃）】
章節序號：第 {chapter_index} 章
{specified_chapter_outline}
 
【前章正文（銜接用）】
{previous_chapters_text or "這是第一章，無前章。"}
 
請根據以上小大綱撰寫第 {chapter_index} 章的完整正文散文。嚴格遵循小大綱中的時間、事件、伏筆和角色安排。
"""
    
    system_prompt = CHAPTER_WRITER_PROMPT.format(writing_style=custom_style)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt_content}
    ]
    
    def save_callback(nid, text, thinking=""):
        import re
        from db import save_chapter, apply_worldview_patch, mark_subsequent_dirty
        
        content = text
        inline_thinking = ""
        
        # Extract <think> tags from content
        think_matches = re.findall(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
        if think_matches:
            inline_thinking = "\n".join(think_matches).strip()
            content = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
            
        # 💡 [START_OF_PROSE] or [正文開始] splitting
        special_words = ["[START_OF_PROSE]", "[正文開始]"]
        for sw in special_words:
            if sw in content:
                parts = content.split(sw, 1)
                inline_thinking = (inline_thinking + "\n" + parts[0].strip()).strip()
                content = parts[1].strip()
                break
                
        final_thinking = (thinking.strip() + "\n" + inline_thinking.strip()).strip()
        
        # Intercept NEW_WORLD_LAW tags (Universal Feedback Loop)
        law_pattern = r'\[NEW_WORLD_LAW:\s*([^\]\-]+?)\s*-\s*([^\]]+?)\]'
        laws = re.findall(law_pattern, content)
        if laws:
            for cat, details in laws:
                apply_worldview_patch(nid, cat.strip(), details.strip())
            # Delay alignment: mark downstream/subsequent chapters and volumes as dirty
            mark_subsequent_dirty(nid, int(chapter_index))
            
        # Clean up any NEW_WORLD_LAW tags from the final prose
        content = re.sub(law_pattern, '', content).strip()
        synopsis = generate_chapter_synopsis(content)
        save_chapter(nid, int(chapter_index), content, synopsis, final_thinking)
        
    return run_agent_stream(novel_id, "writer", messages, save_callback)

def run_editor_agent(novel_id, chapter_index, edit_instructions=None):
    """
    Runs the Editor Agent to polish the given chapter based on user instructions.
    """
    ch_data = get_latest_chapter(novel_id, int(chapter_index))
    if not ch_data:
        # Generate an error event
        def error_gen():
            yield "data: " + json.dumps({
                "type": "error",
                "message": f"Chapter {chapter_index} has no content to edit. Please write it first."
            }, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        return error_gen()
        
    context = compile_context(novel_id)
    plot_json = parse_json_safely(context['plot'])
    current_chapter_outline = None
    if "chapters" in plot_json:
        for ch in plot_json["chapters"]:
            if ch.get("chapter_index") == int(chapter_index):
                current_chapter_outline = ch
                break

    prompt_content = f"""【世界觀設定】
{context['worldbuilding']}
 
【角色設定】
{context['characters']}
 
【第 {chapter_index} 章 原始正文】
{ch_data['content']}
"""
    if current_chapter_outline:
        prompt_content += f"\n\n【第 {chapter_index} 章大綱】\n{json.dumps(current_chapter_outline, ensure_ascii=False, indent=2)}\n"
    if edit_instructions:
        prompt_content += f"\n【用戶編輯指示】\n{edit_instructions}\n"
        
    prompt_content += f"\n請對第 {chapter_index} 章進行精修潤色。只輸出潤色後的完整正文。"
    
    messages = [
        {"role": "system", "content": EDITOR_PROMPT},
        {"role": "user", "content": prompt_content}
    ]
    
    def save_callback(nid, text, thinking=""):
        import re
        from db import save_chapter, apply_worldview_patch, mark_subsequent_dirty
        
        content = text
        inline_thinking = ""
        
        # Extract <think> tags from content
        think_matches = re.findall(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
        if think_matches:
            inline_thinking = "\n".join(think_matches).strip()
            content = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
            
        # 💡 [START_OF_PROSE] or [正文開始] splitting
        special_words = ["[START_OF_PROSE]", "[正文開始]"]
        for sw in special_words:
            if sw in content:
                parts = content.split(sw, 1)
                inline_thinking = (inline_thinking + "\n" + parts[0].strip()).strip()
                content = parts[1].strip()
                break
                
        final_thinking = (thinking.strip() + "\n" + inline_thinking.strip()).strip()
        
        # Intercept NEW_WORLD_LAW tags (Universal Feedback Loop)
        law_pattern = r'\[NEW_WORLD_LAW:\s*([^\]\-]+?)\s*-\s*([^\]]+?)\]'
        laws = re.findall(law_pattern, content)
        if laws:
            for cat, details in laws:
                apply_worldview_patch(nid, cat.strip(), details.strip())
            # Delay alignment: mark downstream/subsequent chapters and volumes as dirty
            mark_subsequent_dirty(nid, int(chapter_index))
            
        # Clean up any NEW_WORLD_LAW tags from the final prose
        content = re.sub(law_pattern, '', content).strip()
        synopsis = generate_chapter_synopsis(content)
        save_chapter(nid, int(chapter_index), content, synopsis, final_thinking)
        
    return run_agent_stream(novel_id, "editor", messages, save_callback)

def run_copilot_chat(novel_id, user_message):
    """
    General novel co-pilot chat that answers questions and guides user edits.
    Uses sqlite chat memory.
    """
    # 1. Fetch memory (only actual user/assistant chats, not massive director evaluations)
    memory = get_chat_memory(novel_id, limit=20, message_type='chat')
    
    # 2. Get novel context
    context = compile_context(novel_id)
    
    # 3. Save user message to database memory
    save_chat_message(novel_id, "user", user_message, message_type="chat")
    
    # 4. Formulate messages
    system_content = CO_PILOT_ORCHESTRATOR_PROMPT.format(
        worldview=context["worldbuilding"],
        characters=context["characters"],
        plot=context["plot"],
        written_chapters=context["written_chapters"]
    )
    
    messages = [{"role": "system", "content": system_content}]
    
    # Add historical messages from memory
    for m in memory:
        messages.append({"role": m["role"], "content": m["content"]})
        
    # Add current user message
    messages.append({"role": "user", "content": user_message})
    
    # For copilot, we use the global LLM config and save the response to chat memory when done
    def save_callback(nid, text, thinking=""):
        import re
        content = text
        inline_thinking = ""
        think_matches = re.findall(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
        if think_matches:
            inline_thinking = "\n".join(think_matches).strip()
            content = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
        final_thinking = (thinking.strip() + "\n" + inline_thinking.strip()).strip()
        
        save_chat_message(nid, "assistant", content, final_thinking, message_type="chat")
        
    return run_agent_stream(novel_id, "global", messages, save_callback)

# --- DIRECTOR PIPELINE DECISION ENGINE ---
# Director 執行模式標記（用於區分一鍵執行模式 vs 一般模式）
# 一鍵執行模式：總監的建議即為執行令（自動執行）
# 一般模式：總監提供建議，由用戶決定
DIRECTOR_EXECUTION_MODE = {"auto_execute": False, "user_prompt": ""}

def set_director_auto_execute(mode: bool):
    """設定 Director 是否為一鍵自動執行模式"""
    DIRECTOR_EXECUTION_MODE["auto_execute"] = mode

def get_director_auto_execute() -> bool:
    """獲取 Director 執行模式"""
    return DIRECTOR_EXECUTION_MODE.get("auto_execute", False)

def set_director_user_prompt(prompt: str):
    """設定當前用戶的創作需求 prompt"""
    DIRECTOR_EXECUTION_MODE["user_prompt"] = prompt

def get_director_user_prompt() -> str:
    """獲取當前用戶的創作需求 prompt"""
    return DIRECTOR_EXECUTION_MODE.get("user_prompt", "")

from agents_director import (
    verify_novel_integrity,
    pre_check_next_agent,
    get_simplified_director_prompt,
    run_director_decision,
    run_director_decision_help
)


def run_agent_stream(novel_id, agent_name, messages, save_callback=None):
    """
    Main engine that handles streaming chunk processing and automatic DB saving.
    """
    accumulated_text = ""
    accumulated_thinking = ""
    
    for sse_line in call_llm_stream(agent_name, messages):
        yield sse_line
        
        # Capture generated content chunks
        if sse_line.startswith("data:"):
            try:
                data_str = sse_line[5:].strip()
                if data_str == "[DONE]":
                    continue
                data = json.loads(data_str)
                if data.get("type") == "content":
                    accumulated_text += data.get("delta", "")
                elif data.get("type") == "thinking":
                    accumulated_thinking += data.get("delta", "")
            except:
                pass
                
    # Once yielding finishes, save the final output
    if save_callback and accumulated_text.strip():
        try:
            import inspect
            sig = inspect.signature(save_callback)
            if "thinking" in sig.parameters:
                save_callback(novel_id, accumulated_text, thinking=accumulated_thinking)
            else:
                save_callback(novel_id, accumulated_text)
        except Exception as e:
            print(f"Error saving in agent callback: {e}")
            # Yield a final error warning (not strictly standard but helps debug)
            yield "data: " + json.dumps({
                "type": "error",
                "message": f"Database save failed: {str(e)}"
            }, ensure_ascii=False) + "\n\n"


# ==============================================================================
# NEW STAGE 2: VOLUME SKELETON PLANNER (簡易章大綱生成器)
# ==============================================================================
def run_volume_skeleton_planner(novel_id, volume_index, user_prompt=None):
    """
    [新功能] 針對特定篇卷，一次性生成底層所有的簡易章節骨架大綱 (Stage 2)
    這是四階段漸進式大綱生成策略的第二階段：
    Stage 1 (Story Architect) -> Stage 2 (Volume Skeleton) -> Stage 3 (Foreshadowing) -> Stage 4 (Plot Expansion)
    """
    import db
    
    context = compile_context(novel_id)
    
    ok_wb, wb_errors = validate_worldview(context.get("worldbuilding", ""))
    ok_char, char_errors = validate_characters(context.get("characters", ""))
    
    if not ok_wb:
        for line in _sse_error_done("無法生成簡易章大綱：缺少世界觀設定。請先完成世界觀（worldview）再進行章綱規劃。"):
            yield line
        return
    if not ok_char:
        for line in _sse_error_done("無法生成簡易章大綱：缺少角色設定（Character Bible）。請先完成角色設計（characters）再進行章綱規劃。"):
            yield line
        return
    
    # 讀取當前卷的設定
    from db import get_volumes
    volumes = get_volumes(novel_id)
    target_vol = None
    for v in volumes:
        if int(v.get("volume_index", 0)) == int(volume_index):
            target_vol = v
            break
    
    if not target_vol:
        for line in _sse_error_done(f"無法找到第 {volume_index} 卷的設定。請先在世界觀設定中規劃篇卷結構。"):
            yield line
        return
    
    vol_title = target_vol.get("title", f"第 {volume_index} 卷")
    vol_summary = target_vol.get("summary", "")
    vol_chapter_count = int(target_vol.get("chapter_count", 50))
    
    # 檢查是否已有大綱骨架，若已有大綱骨架且沒有特定的用戶修改指示，直接跳過以保護現有資料！
    ch_outline_str = target_vol.get("chapters_outline")
    has_existing = False
    if ch_outline_str:
        try:
            ch_list = ch_outline_str if isinstance(ch_outline_str, list) else json.loads(ch_outline_str or "[]")
            if isinstance(ch_list, list) and len(ch_list) > 0:
                has_existing = True
        except:
            pass

    if has_existing and not user_prompt:
        yield "data: " + json.dumps({"type": "content", "delta": f"=== [簡易章大綱生成] ===\n  ℹ️ 偵測到第 {volume_index} 卷《{vol_title}》已有完整大綱骨架，已自動跳過以保護已有數據。\n\n"}, ensure_ascii=False) + "\n\n"
        return
        
    yield "data: " + json.dumps({"type": "content", "delta": f"=== [簡易章大綱生成] ===\n正在為第 {volume_index} 卷《{vol_title}》生成簡易章節骨架...\n章節數量：{vol_chapter_count} 章\n\n"}, ensure_ascii=False) + "\n\n"
    
    # 計算本卷的章節範圍
    start_ch, end_ch = db.get_volume_chapter_range(volumes, int(volume_index))
    
    # 構建世界觀上下文
    worldview_json = db.parse_worldview_to_json(context.get("worldbuilding", ""))
    
    # 滑動視窗聚焦：根據卷的進度篩選相關的伏筆與轉折
    total_vols = len(volumes)
    vol_progress = (int(volume_index) - 1) / max(total_vols - 1, 1) if total_vols > 1 else 0.0
    
    seeds_list = worldview_json.get("foreshadowing_seeds", [])
    turning_points = worldview_json.get("key_turning_points", [])
    
    focused_seeds = []
    if isinstance(seeds_list, list) and seeds_list:
        S = len(seeds_list)
        for idx, seed in enumerate(seeds_list):
            seed_pos = idx / S if S > 1 else 0.0
            if abs(seed_pos - vol_progress) <= 0.3:
                focused_seeds.append(f"[Seed-{idx + 1}] {seed}")
        if not focused_seeds:
            sorted_seeds = sorted(enumerate(seeds_list), key=lambda x: abs((x[0] / S if S > 1 else 0.0) - vol_progress))
            focused_seeds = [f"[Seed-{x[0] + 1}] {x[1]}" for x in sorted_seeds[:6]]
    
    focused_turning_points = []
    if isinstance(turning_points, list) and turning_points:
        T = len(turning_points)
        for idx, tp in enumerate(turning_points):
            tp_pos = idx / T if T > 1 else 0.0
            if abs(tp_pos - vol_progress) <= 0.3:
                focused_turning_points.append(f"[TurningPoint-{idx + 1}] {tp}")
        if not focused_turning_points:
            sorted_tps = sorted(enumerate(turning_points), key=lambda x: abs((x[0] / T if T > 1 else 0.0) - vol_progress))
            focused_turning_points = [f"[TurningPoint-{x[0] + 1}] {x[1]}" for x in sorted_tps[:6]]
    
    seeds_text = "\n".join(focused_seeds) if focused_seeds else "（尚無伏筆種子）"
    turning_points_text = "\n".join(focused_turning_points) if focused_turning_points else "（尚無關鍵轉折點）"
    
    # 構建前卷銜接上下文（如果並非第一卷）
    prev_volume_context = ""
    if int(volume_index) > 1:
        prev_vol_idx = int(volume_index) - 1
        prev_vol = next((v for v in volumes if int(v.get("volume_index", 0)) == prev_vol_idx), None)
        if prev_vol:
            prev_vol_title = prev_vol.get("title", f"第 {prev_vol_idx} 卷")
            prev_vol_summary = prev_vol.get("summary", "")
            prev_volume_context = f"\n\n【前卷銜接參考 - 第 {prev_vol_idx} 卷《{prev_vol_title}》】\n{prev_vol_summary}\n本卷應承接前卷結尾的張力與懸念。"
    
    prompt_content = f"""⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你是宏觀小說結構大師，專精於為大長篇小說建立輕量級的「章節骨骼里程碑」。

## 任務
請根據以下資訊，為第 {volume_index} 卷《{vol_title}》生成 {vol_chapter_count} 個章節的簡易骨架。

## 卷設定
- 卷標題：{vol_title}
- 卷概要：{vol_summary}
- 本卷章節範圍：第 {start_ch} 章至第 {end_ch} 章（共 {vol_chapter_count} 章）
{prev_volume_context}

## 世界觀設定
主題：{worldview_json.get("theme", "未設定")}
核心衝突：{worldview_json.get("main_conflict", "未設定")}
世界觀背景：{worldview_json.get("worldview", "未設定")}

## 全域伏筆與轉折池（已根據本卷進度篩選最相關的種子）
{seeds_text}

## 關鍵轉折點池
{turning_points_text}

## ⚠️ 重要約束 (Stage 2 有機伏筆編織大綱生成)
1. 每章必須有一個清晰的「情節里程碑宣言」—— 這章必須達成什麼敘事目的？
2. 絕對禁止模板化！每個章節標題和概要都必須是獨特的、具體的。
3. 【有機伏筆編織融入】：你必須從一開始就帶著伏筆寫大綱骨架！我們已篩選出本卷專屬的『全域伏筆與轉折池』。
   請在編寫章節的里程碑概要(brief_summary)時，將篩選出的 [Seed-X] 或 [TurningPoint-Y] 有機自然地作為情節背景、道具或衝突織入其中。
   並在對應章節 object 的 `allocated_tasks` 欄位中填寫該伏筆或轉折的完整字串作為 tag 儲存！
   例如：若第 5 章埋下了 `[Seed-1] 魔法晶片的祕密`，請直接在該章節 object 的 `allocated_tasks.foreshadowing_plants` 中寫入 `["[Seed-1] 魔法晶片的祕密"]`，並在 `brief_summary` 內寫出主角在此處自然拾獲神祕晶片的故事細節。
4. 為確保長線敘事張力，每 5-10 章應有一個中等轉折，每卷結尾應有一個強力的章末鉤子。

## 輸出格式（嚴格遵守 JSON）
```json
{{
  "volume_index": {volume_index},
  "chapters_skeleton": [
    {{
      "chapter_index": {start_ch},
      "brief_title": "精煉且富有文采的暫定章節標題",
      "brief_summary": "本章核心情節里程碑宣言（50-100字，描述本章必須達成的敘事目的與前因後果）",
      "allocated_tasks": {{
        "foreshadowing_plants": [],
        "foreshadowing_payoffs": [],
        "turning_points": []
      }}
    }}
  ]
}}
```
"""
    
    messages = [
        {"role": "system", "content": VOLUME_SKELETON_PROMPT},
        {"role": "user", "content": prompt_content}
    ]
    
    # 💡 修正點：移除 save_callback 內部的 yield，改為純執行函式
    def save_callback(nid, text):
        parsed = parse_json_safely(text)
        if isinstance(parsed, dict) and "chapters_skeleton" in parsed:
            from db import save_volume_skeletons
            save_volume_skeletons(nid, volume_index, parsed["chapters_skeleton"])
        else:
            print(f"[WARN] Volume skeleton parse failed: {parsed}")
    
    # 執行並收集輸出
    skeleton_output = ""
    for sse_line in run_agent_stream(novel_id, "plot", messages, save_callback):
        yield sse_line
        if sse_line.startswith("data:"):
            try:
                data_str = sse_line[5:].strip()
                if data_str == "[DONE]":
                    continue
                data = json.loads(data_str)
                if data.get("type") == "content":
                    skeleton_output += data.get("delta", "")
            except:
                pass
    
    # 💡【核心修復】：在串流完全結束後，進行 100% 完整全量數據的終點強制存檔！
    # 防止串流中途修補導致的後半段骨架漏接問題
    if skeleton_output:
        parsed_final = parse_json_safely(skeleton_output)
        if isinstance(parsed_final, dict) and "error" in parsed_final:
            parsed_final = parse_json_safely(clean_json_text(skeleton_output))
            
        if isinstance(parsed_final, dict) and "chapters_skeleton" in parsed_final:
            from db import save_volume_skeletons
            save_volume_skeletons(novel_id, volume_index, parsed_final["chapters_skeleton"])
            print(f"[GUARD SUCCESS] Volume {volume_index} {vol_chapter_count}-chapter full skeleton safely locked into DB.")
            
    # 💡 修正點：將成功訊息改在外層這裡發送，避免 callback 變成生成器
    yield "data: " + json.dumps({"type": "content", "delta": f"  ✅ 第 {volume_index} 卷的簡易章大綱已成功保存到資料庫！\n"}, ensure_ascii=False) + "\n\n"
    yield "data: " + json.dumps({"type": "content", "delta": f"\n=== [第 {volume_index} 卷簡易章大綱生成完成] ===\n"}, ensure_ascii=False) + "\n\n"
    yield "data: " + json.dumps({"type": "done"}) + "\n\n"


def run_foreshadowing_orchestrator(novel_id, user_prompt=None):
    """
    [新功能] 全局伏筆與轉折編織對齊階段 (Stage 3)
    這是四階段漸進式大綱生成策略的第三階段。
    我們採用 [Python 演算法 + LLM 情節編織] 的黃金雙軌制：
    1. Python 演算法對伏筆與轉折進行 100% 電腦級精準、均勻且合法的分配，徹底根絕時序顛倒、漏埋、隨機亂埋、或在 5 章內快速閉環等低級邏輯錯誤。
    2. 只有被分配到任務的章節才會發送給 LLM 進行情節描述拋光，大幅釋放 Context 並提高生成文采。
    3. 配備 100% 雙軌融合保底安全防線，即便 LLM 解析或生成出錯，仍能保證一秒鐘產出 100% 正確的分配。
    """
    import db
    import random
    import hashlib
    import json
    
    context = compile_context(novel_id)
    
    # 獲取世界觀中的伏筆種子與轉折點
    worldview_json = db.parse_worldview_to_json(context.get("worldbuilding", ""))
    foreshadowing_seeds = worldview_json.get("foreshadowing_seeds", [])
    key_turning_points = worldview_json.get("key_turning_points", [])
    
    if not foreshadowing_seeds and not key_turning_points:
        for line in _sse_error_done("無法執行伏筆編織：世界觀中尚無伏筆種子或轉折點設定。請先在世界觀設定中添加伏筆與轉折點。"):
            yield line
        return
    
    # 獲取所有卷的簡易章骨架
    from db import get_all_volume_skeletons
    skeletons = get_all_volume_skeletons(novel_id)
    
    if not skeletons:
        for line in _sse_error_done("無法執行伏筆編織：尚無簡易章大綱骨架。請先完成各卷的簡易章大綱生成（volume_skeleton）。"):
            yield line
        return
    
    yield "data: " + json.dumps({"type": "content", "delta": "=== [全局伏筆編織對齊] ===\n正在啟動高維度 [演算法+LLM雙軌對齊] 進行伏筆與轉折全局調度...\n\n"}, ensure_ascii=False) + "\n\n"
    
    N = len(skeletons)
    S = len(foreshadowing_seeds)
    T = len(key_turning_points)
    
    # 確保 skeletons 按 chapter_index 排序
    skeletons.sort(key=lambda x: int(x.get("chapter_index", 0)))
    chapter_indices = [int(x.get("chapter_index", 0)) for x in skeletons]
    
    # 決定跨度 min_span，以防範短距離快速回收
    if N >= 50:
        min_span = max(15, N // 5)
    elif N >= 20:
        min_span = max(8, N // 4)
    elif N >= 10:
        min_span = max(4, N // 3)
    else:
        min_span = max(1, N // 2)
        
    # 初始化一個分配表映射
    prog_allocations = {
        ch_idx: {
            "chapter_index": ch_idx,
            "title": skeletons[idx].get("brief_title") or skeletons[idx].get("title") or "未命名",
            "summary": skeletons[idx].get("brief_summary") or skeletons[idx].get("summary") or "無",
            "foreshadowing_plants": [],
            "foreshadowing_payoffs": [],
            "turning_points": []
        }
        for idx, ch_idx in enumerate(chapter_indices)
    }
    
    # 使用 novel_id 哈希作為隨機種子，以保證同一小說重試分配時的一致性與穩定性
    h_seed = int(hashlib.md5(novel_id.encode('utf-8')).hexdigest(), 16) % (2**32)
    r = random.Random(h_seed)
    
    # 1. 均勻分配 S 個 seeds 的 plant 和 payoff
    for i in range(S):
        max_plant_idx = N - min_span - 1
        if max_plant_idx <= 0:
            plant_idx = 0
        else:
            # 為了平均分配，將 plant 均勻分佈在全書前中段
            seg_size = float(max_plant_idx + 1) / S
            start_seg = int(i * seg_size)
            end_seg = int((i + 1) * seg_size)
            start_seg = max(0, min(start_seg, max_plant_idx))
            end_seg = max(start_seg + 1, min(end_seg, max_plant_idx + 1))
            plant_idx = r.randint(start_seg, end_seg - 1)
            
        plant_ch = chapter_indices[plant_idx]
        
        # Payoff 必須在 [plant_idx + min_span, N - 1] 之間選擇，保證跨度
        payoff_start = plant_idx + min_span
        if payoff_start >= N:
            payoff_start = N - 1
        payoff_idx = r.randint(payoff_start, N - 1)
        payoff_ch = chapter_indices[payoff_idx]
        
        seed_desc = foreshadowing_seeds[i]
        prog_allocations[plant_ch]["foreshadowing_plants"].append(f"[Seed-{i+1}] {seed_desc}")
        prog_allocations[payoff_ch]["foreshadowing_payoffs"].append(f"[Seed-{i+1}] {seed_desc}")
        
    # 2. 均勻分配 T 個 turning points
    for j in range(T):
        # 平分全書區間
        seg_size = float(N) / T
        start_seg = int(j * seg_size)
        end_seg = int((j + 1) * seg_size)
        start_seg = max(0, min(start_seg, N - 1))
        end_seg = max(start_seg + 1, min(end_seg, N))
        tp_idx = r.randint(start_seg, end_seg - 1)
        tp_ch = chapter_indices[tp_idx]
        
        tp_desc = key_turning_points[j]
        prog_allocations[tp_ch]["turning_points"].append(f"[TurningPoint-{j+1}] {tp_desc}")
        
    # 挑選出有被指派任務的章節進行 LLM 情節編織
    tasked_chapters = []
    for ch_idx in chapter_indices:
        alloc = prog_allocations[ch_idx]
        if alloc["foreshadowing_plants"] or alloc["foreshadowing_payoffs"] or alloc["turning_points"]:
            tasked_chapters.append(alloc)
            
    # 💡 雙軌融合與寫入函數
    def merge_and_save_allocations(nid, llm_allocations):
        """
        將 LLM 回傳的拋光文字與 Python 100% 均勻正確的分配進行強制融合。
        如果 LLM 漏掉某個章節、伏筆種子(Seed-X)或轉折點，則自動套用 Python 保底分配，絕不丟失任何伏筆！
        """
        merged_list = []
        llm_map = {}
        if isinstance(llm_allocations, list):
            for item in llm_allocations:
                idx = item.get("chapter_index")
                if idx is not None:
                    llm_map[int(idx)] = item
                    
        for ch_idx in chapter_indices:
            prog = prog_allocations[ch_idx]
            llm_item = llm_map.get(ch_idx, {})
            
            merged_plants = []
            merged_payoffs = []
            merged_tps = []
            
            # 融合 plants
            for plant_str in prog["foreshadowing_plants"]:
                seed_tag = plant_str.split("]")[0] + "]"
                found = False
                llm_plants_list = llm_item.get("foreshadowing_plants", []) or []
                if isinstance(llm_plants_list, str):
                    llm_plants_list = [llm_plants_list]
                for lp in llm_plants_list:
                    if lp and seed_tag in lp:
                        merged_plants.append(lp)
                        found = True
                        break
                if not found:
                    merged_plants.append(f"在此處自然埋下伏筆線索：{plant_str}")
                    
            # 融合 payoffs
            for payoff_str in prog["foreshadowing_payoffs"]:
                seed_tag = payoff_str.split("]")[0] + "]"
                found = False
                llm_payoffs_list = llm_item.get("foreshadowing_payoffs", []) or []
                if isinstance(llm_payoffs_list, str):
                    llm_payoffs_list = [llm_payoffs_list]
                for lpy in llm_payoffs_list:
                    if lpy and seed_tag in lpy:
                        merged_payoffs.append(lpy)
                        found = True
                        break
                if not found:
                    merged_payoffs.append(f"在此處自然回收並引爆前期鋪墊：{payoff_str}")
                    
            # 融合 turning_points
            for tp_str in prog["turning_points"]:
                tp_tag = tp_str.split("]")[0] + "]"
                found = False
                llm_tps_list = llm_item.get("turning_points", []) or []
                if isinstance(llm_tps_list, str):
                    llm_tps_list = [llm_tps_list]
                for ltp in llm_tps_list:
                    if ltp and tp_tag in ltp:
                        merged_tps.append(ltp)
                        found = True
                        break
                if not found:
                    merged_tps.append(f"在此處觸發關鍵轉折事件：{tp_str}")
                    
            if merged_plants or merged_payoffs or merged_tps:
                merged_list.append({
                    "chapter_index": ch_idx,
                    "foreshadowing_plants": merged_plants,
                    "foreshadowing_payoffs": merged_payoffs,
                    "turning_points": merged_tps
                })
                
        from db import save_foreshadowing_allocations
        save_foreshadowing_allocations(nid, merged_list)
        print(f"[DOUBLE TRACK MERGE SUCCESS] allocations merged and safely locked into DB for {nid}.")
        
    # 💡 分批策略：每批最多 10 個 tasked chapters 送給 LLM，避免單次 prompt 過大導致 60s 超時
    BATCH_SIZE = 10
    all_llm_allocations = []

    def _build_prompt(batch_chapters):
        tasked_text = json.dumps(batch_chapters, ensure_ascii=False, indent=2)
        return f"""⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你是大長篇小說的伏筆編織大師與情節對齊導演。
我們已經透過系統精準分配演算法，為小說中的特定章節規劃好了伏筆與轉折指派任務。

## 任務
請審查以下『已被指派任務的章節清單』（本批共 {len(batch_chapters)} 個章節）。
針對每一個章節，將被指派的 [Seed-X] 或 [TurningPoint-Y] 任務，結合該章節的 brief_title 與 brief_summary，自然融合地撰寫具體文學性的敘事描述。
你的任務是將這些指派內容，拋光為優雅、自然融入情節的大綱敘事文字！

## ⚠️ 重要編織原則
1. **無損保留指派**：不要修改或遺漏被指派的 seed / turning_points 編號（例如 `[Seed-1]`, `[TurningPoint-2]`），這些編號必須完整保留在你的文字描述中！
2. **自然融入**：撰寫 1-2 句具體描述，說明伏筆是如何在情節中自然出現的。
3. **保持 JSON 格式**：你必須嚴格輸出 JSON 格式，其根結構包含一個 `allocations` 陣列。

## 指派任務的章節清單
{tasked_text}

## 輸出格式（嚴格遵守 JSON，包裹在 ```json ... ``` 中）
```json
{{
  "allocations": [
    {{
      "chapter_index": 5,
      "foreshadowing_plants": ["主角在廢墟中拾獲刻有神秘符文的晶片 [Seed-1]，晶片微弱的魔力殘留引起了主角的注意..."],
      "foreshadowing_payoffs": [],
      "turning_points": []
    }}
  ]
}}
```
"""

    for batch_start in range(0, len(tasked_chapters), BATCH_SIZE):
        batch = tasked_chapters[batch_start: batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(tasked_chapters) + BATCH_SIZE - 1) // BATCH_SIZE
        
        yield "data: " + json.dumps({"type": "content", "delta": f"  🔀 LLM 編織批次 {batch_num}/{total_batches}（共 {len(batch)} 個章節）...\n"}, ensure_ascii=False) + "\n\n"

        prompt_content = _build_prompt(batch)
        messages = [
            {"role": "system", "content": "你是一位嚴謹的小說伏筆編織導演，精通將線索自然織入情節骨架中。你必須完全以 JSON 格式回應，不說任何廢話。"},
            {"role": "user", "content": prompt_content}
        ]

        batch_output = ""
        try:
            for sse_line in call_llm_stream("copilot", messages):
                yield sse_line
                if sse_line.startswith("data:"):
                    try:
                        data_str = sse_line[5:].strip()
                        if data_str == "[DONE]":
                            continue
                        data = json.loads(data_str)
                        if data.get("type") == "content":
                            batch_output += data.get("delta", "")
                    except:
                        pass
        except Exception as e:
            print(f"[ERROR] foreshadowing orchestrator batch {batch_num} exception: {e}.")

        # 解析本批 LLM 結果
        parsed_batch = parse_json_safely(batch_output)
        if isinstance(parsed_batch, dict) and "error" in parsed_batch:
            parsed_batch = parse_json_safely(clean_json_text(batch_output))
        if isinstance(parsed_batch, dict) and "allocations" in parsed_batch:
            all_llm_allocations.extend(parsed_batch["allocations"])
            yield "data: " + json.dumps({"type": "content", "delta": f"  ✅ 批次 {batch_num} 編織成功，解析到 {len(parsed_batch['allocations'])} 個章節。\n"}, ensure_ascii=False) + "\n\n"
        else:
            yield "data: " + json.dumps({"type": "content", "delta": f"  ⚠️ 批次 {batch_num} LLM 解析失敗，將使用演算法保底分配。\n"}, ensure_ascii=False) + "\n\n"

    # 雙軌融合：將所有批次的 LLM 結果與演算法分配合併
    merge_and_save_allocations(novel_id, all_llm_allocations)

    yield "data: " + json.dumps({"type": "content", "delta": "\n=== [全局伏筆編織對齊完成] ===\n演算法與 LLM 已協同將所有伏筆與轉折成功對齊分配到各章節！\n"}, ensure_ascii=False) + "\n\n"
    yield "data: " + json.dumps({"type": "done"}) + "\n\n"




