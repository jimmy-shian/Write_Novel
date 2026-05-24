# 🧠 AI Novel Factory - 智能小說創作工廠指南

歡迎來到 **AI Novel Factory (天衍小說創作工廠)**！這是一個專門為小說家、編劇和創意工作者打造的 **多智能體協同創作系統 (Multi-Agent Collaborative System)**。

系統整合了 **NVIDIA 推薦的頂尖大語言模型預設**（包含 120B 思考推理模型、119B 高推理模型等），並透過精緻的 Web 介面與 SQLite 資料庫，為您提供無縫的「靈感 ➡️ 世界觀 ➡️ 角色設計 ➡️ 大綱章節 ➡️ 內文寫作 ➡️ 精細編輯」全鏈路自動化寫作體驗。

---

## 🤖 1. 核心 AI 協同智能體 (Agents) 介紹

本系統由 **5 位專門領域的 AI 專家** 與 **1 位協同創作總監** 組成，每個 Agent 均擁有獨特的系統提示詞 (System Prompt) 與寫作目標：

| 智能體名稱 | 核心角色定位 (Role) | 工作職責與特色 |
| | :--- | :--- |
| **Story Architect**<br>故事結構架構師 | 🗺️ 世界觀構建大師 | 負責規劃小說的**世界觀底層設定**、勢力範圍、力量體系、歷史脈絡與核心衝突。它會將您的零散靈感轉化為架構嚴密的世界觀設定集。 |
| | | **推薦模型**：nvidia/nemotron-3-super-120b-a12b、openai/gpt-oss-120b<br>**推薦溫度**：0.3 - 0.4（需要精準、架構性輸出） |
| **Character Designer**<br>角色設計大師 | 👥 靈魂人物雕刻家 | 根據世界觀背景，精細化雕琢小說中所有核心角色。包含設計角色的名稱、身份、**性格標籤 (Personality)**、**致命缺陷 (Flaws)**、**核心動機 (Motivation)** 與**人物成長弧線 (Arc)**，並輸出成嚴格的 JSON 視覺卡片。 |
| | | **推薦模型**：mistralai/mistral-small-4-119b-2603、qwen/qwen3.5-122b-a10b<br>**推薦溫度**：0.4 - 0.5（需要創意但結構化的人物描寫） |
| **Plot Planner**<br>章節劇情規劃師 | ⏳ 黃金分割大綱師 | 將世界觀與角色動機完美融合，自動將整本小說拆分為結構合理的**章節劇情大綱**。設計每一章的標題、核心情節事件、**寫作目的 (Purpose)**、**伏筆與鋪墊 (Foreshadowing)** 與**情緒基調 (Tone)**。 |
| | | **推薦模型**：openai/gpt-oss-120b、nvidia/nemotron-3-super-120b-a12b<br>**推薦溫度**：0.3 - 0.4（邏輯嚴謹的大綱拆解） |
| **Chapter Writer**<br>小說正文寫作作家 | ✍️ 文字具象魔術師 | 根據當前選中章節的大綱事件、世界觀設定與人物 Bible，進行極具文學張力的**正文 Prose 創作**。支援 **NVIDIA 120B 思考模型 (Nemotron)**，可在正文撰寫前進行深度的推理思考，讓情節銜接與人物對白更符合人性與張力。 |
| | | **推薦模型**：nvidia/nemotron-3-super-120b-a12b、minimaxai/minimax-m2.7、mistralai/mistral-small-4-119b-2603<br>**推薦溫度**：0.6 - 0.7（創意寫作需要高隨機性） |
| **Editor Agent**<br>精緻文風編輯 | 🔍 文字拋光雕刻師 | 對已撰寫的章節正文進行**微調、精修與文筆潤色**。您可以給予它特定的精修指令（如：「加強打鬥動作的緊湊感」、「讓環境氣氛顯得更肅殺寂靜」、「使對話更加綿裡藏針」），它會針對文字細節進行二次加工。 |
| | | **推薦模型**：google/gemma-3n-e4b-it、stepfun-ai/step-3.5-flash<br>**推薦溫度**：0.2 - 0.3（精準的文字微調，需要低隨機性） |
| **Co-pilot Director**<br>AI 總監 Copilot | 💬 隨身智囊 & 導演 | 常駐於右側側邊欄的 AI 對談小助手。它共享當前小說的 SQLite 記憶庫，能夠隨時與您針對特定情節進行腦力激盪、解答創作瓶頸，或提供角色命運的全新點子。 |
| | | **推薦模型**：nvidia/nemotron-3-super-120b-a12b、stepfun-ai/step-3.5-flash<br>**推薦溫度**：0.5 - 0.6（創意建議與互動對話） |

### 每個 Agent 的專屬模型配置（從 .env 讀取）

| Agent | 預設模型 | 說明 | 預設溫度 | Top P | Max Tokens | 深度思考 |
| | :--- | :--- | :---: | :---: | :---: | :---: |
| **Global** | google/gemma-3n-e4b-it | 全域預設模型（Router / Fallback） | 0.70 | 0.95 | 4096 | ✅ |
| **Story Architect** | qwen/qwen3.5-122b-a10b | Planner / Architect，結構設計與任務拆解 | 0.30 | 0.95 | 8192 | ✅ |
| **Character Designer** | openai/gpt-oss-120b | 創意但結構化的人物描寫（使用 MODEL_STORY） | 0.45 | 0.95 | 8192 | ✅ |
| **Plot Planner** | qwen/qwen3.5-122b-a10b | 邏輯嚴謹的大綱拆解（使用 MODEL_CRITIC） | 0.35 | 0.95 | 8192 | ✅ |
| **Chapter Writer** | nvidia/nemotron-3-super-120b-a12b | Main Writer，高品質內容生成核心 | 0.65 | 0.95 | 16384 | ✅ |
| **Editor Agent** | mistralai/mistral-small-4-119b-2603 | 精準的文字微調潤稿 | 0.25 | 0.90 | 8192 | ❌ |
| **Co-pilot** | stepfun-ai/step-3.5-flash | 快速創意建議與互動對話 | 0.55 | 0.95 | 4096 | ❌ |

### 為何各 Agent 需要不同的溫度設定？

| Agent | 溫度原則 | 原因 |
| | :--- | :--- |
| **架構師 / 規劃師** | 低 (0.3-0.35) | 需要精準、架構性輸出，避免過度發散 |
| **角色設計師** | 中低 (0.45) | 需要創意的人物描寫，但要有結構 |
| **正文寫作** | 中高 (0.6-0.65) | 創意寫作需要高隨機性，產生豐富多樣的文學表達 |
| **編輯師** | 極低 (0.25) | 精準的文字微調，需要低隨機性避免偏離原文 |
| **Copilot** | 中 (0.55) | 創意建議與互動對話，需要平衡創意與連貫性 |
| **全域預設** | 高 (0.70) | 作為 Fallback，預設較高溫度適合探索 |

---

## 🚀 2. 環境設定 (.env)

所有 API Key 和模型設定都集中管理在專案根目錄的 `.env` 檔案中。

### ⚠️ 重要：請勿將 .env 提交至版本控制

`.env` 檔案已自動加入 `.gitignore`，不會被 Git 追蹤。

### 首次設定步驟

1. 複製 `.env.example` 為 `.env`（若存在範本檔案）
2. 填入您的 NVIDIA API Key
3. 確認模型設定符合您的需求

### .env 檔案結構

```env
# --- Agent API Keys (NVIDIA API Keys) ---
NVIDIA_API_KEY_GLOBAL="nvapi-xxx"
NVIDIA_API_KEY_ARCHITECT="nvapi-xxx"
NVIDIA_API_KEY_CHARACTER="nvapi-xxx"
NVIDIA_API_KEY_PLOT="nvapi-xxx"
NVIDIA_API_KEY_WRITER="nvapi-xxx"
NVIDIA_API_KEY_EDITOR="nvapi-xxx"
NVIDIA_API_KEY_COPILOT="nvapi-xxx"

# --- Agent Default Models (與前端 Agent 對應) ---
# 前端 Agent: global, architect, character, plot, writer, editor, copilot
# character Agent 會使用 MODEL_CHARACTER，若不存在則用 MODEL_STORY
# plot Agent 會使用 MODEL_PLOT，若不存在則用 MODEL_CRITIC
MODEL_GLOBAL="google/gemma-3n-e4b-it"
MODEL_ARCHITECT="qwen/qwen3.5-122b-a10b"
MODEL_STORY="openai/gpt-oss-120b"        # Character Designer 備援
MODEL_WRITER="nvidia/nemotron-3-super-120b-a12b"
MODEL_EDITOR="mistralai/mistral-small-4-119b-2603"
MODEL_CRITIC="qwen/qwen3.5-122b-a10b"    # Plot Planner 備援
MODEL_COPILOT="stepfun-ai/step-3.5-flash"

# --- Global Defaults ---
DEFAULT_BASE_URL="https://integrate.api.nvidia.com/v1"
DEFAULT_TEMPERATURE=0.7
DEFAULT_TOP_P=0.95
DEFAULT_MAX_TOKENS=4096
DEFAULT_ENABLE_THINKING=1
```

### 設定優先順序

系統讀取設定的優先順序為：
1. **資料庫設定**（您在前端設定頁面儲存的個人化設定）
2. **.env 預設值**（本專案預設的 API Key 和模型）
3. **內建備援值**（當 .env 缺少時的 fallback）

---

## 🎬 3. 小說創作完整流程

本系統提供 **四階段漸進式大綱生成策略**，從靈感到正文寫作的自動化管線：

### Stage 0：創意啟動

在右側 **Copilot 總監側邊欄** 輸入您的創作想法或需求，系統會：
1. 分析並理解您的創作方向
2. 根據現有小說狀態評估下一步
3. 給出創作決策建議

### Stage 1：前期準備（Worldview → Characters）

| 階段 | 負責 Agent | 輸出內容 |
|------|------------|----------|
| 世界觀生成 | Story Architect | 核心主題、衝突設定、力量體系、歷史脈絡 |
| 角色設計 | Character Designer | 角色 Bible（JSON 格式）、性格/缺陷/動機/成長弧線 |

### Stage 2：宏觀骨架生成（Volume Skeleton）

自動遍歷所有卷生成章節骨架，包含：
- **卷結構定義**：每卷的標題、摘要、勢力範圍、章節數量
- **時間軸設定**：卷內的時間線與序列上下文
- **適用法則**：本卷特有的世界觀規則

### Stage 3：伏筆編織對齊（Foreshadowing Orchestration）

全局伏筆編織整合：
- 分析並對齊所有卷的伏筆播種
- 確保伏筆與情節發展的一致性
- 記錄伏筆鋪墊與回收節點

### Stage 4：微觀大綱展開（Plot Expansion）

滾動式生成詳細章節大綱：
- 每批 5 章遞進生成
- 包含標題、目的摘要、情節事件、微觀細節
- 支援增量和修補式更新

### Stage 5：正文寫作（Chapter Writing）

根據大綱撰寫正文：
- 支援深度思考模型（120B Nemotron）
- 可視化思考過程展示
- 自動保存版本歷史

### Stage 6：精緻編輯（Editing）

對已撰寫的正文進行微調：
- 文字潤色
- 風格統一
- 動作/對話/氛圍強化

### 總監決策循環

Copilot Director 持續監控創作狀態，支援：
- **CONTINUE**：自動推進下一階段
- **LOCAL_ALIGN_VOLUME**：單卷 JIT 微創校準
- **INCREMENTAL_INSERT_PLOT**：增量插入大綱
- **GO_BACK_TO_***：回退修改世界觀/角色/大綱
- **AUTO_REGENERATE**：自動重新生成

### 流程圖

```
runPipeline(userPrompt)
    │
    ├─→ runDirectorDecision('init', userPrompt)
    │       │
    │       └─→ executeDirectorAction(decision, userPrompt)
    │               │
    │               ├─ CONTINUE(target='plot')
    │               │       │
    │               │       ├─ Stage 2: generateAllVolumeSkeletons()
    │               │       │       └─→ 依序執行每卷的卷骨架生成
    │               │       │
    │               │       ├─ Stage 3: executePipelineStage('foreshadowing_orchestration')
    │               │       │       └─→ 全局伏筆編織對齊
    │               │       │
    │               │       └─ Stage 4: executePipelineStage('plot')
    │               │               └─→ 微觀大綱滾動展開
    │               │
    │               ├─ LOCAL_ALIGN_VOLUME → 單卷校準對齊
    │               │
    │               ├─ INCREMENTAL_INSERT_PLOT → 增量插入大綱
    │               │
    │               ├─ GO_BACK_TO_* → 回退修改
    │               │
    │               └─ AUTO_REGENERATE → 自動重新生成

自動循環評估（成功/失敗後）:
    └─ setTimeout(() => runPipeline(userPrompt), 2000)
```

---

## 🚀 4. 啟動網站方式

### 步驟 1：安裝依賴套件

確保已安裝 `python-dotenv`：
```powershell
pip install python-dotenv
```

### 步驟 2：開啟終端機 (Terminal)
開啟 Windows 的 **PowerShell** 或 **命令提示字元 (CMD)**。

### 步驟 3：切換至專案根目錄
```powershell
cd "c:\Users\user\Desktop\test_html\新增資料夾\Write_Novel"
```

### 步驟 4：使用虛擬環境 Python 啟動伺服器
```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

---

### 步驟 5：瀏覽並使用網站

當終端機顯示 `Uvicorn running on http://127.0.0.1:8000` 時，開啟瀏覽器造訪：
👉 **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

---

## 🛑 4. 關閉網站方式

1. 切換回執行啟動指令的 **終端機視窗**
2. 同時按下 **`Ctrl + C`**
3. 終端機將顯示 `INFO: Shutting down`，代表伺服器已成功關閉

---

## ⚙️ 5. 模型設定頁面

在網站的左下角點擊 **「⚙️ 模型設定 & API Key」**，即可進入 Agent 的配置面板。

### 前端設定流程

1. 選擇要設定的 Agent（點擊左側導航按鈕）
2. 系統會自動從後端載入該 Agent 的 .env 預設值與資料庫儲存值
3. 填寫或修改 API Key、模型等設定
4. 點擊「**儲存本項設定**」將設定寫入資料庫

### Nvidia Presets 快速套用

在設定面板中有 **Nvidia 推薦模型預設下拉選單**，可一鍵快速套用：

| 預設模型 | 特色 |
| :--- | :--- |
| **nvidia/nemotron-3-super-120b-a12b** | 120B 推理模型，開啟思考模式表現更卓越 |
| **openai/gpt-oss-120b** | 極致強大的通用寫作大模型 |
| **minimaxai/minimax-m2.7** | 精緻的情感細節與文學描寫 |
| **mistralai/mistral-small-4-119b-2603** | 119B 高推理、高智慧模型 |
| **stepfun-ai/step-3.5-flash** | 極速響應，適合流式快速對白 |
| **google/gemma-3n-e4b-it** | Gemma 3n 精校版，適合文字潤色 |

### 啟用思考過程 (Reasoning / Thinking)

若選用支援 Reasoning 的模型（如 Nemotron 思考版），勾選「**啟用深度思考**」後，系統會在寫作正文時輸出詳細的推理心路歷程。

---

祝您創作愉快，筆下生花！✍️✨