# 宏觀大綱生成策略重構任務清單

## 目標
實作「四階段漸進式漏斗流」大綱生成策略，解決長篇小說大綱「骨質疏鬆、短線流水帳」的問題。

## 四階段流程（已完成 ✅）
1. 世界觀設定 → 2. 簡易章綱 (Volume Skeleton) → 3. 伏筆編織 (Foreshadowing Orchestration) → 4. 微觀細修 (Plot Expansion) → 5. 正文寫作

---

## 任務清單（全部完成 ✅）

### Phase 1: 後端 Prompt 與函數新增 (agents.py) ✅
- [x] 1.1 新增 `VOLUME_SKELETON_PROMPT`（簡易章大綱生成器 Prompt）
- [x] 1.2 新增 `FORESHADOWING_ORCHESTRATOR_PROMPT`（全局伏筆調度導演 Prompt）
- [x] 1.3 新增 `run_volume_skeleton_planner` 函數
- [x] 1.4 新增 `run_foreshadowing_orchestrator` 函數
- [x] 1.5 修改 `run_plot_planner` 讓它從資料庫讀取已含伏筆任務的骨架進行細修

### Phase 2: 資料庫函數新增 (db.py) ✅
- [x] 2.1 新增 `save_volume_skeletons` 函數
- [x] 2.2 新增 `get_all_volume_skeletons` 函數
- [x] 2.3 新增 `save_foreshadowing_allocations` 函數

### Phase 3: API 端點新增 (app.py) ✅
- [x] 3.1 新增 `/api/agent/volume-skeleton` 端點
- [x] 3.2 新增 `/api/agent/foreshadowing-orchestrate` 端點

### Phase 4: 前端管道邏輯更新 (pipeline_logic.js) ✅
- [x] 4.1 修改 `resolveNextStageFromDecision` 加入 `volume_skeleton` 和 `foreshadowing_orchestration` 階段

### Phase 5: 前端管道執行更新 (pipeline.js) ✅
- [x] 5.1 在 `executePipelineStage` 中新增 `volume_skeleton` 案例處理
- [x] 5.2 在 `executePipelineStage` 中新增 `foreshadowing_orchestration` 案例處理

### Phase 6: 前端狀態更新 (state.js) ✅
- [x] 6.1 在 `currentNovelData` 中新增 `volume_skeletons` 結構與 `activeVolumeIndex`

### Phase 7: 前端執行路由更新 (app.js) ✅
- [x] 7.1 修改 `executeDirectorAction` 加入新階段的路由處理
- [x] 7.2 修改 `runPipeline` 加入新階段的初始化

### Phase 8: 前端 UI 更新 (index.html) ✅
- [x] 8.1 在進度條中新增 `volume_skeleton` 階段指示器 (🦴 簡易章綱)
- [x] 8.2 在進度條中新增 `foreshadowing_orchestration` 階段指示器 (🕸️ 伏筆編織)

---

## 新增：增量追加角色功能 ✅

### Phase 9: 增量追加角色功能 (agents_incremental.py) ✅
- [x] 9.1 新增 `INCREMENTAL_CHARACTER_APPEND_PROMPT`（精準增量追加新角色 Prompt）
- [x] 9.2 新增 `run_incremental_character_append` 函數
- [x] 9.3 支援多個新角色名稱批量追加

### Phase 10: 增量追加角色 API 端點 (app.py) ✅
- [x] 10.1 新增 `IncrementalCharacterAppendRequest` 結構
- [x] 10.2 新增 `/api/agent/incremental-character-append` 端點
- [x] 10.3 在 import 中新增 `run_incremental_character_append`

---

## 進度追蹤
- 建立時間: 2026-05-25
- 更新時間: 2026-05-25 06:54
- 全部 Phase 完成 ✅

## 核心變更摘要

### 新增的 Prompt (agents_incremental.py)
- `INCREMENTAL_CHARACTER_APPEND_PROMPT`: 精準增量追加新角色到角色聖經末尾

### 新增的函數 (agents_incremental.py)
- `run_incremental_character_append()`: 為新角色設計完整人設並追加到聖經末尾

### 新增的 API 端點 (app.py)
- `POST /api/agent/incremental-character-append`: 增量追加角色端點

### 增量追加角色端點使用方式
```json
{
  "novel_id": "小說ID",
  "new_character_names": ["赵", "林浩", "張銘", "黑曜", "小梅", "凜風", "老張"],
  "user_hint": "請根據世界觀為這些配角設計合理人設"
}
```

### 階段流程更新 (pipeline_logic.js)
- 新增 `volume_skeleton` 和 `foreshadowing_orchestration` 階段

### 進度條 UI 更新 (index.html)
- 🦴 簡易章綱 (Volume Skeleton)
- 🕸️ 伏筆編織 (Foreshadowing Orchestration)