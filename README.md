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
