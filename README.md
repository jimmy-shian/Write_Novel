# AI Novel Factory

智能小說創作系統 - 使用 AI 代理協作生成長篇小說

## 專案結構

```
Write_Novel/
├── backend/                    # 後端 FastAPI 服務
│   ├── app.py                 # 應用入口點 + 路由註冊
│   ├── config.py              # 設定常數
│   ├── db.py                  # SQLite 資料庫層
│   ├── llm.py                 # LLM 呼叫與配置
│   ├── utils.py               # 通用工具函數
│   ├── api/                   # API 路由模組
│   │   ├── novels.py          # 小說 CRUD
│   │   ├── settings.py        # 系統設定
│   │   ├── export.py          # 匯出功能
│   │   ├── volume_routes.py   # 卷管理
│   │   └── diagnostics_routes.py # 診斷/特殊端點
│   ├── schemas/               # 資料結構與驗證
│   │   ├── agent_json.py      # Agent JSON Schema
│   │   ├── validation.py      # 校驗邏輯
│   │   └── constraints.py     # 金律載入
│   ├── prompts/               # 提示詞模板與建構
│   │   ├── prompt_main.py     # 主要提示詞
│   │   ├── prompt_builder.py  # 提示詞組裝
│   │   ├── prompt_detail_modifier.py # 細節修改
│   │   ├── prompt_instructions.py # 系統指令
│   │   └── prompt_manager.py  # 覆寫管理
│   ├── services/              # 核心服務
│   │   ├── director_context.py
│   │   ├── director_tools.py
│   │   ├── diagnostics.py
│   │   ├── incremental_patch_engine.py
│   │   ├── retry_handler.py
│   │   ├── compactor.py
│   │   └── settings_service.py
│   ├── models/                # 資料模型
│   │   ├── parsers.py         # JSON 解析
│   │   └── client.py          # 客戶端模型
│   └── generation/            # 🎯 正式生成流程 (唯一入口)
│       ├── task_router.py     # 任務路由
│       ├── task_schema.py     # 任務 Schema
│       ├── task_validator.py  # 任務驗證
│       ├── stage_registry.py  # 階段註冊
│       ├── context_builder.py # 上下文建構
│       ├── lock_manager.py    # Pipeline 鎖
│       ├── post_processor.py  # 後處理
│       ├── response_builder.py # 回應建構
│       ├── agent_runners.py   # Agent 執行器 (從 agents.py 移出)
│       └── handlers/          # 8 個階段處理器
├── frontend/                  # 前端靜態資源
│   └── static/
│       ├── index.html         # 主頁面
│       ├── style.css          # 樣式
│       ├── app.js             # 入口 (legacy)
│       ├── core/              # 核心工具
│       ├── api/               # API 客戶端
│       ├── pipeline/          # Pipeline 流程
│       ├── ui/                # UI 元件
│       └── generation/        # 🎯 新統一生成客戶端
├── data/                      # 資料目錄
│   ├── novel_factory.db       # 主資料庫
│   ├── novels.db              # 備用資料庫
│   └── gold_rules/            # 金律文檔
├── scripts/                   # 維護腳本
├── docs/                      # 文檔
│   ├── ARCHITECTURE.md        # 架構文檔
│   ├── USER_GUIDE.md          # 使用者指南
│   ├── DEVELOPER_GUIDE.md     # 開發者指南
│   └── archive/               # 舊文檔
└── _archive/                  # 封存區
    ├── legacy/agents.py       # 舊單體 pipeline
    ├── incomplete_db_package/ # 另一套 DB schema
    ├── scratch/               # 除錯腳本
    └── tools/                 # 外部工具
```

## 快速開始

```bash
# 安裝依賴
pip install -r requirements.txt  # fastapi, uvicorn, pydantic, python-dotenv, opencc-python-reimplemented

# 啟動伺服器
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload

# 開啟瀏覽器
http://127.0.0.1:8000
```

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
2. **無雙重入口** - `agents.py` 已封存，不再被 import
3. **單一 DB 層** - 只有 `backend/db.py`，`db/` 套件已封存
4. **乾淨根目錄** - 無除錯/臨時檔案

## 文檔

- [架構文檔](docs/ARCHITECTURE.md)
- [使用者指南](docs/USER_GUIDE.md)
- [開發者指南](docs/DEVELOPER_GUIDE.md)