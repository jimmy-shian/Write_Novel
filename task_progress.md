# 任務進度追蹤

## 問題描述
世界觀各項目的新增/刪除失敗，只有伏筆可以新增是不對的。每一個項目都要可以改（核心主題、核心衝突、世界觀設定、三幕式結構、整體故事大綱、角色漸進規劃策略、關鍵轉折點）。伏筆區域不見了。

## 已完成修復
- [x] 為每個世界觀區塊添加「編輯」和「刪除」按鈕
- [x] 實現 `editWorldviewSection` 函數 - 允許用戶編輯任何區塊內容
- [x] 實現 `deleteWorldviewSection` 函數 - 允許用戶刪除任何區塊
- [x] 實現 `addWorldviewSection` 函數 - 允許用戶新增區塊
- [x] 確保伏筆區域正確顯示（現在始終顯示在底部）

## 修改內容摘要
1. **更新 `renderWorldviewSection` 函數**：為所有區塊（核心主題、核心衝突、世界觀設定、三幕式結構、整體故事大綱）添加了 ✏️ 編輯和 🗑️ 刪除按鈕

2. **新增 `editWorldviewSection` 函數**：使用正則表達式替換指定區塊的內容

3. **新增 `deleteWorldviewSection` 函數**：使用正則表達式刪除整個區塊

4. **新增 `addWorldviewSection` 函數**：允許用戶新增新的區塊類型

5. **伏筆區域**：現在始終顯示在底部，包含 ➕ 新增按鈕和 ✕ 刪除按鈕

## 支援的區塊操作
| 區塊 | 編輯 | 刪除 | 新增 |
|------|------|------|------|
| 核心主題 | ✅ | ✅ | ✅ |
| 核心衝突 | ✅ | ✅ | ✅ |
| 世界觀設定 | ✅ | ✅ | ✅ |
| 三幕式結構 | ✅ | ✅ | ✅ |
| 整體故事大綱 | ✅ | ✅ | ✅ |
| 角色漸進規劃策略 | ✅ | ✅ | - |
| 關鍵轉折點 | ✅ | ✅ | - |
| 伏筆與設定種子 | - | ✅ | ✅ |

---

# Implementation Plan - Settings Syncing, Robust Stream Processing & Resilient AI Parsing

## 實作狀態

### 1. Database and Settings Component
- [x] **db.py**: 移除 DB Prepopulation，添加 migration query 清理空配置
  - 刪除 `db_init()` 中 prepopulate `agent_configs` 的迴圈
  - 添加 `DELETE FROM agent_configs WHERE api_key = '' OR api_key IS NULL` 清理空配置
- [x] **app.py**: 移除 `parse_worldview_to_json_robust` 函數和 monkeypatching

### 2. Frontend Interface and Stream Processing
- [x] **static/app.js**: 
  - 更新 `saveCurrentAgentSettings()` 正確處理 `0` 或 `0.0` 的 temperature 和 top_p
  - 確保 `enable_thinking` 正確讀取布林值
  - 在 `executePipelineStage()` 中添加 `failed` 標誌防止重複解析

### 3. Story Architect Parsing Logic
- [x] **agents_incremental.py**: 增強 `save_callback` 中的純文字解析 fallback
  - 實現 `_strip_bullet()` 去除項目符號前綴
  - 實現 `_extract_after_colon()` 提取冒號後內容
  - 實現 `_parse_bullet_list()` 解析 bullet list 為字串列表
  - 實現 `_parse_act_from_line()` 從單行解析 act 內容
  - 實現 `_parse_wave_from_line()` 從單行解析 wave 內容
  - 增強 `foreshadowing_seeds` 和 `key_turning_points` 的純文字 fallback
  - 增強 `three_act_structure` 和 `progressive_character_plan` 的純文字 fallback

## 驗證結果
- [x] `/api/settings` 端點正確返回 `.env` 配置
- [x] 應用程式成功啟動於 port 8001
- [x] 設定從 `.env` 正確載入（temperature、top_p、enable_thinking 等）
