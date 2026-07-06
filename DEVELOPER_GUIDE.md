# 🛠️ AI Novel Factory - 開發者與工程師指南

本文件專為工程師與開發人員設計，詳細說明 **AI Novel Factory** 專案的啟動方式、環境配置、SQLite 資料庫架構、常用維護與清理指令、程式碼邏輯結構，以及測試執行。

---

## 🚀 1. 環境準備與服務啟動

### 執行環境
- **作業系統**：Windows
- **指定 Python 虛擬環境路徑**：`C:\Users\user\venv\Scripts\python.exe`
- **編碼規範**：系統所有中文處理與檔案讀寫一律強制使用 **`UTF-8`** 編碼。

### 服務啟動步驟
1. 開啟 Windows **PowerShell** 或 **命令提示字元 (CMD)**。
2. 切換至專案根目錄：
   ```powershell
   cd "c:\Users\user\Desktop\test_html\Write_Novel"
   ```
3. 使用虛擬環境 Python 啟動 Uvicorn 伺服器：
   ```powershell
   C:\Users\user\venv\Scripts\python.exe -m pip install -r requirements.txt
   C:\Users\user\venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
   ```
4. 啟動成功後，造訪本地服務網址：
   👉 **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

### 關閉服務
在執行啟動指令的終端機視窗中，同時按下 **`Ctrl + C`** 即可安全關閉伺服器。

---

## ⚙️ 2. 環境變數配置 (`.env`)

所有敏感資訊與 API Keys 均儲存於專案根目錄的 `.env` 檔案中，請勿提交至 Git 倉庫。

### 環境變數配置說明
- **`NVIDIA_API_KEY_*`**：各智能體的 API Key。支援為不同 Agent 設定獨立的金鑰。
- **`MODEL_*`**：各智能體預設套用的模型名稱。
- **`DEFAULT_*`**：全域預設值，例如 `DEFAULT_BASE_URL` 指向 NVIDIA API 網址，以及預設的 `DEFAULT_TEMPERATURE` 等。

### 配置讀取優先權
1. **資料庫設定**：在網頁前端「⚙️ 模型設定 & API Key」中所儲存並修改的設定（優先權最高）。
2. **本地環境變數 (`.env`)**：專案設定預設值。
3. **程式碼內置備援值**：若以上兩者皆缺少時的 Fallback 模型與參數。

---

## 統一校閱標準

總監審核先走程式硬性檢查，再做內容品質判斷。

- `backend/services/director_tools.py::evaluate_output` 統一檢查 `worldview`、`foreshadowing`、`characters`、`volumes`、`volume_skeleton`、`writer`、`editor`。
- 硬性檢查範圍包含 JSON 解析、必填欄位、數量限制、章節/卷索引連續性、正文基本長度與占位內容。
- 長列表或完整章節不得只看摘要。總監需呼叫 `inspect_content_block` 或 `expand_collapsed_json` 分段展開，再判斷內容品質。
- 只有硬性檢查失敗或內容問題有明確位置時才退回；一般風格建議應寫成 feedback，不阻斷流程。

---

## 📊 3. SQLite 資料庫架構

資料庫名稱為 [novel_factory.db](file:///c:/Users/user/Desktop/test_html/Write_Novel/novel_factory.db)，包含以下 **9 個核心資料表**：

### 1. `novels` (小說元數據表)
儲存小說的基本屬性。
- `id` (TEXT PRIMARY KEY) - UUID。
- `title` (TEXT) - 小說名稱。
- `genre` (TEXT) - 題材類型。
- `style` (TEXT) - 寫作風格。
- `pipeline_prompt` (TEXT) - 大綱生成初始提示詞。
- `worldview_patches` (TEXT) - 儲存後續增量修補的世界觀修補記錄 (JSON Array)。
- `created_at` (TIMESTAMP)

### 2. `worldbuilding` (世界觀表)
採用版本化管理，保留每次修改的世界觀歷史。
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `novel_id` (TEXT, 外鍵)
- `content` (TEXT) - 完整世界觀設定（JSON 格式）。
- `version` (INTEGER) - 版本號，從 1 開始遞增。
- `created_at` (TIMESTAMP)

### 3. `characters` (角色聖經表)
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `novel_id` (TEXT, 外鍵)
- `json_data` (TEXT) - 完整的角色聖經 JSON 數據。
- `version` (INTEGER)
- `created_at` (TIMESTAMP)

### 4. `plot_chapters` (主大綱章節表)
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `novel_id` (TEXT, 外鍵)
- `outline_json` (TEXT) - 全書劇情大綱主 JSON。
- `version` (INTEGER)
- `is_dirty` (INTEGER) - 標記是否被修改但未寫入。
- `created_at` (TIMESTAMP)

### 5. `chapters` (正文章節內容表)
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `novel_id` (TEXT, 外鍵)
- `chapter_index` (INTEGER) - 章節索引（1-indexed）。
- `content` (TEXT) - 已撰寫好的正文。
- `synopsis` (TEXT) - 該章大綱摘要。
- `thinking` (TEXT) - AI 寫作正文時的深度思考推理過程 (Reasoning Process)。
- `is_dirty` (INTEGER)
- `version` (INTEGER)
- `created_at` (TIMESTAMP)

### 6. `chat_memory` (對話記憶與總監日誌表)
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `novel_id` (TEXT, 外鍵)
- `role` (TEXT) - 發言角色 (`user` / `assistant`)。
- `content` (TEXT) - 對話內容。
- `thinking` (TEXT) - 側邊欄 Copilot 的深度思考過程。
- `message_type` (TEXT) - 消息類型：`chat` (普通對談) 或 `director` (總監分析日誌，用以避免 Token 爆炸)。
- `timestamp` (DATETIME)

### 7. `agent_configs` (智能體設定表)
- `agent_name` (TEXT PRIMARY KEY) - 例如 `writer`, `plot`, `architect` 等。
- `api_key` (TEXT)
- `base_url` (TEXT)
- `model` (TEXT)
- `temperature` (REAL)
- `top_p` (REAL)
- `max_tokens` (INTEGER)
- `enable_thinking` (INTEGER) - 1 為啟用，0 為停用。

### 8. `volumes` (篇卷架構與大綱表)
大綱生成策略的中間橋樑層，管理各卷的微觀章節骨架。
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `novel_id` (TEXT, 外鍵)
- `volume_index` (INTEGER) - 卷索引。
- `title` (TEXT) - 卷標題。
- `summary` (TEXT) - 卷大綱與劇情走勢。
- `factions` (TEXT) - 涉及的勢力範圍。
- `chapter_count` (INTEGER) - 本卷規劃章節數（預設 50）。
- `time_timeline` (TEXT) - 時間線設定。
- `sequence_context` (TEXT) - 上下文關係。
- `applicable_rules` (TEXT) - 適用法則。
- `chapters_outline` (TEXT) - 本卷內所有章節的骨架與詳細微觀大綱 (JSON 格式)。
- `is_dirty` (INTEGER)
- `created_at` (TIMESTAMP)

### 9. `foreshadowing_blueprints` (全局伏筆藍圖表)
- `novel_id` (TEXT PRIMARY KEY)
- `blueprint_json` (TEXT) - 儲存跨卷伏筆鋪墊 (Plants) 與回收 (Payoffs) 節點的藍圖。
- `updated_at` (TIMESTAMP)

---

## 🛠️ 4. 常用運維操作與細項指令

### A. 資料庫內容完全清理
在開發與調試期間，若需要**保留小說列表 (`novels` 表)** 但**清空所有生成的設定與正文**（包括角色、篇卷、正文、大綱、記憶與伏筆表），可使用以下指令：

```powershell
# 1. 執行清理腳本
C:\Users\user\venv\Scripts\python.exe scratch/clear_generated_content.py

# 2. 驗證清理後的資料庫狀態
C:\Users\user\venv\Scripts\python.exe scratch/verify_after_clear.py
```

快捷的合併命令：
```powershell
C:\Users\user\venv\Scripts\python.exe scratch/clear_generated_content.py && C:\Users\user\venv\Scripts\python.exe scratch/verify_after_clear.py
```

### B. 部分數據修補與重置
若僅需要將已生成的詳細大綱回退至初始的「骨架大綱」、保留首 10 個核心角色、並清空 plot_chapters 表以進行重新展開，可執行：
```powershell
C:\Users\user\venv\Scripts\python.exe scratch/clear_data.py
```
> [!NOTE]
> `clear_data.py` 預設的 `novel_id` 需手動修改為您當前要測試的小說 UUID。

---

## 🧪 5. 整合單一測試套件執行

根據本專案的測試規範，**所有測試代碼均整合在單一 Python 檔案內**，禁止分次或分檔案執行。

### 執行單一完整測試
請在專案根目錄下執行以下指令：
```powershell
C:\Users\user\venv\Scripts\python.exe test_all.py
```
此測試會自動初始化一個測試資料庫、執行資料庫的 CRUD 驗證、版本管理測試、格式解析測試，以及 API 連通性測試。

---

## 📦 6. 資料匯出技術細節與整合

### 1. 後端 API 設計
系統提供以下 FastAPI API 用於小說數據導出：
- **端點路徑**：`GET /api/novels/{novel_id}/export`
- **查詢參數**：
  - `format`：`txt` (純文字正文) 或 `markdown` (包含設定與正文的 Markdown)
- **處理常式位置**：[app.py](file:///c:/Users/user/Desktop/test_html/Write_Novel/app.py) 中的 `export_novel` 端點。
- **編碼頭**：
  ```python
  headers = {
      "Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"
  }
  ```

### 2. 命令列匯出工具 (`export_novel.py`)
除了 Web 端，開發者也可以使用命令列工具 [export_novel.py](file:///c:/Users/user/Desktop/test_html/Write_Novel/export_novel.py) 進行資料提取：

- **列出資料庫中所有可用的小說與 UUID**：
  ```powershell
  C:\Users\user\venv\Scripts\python.exe export_novel.py --list
  ```
- **匯出為 TXT 格式**：
  ```powershell
  C:\Users\user\venv\Scripts\python.exe export_novel.py --novel-id <NOVEL_UUID> --format txt
  ```
- **匯出為 Markdown 格式**：
  ```powershell
  C:\Users\user\venv\Scripts\python.exe export_novel.py --novel-id <NOVEL_UUID> --format markdown
  ```
- **指定自訂輸出路徑**：
  ```powershell
  C:\Users\user\venv\Scripts\python.exe export_novel.py --novel-id <NOVEL_UUID> --format markdown --output "./scratch/my_novel.md"
  ```

### 3. 前端 UI 整合代碼範例
若前端需要調用此導出 API，可在 [static/index.html](file:///c:/Users/user/Desktop/test_html/Write_Novel/static/index.html) 或對應的 JS 控制器中，為按鈕綁定以下點擊事件：

```javascript
function downloadNovel(novelId, format = 'txt') {
  if (!novelId) {
    showToast('請先選擇小說');
    return;
  }
  
  // 構建 API 下載請求
  const url = `/api/novels/${novelId}/export?format=${format}`;
  
  // 建立隱藏的 a 標籤觸發下載
  const link = document.createElement('a');
  link.href = url;
  link.download = ''; // 讓伺服器 header 決定檔名
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  
  showToast(`正在發送匯出請求 (${format.toUpperCase()})...`);
}
```

---

## 🧭 7. 原始碼結構與邏輯說明

- **[backend/app.py](file:///c:/Users/user/Desktop/test_html/Write_Novel/backend/app.py)**：FastAPI 應用入口，註冊 API 路由、靜態前端與 `/api/generation-task`。
- **[backend/db.py](file:///c:/Users/user/Desktop/test_html/Write_Novel/backend/db.py)**：SQLite 資料庫存取層。提供小說設定、版本管理、對話紀錄與 Agent 配置等讀寫介面。
- **[backend/generation/agent_runners.py](file:///c:/Users/user/Desktop/test_html/Write_Novel/backend/generation/agent_runners.py)**：正式 Agent 執行器。`agents.py` 已移至 `_archive/legacy/`，不再作為 runtime 入口。
- **[backend/schemas/agent_json.py](file:///c:/Users/user/Desktop/test_html/Write_Novel/backend/schemas/agent_json.py)**：定義各個智能體輸出內容的 JSON Schema 與通過標準。
- **[backend/services/director_tools.py](file:///c:/Users/user/Desktop/test_html/Write_Novel/backend/services/director_tools.py)**：總監工具層，包含 `evaluate_output`、內容展開、局部補強與子代理呼叫。
