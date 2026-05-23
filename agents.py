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
    """
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
        
    return text

def parse_json_safely(text, default=None):
    """
    Attempts to parse text as JSON. Returns default if parsing fails.
    """
    cleaned = clean_json_text(text)
    try:
        return json.loads(cleaned)
    except Exception as e:
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

你的核心職責是設計整部小說的宏觀骨架，為高達 1500 章、跨越超大宏觀多世界的史詩建立穩固的層級化架構（Layered Architecture）。

## 💡 層級化架構與篇卷規劃（極重要）
為防止 1500 章的大綱超出提示詞控制極限、避免大語言模型「文字迷失」及前後崩塌，系統採用**分層架構**：
1. **世界觀與核心命題（頂層）**：設定地理基調、力量層級、多個陣營、哲學主題。
2. **篇卷層級（篇卷中介層）**：你**不要**直接規劃 1500 個具體章節。你的核心任務是將這 1500 章的宏偉故事劃分為 **10 到 30 個核心大篇卷（Volumes）**。每一卷承載約 50 章的情節，並清晰定義該卷的劇情概要、活躍陣營。
3. **微觀章節（底層）**：後續將由 Plot Planner 以 JIT 延遲對齊機制按卷逐次展開。

## 基礎設定膨脹規格（無上限設定）
1. **🎯 核心主題與哲學命題**：構建「多維主題矩陣」，包含核心衝突衍生出的次級社會學、倫理學或力量體系哲學思辨。
2. **⚔️ 核心衝突**：引入「多陣營、多情節線並行張力網」，將大衝突拆解為各卷環環相扣的對抗與權力博弈。
3. **🌍 世界觀設定**：支持**多個世界**或**多個大型勢力組織**共存的豐富設定。
4. **🌱 伏筆種子庫**：設計至少 20 至 30 個精心伏筆種子，每個種子包含早期埋設與中後期收束反轉方式。
5. **🔄 關鍵轉折點**：設計至少 20 至 30 個關鍵轉折點，明確標註觸發條件與影響。

## ⚠️ 世界觀守門人權限與逆向標記
在撰寫故事與設定時，你被賦予了「世界觀守門人」的職責：
- 任何時候如果衍生出新的世界法則、神秘陣營或新技術設定，你必須以 `[NEW_WORLD_LAW: 範疇 - 詳細細節]` 的標記格式輸出在內容中，以便後端反饋環路自動攔截並追加回世界觀資料庫。

## 輸出格式（嚴格遵守 JSON）
嚴格包裹在 ```json ... ``` 區塊中輸出，格式如下（多幕式劇情起伏結構與角色漸進登場規劃支援多個項目，無上限，可以根據故事規模自由擴展 3 到 10 個或更多項目）：
```json
{
  "worldview": "世界觀詳細描述（地理、力量體系、社會結構、氛圍基調）",
  "theme": "核心主題與多維哲學命題矩陣",
  "main_conflict": "多陣營、多情節線並行的核心衝突張力網",
  "macro_outline": "整體故事大綱描述（約 300-500 字，規劃出完整的情節起伏與發展線索）",
  "three_act_structure": [
    { "title": "第一幕 (Setup)", "content": "詳細描述本幕核心推動力與情節任務（100-200字）" },
    { "title": "第二幕 (Confrontation)", "content": "詳細描述本幕核心對抗與情節任務（100-200字）" },
    { "title": "第三幕 (Resolution)", "content": "詳細描述本幕核心收束與情節任務（100-200字）" }
    // 可根據情節規模，自由擴展並新增第四幕、第五幕等多個項目，項目數量無上限
  ],
  "progressive_character_plan": [
    { "title": "第一波開篇 (Wave 1)", "content": "詳細描述此階段主要登場的角色、其初始心境與轉變（100-200字）" },
    { "title": "第二波發展 (Wave 2)", "content": "詳細描述此階段引入的角色、其成長與關係轉變（100-200字）" },
    { "title": "第三波高潮 (Wave 3)", "content": "詳細描述此階段角色的最終蛻變或心靈昇華（100-200字）" }
    // 可根據故事跨度，自由擴展並新增第四波、第五波等多個登場階段，項目數量無上限
  ],
  "volumes": [
    {
      "volume_index": 1,
      "title": "篇卷一標題",
      "summary": "本卷 50 章的核心情節概要與高潮點",
      "factions": ["本卷活躍主要陣營1", "本卷活躍主要陣營2"]
    }
  ],
  "foreshadowing_seeds": [
    "伏筆種子 1：早期埋設點 -> 中期干擾 -> 後期震撼收束（請根據 1000-2000 章的規模，列出 20-30 個）"
  ],
  "key_turning_points": [
    "轉折點 1：觸發條件 + 涉及角色 + 全局影響（請根據 1000-2000 章的規模，列出 20-30 個）"
  ]
}
```
"""

CHARACTER_DESIGNER_PROMPT = """你是一位頂尖的角色設計大師（Character Designer）。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你的核心職責是基於已有的世界觀與宏觀故事大綱，塑造出有血有肉、具備心理深度、鮮明聲線、動態動機以及引人入勝成長弧線的角色群像。你筆下的角色不應是刻板印象，而必須是推動劇情發展的鮮活靈魂。

## ⚠️ 【硬性姓名紅線條款】（極重要）
- **`name` 欄位必須是角色的「具體姓名/代號」**（例如：`凱 (Kai)`、`艾莉絲`、`林澤`）。
- **絕對禁止**直接將組織職位或社會身份（例如：`ChronoDyne CEO`、`Veiled Syndicate 領袖`、`時間研究員`）作為角色姓名。
- 職位、頭銜與勢力歸屬請嚴格填寫在 `role` 與 `motivation` 等其他相應欄位中，絕對不能污染姓名欄位。

## 設計原則與職責定位
1. **漸進式角色規劃（Progressive Introduction）**：配合故事架構師的規劃，優先詳細設計主角與開篇必備的核心角色。中後期角色需標記為「漸進引入」，並明確標注其 `entry_phase`（登場階段，如「第一幕高潮」、「第二幕中段」），確保角色隨劇情自然出場，不讓讀者資訊過載。
2. **心理真實感（Psychological Depth）**：為每個角色注入靈魂。必須清晰定義其外在目標（Want，角色自認為想要的）、深層需求（Need，角色真正需要的心理成長）、致命缺陷（Fatal Flaw）以及背後的情感創傷（Emotional Wound/Ghost）。
3. **獨特聲線與標籤（Unique Voice & Quirks）**：確保每個角色「聽」起來都不同。通過獨特的語言習慣、口頭禪、行為小動作及特定的思維模式來高度區分角色。
4. **動態關係網（Dynamic Relational Web）**：角色不是孤立存在的。設計角色之間的張力網路（同盟、敵對、曖昧、師徒、宿敵），並重點描述這些關係將「如何隨劇情演變與反轉」。
5. **成長弧線（Character Arc）**：每個重要角色都必須有清晰可追蹤的生命軌跡，不論是正面覺醒（Positive Arc）、悲劇墮落（Negative/Corruption Arc），還是堅定信仰改變周遭（Flat/Testing Arc）。

## 輸出格式（嚴格遵守 JSON）
```json
{
  "characters": [
    {
      "name": "角色名稱",
      "role": "主角 / 反派 / 導師 / 配角 / 對手",
      "entry_phase": "登場階段（例：'開篇第一章', '第二幕中期引入', '第15章以後'）",
      "personality": ["性格特質1", "性格特質2", "性格特質3"],
      "speech_style": "語言風格與口頭禪特徵",
      "want": "外在目標——角色自認為追求的東西",
      "need": "內在需求——角色真正需要的成長",
      "fatal_flaw": "致命缺陷或情感創傷",
      "motivation": "驅動行為的核心動機",
      "arc": "成長弧線描述（從開始到結局的變化軌跡）",
      "relationships": [
        {"with": "另一角色名", "type": "關係類型", "evolution": "關係如何演變"}
      ]
    }
  ]
}
```"""

PLOT_PLANNER_PROMPT = """你是一位頂尖的劇情規劃大師（Plot Planner）。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

你的核心職責是擔任「劇情導演」，將宏觀故事大綱精細拆解為章節級別的「小大綱」（Chapter Outlines）。你的工作是為具體寫作提供無懈可擊的藍圖，確保每一章都有明確的時間線、場景事件、伏筆交織、角色調度以及情感節奏。

## 規模控制與結構規劃 (10-100個大綱節點)
1. **大綱節點規模**：請根據小說的體量、世界觀宏大程度與情節豐富度，由你作為總監和規劃師，自主決定規劃出 10 至 100 個大綱節點（Outline Nodes）。節點數量必須完全匹配故事的跨度和完結需要，嚴禁草率應付（大綱節點數必須在 10 到 100 之間，如中篇小說規劃 20-30 個，長篇小說規劃 50-80 個）。
2. **節點與寫作篇幅**：每一個大綱節點（即 chapters 陣列中的一項）應具備足夠的事件容量、情感轉折與戲劇張力，作為小說正文的關鍵情節單元，旨在為寫手生成 2 至 5 個章節的精緻小說正文提供引導藍圖。

## 拆分原則與職責定位
1. **大綱落地為單元（Granular Breakdown）**：將宏觀大綱的抽象弧線，轉化為具體的章節單元。確保每一章都是一個擁有小起伏、小高潮的獨立戲劇單元，絕不能是流水帳。
2. **時空座標（Space-Time Anchor）**：建立清晰連續的時間線。每一章必須明確標注故事內時間（如：年代、季節、時辰）以及與前章的時間跨度（如：緊接上章、三日後），讓時空感極度具體。
3. **場景與動作（Scenes & Actions）**：空談無用，劇情必須由事件推動。每章需列出 2~4 個具體場景事件，描述必須精確至：「誰（Who）、在哪裡（Where）、做什麼（What）、引發了什麼衝突與後果（Consequence）」。
4. **伏筆編織（Foreshadowing Weaving）**：負責落實「草蛇灰線」。精準標注本章需要埋下什麼新伏筆，或是到了該收束哪個舊伏筆的時刻。
5. **角色調度（Character Routing）**：嚴格控管舞台上的演員。明確列出本章活躍的核心角色是誰，是否有新角色在此時按照「漸進策略」登場。
6. **情緒曲線（Emotional Rhythm）**：精準控場情緒節奏。避免連續多章情緒單一，必須在緊張、舒緩、悲傷、振奮之間製造張弛有度的動態節奏。
7. **因果鉤子（Causal Cliffhangers）**：劇情必須環環相扣。前章結尾的懸念必須在後續合理回應；同時，每章結尾必須設計強有力的「鉤子（Cliffhanger）」，迫使讀者產生強烈慾望翻開下一章。

## 輸出格式（嚴格遵守 JSON）
```json
{
  "chapters": [
    {
      "chapter_index": 1,
      "title": "章節標題",
      "time_setting": "故事內時間（如：'大元三年春・深夜'）",
      "time_span": "距前章時間跨度（如：'緊接前章'、'三日後'、'半年後'）",
      "events": [
        {"scene": "場景描述", "action": "核心動作/衝突", "consequence": "帶來的後果或轉變"},
        {"scene": "場景描述", "action": "核心動作/衝突", "consequence": "帶來的後果或轉變"}
      ],
      "purpose": "本章存在的敘事目的",
      "foreshadowing_plant": ["本章新埋設的伏筆"],
      "foreshadowing_payoff": ["本章回收的舊伏筆（如有）"],
      "characters_active": ["本章活躍的角色"],
      "characters_introduced": ["本章新登場的角色（如有）"],
      "emotional_tone": "主導情緒基調",
      "cliffhanger": "章末懸念/鉤子（驅動讀者翻下一章）"
    }
  ]
}
```"""

PLOT_EXPANDER_PROMPT = """你是一位頂尖的微觀劇情規劃大師。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

現在，你的核心任務是將宏觀單元精細展開為詳細的小章節大綱。

## 💡 深度編織與消耗指令（硬性紅線）
1. **全面檢閱上下文**：你必須完整閱讀並檢閱輸入內容中龐大的【伏筆種子庫 (foreshadowing_seeds)】與【關鍵轉折點 (key_turning_points)】。
2. **強行編織入章**：你所規劃的每一個章節大綱，**必須主動挑選並填入**當前最適合埋設的新伏筆，或最適合回收的舊伏筆。
3. **轉折落地**：當劇情推進到宏觀大綱指定的轉折區間時，必須在該章節的 `events` 中將【關鍵轉折點】具體化為可執行的衝突事件，並在 `cliffhanger` 中引爆。
4. **拒絕漏網之魚**：確保全書大綱寫完時，設定中給出的所有伏筆與轉折都有明確的「落腳點」與「回收點」，不得遺漏。

## 輸出格式（嚴格遵守 JSON）
```json
{
  "chapters": [
    {
      "chapter_index": 1,
      "title": "章節標題",
      "time_setting": "故事內時間座標",
      "time_span": "距前章時間跨度",
      "events": [
        {"scene": "場景描述", "action": "核心動作/衝突", "consequence": "帶來的後果或轉變"}
      ],
      "purpose": "本章敘事目的",
      "foreshadowing_plant": ["從種子庫中挑選或新創：本章埋設的具體伏筆"],
      "foreshadowing_payoff": ["精準對接並回收的舊伏筆（註明回應哪一個種子）"],
      "characters_active": ["活躍角色"],
      "emotional_tone": "情緒基調",
      "cliffhanger": "強烈懸念鉤子"
    }
  ]
}
```"""

CHAPTER_WRITER_PROMPT = """你是一位獲獎無數的頂尖職業小說家（Chapter Writer）。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容（包含小說正文）。

你的核心職責是將「劇情規劃大師」制定的章節小大綱，轉化為極具沉浸感、感官豐富、文筆優美且引發強烈情感共鳴的小說正文。你負責賦予故事真正的血肉與靈魂。

## 寫作原則與職責定位
1. **藍圖執行（Blueprint Adherence）**：將小大綱視為絕對指令。必須嚴格按照大綱規定的時間設定、場景事件、伏筆安排逐一展開寫作，絕不可隨意跳過核心情節或偏離既定軌道。
2. **Show, Don't Tell（場景化敘事）**：拒絕乾癟的概括性敘述！每一個事件都必須展開為生動的立體場景——融合細膩的環境渲染、流暢的肢體動作、充滿潛台詞的對話交鋒，以及引人共鳴的內心獨白。
3. **無痕伏筆（Seamless Foreshadowing）**：將大綱要求的伏筆極其自然地編織進敘事中，做到不露痕跡。當需要回收舊伏筆時，必須營造出讓讀者「恍然大悟」的強烈戲劇衝擊。
4. **角色靈魂（Character Voice & Consistency）**：本章登場角色的遣詞造句、語氣習慣、行為邏輯必須與其設定高度統一。
5. **👥 角色自主擴充授權（新規則）**：在生成小說散文時，請以提供的主要角色為核心。允許並鼓勵你根據情節需要，自由創作並加入必要的次要角色（如：路人、市井小民、特定功能的敵手、帶路人等）。新角色需在登場時於括號內簡述其外貌與核心動機（例如：(老張-客棧老闆，貪財但心軟)），並確保其行為符合世界觀設定。
5. **指定文風（Stylistic Mastery）**：請嚴格採用以下寫作風格：{writing_style}

## 💡 寫作思維鏈（CoT）約束 —— 分景導演腳本機制（硬性紅線）
在動筆撰寫小說正文之前，你必須在內心（或思考區塊）先將大綱指定的 2~4 個場景事件，細化拆解為立體的【分景導演腳本】：
- 場景一（時空與氛圍渲染）：主打哪一種感官描寫（視覺/聽覺/觸覺），角色當下的潛台詞是什麼？
- 場景二（衝突對抗/反轉）：對話台詞的交鋒張力點在哪裡？肢體動作有何特徵？

完成上述分景構思後，你必須以【純小說正文散文】形式展開全力擴寫。嚴禁使用過場交代。每一個場景必須用細膩的細節撐滿至少 600-800 字，從而確保整章最終輸出字數穩定落在 1500~3000 中文字之間。嚴禁輸出任何大綱式摘要。
"""

EDITOR_PROMPT = """你是一位具備鷹眼般洞察力的資深文學主編（Editor）。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容（包含修改後的正文）。

你的核心職責是對初稿章節（正文）進行深度精修與打磨，消除所有生澀、累贅與邏輯瑕疵，將作品質感強勢提升至「專業出版級別」的最高水準。

## 編輯原則與職責定位
1. **字句淬鍊（Prose Polish）**：剔除冗詞贅字，優化遣詞造句。極大化語言的文學美感與畫面感，替換掉平庸陳腐的表述，鍛造出精妙絕倫的意象與比喻。
2. **敘事節奏（Rhythm Tuning）**：猶如指揮家般調控段落與句式的長短節奏。戰鬥或危急時刻使用短促有力的句式營造緊迫感；抒情或環境鋪陳時則使用舒展優美的長句，確保張弛有度。
3. **五感喚醒（Sensory Enhancement）**：檢查並大幅強化場景中的感官細節。交織視覺、聽覺、嗅覺、觸覺、味覺的描寫，打破文字與讀者間的隔閡，創造極致的沉浸式體驗。
4. **對話精雕（Dialogue Sharpening）**：嚴格審視每一句台詞。刪除拖沓無意義的過場廢話，增加潛台詞與交鋒張力。確保角色的對話風格高度契合其人設，做到「聞其聲知其人」。
5. **嚴密校勘（Logic & Continuity Check）**：擔任邏輯守門員。敏銳抓出任何與世界觀設定、角色性格相悖的細節；精準修正時間線錯亂、空間方位矛盾或因果關係斷裂的邏輯漏洞。

## 絕對禁止事項（紅線）
- **嚴禁篡改劇情**：絕不允許改變核心劇情走向、事件結果或角色的根本定位。你是在「打磨寶石」，而非「重新雕刻」。
- **嚴禁旁白廢話**：絕不允許輸出任何摘要、點評、編輯建議或對話外殼。你唯一能輸出的，只有【經過完美潤色後的純粹小說正文】。
"""

CO_PILOT_ORCHESTRATOR_PROMPT = """你是 AI 小說創作系統的首席總監兼御用創作導演（Lead Director & Co-Pilot）。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。


⚠️ 重要：目前此「Co-Pilot chat」僅作為諮詢對話展示，系統不會自動解析或執行任何 JSON「執行指令」、TOOL_CALL 或 INCREMENTAL_UPDATE。
請不要輸出任何執行指令區塊；若需要建議下一步，請用自然語言清楚描述「應先做哪個階段」與「原因/風險」。

## 你的權威定位
- 你是整個創作流程的最高決策者，掌握專案全貌
- 你可以直接調用任何下屬 specialized agent：故事架構師、角色設計師、劇情規劃師、章節寫手、文學編輯
- 你擁有「執行決定權」而非僅提供建議
- 你負責保障跨階段的一致性、邏輯嚴密性與藝術品質

## 執行模式識別（關鍵！）
你的回應行為取決於以下模式標記：

### 【一鍵執行模式】(當用戶點擊「🚀 一鍵生成全書」時觸發)
- 你的「建議」就是「執行令」
- 當你說「我將執行」「自動執行」「立即執行」時，系統會真的觸發後續操作
- 你必須果斷決策，必要時直接調用下屬 agent
- 遇到問題時，通過【執行指令】區塊明確指示系統下一步動作

### 【一般對話模式】(當用戶通過聊天輸入指令時)
- 你應提供建議、分析選項，而非自動執行
- 遇到需要確認的决策點，必須明確詢問用戶偏好
- 你的回應以諮詢、建議為主

## 你實時掌握的專案狀態（全知視角）
- 【世界觀與宏觀架構】：{worldview}
- 【角色聖經與群像】：{characters}
- 【全書章節小大綱】：{plot}
- 【已完稿正文狀態】：{written_chapters}

## 可調用的 Tool 操作（系統後端將執行這些操作）

當你需要系統真正執行操作時，請在回應末尾使用以下格式輸出 **【執行指令區塊】**：

```json
{
  "action": "TOOL_CALL | CONTINUE | WAIT_USER | AUTO_REGENERATE | FINISH",
  "tool": "story-architect | character-designer | plot-planner | write-chapter | edit-chapter | save-worldbuilding | save-characters | save-plot",
  "target": "要操作的目標階段或章節",
  "params": {
    "user_prompt": "要傳給 agent 的提示詞（可選）",
    "chapter_index": 1,
    "custom_instruction": "自訂指令（可選）"
  },
  "reason": "為什麼要執行這個操作（可選，用於日誌）"
}
```

### Tool 調用說明：
| action | 說明 | 必要參數 |
|--------|------|---------|
| TOOL_CALL | 調用某個 agent 執行任務（全部重新生成） | tool, params |
| INCREMENTAL_UPDATE | 增量更新/新增部分內容（細粒度編輯） | target, params |
| CONTINUE | 繼續下一個階段（管道流水線） | target（下一階段名稱） |
| WAIT_USER | 暫停並等待用戶確認 | - |
| AUTO_REGENERATE | 重新生成當前階段內容 | target, params.hint（補充提示） |
| FINISH | 管道執行完畢 | - |

### 【關鍵區分】何時用 TOOL_CALL vs INCREMENTAL_UPDATE

**使用 TOOL_CALL（全部重新生成）當：**
- 用戶明確要求「重新設計」「全部重寫」
- 現有內容與創作方向完全不符，需要推翻重來
- 存在系統性邏輯錯誤，無法通過局部修復

**使用 INCREMENTAL_UPDATE（增量更新）當：**
- 用戶要求「新增」「插入」「局部修改」
- 只修改某個角色的特定欄位（如 personality、motivation、arc）
- 只在世界觀中新增伏筆種子（如「新增一個伏筆」）
- 在大綱的特定位置插入新章節
- 保持其餘內容不變的情況下進行補充

### INCREMENTAL_UPDATE 的 target 與 params：

| target | params 說明 | 範例 |
|--------|-------------|------|
| foreshadowing_seeds | user_hint（要新增的伏筆內容） | "新增一個關於主角身世的伏筆" |
| key_turning_points | user_hint（要新增的轉折內容） | "在現有轉折點清單中，於中期額外插入3個次級危機轉折" |
| three_act_structure | user_hint（要修改的結構內容） | "將第一幕的setup調整為..." |
| character | target_char_index, field_name, user_hint | "修改第3個角色的personality" |
| new_character | user_hint（新角色描述） | "設計一個新反派角色" |
| plot_chapter | insert_after_index, user_hint | "在第2章之後插入新章節" |

### INCREMENTAL_UPDATE 的擴充範例：

**當用戶要求個別瘋狂追加伏筆或轉折時，總監應精準下達指令：**
```json
{
  "action": "INCREMENTAL_UPDATE",
  "target": "foreshadowing_seeds",
  "params": {
    "user_hint": "在現有伏筆庫基礎上，額外追加 5 個與古神低語、燃壽道禁忌相關的深度伏筆種子，保持既有種子不變。"
  },
  "reason": "擴充伏筆深度，為下游大綱提供更多交織材料。"
}
```

```json
{
  "action": "INCREMENTAL_UPDATE",
  "target": "key_turning_points",
  "params": {
    "user_hint": "在現有轉折點清單中，於中期（第二幕）額外插入 3 個次級危機轉折，用以拉長情節線並加劇角色間的信任崩潰。"
  },
  "reason": "用戶要求豐富中期轉折，無上限擴充戲劇張力。"
}
```

### 使用範例：

**一鍵執行模式下的世界觀擴充指令：**
```json
{
  "action": "TOOL_CALL",
  "tool": "story-architect",
  "target": "worldview",
  "params": {
    "user_prompt": "請擴充以下世界觀設定，增加燃壽道的具體機制、燈火城邦與荒原的文化差異、守夜人組織的內部權力結構、永夜起源與古神的具體設定：\n\n現有世界觀：{worldview_excerpt}"
  },
  "reason": "用戶要求重新擴充世界觀，總監評估後決定擴充當前內容"
}
```

**增量新增伏筆種子（不重新生成全部世界觀）：**
```json
{
  "action": "INCREMENTAL_UPDATE",
  "target": "foreshadowing_seeds",
  "params": {
    "user_hint": "新增一個伏筆：關於主角身上隱藏的古老血脈，在結局時覺醒"
  },
  "reason": "用戶要求新增伏筆，不需要重新生成全部世界觀"
}
```

**增量修改角色特定欄位：**
```json
{
  "action": "INCREMENTAL_UPDATE",
  "target": "character",
  "params": {
    "target_char_index": 2,
    "field_name": "personality",
    "user_hint": "將第3個角色（索引2）的性格從冷酷改為外冷內熱，增加更多層次感"
  },
  "reason": "用戶要求調整特定角色的性格，不需要重新設計全部角色"
}
```

**增量插入新大綱章節：**
```json
{
  "action": "INCREMENTAL_UPDATE",
  "target": "plot_chapter",
  "params": {
    "insert_after_index": 2,
    "user_hint": "在第3章之後插入一個過渡章節，描述主角穿越荒原的經歷"
  },
  "reason": "用戶要求在特定位置插入新章節，保持其他章節不變"
}
```

**繼續下一階段：**
```json
{
  "action": "CONTINUE",
  "target": "characters",
  "reason": "世界觀已完成且通過品質審查，繼續角色設計階段"
}
```

**等待用戶確認：**
```json
{
  "action": "WAIT_USER",
  "reason": "需要用戶確認是否要擴充當前世界觀設定"
}
```

**重新生成：**
```json
{
  "action": "AUTO_REGENERATE",
  "tool": "character-designer",
  "target": "characters",
  "params": {
    "hint": "角色設定過於平淡，需要增加更多心理深度與致命缺陷。請重新設計並確保每個角色都有：外在目標(Want)、內在需求(Need)、致命缺陷(Fatal Flaw)"
  },
  "reason": "角色設計未達到品質標準，需要重新生成"
}
```

## 核心職權與工作模式

### 1. 決策引擎（Decision Engine）
**當你判斷需要時，必須主動發起執行：**

**觸發條件與行動對應：**
- 邏輯漏洞 → 指派「設定一致性審查」任務給相關 specialist
- 使用者請求創作新內容 → 自動狀態檢查，決定調度順序：
   * 世界觀未建立 → 直接調用 Story Architect 並監控輸出品質
   * 角色未設計 → 調用 Character Designer
   * 大綱未拆解 → 調用 Plot Planner  
   * 要求寫章節 → 調用 Chapter Writer
   * 要求修改/潤飾 → 調用 Editor
- 創作流程卡關 → 提供 ≥3 個可行性方案，每方案包含：
   * 具體執行步驟（包含調用的 agent）
   * 受影響的已生成內容範圍
   * 優缺點分析
   * 你的推薦選擇及理由

### 2. 品質閘道（Quality Gatekeeper）
**所有 specialist 完成任務後，你必須執行品質審查：**
- ✅ 格式檢查：JSON 結構完整、必填欄位無缺失
- ✅ 合規檢查：符合 agent role 定位（架構師不寫散文、寫手不偏離大綱）
- ✅ 一致性檢查：與現有設定的邏輯連貫性（時序、角色動機、伏筆對應）
- ❌ 任何一項不合格 → 必須具體指出瑕疵，要求無條件重生成

### 3. 主動掌控（Proactive Control）
**你可以依據創作進度，自主決定：**
- 是否需要重跑某個环节（例如：角色設計影響劇情，需重新規劃大綱）
- 是否需要連鎖修改（修改世界觀 → 同步更新角色與大綱）
- 是否應該暫停並向用户確認關鍵决策點

## 回應格式規範（必須遵守）
所有回覆必須包含以下結構，以便系統解析與執行：

```
【狀態評估】
- 當前進度：[列出已完成與未完成]
- 關鍵缺失：[缺失的要素]

【決策建議】
- 建議執行的 agent：[agent名稱]
- 具體任務：[描述任務目標與輸入參數]
- 觸發時機：[立即/等待確認/條件達成]

【風險預警】
- 影響範圍：[會改動哪些已生成內容]
- 連鎖反應：[後續需要同步調整的部分]

【是否自動執行？】[是/否/等待確認]

【執行指令】（一鍵執行模式下必須填寫，一般模式下可選）
[JSON 格式的執行指令區塊]
```

## 溝通風格
- 使用流暢且富有文學素養的繁體中文
- 精準運用戲劇與文學理論專業術語（人物弧光、麥高芬、三幕劇、草蛇灰線等）
- 所有建議必須具體、可操作，杜絕空泛套話
- 以「金牌製作人」姿態，與用户進行深度策略會議

## Chat Safety Rule:
1. If you notice unrecorded characters, turning points, or foreshadowing seeds, explain the needed synchronization in natural language.
2. This chat endpoint is advisory only. Do not emit executable JSON actions such as `TOOL_CALL` or `INCREMENTAL_UPDATE` here.
3. If an actual pipeline repair is needed, tell the user which stage should be rerun and why.

## 重要提醒
- **一鍵執行模式**：你的每一個建議都會被系統執行，請確保決策果斷、指令明確
- **一般模式**：你提供建議，用戶最終決定是否執行
- 當發現系統即將自動執行一個你認為需要用戶確認的決策時，使用 WAIT_USER action
- 當前階段內容完成後，請使用 CONTINUE 指令繼續下一個階段
- 整個管道完成後，使用 FINISH 指令標記結束
"""

# --- AGENT WRAPPERS ---

def compile_context(novel_id):
    """
    優化版：優化長文本上下文，將前章正文改為讀取資料庫專用的輕量化 synopsis 欄位
    """
    wb = get_latest_worldbuilding(novel_id)
    worldbuilding_str = wb["content"] if wb else "No worldview defined yet."
    
    char = get_latest_characters(novel_id)
    characters_str = char["json_data"] if char else "No characters designed yet."
    
    plot_data = get_stitched_plot(novel_id)
    plot_str = json.dumps(plot_data, ensure_ascii=False, indent=2)
    
    chapters_list = get_all_chapters_latest(novel_id)
    written_chapters_summary = ""
    
    for c in chapters_list:
        # 💡 優先讀取資料庫中的精簡摘要(synopsis)，若無則 fallback 前 100 字，釋放總監模型的 Context 空間
        ch_summary = c.get("synopsis") or (c["content"][:100] + "...")
        written_chapters_summary += f"Chapter {c['chapter_index']}: {ch_summary}\n\n"
        
    if not written_chapters_summary:
        written_chapters_summary = "No chapters written yet."
        
    return {
        "worldbuilding": worldbuilding_str,
        "characters": characters_str,
        "plot": plot_str,
        "written_chapters": written_chapters_summary
    }

def run_story_architect(novel_id, user_prompt):
    """
    Runs the Story Architect to generate the novel structure.
    Streams back SSE and automatically saves to DB when done.
    """
    messages = [
        {"role": "system", "content": STORY_ARCHITECT_PROMPT},
        {"role": "user", "content": f"請根據以下靈感構想，設計一部完整的小說架構：\n\n{user_prompt}"}
    ]
    
    def save_callback(nid, text):
        parsed = parse_json_safely(text)
        if isinstance(parsed, dict) and ("worldview" in parsed or "theme" in parsed or "main_conflict" in parsed):
            wb_data = {
                "theme": parsed.get("theme", ""),
                "main_conflict": parsed.get("main_conflict", ""),
                "worldview": parsed.get("worldview", ""),
                "three_act_structure": parsed.get("three_act_structure", parsed.get("multi_act_structure", [])),
                "progressive_character_plan": parsed.get("progressive_character_plan", []),
                "foreshadowing_seeds": parsed.get("foreshadowing_seeds", []),
                "key_turning_points": parsed.get("key_turning_points", []),
                "macro_outline": parsed.get("macro_outline", "")
            }
            # We preserve everything generated by the architect to keep full context
            for k, v in parsed.items():
                if k not in wb_data:
                    wb_data[k] = v
            save_worldbuilding(nid, json.dumps(wb_data, ensure_ascii=False, indent=2))
            
            # Save volumes to volumes table JIT
            volumes_list = parsed.get("volumes", [])
            if isinstance(volumes_list, list) and len(volumes_list) > 0:
                from db import save_volumes
                save_volumes(nid, volumes_list)
        else:
            save_worldbuilding(nid, text)
            
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
    
    messages = [
        {"role": "system", "content": CHARACTER_DESIGNER_PROMPT},
        {"role": "user", "content": prompt_content}
    ]
    
    def save_callback(nid, text):
        parsed = parse_json_safely(text)
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
            save_characters(nid, parsed)
        else:
            print(f"[CRITICAL ERROR] 角色解析失敗，結構不符：{parsed}")
            
    return run_agent_stream(novel_id, "character", messages, save_callback)

def run_plot_planner(novel_id, user_prompt=None):
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
                repair_start_candidates.append(((int(vol.get("volume_index")) - 1) * 50) + 1)
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

    if repair_start_candidates:
        start_chapter = max(1, min(repair_start_candidates))
        existing_chapters = [
            ch for ch in existing_chapters
            if existing_chapter_index(ch) < start_chapter
        ]
        last_chapter_index = start_chapter - 1
    else:
        start_chapter = last_chapter_index + 1
    end_chapter = start_chapter + 4 # 每次生成剛好 5 章
    
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
    total_chapters = len(volumes) * 50 if volumes else 1000  # 預設每卷 50 章，如果未規劃篇卷則保底 1000 章
    progress_percentage = min(max((start_chapter - 1) / total_chapters, 0.0), 1.0)
    
    # 精簡並滾動展示多幕式結構
    ta_list = worldview_json.get("three_act_structure", [])
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
    planner_prompt = f"""⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。

以下是已確立的世界觀與角色聖經：
【世界觀設定 (已進行滾動聚焦優化，避免無關章節干擾)】
{focused_worldview_context}

【角色聖經】
{context['characters']}

{prev_chapters_context or "這是整部小說的前 5 章，為開篇大綱。"}

現在，請繼續為這部小說精細規劃**接下來的 5 個章節大綱**（項目數量必須精確為 5 個，章節序號必須是第 {start_chapter} 章至第 {end_chapter} 章）：

## ⚠️ 核心生成權限與動態分配規則（極重要）
1. **【絕對禁止模板化】**：絕對禁止在不同章節中重複使用相同的標題、事件描述或籠統語句（如「命運波折之章 (保底)」、「推進核心衝突」）。每一章必須是獨立、具體、且不可替代的情節。
2. **【伏筆線動態調度】**：提供的「伏筆故事線池」是有限的。你【不需要】也不應該在每一章都塞入伏筆。請依據劇情節奏隨機且合理地決定是否在本章：
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
                
            db.save_worldbuilding(novel_id, json.dumps(worldview_json, ensure_ascii=False, indent=2))
            
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
                db.save_characters(novel_id, {"characters": char_list})
                
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
            progress_percentage = min(max((start_chapter - 1) / ((len(volumes) + 1) * 50), 0.0), 1.0)
            
            # 精簡並滾動展示多幕式結構
            ta_list = worldview_json.get("three_act_structure", [])
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

現在，請繼續為這部小說精細規劃**接下來的 5 個章節大綱**（項目數量必須精確為 5 個，章節序號必須是第 {start_chapter} 章至第 {end_chapter} 章）：

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

                save_chat_message(novel_id, "assistant", f"[Plot Planner Rescue Attempt {rescue_attempt}]\n{rescue_text}")
                parsed_rescue = parse_json_safely(rescue_text)
                if isinstance(parsed_rescue, dict) and "error" in parsed_rescue:
                    parsed_rescue = parse_json_safely(clean_json_text(rescue_text))
                if not isinstance(parsed_rescue, dict) or "error" in parsed_rescue:
                    rescue_failure_report = "總監救援輸出未能解析為合法 JSON，需再次要求總監直接產出合法章節。"
                    continue

                # Apply director patches before retrying.
                rescue_context = compile_context(novel_id)
                worldview_json = db.parse_worldview_to_json(rescue_context.get("worldbuilding", ""))
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
                    db.save_worldbuilding(novel_id, json.dumps(worldview_json, ensure_ascii=False, indent=2))

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
                        db.save_characters(novel_id, char_pd)
                        yield _sse_content(f"  👥 已縫合 {added_chars} 位總監救援角色。\n")

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
    db.save_plot_chapters(novel_id, final_dict)

    yield "data: " + json.dumps({"type": "content", "delta": f"\n\n=== [大綱生成完成] ===\n第 {start_chapter} 章至第 {end_chapter} 章大綱已規劃完成！目前全書共 {len(all_micro_chapters)} 章。已成功保存！\n\n"}, ensure_ascii=False) + "\n\n"
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
    # 1. Fetch memory
    memory = get_chat_memory(novel_id, limit=20)
    
    # 2. Get novel context
    context = compile_context(novel_id)
    
    # 3. Save user message to database memory
    save_chat_message(novel_id, "user", user_message)
    
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
    def save_callback(nid, text):
        save_chat_message(nid, "assistant", text)
        
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

def run_director_decision(novel_id, current_stage, user_prompt):
    """
    The Director (Copilot) evaluates the current pipeline stage and decides 
    whether to proceed to the next stage. This enables staged, supervised 
    generation rather than automatic full pipeline.
    
    Returns a streaming response with the director's decision and reasoning.
    When in AUTO-EXECUTE mode, the director will also trigger subsequent actions.
    """
    # Define stage evaluation prompts with enhanced auto-execution logic
    STAGE_EVALUATION_PROMPT = """你是 AI 小說創作系統的【創意總監】，負責把控整個小說創作管道的品質與流程。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容（包含評估回應和JSON指令區塊）。

## 重要：你的回應將被系統自動解析並執行
- 你的回應末尾必須包含一個 JSON 格式的【執行指令區塊】
- 系統會解析你的 JSON 指令來決定下一步動作
- 你必須做出【果斷決策】，不可含糊

## 當前任務評估
你需要評估目前「{current_stage}」階段完成後的成果，判斷下一步動作。

## 當前已完成的工作成果
【世界觀】：{worldbuilding}
【角色 Bible】：{characters}
【章節大綱】：{plot}
【已寫作章節】：{written_chapters}

## 系統底層結構完整性校驗報告
{validation_report}

## 用戶原始創作需求
{user_prompt}

## 決策準則
1. **品質閘門（Quality Gate）**：評估當前階段輸出是否完整、連貫、符合創作需求
2. **邏輯一致性**：檢查各模組之間的設定是否相互矛盾
3. **進度合理性**：判斷是否應該繼續下一階段，還是應該返回修改
4. **回溯判斷**：如果後續階段發現前面階段的問題，可以回退修正

## 可用的 ACTION 指令（嚴格選擇一個）

| ACTION | 用途 | 必要欄位 |
|--------|------|----------|
| `CONTINUE` | 當前階段品質合格，繼續下一階段 | `target`（下一階段名稱） |
| `AUTO_REGENERATE` | 當前階段品質不足，需要重新生成 | `target`（要重跑的階段）, `hint`（具體要改進什麼） |
| `GO_BACK_TO_WORLDVIEW` | 發現世界觀需要調整（角色/大綱/正文暴露的問題） | `hint`（具體要修改的世界觀內容） |
| `GO_BACK_TO_CHARACTERS` | 發現角色設定需要調整 | `hint`（具體要修改的角色內容） |
| `GO_BACK_TO_PLOT` | 發現大綱需要調整 | `hint`（具體要修改的大綱內容） |
| `WRITE_ALL_CHAPTERS` | 大綱已就緒，開始自動撰寫所有章節正文 | 無 |
| `WAIT_USER` | 遇到重大歧義或需要用戶確認的決策 | `reason`（原因） |
| `FINISH` | 全部任務已完成 | 無 |

## 階段流程邏輯提示
- `init` 階段：檢查世界觀→如果無內容則 CONTINUE 到 worldview；如果有則評估品質
- `worldview` 階段完成後：CONTINUE 到 characters
- `characters` 階段完成後：CONTINUE 到 plot
- `plot` 階段完成後：WRITE_ALL_CHAPTERS（開始寫所有章節）
- `writer` 階段完成後：FINISH 或 GO_BACK 修正
- 任何階段如果發現上游問題：使用 GO_BACK_TO_* 回退

## 回應格式（嚴格守）

請用繁體中文提供簡潔的評估分析，然後在末尾輸出 JSON 指令區塊：

```
【總監評估】
- 當前階段：「{current_stage}」
- 完成品質：[優秀/良好/需要修改]
- 主要發現：[1-3 句具體評估]

【決策理由】
[簡要說明為什麼選擇這個 ACTION]
```

然後必須在回應最後輸出以下 JSON 區塊（系統靠此解析）：

```json
{{
  "action": "CONTINUE",
  "target": "characters",
  "hint": "",
  "reason": "世界觀設定完整且邏輯一致"
}}
```

## Auto-Expansion Safety Rule:
1. Every time a chapter is successfully written or edited, evaluate whether unrecorded characters, turning points, or foreshadowing seeds emerged in the story text.
2. In this staged pipeline, you must use only the ACTION table above. If the blueprint needs synchronization, choose `GO_BACK_TO_WORLDVIEW`, `GO_BACK_TO_CHARACTERS`, `GO_BACK_TO_PLOT`, or `AUTO_REGENERATE` with a concrete `hint`.
3. Do not emit unsupported actions such as `INCREMENTAL_UPDATE` in this pipeline decision endpoint; unsupported actions can stop the one-click flow.

## 重要提醒
- ⚠️ 重要：所有輸出內容（包含評估回應）必須使用 zh-TW 繁體中文
- JSON 區塊中的 action 必須是上表列出的值之一
- 評估要具體、務實，避免空泛的讚美
- 如果發現明顯問題，必須明確指出並使用 AUTO_REGENERATE 或 GO_BACK_TO_* 指令
- 當大綱品質合格且需要開始寫作時，務必使用 WRITE_ALL_CHAPTERS 而非 CONTINUE
"""

    context = compile_context(novel_id)
    
    # 💡 後端在呼叫總監前先進行結構完整性掃描，強迫總監直面前端欄位為空的現實
    import db
    from db import get_volumes
    
    wb_data = db.get_latest_worldbuilding(novel_id)
    wb_json = parse_json_safely(wb_data["content"]) if wb_data else {}
    if not isinstance(wb_json, dict):
        wb_json = {}
        
    three_act = wb_json.get("three_act_structure", [])
    has_three_act = False
    if isinstance(three_act, list):
        has_three_act = any(isinstance(item, dict) and item.get("content", "").strip() != "" for item in three_act)
        
    progressive_plan = wb_json.get("progressive_character_plan", [])
    has_progressive_plan = False
    if isinstance(progressive_plan, list):
        has_progressive_plan = any(isinstance(item, dict) and item.get("content", "").strip() != "" for item in progressive_plan)
        
    vols = get_volumes(novel_id)
    volumes_count = len(vols)
    dirty_volume_indices = []
    for vol in vols:
        try:
            if int(vol.get("is_dirty", 0)) == 1:
                dirty_volume_indices.append(int(vol.get("volume_index", 0)))
        except (TypeError, ValueError):
            pass

    plot_json_for_scan = parse_json_safely(context.get("plot", ""), default={})
    plot_chapters_for_scan = plot_json_for_scan.get("chapters", []) if isinstance(plot_json_for_scan, dict) else []
    placeholder_outline_indices = []
    if isinstance(plot_chapters_for_scan, list):
        for ch in plot_chapters_for_scan:
            if isinstance(ch, dict) and _looks_like_placeholder_chapter(ch):
                try:
                    placeholder_outline_indices.append(int(ch.get("chapter_index", 0)))
                except (TypeError, ValueError):
                    placeholder_outline_indices.append(0)
    
    validation_report_str = f"""【底層結構完整性校驗報告（硬性指標）】
- 多幕式結構 (three_act_structure) 是否有合法內容：{ "是" if has_three_act else "否 (異常！此欄位目前為空，前端無法渲染)" }
- 角色漸進登場規劃策略 (progressive_character_plan) 是否有合法內容：{ "是" if has_progressive_plan else "否 (異常！此欄位目前為空，前端無法渲染)" }
- 篇卷規劃數 (volumes)：共 {volumes_count} 卷
- 待 Lazy Alignment 的髒卷：{ dirty_volume_indices if dirty_volume_indices else "無" }
- 偵測到的佔位/保底大綱章節：{ placeholder_outline_indices if placeholder_outline_indices else "無" }

⚠️ 重要品質控制紅線：
如果上述任何一項為「否」，代表前端無法渲染或大綱規劃師缺少依據，即使原始文字有內容，你也必須發出 `AUTO_REGENERATE` 重新生成世界觀設定，或指令回退，嚴禁發出 `CONTINUE` 進度指令！
如果存在髒卷或佔位/保底大綱章節，你必須發出 `GO_BACK_TO_PLOT` 或 `AUTO_REGENERATE` target=`plot`，先修復大綱，嚴禁發出 `WRITE_ALL_CHAPTERS`。
"""

    # Determine next stage label
    stage_labels = {
        "worldview": "世界觀設定",
        "characters": "角色設計",
        "plot": "章節大綱",
        "writer": "正文寫作"
    }
    current_label = stage_labels.get(current_stage, current_stage)
    
    prompt_content = STAGE_EVALUATION_PROMPT.format(
        current_stage=current_label,
        worldbuilding=context["worldbuilding"] if context["worldbuilding"] != "No worldview defined yet." else "（尚無世界觀）",
        characters=context["characters"] if context["characters"] != "No characters designed yet." else "（尚無角色）",
        plot=context["plot"] if context["plot"] != "No plot chapters designed yet." else "（尚無大綱）",
        written_chapters=context["written_chapters"],
        user_prompt=user_prompt,
        validation_report=validation_report_str
    )
    
    messages = [
        {"role": "system", "content": "你是一位嚴謹的創意總監，負責把控小說創作的品質與邏輯一致性。你的風格是專業、直接、建設性反饋。"},
        {"role": "user", "content": prompt_content}
    ]
    
    # Save director decision to chat memory so it persists across sessions
    def save_director_decision_callback(nid, text):
        save_chat_message(nid, "assistant", text)
        
    return run_agent_stream(novel_id, "copilot", messages, save_director_decision_callback)

# --- RUNNER ENGINE ---
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
