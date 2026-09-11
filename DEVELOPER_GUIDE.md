# AI Novel Factory - 開發者手冊 (v4.0.0)

本手冊涵蓋環境建置、版本控制、開源授權邊界、SQLite 資料庫架構、Graphiti 時序動態記憶引擎、React + Vite 前端架構、OpenDesign 規範與自動化測試。

---

## 1. 開發環境配置與服務啟動

### 核心環境規範
- **作業系統**：Windows 10 / 11
- **指定 Python 虛擬環境路徑**：`C:\Users\Administrator\venv\Scripts\python.exe`
- **指定 Node.js 環境**：Node.js v20+ / v22+ 與 npm
- **編碼規範**：所有 Python 檔案、TypeScript 檔案與資料庫交互一律強制採用 **`UTF-8 (無 BOM)`** 編碼。
- **樣式與介面規範**：**嚴格禁止 Inline Styles**，全站 100% 透過 `opendesign.css` 管理；**禁止裝飾性卡通 Emoji**，全面採用精準 SVG 與 6px 狀態指示點。

### 服務啟動步驟

#### A. 前端構建與啟動
```powershell
# 1. 進入前端目錄
cd frontend

# 2. 安裝相依套件 (初次執行)
npm install

# 3. 構建生產發布包 (輸出至 frontend/dist/)
npm run build

# 4. (選用) 獨立前端熱重載開發模式
npm run dev
```

#### B. 後端伺服器啟動
```powershell
# 切換回專案根目錄
cd ..

# 透過指定虛擬環境啟動 Uvicorn 伺服器
C:\Users\Administrator\venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```
後端啟動後，FastAPI 會**自動優先掛載並提供 `frontend/dist/` 打包產物**。造訪 `http://127.0.0.1:8000/` 即可直接進入最新版 React 創作工作台。

---

## 2. 開源授權邊界與 Clean-Room 實作原則

本專案在整併與參考開源專案時，嚴格恪守開源授權界限（詳見 [THIRD_PARTY_NOTICES.md](file:///c:/Users/Administrator/Desktop/Write_Novel/THIRD_PARTY_NOTICES.md)）：

1. **`AI-Novel-Writer` (GPL-3.0) 授權界限**：
   - 僅作為功能架構、使用者介面排版（4 欄 IDE 網格、抽屜交互）與審閱工作流的**概念與行為規格參考**。
   - **絕對禁止代碼複製**：嚴禁複製、移植、翻譯或機械改寫任何 GPL-3.0 代碼，本專案所有 React 元件、Hook、演算法（包括 LCS Line Diff）皆為純粹根據行為規格獨立全新實作之 Clean-Room 代碼。
2. **`Monogatari-Assistant-FE` (Apache-2.0)**：
   - 元素間距、排版概念與靈感借鑒，已保留完整 NOTICE 與 Attribution 標註。
3. **`Graphiti` (Apache-2.0)**：
   - 時序知識圖譜、Episode 抽取與事實作廢追蹤之概念與架構參考，已於 `THIRD_PARTY_NOTICES.md` 完整聲明。

---

## 3. 單一事實來源版本號管理 (SSOT)

本專案版本號遵循 **Single Source of Truth** 原則：
- **唯一維護位置**：專案根目錄 [`version.json`](file:///c:/Users/Administrator/Desktop/Write_Novel/version.json)
  ```json
  {
    "name": "AI Novel Factory",
    "version": "4.0.0",
    "codename": "ObsidianGraphiti",
    "release_date": "2026-09-05"
  }
  ```
- **引用規範**：
  - 後端：透過 `from backend.common.version import get_version, get_app_info` 動態讀取。
  - 前端：透過 `import versionConfig from '../../../version.json'`（定義於 `frontend/src/config/version.ts`）取得常數。
  - **嚴禁在任何其他代碼檔案中手動硬編碼版本號字串**。

---

## 4. SQLite 資料庫完整架構 (`novel_factory.db`)

資料庫由 [`backend/persistence/schema.py`](file:///c:/Users/Administrator/Desktop/Write_Novel/backend/persistence/schema.py) 進行集中建表與升級維護，包含 14 個主要資料表：

### A. 小說核心表
1. **`novels`**：作品元資訊 (`id`, `title`, `genre`, `style`, `pipeline_prompt`, `created_at`)。
2. **`worldbuilding`**：版本化世界觀歷史設定 (`id`, `novel_id`, `content`, `version`)。
3. **`characters`**：角色聖經與關聯網絡 (`id`, `novel_id`, `json_data`, `version`)。
4. **`plot_chapters`**：全書大綱主 JSON 表。
5. **`chapters`**：章節正文與思考歷程 (`novel_id`, `chapter_index`, `content`, `synopsis`, `thinking`, `is_dirty`, `version`)。
6. **`volumes`**：篇卷結構與 50 章微觀大綱。
7. **`foreshadowing_blueprints`**：全局伏筆鋪設與回收藍圖。
8. **`chat_memory`**：對話記憶與總監日誌。
9. **`agent_configs`**：LLM 智能體參數快取備份。

### B. Graphiti 時序記憶圖譜專用表
10. **`temporal_episodes`**：
    - 紀錄每一章節的情節片段摘要與內容雜湊。
    - 欄位：`id` (UUID), `novel_id`, `chapter_index`, `summary`, `content_hash`, `created_at`。
11. **`temporal_entities`**：
    - 追蹤登場之角色、物品、地點、勢力或修煉概念。
    - 欄位：`id`, `novel_id`, `name`, `entity_type`, `summary`, `attributes` (JSON), `created_chapter`, `updated_chapter`。
12. **`temporal_facts`**：
    - 時序事實命題核心表，支援生命週期與動態作廢。
    - 欄位：`id`, `novel_id`, `source_entity_id`, `target_entity_id`, `relation_type`, `fact_statement`, `valid_from_chapter`, `invalid_from_chapter`, `is_active`, `superseded_by`。
    - **切片邏輯**：當查詢第 $N$ 章記憶時，條件為 `valid_from_chapter <= N AND (invalid_from_chapter IS NULL OR invalid_from_chapter > N)`。

### C. 專用術語庫與草稿提案表
13. **`story_terms`**：
    - 專用名詞庫，自動作為 Prompt 約束注入。
    - 欄位：`id`, `novel_id`, `category`, `term`, `definition`, `notes`, `created_at`。
14. **`draft_proposals`**：
    - 暫存 AI 總監或編輯產出的修改建議。
    - 欄位：`id`, `novel_id`, `chapter_index`, `original_text`, `proposed_text`, `review_comments` (JSON), `status` (`pending` / `accepted` / `rejected`), `created_at`。

---

## 5. 前端架構與 OpenDesign 規範

前端採用 **React 18 + TypeScript + Vite**，位於 `frontend/` 目錄：

```
frontend/src/
├── api/                  # 封裝型別化的後端端點請求
├── components/
│   ├── common/           # Button, Badge, StatusDot, CopyCard, ModelChip, Modal, Icons (SVG)
│   ├── layout/           # ActivityRail, ExplorerDrawer, WorkspaceHeader, BottomDock, MobileNav
│   ├── editor/           # EditorPane, DiffViewer, ProposalInbox, TaskPicker, WorldviewPane
│   ├── graph/            # TemporalGraphBoard (時序切片與事實作廢面板)
│   ├── copilot/          # CopilotDrawer, StageSelector, DirectorRecordsStream
│   ├── novel/            # CreateNovelModal, DeleteNovelModal, ResetNovelModal
│   └── settings/         # SettingsModal (API 參數與動態模型), TermsModal (術語庫維護)
├── config/               # 引用 version.json
├── hooks/                # useNovel, useTemporalGraph, useProposals, useExpansionSync
├── platform/             # 平台抽象層 (Web / Android APK / Desktop)
├── storage/              # 本地狀態管理
├── types/                # 全域 TypeScript 型別定義
├── styles/               # opendesign.css (Zinc/Obsidian 暗黑設計系統)
└── utils/                # diff.ts (LCS 行級對比), clipboard.ts, time.ts
```

### 關鍵技術規範
1. **嚴格零 Inline Style**：全專案無任何 `style="..."` 或 JSX `style={{...}}`，所有元素樣式由 `opendesign.css` 統一管理。
2. **極簡無 Emoji 政策**：統一向量 SVG（`components/common/Icons.tsx`）與 6px 狀態圓點（`.status-dot.success`, `.status-dot.danger`）。
3. **平台解耦與打包相容**：前端所有資源引用均使用相對路徑（`base: './'`），`platform/index.ts` 抽象平台能力，相容 Web / Android APK (Capacitor) / Windows Desktop (Electron)。

---

## 6. 自動化測試規範

專案採用 **Pytest** 作為後端與整合測試驅動器，配置於 [`pytest.ini`](file:///c:/Users/Administrator/Desktop/Write_Novel/pytest.ini)。

### 執行全套測試
```powershell
C:\Users\Administrator\venv\Scripts\python.exe -m pytest
```

### 測試模組一覽
- **`tests/test_frontend_build_integration.py`**：FastAPI 靜態掛載優先級與 SSOT 版本號讀取。
- **`tests/test_temporal_and_story_extensions.py`**：時序事實生命週期、作廢機制、術語庫約束與提案流程。
- **`tests/test_volume_outline_persistence.py`**：篇卷大綱持久化驗證。
- **`tests/unit/test_writer_context_builder.py`**：Graphiti 時序記憶動態注入。
- **`tests/unit/test_gold_rules_governance.py`**：黃金規則治理邏輯。
- **`tests/unit/test_tool_loop_fix.py`**：Agent 工具調用死循環防護。
- **`tests/unit/test_autonomous_pipeline_safeguards.py`**：自主管線安全機制。
- **`tests/unit/test_character_worldview_increment.py`**：角色與世界觀增量更新。
- **`tests/unit/test_chat_memory_modularization.py`**：對話記憶模組化。
- **`tests/unit/test_context_architecture_safeguards.py`**：上下文架構安全。
- **`tests/unit/test_parsers_salvage.py`**：LLM 輸出解析容錯。
- **`tests/unit/test_prompt_and_proposals.py`**：Prompt 與提案流程。
- **`tests/unit/test_sql_performance_and_safeguards.py`**：SQL 性能與安全。
- **`tests/narrative_regression/test_narrative_benchmark.py`**：敘事長篇基準測試。


## 7. 本地打包與 GitHub Actions 遠端 CI/CD

### A. 本地一鍵打包腳本 (build_app.py)
```powershell
python build_app.py --target apk       # Android APK (mykey 簽名)
python build_app.py --target electron   # Windows Electron Portable
python build_app.py --target installer  # Windows NSIS 安裝包
python build_app.py --target all        # 全平台
python build_app.py --target web        # 僅前端構建
```
編譯成品輸出至 `dist-packages/`。

### B. GitHub Actions CI/CD (.github/workflows/build_and_release.yml)
推送至 `master` 或建立 `v*` 標籤時觸發：
1. **test-and-build-web**：Python 3.11 + Node.js 22，Pytest + 前端構建 + GitHub Pages 部署。
2. **build-android-apk**：JDK 21 + Android SDK，Gradle 簽名封裝 APK。
3. **build-windows-electron**：PyInstaller + Electron-builder 打包 portable .exe。

---

## 8. 部署架構

### 分支與發布目標

| 部署目標 | 核心內容 |
| :--- | :--- |
| **`master`** | FastAPI 後端 + React 前端 + SQLite + 自主寫作管線 |
| **GitHub Pages** | CI 自動從 `frontend/dist/` 發布，連接 HF Space 後端 |
| **Android APK** | Capacitor 封裝，支援遠端伺服器對接 |
| **Windows Electron** | Electron 封裝，portable 可攜版 |

### 雲端無人值守自主寫作 (Autonomous Pipeline)
1. **後端自主推進**：前端不涉入創作決策。後端收到啟動指令後，AI 總監自動檢查進度並逐階段推進：世界觀 → 角色 → 伏筆 → 分卷 → 細綱 → 逐章撰寫與精修。
2. **斷線續寫**：進度即時寫入 SQLite，同步至 HF Storage Bucket。前端每 3 秒輪詢 `/api/pipeline/auto-status`。
3. **多小說並行**：`AutonomousPipelineManager` 支援多執行緒同時背景創作。

### Hugging Face Spaces 整合
- 入口檔 `app.py`（Gradio SDK + ZeroGPU 相容）。
- 雲端啟動時自動從 HF Storage Bucket 還原資料庫。
- 前端由 GitHub Pages 獨立託管，後端運行於 HF Space。
