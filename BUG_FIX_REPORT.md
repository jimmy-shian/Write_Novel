# 跨主後端級聯覆蓋 Bug 修復報告

## 🔍 問題診斷

### 核心原因：後端 Stage 4 的「毀滅性覆蓋」抹殺了骨架

1. **後端 Bug（根源）**：
   - 在 `db.py` 的 `update_volume_outline` 函數中
   - 當執行 Stage 4（細化微觀大綱）生成第 10 章時，後端會把新生成的第 10 章組成 `node_chapters` 數組傳入
   - 原來的代碼**直接全盤覆蓋**了該卷的 `chapters_outline`，導致原本存在的第 11~48 章骨架**集體被抹殺**

2. **前端Bug（為何修正後直接消失）**：
   - 前端 `renderers.js` 中加入了防禦邏輯：`if (realMaterialCount === 0)` 才補足到 50 章
   - 當第 10 章細化成功後，`realMaterialCount = 1`，前端關閉了自動生成空白格子的保底機制
   - 但資料庫裡的 11~48 章骨架已被後端覆蓋清空，導致第 11 章之後的卡片**直接消失**

## ✅ 修復方案

### Step 1：修復 `update_volume_outline` 函數（已完成）

**檔案**：`db.py`（第 616-653 行）

**改動**：將毀滅性覆蓋改為「智慧型增量合併」

#### 核心改進邏輯：

```python
def update_volume_outline(novel_id, volume_index, node_chapters):
    """
    [完美修復版] 將特定篇卷的高解像度微觀大綱更新至資料庫。
    採用智慧增量合併演算法，絕對不覆蓋抹殺同卷內其他已存在的 Stage 2 骨架章節。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 先讀取當前資料庫中該卷已存在的所有章節大綱/骨架
    row = cursor.execute(
        "SELECT chapters_outline FROM volumes WHERE novel_id = ? AND volume_index = ?", 
        (novel_id, volume_index)
    ).fetchone()
    
    existing_chapters = []
    if row and row["chapters_outline"]:
        try:
            parsed = json.loads(row["chapters_outline"])
            if isinstance(parsed, list):
                existing_chapters = parsed
        except:
            pass
            
    # 2. 建立 chapter_index -> chapter_obj 的字典緩衝區
    merged_map = {}
    for ch in existing_chapters:
        ch_idx = ch.get("chapter_index")
        if ch_idx is not None:
            merged_map[int(ch_idx)] = ch
            
    # 3. 用新生成的高解像度微觀章節精確覆蓋或插入緩衝區
    for nc in node_chapters:
        ch_idx = nc.get("chapter_index")
        if ch_idx is not None:
            merged_map[int(ch_idx)] = nc
            
    # 4. 重新轉回列表並依章節序號由小到大排序
    merged_chapters = list(merged_map.values())
    merged_chapters.sort(key=lambda x: int(x.get("chapter_index", 0)))
    
    # 5. 將融合後完整的章節池同步回寫至 volumes 表
    chapters_json = json.dumps(_convert_obj_to_traditional(merged_chapters), ensure_ascii=False)
    cursor.execute(
        "UPDATE volumes SET chapters_outline = ?, is_dirty = 0 WHERE novel_id = ? AND volume_index = ?",
        (chapters_json, novel_id, volume_index)
    )
    conn.commit()
    conn.close()
    
    # 6. 同步將融合後的完整列表縫合回 master plot_chapters 大綱主表
    plot = get_latest_plot_chapters(novel_id)
    all_ch = plot["parsed_data"].get("chapters", []) if plot else []
    
    filtered_ch = []
    vols = get_volumes(novel_id)
    for c in all_ch:
        ch_idx = c.get("chapter_index")
        if ch_idx is not None:
            c_vol = get_chapter_volume_index(vols, int(ch_idx))
            if c_vol != int(volume_index):
                filtered_ch.append(c)
        else:
            filtered_ch.append(c)
            
    # 將本次大融合後的完整章節列表推入主線大綱
    for mc in merged_chapters:
        filtered_ch.append(mc)
        
    # 全局排序
    filtered_ch.sort(key=lambda x: int(x.get("chapter_index", 0)) if x.get("chapter_index") is not None else 99999)
    
    # 7. 安全儲存回主線
    save_plot_chapters(novel_id, {"chapters": filtered_ch})
```

**算法特點**：
- 使用 `chapter_index` 作為鍵的字典映射，確保精確定位
- 保留所有現有章節骨架（Stage 2）
- 新生成的微觀章節（Stage 4）**精確覆蓋**同名索引的章節
- 最終結果：同卷內所有章節（包括未細化的骨架）完整保留

## 🔄 驗證流程

由於舊的 11~48 章骨架資料已經被毀滅性覆蓋抹殺了，請按以下步驟恢復：

1. **重新點擊 Stage 2（生成骨架大綱）**：
   - 讓後端分批滾動式生成器把第一卷的 48 章完整骨架重新寫入 `volumes` 資料表

2. **重新點擊 Stage 4（細化微觀大綱）**：
   - 為第 10 章重新生成微觀情節
   - 觸發增量合併邏輯，第 10 章升級為細緻 Prose 視圖
   - **11~48 章的骨架完整保留**，不會消失

## 📊 技術細節

| 層級 | 表格 | 欄位 | 處理方式 |
|------|------|------|----------|
| Volume Layer | `volumes` | `chapters_outline` | 增量合併（字典映射 + 排序） |
| Master Plot | `plot_chapters` | `outline_json` | 過濾重組 + 全局排序 |
| Chapter Content | `chapters` | `content` | 不影響（已寫內容安全） |

## 🎯 預期效果

- ✅ Stage 4 細化第 10 章後，第 11~48 章的骨架**不會消失**
- ✅ 前端 `renderers.js` 仍會顯示 `realMaterialCount = 1`（只細化了一章）
- ✅ 但由於資料庫保留了完整骨架，前端會正常渲染 11~48 章的空白格子
- ✅ 用戶可以繼續點擊任一章节進行細化

## 📝 程式碼變更摘要

| 檔案 | 函數 | 行數 | 變更類型 |
|------|------|------|----------|
| db.py | update_volume_outline | 616-653 | 完全替換（邏輯重寫） |
| db.py | 新增註釋 | - | 說明增量合併算法 |

---

**修復完成日期**：2025-05-25  
**修復工程師**：Cline  
**Bug 等級**：跨主後端級聯覆蓋（P0-Critical）

