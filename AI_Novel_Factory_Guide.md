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
| **Character Designer** | mistralai/mistral-small-4-119b-2603 | 創意但結構化的人物描寫 | 0.45 | 0.95 | 4096 | ✅ |
| **Plot Planner** | openai/gpt-oss-120b | 邏輯嚴謹的大綱拆解 | 0.35 | 0.95 | 8192 | ✅ |
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

# --- Agent Default Models ---
MODEL_GLOBAL="qwen/qwen3.5-122b-a10b"
MODEL_ARCHITECT="nvidia/nemotron-3-super-120b-a12b"
MODEL_CHARACTER="mistralai/mistral-small-4-119b-2603"
MODEL_PLOT="openai/gpt-oss-120b"
MODEL_WRITER="minimaxai/minimax-m2.7"
MODEL_EDITOR="google/gemma-3n-e4b-it"
MODEL_COPILOT="nvidia/nemotron-3-super-120b-a12b"

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

## 🚀 3. 啟動網站方式

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
C:\Users\user\venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

---

### ⚠️ 啟動疑難排解：連接埠衝突 (WinError 10013)

若遇到 `WinError 10013`，代表連接埠被佔用。**更換連接埠**即可：
```powershell
C:\Users\user\venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001 --reload
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