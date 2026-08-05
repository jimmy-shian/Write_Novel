# AI Novel Factory

智能小說創作系統 - 使用 AI 代理協作生成長篇小說

## 專案結構

```
Write_Novel/
├── backend/
│   ├── app.py                    # FastAPI app + router registration
│   ├── api/                      # resource route packages
│   │   ├── novels/routes.py
│   │   ├── settings/routes.py
│   │   ├── export/routes.py
│   │   ├── volumes/routes.py
│   │   └── diagnostics/routes.py
│   ├── agents/                   # isolated agent runtime packages
│   │   ├── story_architect/
│   │   ├── character_designer/
│   │   ├── foreshadowing_orchestrator/
│   │   ├── volumes_planner/
│   │   ├── volume_skeleton/
│   │   ├── chapter_writer/
│   │   ├── editor/
│   │   ├── director/
│   │   ├── copilot/
│   │   ├── incremental/
│   │   └── shared/
│   ├── common/                   # shared config, LLM transport, utilities
│   ├── generation/               # generation routing, orchestration, handlers
│   │   ├── routing/
│   │   ├── orchestration/
│   │   └── handlers/
│   ├── persistence/              # DB connection, schema, repositories
│   │   └── repositories/
│   ├── prompts/                  # prompt constants and shared prompt context
│   ├── schemas/                  # output schemas and validation
│   └── services/                 # diagnostics, director tools, settings, foreshadowing
├── frontend/                     # static frontend assets
├── data/                         # runtime data and gold rules
├── docs/                         # project documentation
├── tools/                        # maintenance tools
└── _archive/                     # legacy and scratch material
```

## 快速開始

```bash
# 安裝依賴
pip install -r requirements.txt

# 啟動伺服器
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload

# 開啟瀏覽器
http://127.0.0.1:8000
```

## 環境變數設定 (.env)

在專案根目錄建立 `.env` 檔案，依照下方模板填入各代理的設定。

### Agent 名稱

設定檔使用以下代理名稱（與程式中 `agent_name` 對應）：

`global`, `architect`, `character`, `volumes`, `volume_skeleton`, `plot`, `writer`, `editor`, `copilot`

`ARCHITECT` 對應 Story Architect；`CHARACTER` 對應 Character Designer；`PLOT` 對應 Plot Planner；`VOLUME_SKELETON` 對應 Skeleton Planner；`COPILOT` 對應 AI Director Copilot。`VOLUMES` 若未提供 `NVIDIA_API_KEY_VOLUMES`，會 fallback 到 `NVIDIA_API_KEY_ARCHITECT`。

### .env 模板

```dotenv
# ==========================================
# AI Novel Factory - Environment Configuration
# ==========================================

# --- Agent API Keys (NVIDIA API Keys) ---
# 每個代理使用獨立 key 以分散 rate limit
NVIDIA_API_KEY_GLOBAL="nvapi-YOUR_KEY_HERE"
NVIDIA_API_KEY_ARCHITECT="nvapi-YOUR_KEY_HERE"
NVIDIA_API_KEY_CHARACTER="nvapi-YOUR_KEY_HERE"
NVIDIA_API_KEY_PLOT="nvapi-YOUR_KEY_HERE"
# NVIDIA_API_KEY_VOLUMES="nvapi-YOUR_KEY_HERE"  # 可選，未設則 fallback 到 ARCHITECT
NVIDIA_API_KEY_VOLUME_SKELETON="nvapi-YOUR_KEY_HERE"  # 可選，未設則 fallback 到 PLOT
NVIDIA_API_KEY_WRITER="nvapi-YOUR_KEY_HERE"
NVIDIA_API_KEY_EDITOR="nvapi-YOUR_KEY_HERE"
NVIDIA_API_KEY_COPILOT="nvapi-YOUR_KEY_HERE"

# --- Global Agent Settings ---
MODEL_GLOBAL="openai/gpt-oss-120b"
BASE_URL_GLOBAL="https://integrate.api.nvidia.com/v1"
TEMPERATURE_GLOBAL=1.0
TOP_P_GLOBAL=0.95
MAX_TOKENS_GLOBAL=16384
ENABLE_THINKING_GLOBAL=0

# MODELS_CONFIG='{}'  # 可選：以 JSON 指定 model preset 覆寫

# --- 1. Story Architect Agent ---
MODEL_ARCHITECT="openai/gpt-oss-120b"
BASE_URL_ARCHITECT="https://integrate.api.nvidia.com/v1"
TEMPERATURE_ARCHITECT=1.0
TOP_P_ARCHITECT=0.95
MAX_TOKENS_ARCHITECT=16384
ENABLE_THINKING_ARCHITECT=0

# --- 2. Character Designer Agent ---
MODEL_CHARACTER="openai/gpt-oss-120b"
BASE_URL_CHARACTER="https://integrate.api.nvidia.com/v1"
TEMPERATURE_CHARACTER=1.0
TOP_P_CHARACTER=0.95
MAX_TOKENS_CHARACTER=16384
ENABLE_THINKING_CHARACTER=0

# --- 3. Plot Planner Agent ---
MODEL_PLOT="openai/gpt-oss-120b"
BASE_URL_PLOT="https://integrate.api.nvidia.com/v1"
TEMPERATURE_PLOT=1.0
TOP_P_PLOT=0.95
MAX_TOKENS_PLOT=16384
ENABLE_THINKING_PLOT=0

# --- 3.1 Skeleton Planner Agent ---
MODEL_VOLUME_SKELETON="openai/gpt-oss-120b"
BASE_URL_VOLUME_SKELETON="https://integrate.api.nvidia.com/v1"
TEMPERATURE_VOLUME_SKELETON=1.0
TOP_P_VOLUME_SKELETON=0.95
MAX_TOKENS_VOLUME_SKELETON=16384
ENABLE_THINKING_VOLUME_SKELETON=0

# --- 4. Chapter Writer Agent ---
MODEL_WRITER="openai/gpt-oss-120b"
BASE_URL_WRITER="https://integrate.api.nvidia.com/v1"
TEMPERATURE_WRITER=1.0
TOP_P_WRITER=0.95
MAX_TOKENS_WRITER=16384
ENABLE_THINKING_WRITER=0

# --- 5. Editor Agent ---
MODEL_EDITOR="openai/gpt-oss-120b"
BASE_URL_EDITOR="https://integrate.api.nvidia.com/v1"
TEMPERATURE_EDITOR=1.0
TOP_P_EDITOR=0.95
MAX_TOKENS_EDITOR=16384
ENABLE_THINKING_EDITOR=0

# --- 6. AI Director Copilot Agent ---
MODEL_COPILOT="openai/gpt-oss-120b"
BASE_URL_COPILOT="https://integrate.api.nvidia.com/v1"
TEMPERATURE_COPILOT=1.0
TOP_P_COPILOT=0.95
MAX_TOKENS_COPILOT=16384
ENABLE_THINKING_COPILOT=0

# --- Default Fallback Parameters ---
DEFAULT_BASE_URL="https://integrate.api.nvidia.com/v1"
DEFAULT_TEMPERATURE=1.0
DEFAULT_TOP_P=0.95
DEFAULT_MAX_TOKENS=16384
DEFAULT_ENABLE_THINKING=0
```

### 欄位說明

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `NVIDIA_API_KEY_{AGENT}` | 該代理的 API key；未設時 fallback 到 `NVIDIA_API_KEY_GLOBAL` | - |
| `MODEL_{AGENT}` | 該代理使用的模型；未設時 fallback 到 `MODEL_GLOBAL` | `patcher-main` |
| `BASE_URL_{AGENT}` | 該代理的 API endpoint；未設時 fallback 到 `DEFAULT_BASE_URL` | `https://integrate.api.nvidia.com/v1` |
| `TEMPERATURE_{AGENT}` | 採樣溫度，範圍 0.0–2.0 | 1.0 |
| `TOP_P_{AGENT}` | nucleus sampling 機率上限，範圍 0.0–1.0 | 0.95 |
| `MAX_TOKENS_{AGENT}` | 單次回應最大 token 數，須為正整數 | 16384 |
| `ENABLE_THINKING_{AGENT}` | 是否啟用 reasoning，`0`/`1` | 0 |
| `MODEL_STORY` / `MODEL_CRITIC` | 舊別名，分別 fallback 到 `MODEL_CHARACTER` / `MODEL_PLOT` | - |
| `MODELS_CONFIG` | JSON 字串，可指定 model preset 覆寫 payload 參數 | `{}` |

## 核心 API

| 端點 | 說明 |
|------|------|
| `POST /api/novels` | 建立小說 |
| `GET /api/novels` | 列出小說 |
| `GET /api/novels/{id}` | 取得小說完整資料 |
| `POST /api/generation-task` | **統一生成端點** (SSE/JSON) |
| `GET /api/novels/{id}/export` | 匯出小說 (txt/md) |
| `GET /api/settings` | 取得設定 |
| `POST /api/settings` | 更新設定 |

### 生成任務 Payload 範例

```json
{
  "novel_id": "uuid",
  "stage": "worldview",
  "task_type": "generate",
  "scope": "global",
  "instruction": "請生成一個奇幻世界觀",
  "options": { "stream": true }
}
```

階段：`worldview`, `characters`, `foreshadowing`, `volumes`, `volume_skeleton`, `writer`, `editor`, `evaluate`

## 架構原則

1. **單一生成流程** - 只有 `backend/generation/` 是正式 runtime
2. **無雙重入口** - 舊 `agents.py` 已封存，不再被 import
3. **模組化 DB 層** - 資料庫程式碼集中於 `backend/persistence/`
4. **乾淨根目錄** - 無除錯/臨時檔案

## 統一校閱標準

總監審核分成兩層：

1. **程式硬性檢查**：`evaluate_output` 統一檢查 `worldview`、`foreshadowing`、`characters`、`volumes`、`volume_skeleton`、`writer`、`editor` 的 JSON 格式、必填欄位、索引連續性、數量限制與明顯空內容。
2. **內容品質檢查**：長列表或完整章節不要只看摘要。總監需用 `inspect_content_block` 或 `expand_collapsed_json` 分段展開，再判斷角色一致性、伏筆執行、章節節奏與文風品質。

硬性檢查不通過才阻斷流程；主觀品質問題應給明確修改位置與理由。

## 文檔

- [架構文檔](docs/ARCHITECTURE.md)
- [使用者指南](docs/USER_GUIDE.md)
- [開發者指南](docs/DEVELOPER_GUIDE.md)
