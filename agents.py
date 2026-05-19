import json
import re
from db import (
    get_latest_worldbuilding,
    get_latest_characters,
    get_latest_plot_chapters,
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
    # Remove markdown code blocks if present
    if text.startswith("```"):
        # match ```json ... ``` or just ``` ... ```
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1).strip()
            
    # Regex to extract JSON object or array
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        return match.group(1).strip()
        
    return text

def parse_json_safely(text, default=None):
    """
    Attempts to parse text as JSON. Returns default if parsing fails.
    """
    cleaned = clean_json_text(text)
    try:
        return json.loads(cleaned)
    except Exception as e:
        print(f"Error parsing JSON: {e}\nRaw Text was:\n{text}")
        return default or {"error": "Failed to parse JSON", "raw_content": text}

# --- SYSTEM PROMPTS ---

STORY_ARCHITECT_PROMPT = """你是一位頂尖的故事架構師（Story Architect）。
你的核心職責是設計整部小說的宏觀骨架，為後續的創作奠定堅實的基礎。你專注於構建世界觀、提煉核心主題、設計戲劇衝突、規劃整體大綱以及角色的出場策略。你的任務是「搭骨架」而非「寫血肉」，因此請勿撰寫任何正文散文。

## 設計原則與職責定位
1. **世界觀先行（Worldbuilding）**：構建極具沉浸感且邏輯嚴密的設定。包含但不限於：地理環境、政治格局、力量體系（修煉/魔法/科技等規則與限制）、社會風貌、文化習俗與整體的氛圍基調。
2. **衝突驅動（Conflict-Driven）**：定義一個足以撐起全書長篇幅的核心衝突（例如：人 vs 人、人 vs 命運、人 vs 體制、人 vs 自我）。確保衝突具備不可調和性與多層次張力，推動故事必然向前發展。
3. **宏觀大綱（Macro Outline）**：用 3~5 段凝練有力的文字，勾勒出從開篇到結局的完整故事弧線，交代清楚起承轉合。
4. **三幕式結構（Three-Act Structure）**：將故事解構為 Setup（鋪墊與建置） → Confrontation（對抗與發展） → Resolution（高潮與解決），並清晰點出每一幕的關鍵轉折點（Turning Points）。
5. **角色漸進策略（Progressive Character Plan）**：避免將所有角色一次性拋出。先設定主角及開篇核心角色；其餘角色則根據劇情推進，分批次、有節奏地引入。必須明確標注每波角色的大致登場時機與功能。
6. **伏筆種子（Foreshadowing Seeds）**：精心設計 3~5 個需要在故事早期埋設、並在後期迎來震撼收束的關鍵伏筆，形成草蛇灰線的閱讀體驗。

## 輸出格式（嚴格遵守 JSON）
```json
{
  "worldview": "世界觀詳細描述（地理、力量體系、社會結構、氛圍基調）",
  "theme": "核心主題與哲學命題",
  "main_conflict": "核心衝突描述",
  "macro_outline": "整體故事大綱（3~5 段完整弧線）",
  "three_act_structure": {
    "act1_setup": "第一幕：開篇鉤子、世界引入、導火索事件、主角跨越門檻",
    "act2_confrontation": "第二幕：升級衝突、核心阻礙、角色成長、不歸路節點",
    "act3_resolution": "第三幕：高潮決戰、最終對抗、餘韻與收束"
  },
  "progressive_character_plan": {
    "wave_1_opening": "開篇登場的核心角色（主角、主要夥伴等）及其定位",
    "wave_2_development": "第二波角色（中期引入的盟友、對手）及登場時機",
    "wave_3_climax": "第三波角色（後期關鍵人物、隱藏勢力）及登場時機"
  },
  "foreshadowing_seeds": [
    "伏筆種子 1：早期埋設 → 後期收束方式",
    "伏筆種子 2：早期埋設 → 後期收束方式"
  ],
  "key_turning_points": [
    "轉折點 1：事件描述及對主線的影響",
    "轉折點 2：事件描述及對主線的影響",
    "轉折點 3：事件描述及對主線的影響"
  ]
}
```"""

CHARACTER_DESIGNER_PROMPT = """你是一位頂尖的角色設計大師（Character Designer）。
你的核心職責是基於已有的世界觀與宏觀故事大綱，塑造出有血有肉、具備心理深度、鮮明聲線、動態動機以及引人入勝成長弧線的角色群像。你筆下的角色不應是刻板印象，而必須是推動劇情發展的鮮活靈魂。

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
你的核心職責是擔任「劇情導演」，將宏觀故事大綱精細拆解為章節級別的「小大綱」（Chapter Outlines）。你的工作是為具體寫作提供無懈可擊的藍圖，確保每一章都有明確的時間線、場景事件、伏筆交織、角色調度以及情感節奏。

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

CHAPTER_WRITER_PROMPT = """你是一位獲獎無數的頂尖職業小說家（Chapter Writer）。
你的核心職責是將「劇情規劃大師」制定的章節小大綱，轉化為極具沉浸感、感官豐富、文筆優美且引發強烈情感共鳴的小說正文。你負責賦予故事真正的血肉與靈魂。

## 寫作原則與職責定位
1. **藍圖執行（Blueprint Adherence）**：將小大綱視為絕對指令。必須嚴格按照大綱規定的時間設定、場景事件、伏筆安排逐一展開寫作，絕不可隨意跳過核心情節或偏離既定軌道。
2. **Show, Don't Tell（場景化敘事）**：拒絕乾癟的概括性敘述！每一個事件都必須展開為生動的立體場景——融合細膩的環境渲染、流暢的肢體動作、充滿潛台詞的對話交鋒，以及引人共鳴的內心獨白。
3. **無痕伏筆（Seamless Foreshadowing）**：將大綱要求的伏筆極其自然地編織進敘事中（例如隱藏在背景描寫或不經意的對話中），做到不露痕跡。當需要回收舊伏筆時，必須營造出讓讀者「恍然大悟」的強烈戲劇衝擊。
4. **角色靈魂（Character Voice & Consistency）**：徹底吃透「角色聖經」。本章登場角色的遣詞造句、語氣習慣、行為邏輯必須與其設定高度統一。若有新角色登場，務必為其設計一個極具辨識度、令人過目不忘的「高光出場」。
5. **情緒與鉤子（Emotion & Cliffhanger）**：精準拿捏本章的情緒基調。在章節末尾，必須巧妙設置強烈的情緒鉤子或劇情懸念，製造「欲知後事如何」的強大牽引力，逼迫讀者立刻翻閱下一章。
6. **篇幅與完整度（Length & Completeness）**：輸出字數應控制在 1500~3000 中文字之間。嚴禁輸出任何大綱式的摘要或說明文字，你只能、也必須只輸出「純粹的小說正文散文」。
7. **指定文風（Stylistic Mastery）**：請嚴格採用以下寫作風格：{writing_style}

## 輸入上下文參考
寫作時，你將獲得並需綜合參考以下資訊：
- 世界觀設定
- 角色聖經（Character Bible）
- 本章精細小大綱（包含時間、事件、伏筆、角色調度）
- 前章正文（確保敘事語氣與情節的完美銜接）
"""

EDITOR_PROMPT = """你是一位具備鷹眼般洞察力的資深文學主編（Editor）。
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
| TOOL_CALL | 調用某個 agent 執行任務 | tool, params |
| CONTINUE | 繼續下一個階段（管道流水線） | target（下一階段名稱） |
| WAIT_USER | 暫停並等待用戶確認 | - |
| AUTO_REGENERATE | 重新生成當前階段內容 | target, params.hint（補充提示） |
| FINISH | 管道執行完畢 | - |

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
    Retrieves the latest state of the novel to be used as context in prompts.
    """
    wb = get_latest_worldbuilding(novel_id)
    worldbuilding_str = wb["content"] if wb else "No worldview defined yet."
    
    char = get_latest_characters(novel_id)
    characters_str = char["json_data"] if char else "No characters designed yet."
    
    plot = get_latest_plot_chapters(novel_id)
    plot_str = plot["outline_json"] if plot else "No plot chapters designed yet."
    
    chapters_list = get_all_chapters_latest(novel_id)
    written_chapters_summary = ""
    for c in chapters_list:
        content_preview = c["content"][:200] + "..." if len(c["content"]) > 200 else c["content"]
        written_chapters_summary += f"Chapter {c['chapter_index']}: {content_preview}\n\n"
        
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
        if "worldview" in parsed:
            # Format progressive character plan
            prog_plan = parsed.get("progressive_character_plan", {})
            if isinstance(prog_plan, dict):
                prog_text = "\n".join([f"- {k}: {v}" for k, v in prog_plan.items()])
            else:
                prog_text = str(prog_plan)
            
            # Format three act structure
            three_act = parsed.get("three_act_structure", {})
            act1 = three_act.get("act1_setup", three_act.get("act1", ""))
            act2 = three_act.get("act2_confrontation", three_act.get("act2", ""))
            act3 = three_act.get("act3_resolution", three_act.get("act3", ""))
            
            formatted_wb = (
                f"【核心主題】\n{parsed.get('theme', '')}\n\n"
                f"【核心衝突】\n{parsed.get('main_conflict', '')}\n\n"
                f"【世界觀設定】\n{parsed.get('worldview', '')}\n\n"
                f"【整體故事大綱】\n{parsed.get('macro_outline', '')}\n\n"
                f"【三幕式結構】\n"
                f"  第一幕（Setup）：{act1}\n"
                f"  第二幕（Confrontation）：{act2}\n"
                f"  第三幕（Resolution）：{act3}\n\n"
                f"【角色漸進規劃策略】\n{prog_text}\n\n"
                f"【伏筆種子】\n" + "\n".join([f"  • {s}" for s in parsed.get("foreshadowing_seeds", [])]) + "\n\n"
                f"【關鍵轉折點】\n" + "\n".join([f"  • {e}" for e in parsed.get("key_turning_points", parsed.get("key_events", []))])
            )
            save_worldbuilding(nid, formatted_wb)
            
    return run_agent_stream(novel_id, "architect", messages, save_callback)

def run_character_designer(novel_id, user_prompt=None):
    """
    Runs the Character Designer to generate/design character profiles based on worldview.
    """
    context = compile_context(novel_id)
    
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
        if "characters" in parsed:
            save_characters(nid, parsed)
            
    return run_agent_stream(novel_id, "character", messages, save_callback)

def run_plot_planner(novel_id, user_prompt=None):
    """
    Runs the Plot Planner to break the story worldview and character bible into chapters.
    """
    context = compile_context(novel_id)
    
    prompt_content = f"以下是已確立的世界觀與故事架構：\n{context['worldbuilding']}\n\n角色聖經（Character Bible）：\n{context['characters']}\n\n"
    if user_prompt:
        prompt_content += f"用戶對章節規劃的指示：\n{user_prompt}\n\n"
    prompt_content += "請將大綱拆分為詳細的章節小大綱，每章關聯時間、事件、伏筆、角色。嚴格以 JSON 格式輸出。"
    
    messages = [
        {"role": "system", "content": PLOT_PLANNER_PROMPT},
        {"role": "user", "content": prompt_content}
    ]
    
    def save_callback(nid, text):
        parsed = parse_json_safely(text)
        if "chapters" in parsed:
            save_plot_chapters(nid, parsed)
            
    return run_agent_stream(novel_id, "plot", messages, save_callback)

def run_chapter_writer(novel_id, chapter_index, custom_style="Swiss Modernism 2.0 (Elegant, polished, sensory, dramatic)"):
    """
    Runs the Chapter Writer to write the actual prose for the specified chapter index.
    """
    context = compile_context(novel_id)
    
    # Extract specific chapter details if we have plot chapter data
    plot_json = parse_json_safely(context["plot"])
    specified_chapter_outline = "No outline found for this chapter index."
    
    if "chapters" in plot_json:
        for ch in plot_json["chapters"]:
            if ch.get("chapter_index") == int(chapter_index):
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
    
    def save_callback(nid, text):
        save_chapter(nid, int(chapter_index), text)
        
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
    
    prompt_content = f"""【世界觀設定】
{context['worldbuilding']}

【角色設定】
{context['characters']}

【第 {chapter_index} 章 原始正文】
{ch_data['content']}
"""
    if edit_instructions:
        prompt_content += f"\n【用戶編輯指示】\n{edit_instructions}\n"
        
    prompt_content += f"\n請對第 {chapter_index} 章進行精修潤色。只輸出潤色後的完整正文。"
    
    messages = [
        {"role": "system", "content": EDITOR_PROMPT},
        {"role": "user", "content": prompt_content}
    ]
    
    def save_callback(nid, text):
        save_chapter(nid, int(chapter_index), text)
        
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
# Director 執行模式標記
DIRECTOR_EXECUTION_MODE = {"auto_execute": False}

def set_director_auto_execute(mode: bool):
    """設定 Director 是否為一鍵自動執行模式"""
    DIRECTOR_EXECUTION_MODE["auto_execute"] = mode

def get_director_auto_execute() -> bool:
    """獲取 Director 執行模式"""
    return DIRECTOR_EXECUTION_MODE.get("auto_execute", False)

def run_director_decision(novel_id, current_stage, user_prompt):
    """
    The Director (Copilot) evaluates the current pipeline stage and decides 
    whether to proceed to the next stage. This enables staged, supervised 
    generation rather than automatic full pipeline.
    
    Returns a streaming response with the director's decision and reasoning.
    When in AUTO-EXECUTE mode, the director will also trigger subsequent actions.
    """
    # Define stage evaluation prompts with enhanced auto-execution logic
    STAGE_EVALUATION_PROMPT = """你是 AI 小說創作系統的【創意總監】。

## 重要：執行模式識別
- 如果你處於「一鍵執行模式」（系統已自動呼叫你），你必須做出【果斷決策並付諸行動】
- 你的回應不僅是建議，而是【執行指令】
- 當你說「自動執行」「立即執行」「我將執行」時，系統會真正觸發後續操作

## 當前任務評估
你需要評估目前「{current_stage}」階段完成後的成果，判斷是否應該繼續執行下一階段。

## 當前已完成的工作成果
【世界觀】：{worldbuilding}
【角色 Bible】：{characters}
【章節大綱】：{plot}
【已寫作章節】：{written_chapters}

## 用戶原始創作需求
{user_prompt}

## 決策準則
1. **品質閘門（Quality Gate）**：評估當前階段輸出是否完整、連貫、符合創作需求
2. **邏輯一致性**：檢查各模組之間的設定是否相互矛盾
3. **進度合理性**：判斷是否應該繼續下一階段，還是應該返回修改

## 【關鍵】一鍵執行模式下的決策邏輯

當你發現問題需要「重跑」或「擴充」時，你必須：
1. 明確指出需要補充的內容
2. 在回應結尾添加【執行指令區塊】，格式如下：
```
【執行指令】
ACTION: AUTO_REGENERATE
TARGET: {current_stage}
HINT: {具體要補充的內容提示}
```

當輸出品質良好，可以繼續時：
```
【執行指令】
ACTION: CONTINUE
TARGET: {next_stage}
```

當需要用戶確認時：
```
【執行指令】
ACTION: WAIT_USER
REASON: {需要確認的原因}
```

## 回應格式（嚴格遵守）
```
【總監評估】
- 當前階段：「{current_stage}」完成品質：[優秀/良好/需要修改]
- 主要發現：[具體評估]

【總監建議】
- 是否繼續：[是/否，建議...]
- 理由：[具體理由]

【下一步行動】
- 建議：[繼續/重跑當前階段/暫停等待用戶指示]

【執行指令】
ACTION: [CONTINUE|AUTO_REGENERATE|WAIT_USER]
TARGET: [下一階段/當前階段]
HINT: [可選，針對重跑的補充提示]
```

## 重要提醒
- 請使用繁體中文回覆
- 評估要具體、務實，避免空泛的讚美
- 如果發現明顯問題，必須明確指出並建議修正
- 【在一鍵執行模式下，你的「建議」就是「執行令」】
"""

    context = compile_context(novel_id)
    
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
        user_prompt=user_prompt
    )
    
    messages = [
        {"role": "system", "content": "你是一位嚴謹的創意總監，負責把控小說創作的品質與邏輯一致性。你的風格是專業、直接、建設性反饋。"},
        {"role": "user", "content": prompt_content}
    ]
    
    return run_agent_stream(novel_id, "copilot", messages)

# --- RUNNER ENGINE ---
def run_agent_stream(novel_id, agent_name, messages, save_callback=None):
    """
    Main engine that handles streaming chunk processing and automatic DB saving.
    """
    accumulated_text = ""
    
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
            except:
                pass
                
    # Once yielding finishes, save the final output
    if save_callback and accumulated_text.strip():
        try:
            save_callback(novel_id, accumulated_text)
        except Exception as e:
            print(f"Error saving in agent callback: {e}")
            # Yield a final error warning (not strictly standard but helps debug)
            yield "data: " + json.dumps({
                "type": "error",
                "message": f"Database save failed: {str(e)}"
            }, ensure_ascii=False) + "\n\n"
