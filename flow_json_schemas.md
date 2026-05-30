# AI 小說工廠流程 JSON 資料格式規範

本文檔定義 AI_Novel_Factory 系統中各個流程（Agent）產生或使用的資料 JSON 結構，可直接引用。

---

## 目錄

1. [worldview](#1-worldview-世界觀架構師-story-architect-agent) - 世界觀架構師
2. [characters](#2-characters-角色設計師-character-designer-agent) - 角色設計師
3. [volumes](#3-volumes-篇卷規劃師-volumes-planner-agent) - 篇卷規劃師
4. [volume_skeleton](#4-volume_skeleton-篇卷骨架規劃師-volume-skeleton-planner) - 篇卷骨架規劃師
5. [foreshadowing_orchestration](#5-foreshadowing_orchestration-伏筆編織導演-foreshadowing-orchestrator) - 伏筆編織導演
6. [plot](#6-plot-大綱規劃師-plot-planner-agent) - 大綱規劃師
7. [writer](#7-writer-正文寫作作家-chapter-writer-agent) - 正文寫作作家
8. [editor](#8-editor-編輯姬-editor-agent) - 編輯姬

---

## 1. worldview (世界觀架構師 Story Architect Agent)

**資料表**: `worldbuilding`  
**用途**: 使用者要更新、新增或重新生成世界觀設定或多幕式結構等。

### 完整 JSON 結構

```json
{
  "theme": "核心主題描述",
  "main_conflict": "核心衝突描述",
  "worldview": "世界觀設定詳細內容",
  "macro_outline": "整體故事大綱",
  "multi_act_structure": [
    {
      "title": "第一幕 (Setup)",
      "content": "第一幕內容描述"
    },
    {
      "title": "第二幕 (Confrontation)",
      "content": "第二幕內容描述"
    },
    {
      "title": "第三幕 (Resolution)",
      "content": "第三幕內容描述"
    }
  ],
  "progressive_character_plan": [
    {
      "title": "第一波開篇 (Wave 1)",
      "content": "第一波角色規劃內容"
    },
    {
      "title": "第二波發展 (Wave 2)",
      "content": "第二波角色規劃內容"
    },
    {
      "title": "第三波高潮 (Wave 3)",
      "content": "第三波角色規劃內容"
    }
  ],
  "foreshadowing_seeds": [
    "伏筆種子1描述",
    "伏筆種子2描述"
  ],
  "key_turning_points": [
    "關鍵轉折點1描述",
    "關鍵轉折點2描述"
  ]
}
```

### 欄位說明

| 欄位 | 類型 | 說明 |
|------|------|------|
| `theme` | string | 核心主題，描述小說的中心思想和主旨 |
| `main_conflict` | string | 核心衝突，描述主要矛盾和衝突點 |
| `worldview` | string | 世界觀設定，包含世界規則、背景等 |
| `macro_outline` | string | 整體故事大綱，宏觀敘述故事走向 |
| `multi_act_structure` | array | 多幕式結構，三幕式戲劇結構定義 |
| `progressive_character_plan` | array | 角色漸進規劃，分階段的角色發展策略 |
| `foreshadowing_seeds` | array | 伏筆種子，預埋的伏筆列表 |
| `key_turning_points` | array | 關鍵轉折點，故事的重要轉折節點 |

---

## 2. characters (角色設計師 Character Designer Agent)

**資料表**: `characters`  
**用途**: 使用者要新增、修改、擴充或重新生成角色聖經/角色卡。

### 完整 JSON 結構

```json
{
  "characters": [
    {
      "name": "角色名稱",
      "role": "主角/配角/反派/導師/工具人等",
      "entry_phase": "登場階段描述",
      "personality": ["性格特質1", "性格特質2"],
      "want": "角色慾望/目標",
      "need": "角色真正需要",
      "fatal_flaw": "致命缺陷/弱點",
      "motivation": "行為動機",
      "arc": "角色弧線/成長軌跡",
      "speech_style": "說話風格描述",
      "appearance": "外貌描述",
      "background": "背景故事",
      "relationships": [
        {
          "with": "關聯角色名稱",
          "type": "關係類型",
          "evolution": "關係演變"
        }
      ]
    }
  ]
}
```

### 欄位說明

| 欄位 | 類型 | 說明 |
|------|------|------|
| `name` | string | 角色名稱（必填，不可為空或佔位符） |
| `role` | string | 角色定位（主角、配角、反派、導師等） |
| `entry_phase` | string | 登場階段/時期 |
| `personality` | array | 性格特質列表 |
| `want` | string | 角色表面上的慾望/目標 |
| `need` | string | 角色真正內在需要 |
| `fatal_flaw` | string | 致命缺陷/弱點 |
| `motivation` | string | 行為動機 |
| `arc` | string | 角色弧線/成長軌跡 |
| `speech_style` | string | 說話風格描述 |
| `appearance` | string | 外貌特徵描述 |
| `background` | string | 背景故事 |
| `relationships` | array | 與其他角色的關係列表 |

---

## 3. volumes (篇卷規劃師 Volumes Planner Agent)

**資料表**: `volumes`  
**用途**: 使用者要重新規劃、切分篇卷或篇卷概要。

### 完整 JSON 結構（volumes_list）

```json
[
  {
    "volume_index": 1,
    "title": "第一卷標題",
    "summary": "本卷概要描述",
    "factions": ["勢力1", "勢力2"],
    "chapter_count": 50,
    "time_timeline": "時間線描述",
    "sequence_context": "序列上下文",
    "applicable_rules": ["法則1", "法則2"]
  },
  {
    "volume_index": 2,
    "title": "第二卷標題",
    "summary": "本卷概要描述",
    "factions": ["勢力3"],
    "chapter_count": 50,
    "time_timeline": "時間線描述",
    "sequence_context": "序列上下文",
    "applicable_rules": ["法則3"]
  }
]
```

### 欄位說明

| 欄位 | 類型 | 說明 |
|------|------|------|
| `volume_index` | integer | 篇卷序號（1-indexed） |
| `title` | string | 篇卷標題 |
| `summary` | string | 篇卷概要/摘要 |
| `factions` | array/string | 涉及勢力/陣營列表（可為 JSON 字串） |
| `chapter_count` | integer | 本卷章節數（預設 50） |
| `time_timeline` | string | 時間線描述 |
| `sequence_context` | string | 序列上下文/前置條件 |
| `applicable_rules` | array/string | 適用法則列表（可為 JSON 字串） |

### 資料庫欄位對應

| 資料庫欄位 | 說明 |
|------------|------|
| `novel_id` | 小說 ID |
| `volume_index` | 篇卷序號 |
| `title` | 篇卷標題 |
| `summary` | 篇卷概要 |
| `factions` | 勢力 JSON |
| `is_dirty` | 是否需要重新生成（0/1） |
| `chapter_count` | 章節數 |
| `time_timeline` | 時間線 |
| `sequence_context` | 序列上下文 |
| `applicable_rules` | 適用法則 JSON |

---

## 4. volume_skeleton (篇卷骨架規劃師 Volume Skeleton Planner)

**資料表**: `volumes.chapters_outline`  
**用途**: 使用者要重新拆解簡易章節骨架。

### 完整 JSON 結構（chapters_skeleton）

```json
[
  {
    "chapter_index": 1,
    "chapter_title": "第一章標題",
    "chapter_summary": "章節簡要摘要"
  },
  {
    "chapter_index": 2,
    "chapter_title": "第二章標題",
    "chapter_summary": "章節簡要摘要"
  }
]
```

### 欄位說明

| 欄位 | 類型 | 說明 |
|------|------|------|
| `chapter_index` | integer | 章節序號（1-indexed） |
| `chapter_title` | string | 章節標題/名稱 |
| `chapter_summary` | string | 章節簡要摘要（不超過50字） |

### 進階結構（含伏筆編織後）

```json
[
  {
    "chapter_index": 1,
    "chapter_title": "第一章標題",
    "chapter_summary": "章節簡要摘要",
    "volume_index": 1,
    "volume_title": "第一卷標題",
    "allocated_tasks": {
      "foreshadowing_plants": ["伏筆描述1"],
      "foreshadowing_payoffs": [],
      "turning_points": []
    }
  }
]
```
---

## 5. plot (大綱規劃師 Plot Planner Agent)

**資料表**: `plot_chapters`  
**用途**: 使用者要展開或更新詳細的章節情節大綱。

### 完整 JSON 結構

```json
{
  "chapters": [
    {
      "chapter_index": 1,
      "chapter_title": "第一章標題",
      "chapter_summary": "詳細章節摘要",
      "scenes": [
        {
          "scene_index": 1,
          "location": "場景地點",
          "characters": ["角色1", "角色2"],
          "content": "場景詳細描述"
        }
      ],
      "allocated_tasks": {
        "foreshadowing_plants": ["伏筆1"],
        "foreshadowing_payoffs": ["伏筆回收1"],
        "turning_points": ["轉折點1"]
      }
    }
  ]
}
```

### 欄位說明

| 欄位 | 類型 | 說明 |
|------|------|------|
| `chapter_index` | integer | 章節序號（1-indexed） |
| `chapter_title` | string | 章節標題 |
| `chapter_summary` | string | 章節詳細摘要 |
| `scenes` | array | 場景列表（可選） |
| `allocated_tasks` | object | 分配的伏筆任務 |

### 章節摘要結構（可接受的變體）

```json
{
  "chapter_index": 1,
  "brief_title": "簡要標題",
  "brief_summary": "簡要摘要",
  "allocated_tasks": {}
}
```

---

## 6. writer (正文寫作作家 Chapter Writer Agent)

**資料表**: `chapters`  
**用途**: 使用者要開始撰寫特定章節的正文。

### 輸入結構（從 plot_chapters 讀取）

```json
{
  "chapter_index": 1,
  "chapter_title": "第一章標題",
  "chapter_summary": "章節摘要",
  "scenes": [...],
  "allocated_tasks": {
    "foreshadowing_plants": [...],
    "foreshadowing_payoffs": [...],
    "turning_points": [...]
  }
}
```

### 輸出結構（保存到 chapters 表）

```json
{
  "novel_id": "小說ID",
  "chapter_index": 1,
  "content": "正文內容（完整章節文字）",
  "synopsis": "章節概要/梗概（可選）",
  "thinking": "思考過程（可選）"
}
```

### 欄位說明

| 欄位 | 類型 | 說明 |
|------|------|------|
| `novel_id` | string | 小說 ID |
| `chapter_index` | integer | 章節序號 |
| `content` | string | 正文內容（完整章節） |
| `synopsis` | string | 章節概要/梗概 |
| `thinking` | string | AI 思考過程 |

---

## 7. editor (編輯姬 Editor Agent)

**資料表**: `chapters`  
**用途**: 使用者要對已寫好的某章正文進行潤色、精修、拋光或修改。

### 輸入結構

```json
{
  "novel_id": "小說ID",
  "chapter_index": 1,
  "content": "原始正文內容",
  "synopsis": "章節概要"
}
```

### 輸出結構（更新到 chapters 表）

```json
{
  "novel_id": "小說ID",
  "chapter_index": 1,
  "content": "潤色後的正文內容",
  "synopsis": "更新後的章節概要"
}
```

### 欄位說明

| 欄位 | 類型 | 說明 |
|------|------|------|
| `novel_id` | string | 小說 ID |
| `chapter_index` | integer | 章節序號 |
| `content` | string | 潤色後的正文內容 |
| `synopsis` | string | 更新後的章節概要 |

---

## 附錄：資料表對應關係

| 流程 | 資料表 | 主要欄位 | 版本控制 |
|------|--------|----------|----------|
| worldview | `worldbuilding` | `content` (JSON) | ✅ 是 |
| characters | `characters` | `json_data` (JSON) | ✅ 是 |
| volumes | `volumes` | 各欄位 | ❌ 否 |
| volume_skeleton | `volumes` | `chapters_outline` | ❌ 否 |
| foreshadowing_orchestration | `volumes.chapters_outline` | `allocated_tasks` | ❌ 否 |
| plot | `plot_chapters` | `outline_json` (JSON) | ✅ 是 |
| writer | `chapters` | `content`, `synopsis` | ✅ 是 |
| editor | `chapters` | `content`, `synopsis` | ✅ 是 |

---

## 附錄：伏筆編織任務結構（allocated_tasks）

```json
{
  "foreshadowing_plants": [
    "埋下的伏筆1描述",
    "埋下的伏筆2描述"
  ],
  "foreshadowing_payoffs": [
    "回收的伏筆1描述"
  ],
  "turning_points": [
    "轉折點1描述"
  ]
}
```

---

*基於 `db.py` 程式碼分析*