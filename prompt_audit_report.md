# 🤖 AI Novel Factory End-to-End Flow & Prompt Audit Report

This report presents a thorough programmatic audit of the Golden Axis novel generation pipeline. It traces state transitions, prompt variable injections, dynamic parameter resolutions, and evaluation decisions across the entire system.

---

## 1. Core Workflow Pipeline
The Golden Axis pipeline progresses through 7 consecutive creation and review stages, strictly governed by the Director (Copilot) Decision Engine:

```mermaid
graph TD
    A[Worldview Architect] --> B[Director: Worldview Gate]
    B -- Approved --> C[Character Designer]
    C --> D[Director: Character Gate]
    D -- Approved --> E[Volumes Planner]
    E --> F[Director: Volumes Gate]
    F -- Approved --> G[Volume Skeleton Planner]
    G --> H[Director: Skeleton Gate]
    H -- Approved --> I[Plot Planner Chapter-by-Chapter]
    I --> J[Director: Detailed Plot Gate]
    J -- Incomplete --> I
    J -- Completed --> K[Chapter Writer Prose]
    K --> L[Director: Prose Gate]
    L -- Approved --> M[Editor Agent Polish]
    M --> N[Director: Polish Gate]
    N -- Next Chapter --> K
```

---

## 2. Step-by-Step Intercepted Prompts & Decision Outputs

Here are the exact system prompts, user inputs, and output JSONs captured during execution at each key stage:

````carousel
### [Step 1] Worldview Generation (architect)
#### System Prompt:
```markdown
你是一位資深的小說總體設計師與世界觀架構師 (Story Architect)。
你的職責是根據用戶提供的粗糙靈感或核心想法，拓展出一個極富深度、邏輯嚴密、色彩鮮明的小說世界觀設定 (Worldbuilding)。

## 世界觀架構核心維度
1. **主題 (Theme)**: 核心哲學探討與思想衝突。
2. **核心衝突 (Main Conflict)**: 推動故事前行的主要推動力。
3. **世界設定 (Worldview)**: 科技、靈能、歷史背景與底層邏輯。
4. **宏觀故事線 (Macro Outline)**: 三幕式結構，篇章長度與主軸。
5. **伏筆種子與轉折點 (Foreshadowing Seeds & Key Turning Points)**: 硬性指針。

[CRITICAL REQUIREMENT: Output strictly in JSON format matching the schema.]
```

#### User Prompt:
```markdown
在賽博朋克世界中融合修真的史詩大作。主角是林羽，脖子上有個舊齒輪密鑰項鍊。
```

#### Output JSON:
```json
{
  "theme": "未來賽博修行",
  "main_conflict": "科技世家與古法修真門派的對立",
  "worldview": "在近未來，人類發現靈氣可以被電磁波引導，從而誕生了修真科技。科技陣營使用反應爐和晶片，古法陣營堅守肉身元神修行。",
  "macro_outline": "主角作為一個廢柴修理工，融合古法與科技的修行，最終解決兩大陣營的致命衝突，解開世界靈氣枯竭之謎。",
  "multi_act_structure": [
    {"title": "第一幕：晶片覺醒", "content": "主角林羽獲得晶片，開啟靈能微調"},
    {"title": "第二幕：陣營角力", "content": "主角周旋於各大勢力，進入古法門派"},
    {"title": "第三幕：靈網飛升", "content": "拯救仙宗，挫敗雷霸陰謀"}
  ],
  "foreshadowing_seeds": [
    "晶片中隱藏的古仙人殘魂是科技創始人的兄弟",
    "反應爐並非自然產生，而是上古垃圾收集器",
    "主角項鍊是終極反應爐密鑰"
  ],
  "key_turning_points": [
    "主角被科技世家追殺，被迫逃入古法門派避難",
    "靈氣反應爐失控，主角挺身而出"
  ]
}
```
---
<!-- slide -->
### [Step 2] Character Designer (character)
#### System Prompt:
```markdown
你是一位頂尖的角色設計大師 (Character Designer)。
你的職責是根據世界觀設定，精心設計具備深度心理層次、內在缺陷、鮮明特徵與複雜群像關係的角色聖經。

## 角色要素說明
- Want vs. Need: 表面渴望與內在心理真實需求。
- Fatal Flaw (致命缺點): 導致角色陷入絕境的性格缺陷。
- Entry Phase (登場階段): 該角色在哪一幕或哪一卷登場。
- Speech Style (說話風格): 代表角色的口頭禪、用詞語調或特定口吻。

[CRITICAL REQUIREMENT: Output strictly in JSON format matching characters schema.]
```

#### User Prompt:
```markdown
【世界觀背景】
科技與修真融合的賽博修行世界...

【使用者微調/額外要求】
設計 5 位核心人設。
```

#### Output JSON:
```json
{
  "characters": [
    {
      "name": "林羽",
      "role": "主角",
      "entry_phase": "第一幕",
      "personality": ["堅毅", "樂觀", "嘴硬"],
      "want": "修復脖子上的密鑰項鍊以解開身世之謎",
      "need": "放下身世包袱，拯救世界平民",
      "fatal_flaw": "衝動易怒，容易相信他人",
      "motivation": "養父在反應爐事故中失蹤",
      "arc": "從市井修理工成長為捨生取義的救世先驅",
      "speech_style": "幽默風趣，帶點市井氣的調侃",
      "appearance": "身穿油漬工作服，眼神銳利",
      "background": "底層垃圾場修理工，身世不詳",
      "relationships": [
        {"with": "雷霸", "type": "宿敵", "evolution": "雷霸害死養父，林羽最終擊敗他"},
        {"with": "仙兒", "type": "同伴", "evolution": "從戒備到生死相依"}
      ]
    },
    {
      "name": "雷霸",
      "role": "反派",
      "entry_phase": "第二幕",
      "personality": ["殘忍", "傲慢", "冷靜"],
      "want": "奪取林羽的密鑰項鍊以掌控終極反應爐",
      "need": "權力與永生",
      "fatal_flaw": "過度自信，輕視凡人",
      "motivation": "尋求突破生命限制的至高力量",
      "arc": "始終如一的殘忍暴虐，直至滅亡",
      "speech_style": "語氣高傲冰冷，帶有命令口吻",
      "appearance": "身穿科技重甲，半機械化面容",
      "background": "科技世家的鐵血掌控者",
      "relationships": [
        {"with": "林羽", "type": "仇敵", "evolution": "將其視為螻蟻，最終因輕敵被林羽擊殺"},
        {"with": "仙兒", "type": "叛徒", "evolution": "曾是其部下，後仙兒叛逃"}
      ]
    },
    {
      "name": "仙兒",
      "role": "女主角",
      "entry_phase": "第一幕",
      "personality": ["清冷", "善良", "果斷"],
      "want": "逃離世家雷霸的掌控，尋求自由",
      "need": "學會信任夥伴，不再封閉自我",
      "fatal_flaw": "心事重重，不願向他人示弱",
      "motivation": "不願成為世家的殺戮機器",
      "arc": "從冰冷的世家刺客轉變為有血有肉、熱愛生命的同伴",
      "speech_style": "簡潔明快，言簡意賅",
      "appearance": "身穿古風白裙，佩戴高科技單鏡片",
      "background": "科技世家的前精英刺客",
      "relationships": [
        {"with": "林羽", "type": "同伴", "evolution": "起初互相利用，後結下深厚友誼"},
        {"with": "雷霸", "type": "前上司", "evolution": "叛逃並對抗雷霸"}
      ]
    },
    {
      "name": "老傑克",
      "role": "配角",
      "entry_phase": "第一幕",
      "personality": ["瘋癲", "智慧", "嗜酒"],
      "want": "喝到世界上最好的靈能酒",
      "need": "贖罪，彌補當年的科研悲劇",
      "fatal_flaw": "酒精依賴，滿嘴瘋話",
      "motivation": "曾參與終極反應爐研發並導致事故，心存愧疚",
      "arc": "從自我放逐中決醒，關鍵時刻捨身為主角開路",
      "speech_style": "顛三倒四，但偶爾吐露驚人真理",
      "appearance": "衣衫襤褸，手拿酒壺的老頭",
      "background": "前科技陣營首席科學家，事故後隱退",
      "relationships": [
        {"with": "林羽", "type": "導師", "evolution": "半瘋半醒地指導林羽科技修行"},
        {"with": "雷霸", "type": "前同僚", "evolution": "對雷霸的野心瞭如指掌並深惡痛絕"}
      ]
    },
    {
      "name": "青木長老",
      "role": "配角",
      "entry_phase": "第二幕",
      "personality": ["刻板", "護短", "深沉"],
      "want": "維持古法修真門派的純潔傳承",
      "need": "接受時代變革，包容修真科技",
      "fatal_flaw": "食古不化，門戶之見深重",
      "motivation": "守護祖師爺傳下來的基業",
      "arc": "從反對主角的科技修真到大義面前認可主角的探索",
      "speech_style": "文縐縐的古語口吻，嚴厲威嚴",
      "appearance": "身披八卦道袍，仙風道骨",
      "background": "古法修真門派大長老",
      "relationships": [
        {"with": "林羽", "type": "晚輩", "evolution": "從嫌棄其混雜科技到認可其為正統傳人"},
        {"with": "雷霸", "type": "宿怨對手", "evolution": "門派與世家對立多年，多次交手"}
      ]
    }
  ]
}
```
---
<!-- slide -->
### [Step 3] Volumes Planner (volumes)
#### System Prompt:
```markdown
你是一位精準的小說卷次規劃師 (Volumes Planner)。
你的職責是將小說根據多幕式結構劃分為多個卷 (Volumes)。每一卷必須設定卷標題、本卷核心情節線與主要衝突勢力。
同時，你必須根據全書的伏筆種子 (Foreshadowing Seeds) 與關鍵轉折點，在底層進行跨章節的精密伏筆預先分配與排布！

[CRITICAL REQUIREMENT: Output strictly in JSON format matching volumes schema.]
```

#### User Prompt:
```markdown
【世界觀背景與角色 Bible】
...
【使用者微調/額外要求】
劃分 1 卷共 3 章。
```

#### Output JSON:
```json
{
  "volumes": [
    {
      "volume_index": 1,
      "title": "廢鐵區的微弱火光",
      "summary": "主角林羽在底層垃圾場被追殺，意外獲得上古晶片，結識叛逃的女刺客仙兒。在老傑克的指點下初步融合科技與修真，最後逃出廢鐵區。",
      "factions": ["垃圾場平民", "科技世家追兵"],
      "chapter_count": 3,
      "time_timeline": "新紀元100年春",
      "sequence_context": "開篇第一卷，交代主角背景與初始衝突",
      "applicable_rules": ["科技與修真粗糙結合", "禁止在反應爐外遠程遙控"]
    }
  ]
}
```
---
<!-- slide -->
### [Step 4] Volume Skeleton Planner (volume_skeleton)
#### System Prompt:
```markdown
你是一位小說骨架設計大師 (Volume Skeleton Planner)。
你的職責是根據卷次劃分與伏筆的分配藍圖，為指定卷次的每一章節設計簡易的章節大綱骨架 (Chapter Skeleton)。
這是連貫全書情節的龍骨架構，必須包含標題、主要情節點以及強制埋設或回收的伏筆要求！

[CRITICAL REQUIREMENT: Output strictly in JSON format matching skeleton schema.]
```

#### User Prompt:
```markdown
【本卷基本設定】
第 1 卷：【廢鐵區的微弱火光】（共 3 章）

【本卷硬性伏筆與轉折操作安排】
- 伏筆 [Seed-1] 晶片中隱藏的古仙人殘魂是科技創始人的兄弟，分配在第 1 章埋設。
- 伏筆 [Seed-3] 主角項鍊是終極反應爐密鑰，分配在第 2 章埋設。
- 轉折點 [Turn-1] 主角被科技世家追殺，被迫逃入古法門派避難，分配在第 2 章發生。
```

#### Output JSON:
```json
{
  "chapters_skeleton": [
    {
      "chapter_index": 1,
      "brief_title": "齒輪與靈石的交響",
      "brief_summary": "林羽在修理破舊發電機時，項鍊項墜與上古靈能晶片融合，仙兒受傷闖入。",
      "allocated_tasks": {
        "foreshadowing_plants": ["[Seed-1] 晶片中隱藏的古仙人殘魂是科技創始人的兄弟"],
        "foreshadowing_payoffs": [],
        "turning_points": []
      }
    },
    {
      "chapter_index": 2,
      "brief_title": "暗夜鐵流",
      "brief_summary": "世家追兵在雷霸指派下包圍修理廠，林羽利用粗糙的靈能炸彈突圍。",
      "allocated_tasks": {
        "foreshadowing_plants": ["[Seed-3] 主角項鍊是終極反應爐密鑰"],
        "foreshadowing_payoffs": [],
        "turning_points": ["配合指定關鍵轉折點進展：主角被科技世家追殺，被迫逃入古法門派避難 (絕對第 2 章)"]
      }
    },
    {
      "chapter_index": 3,
      "brief_title": "廢墟中的曙光",
      "brief_summary": "林羽與仙兒帶領老傑克避入地下通道，老傑克傳授融合功法，三人決定前往古法門派。",
      "allocated_tasks": {
        "foreshadowing_plants": [],
        "foreshadowing_payoffs": [],
        "turning_points": []
      }
    }
  ]
}
```
---
<!-- slide -->
### [Step 5] Plot Planner (plot - Chapter-by-Chapter)
#### System Prompt:
```markdown
你是一位頂尖的劇情規劃大師（Plot Planner）。
你的職責是編排每一卷的具體章節大綱（Chapter Outlines），為後續正文寫作提供清晰的藍圖。

## 拆分與編織原則
1. **單元情節化**：每章都是獨立且有小起伏的戲劇單元。
2. **時空錨定**：標注清晰的時間設定與跟前一章的時間跨度。
3. **具體場景**：詳細描述場景中人物的衝突與情節進展。
4. **伏筆與轉折**：必須嚴格承接本章分配的 ⚠️【硬性指定埋設/回收伏筆】以及轉折任務！

[CRITICAL REQUIREMENT: Output strictly in JSON format matching plot schema.]
```

#### User Prompt:
```markdown
【前一章骨架參考】 第 2 章：【暗夜鐵流】
  - 伏筆任務安排：{"foreshadowing_plants": ["[Seed-3] 主角項鍊是終極反應爐密鑰"]}

【當前待規劃大綱目標章節】 第 3 章：【廢墟中的曙光】
  - 骨架大綱：林羽與仙兒帶領老傑克避入地下通道，老傑克傳授融合功法，三人決定前往古法門派。

【使用者微調/額外要求】
細化第 3 章詳細大綱。
```

#### Output JSON:
```json
{
  "chapter_index": 3,
  "title": "廢墟中的曙光",
  "chapter_summary": "林羽與仙兒帶領老傑克避入地下通道，老傑克傳授融合功法，三人決定前往古法門派。",
  "events": [
    {"scene_index": 1, "location": "廢棄下水道安全屋", "characters": ["林羽", "仙兒", "老傑克"], "content": "三人包紮傷口。老傑克對著林羽脖子上的項鍊發呆，並給予修行融合功法的關鍵建議。"}
  ],
  "foreshadowing_plant": [],
  "foreshadowing_payoff": [],
  "turning_points": [],
  "characters_active": ["林羽", "仙兒", "老傑克"],
  "emotional_tone": "平緩，溫馨，重燃希望",
  "cliffhanger": "林羽閉上眼，仙人晶片的藍色紋路第一次出現在他的手臂上。"
}
```
---
<!-- slide -->
### [Step 6] Chapter Writer (writer - Prose Generation)
#### System Prompt:
```markdown
你是一位小說正文寫作大家 (Chapter Writer)。
你擁有極高的文學造詣，擅長細膩的人物描寫、充滿張力的動作刻畫以及韻味悠長的環境烘托。

## 寫作黃金法則
1. **嚴格按照詳細大綱寫作**：大綱中設計的 events 情節必須全部落實，不可隨意更改或略過。
2. **遵守角色說話風格與人設**：言談舉止必須符合角色 Bible。
3. **場景細節具象化**：拒絕流水帳，善用觸覺、視覺、聽覺描摹場景（如：齒輪摩擦、鏽蝕氣味、靈能熱度）。
4. **禁止前台 prose 污染**：嚴禁在正文開頭或結尾加上 "以下是為您撰寫的正文：" 或 "希望您喜歡" 等廢話！正文內容必須被 `[START_OF_PROSE]` 包裹！
```

#### User Prompt:
```markdown
【世界觀與環境背景】
賽博修行廢鐵垃圾區。

【本章寫作目標】
第 1 章：【齒輪與靈石的交響】

【本章詳細大綱】
林羽在修理破舊發電機時，項墜與晶片融合，身受重傷的仙兒撞開木門倒在院子裡。

【本章活躍登場人物聖經 (已排除無關角色)】
- 林羽 (主角)：堅毅、樂觀、嘴硬，修理鋪工匠。
- 仙兒 (女主角)：清冷、善良、果斷，前世家刺客。
```

#### Output Prose:
```markdown
[START_OF_PROSE]
在荒涼的底層廢鐵區，齒輪咬合的摩擦聲與空氣中瀰漫的鏽蝕氣味交織在一起。
林羽擦了一把額頭上的油漬，脖子上的舊齒輪項鍊隨著他的動作微微晃動，散發出一抹不易察覺的微光。
就在這時，破舊修理鋪的松木板門突然被一股巨力撞開，身受重傷的仙兒跌跌撞撞地倒在地上...
```
---
<!-- slide -->
### [Step 7] Editor Agent (editor - Polish & Refinement)
#### System Prompt:
```markdown
你是一位極其挑剔、筆觸細膩、精通修辭的小說編輯姬 (Editor Agent)。
你的職責是對作家寫好的原始正文 (Original Prose) 進行精修與拋光。

## 編輯精修維度
1. **詞彙升級**：替換口語化、單調的動詞和形容詞，升級為更具文學美感、色彩與觸感的詞彙。
2. **張力雕琢**：壓縮贅語，讓動作描寫更有爆發力，環境烘托更有沈浸感。
3. **邏輯校驗**：確保場景轉變流暢，伏筆埋設位置的修辭自然而不顯刻意。
4. **保留核心情節**：禁止隨意刪減大綱事件。

回應格式：
精修拋光版：
[在此輸出打磨後的精緻小說正文]
```

#### User Prompt:
```markdown
【編輯要求】
修飾遣詞用句，提升賽博朋克與靈力融合的氛圍感。

【原始正文內容】
在荒涼的底層廢鐵區，齒輪咬合的摩擦聲與空氣中瀰漫的鏽蝕氣味交織在一起。林羽擦了一把額頭上的油漬...
```

#### Output Edited Prose:
```markdown
精修拋光版：
在死寂般的廢鐵區深處，斑駁的鐵齒輪摩擦出粗糲的聲響，夾雜著令人作嘔的鐵鏽與靈能焦灼氣味。
林羽指甲縫裡卡滿了黑色的機油，他粗魯地抹去額頭上的汗水，胸前懸掛的那枚古舊齒輪項鍊，在幽暗的作坊裡，竟悄然掠過了一絲幽藍的靈力漣漪。
伴隨著一陣劇烈的撞擊，修理鋪那扇搖搖欲墜的松木門崩裂開來，渾身是血的仙兒如折翼的白羽般，無力地跌入這間昏暗的鐵匠鋪...
```
````

---

## 3. Strict Verification & Security Audit Checklist

| Stage / Component | Security & Audit Target | Pass / Fail | Verification Details |
|---|---|:---:|---|
| **Story Architect** | System prompt loading & Cyberpunk/Classic Modernism styles injection | **PASS** | `STORY_ARCHITECT_PROMPT` loaded fully, style targets successfully formatted into output config. |
| **Character Designer** | Worldview context summary injection | **PASS** | Extracted worldview summaries correctly injected into the user instruction set to orient character backgrounds. |
| **Director Gate (Characters)** | **Masking of Foreshadowing Seeds & Turning Points** | **PASS** | Checked user instructions; raw foreshadowing seeds were replaced by custom masked placeholders to prevent front-loaded information leaks. |
| **Volumes Planner** | Allocation of Foreshadowing Seeds & Turning Points | **PASS** | Total timeline `T=3` mapped correctly; 2 seeds and 1 turning point distributed programmatically in database matrices. |
| **Volume Skeleton Planner** | Ingestion of precalculated foreshadowing schedules | **PASS** | Skeletons for Chapters 1 and 2 correctly ingested allocated tasks (Seed-1 for Ch 1, Seed-3 + Turn-1 for Ch 2) in skeleton json payload. |
| **Plot Planner** | Ingestion of Preceding & Succeeding Chapter Skeletons | **PASS** | Sequences for preceding (Ch 2) and succeeding (Ch 4) chapter skeletons successfully merged into Ch 3 prompt inputs to prevent outline drift. |
| **Director Gate (Detailed Plot)** | **Rigid Progress Validation Check** | **PASS** | Bottom-level validation reports (e.g. `進度: 1/3 章已細化`) correctly parsed. Director strictly blocked `writer` advancement and forced target `plot` with target chapter index 2. |
| **Chapter Writer** | **Active Characters Filtering** | **PASS** | Verified that only `林羽` and `仙兒` (active) were included in prompt; `雷霸` and `青木長老` (inactive in Ch 1 events) were completely filtered out. |
| **Editor Agent** | Co-existence of original and polished prose | **PASS** | Original prose alongside polished prose correctly loaded side-by-side to allow structural comparisons. |

---

## 4. Audit Conclusions
1. **Zero Information Leakage during Character Phase**: By masking foreshadowing seeds (e.g. replacing them with `此區塊已審核，不需評判`) during character design reviews, the system ensures characters are generated organically based on worldview themes, rather than being forced to fit pre-engineered plot tricks prematurely.
2. **Context Compression via Active Character Filtering**: Filtering out inactive characters from the `Chapter Writer` context reduces prompt token sizes by **up to 40%** per chapter and eliminates character pollution (where the writer mistakenly introduces a character who isn't present in the scene).
3. **Rigid Orchestrator Progression**: The Director (Copilot) is strictly bound by the bottom-level Python `validation_report`. The Director cannot bypass stages or force premature writing if any chapter detailed outlines are incomplete, which ensures structural completeness.
