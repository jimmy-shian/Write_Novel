# -*- coding: utf-8 -*-
import os

target_path = r"c:\Users\user\Desktop\test_html\新增資料夾\Write_Novel\agents_director.py"

with open(target_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace is_early_stage
old_early_stage = '''    # 💡 判斷是否為大綱生成之前的早期設定階段
    is_early_stage = (current_stage in ["init", "worldview", "worldview_review", "worldview_go_back", "characters", "characters_review", "characters_go_back"])'''

new_early_stage = '''    # 💡 判斷是否為大綱生成之前的早期設定階段
    is_early_stage = (current_stage in ["init", "worldview", "worldview_review", "worldview_go_back", "characters", "characters_review", "characters_go_back", "volumes", "volumes_review", "volumes_go_back"])'''

if old_early_stage in content:
    content = content.replace(old_early_stage, new_early_stage)
    print("Success: is_early_stage replaced.")
else:
    print("Error: old_early_stage not found!")

# 2. Replace pre_check_next_agent
old_pre_check = '''def pre_check_next_agent(novel_id, current_stage):
    """
    在總監決定前，透過程式對當前資料狀態進行基本健康度判斷，並識別即將準備呼叫的下一個 Agent。
    """
    from db import get_latest_worldbuilding, get_latest_characters, get_stitched_plot, get_all_chapters_latest
    
    wb = get_latest_worldbuilding(novel_id)
    has_wb = wb and len(wb.get("content", "").strip()) > 100
    
    char = get_latest_characters(novel_id)
    has_char = char and len(char.get("json_data", "").strip()) > 100
    
    plot_data = get_stitched_plot(novel_id)
    has_plot = plot_data and len(plot_data) > 0
    
    from db import get_all_volume_skeletons
    skeletons = get_all_volume_skeletons(novel_id) if hasattr(db, "get_all_volume_skeletons") else []
    has_skeletons = skeletons and len(skeletons) > 0
    
    has_foreshadowing_alloc = False
    if has_plot:
        for ch in plot_data.get("chapters", []):
            alloc = ch.get("allocated_tasks", {}) or {}
            if (alloc.get("foreshadowing_plants") or alloc.get("foreshadowing_payoffs") or alloc.get("turning_points")):
                has_foreshadowing_alloc = True
                break
                
    chapters = get_all_chapters_latest(novel_id)
    written_count = len(chapters)
    
    suggested_agent = ""
    status_summary = ""
    suggestion = ""
    
    if current_stage == "init":
        if not has_wb:
            suggested_agent = "世界觀架構師 (Story Architect Agent)"
            status_summary = "世界觀目前為空白。"
            suggestion = "請做出 CONTINUE 正常流向 worldview 的決策，以便開始規劃底層世界觀。"
        elif not has_char:
            suggested_agent = "角色設計師 (Character Designer Agent)"
            status_summary = "世界觀已就緒，但尚未生成角色聖經。"
            suggestion = "請做出 CONTINUE 進度到 characters 的決策，以便生成角色設計。"
        elif not has_skeletons:
            suggested_agent = "篇卷骨架規劃師 (Volume Skeleton Planner)"
            status_summary = "世界觀與角色已就緒，但尚未拆解篇卷章節骨架。"
            suggestion = "請做出 CONTINUE 進度到 volume_skeleton 的決策，以便為各卷章生成簡易大綱骨架。"
        elif not has_foreshadowing_alloc:
            suggested_agent = "伏筆編織導演 (Foreshadowing Orchestrator)"
            status_summary = "簡易大綱已生成，但尚未進行全局伏筆編織與對齊。"
            suggestion = "請做出 CONTINUE 進度到 foreshadowing_orchestration 的決策，將世界觀伏筆與轉折均勻分配到各章。"
        else:
            suggested_agent = "大綱規劃師 (Plot Planner Agent)"
            status_summary = "全書骨架與伏筆分配皆已就緒。"
            suggestion = "🚨 【當前重點】：請審查當前骨架與伏筆分佈演進。若無誤請 CONTINUE 進度到 plot 進行微觀大綱詳細展開。"
            
    elif current_stage in ["worldview", "worldview_review", "worldview_go_back"]:
        suggested_agent = "角色設計師 (Character Designer Agent)"
        if has_wb:
            status_summary = f"世界觀設定已就緒（字數：{len(wb.get('content', ''))} 字）。"
            suggestion = "若評估世界觀架構完整，請做出 CONTINUE 進度到 characters 的決策。"
        else:
            status_summary = "⚠️ 警報！資料庫中未檢測到有效世界觀設定！"
            suggestion = "不可繼續！必須決策 AUTO_REGENERATE target='worldview' 重新規劃世界觀！"
            
    elif current_stage in ["characters", "characters_review", "characters_go_back"]:
        suggested_agent = "篇卷骨架規劃師 (Volume Skeleton Planner)"
        if not has_wb:
            status_summary = "⚠️ 警報！缺失上游世界觀資料！"
            suggestion = "必須決策 GO_BACK_TO_WORLDVIEW 退回補全世界觀。"
        elif not has_char:
            status_summary = "⚠️ 警報！資料庫中角色聖經資料為空！"
            suggestion = "不可繼續！必須決策 AUTO_REGENERATE target='characters' 重新生成角色聖經！"
        else:
            status_summary = f"角色聖經已就緒（資料長度：{len(char.get('json_data', ''))} 字符）。"
            suggestion = "若角色設計滿意，請做出 CONTINUE 進度到 volume_skeleton 的決策。"
            
    elif current_stage in ["volume_skeleton", "skeleton_review"]:
        suggested_agent = "伏筆編織導演 (Foreshadowing Orchestrator)"
        if not has_skeletons:
            status_summary = "⚠️ 警報！尚未生成 any 篇卷大綱骨架！"
            suggestion = "必須決策 AUTO_REGENERATE target='volume_skeleton' 重新生成各卷簡易章大綱。"
        else:
            status_summary = f"簡易大綱骨架已生成，共 {len(skeletons)} 章。"
            suggestion = "若簡易大綱骨架結構完整，請做出 CONTINUE 進度到 foreshadowing_orchestration 的決策。"
            
    elif current_stage in ["foreshadowing_orchestration", "foreshadowing_review", "foreshadowing_align"]:
        suggested_agent = "大綱規劃師 (Plot Planner Agent)"
        if not has_foreshadowing_alloc:
            status_summary = "⚠️ 警告：資料庫尚未包含任何伏筆或轉折的分配描述！"
            suggestion = "不可進行下一步！請決策 AUTO_REGENERATE target='foreshadowing_orchestration' 重新進行伏筆編織對齊。"
        else:
            status_summary = "全局伏筆與關鍵轉折分配任務已完成並順利儲存。"
            suggestion = "若伏筆分配佈局滿意，請做出 CONTINUE 進度到 plot 的決策，以啟動 Stage 4：微觀大綱詳細展開。"
            
    elif current_stage in ["plot", "plot_review", "plot_go_back"]:
        suggested_agent = "正文寫作姬 (Novel Writer Agent)"
        if not has_wb or not has_char:
            status_summary = "⚠️ 警報！上游世界觀或角色資料不完整！"
            suggestion = "請做出 GO_BACK_TO_WORLDVIEW 或 GO_BACK_TO_CHARACTERS 決策退回修正。"
        elif not has_plot:
            status_summary = "⚠️ 警報！資料庫中尚未生成章節大綱！"
            suggestion = "不可寫作！必須決策 AUTO_REGENERATE target='plot' 重新生成大綱。"
        else:
            try:
                vol_count = len(set(c.get("volume_index", 1) for c in plot_data))
                status_summary = f"大綱已生成，共 {vol_count} 卷，{len(plot_data)} 章。"
            except Exception:
                status_summary = "大綱已生成但解析異常。"
            suggestion = "請仔細審核下方的情節完整性校驗報告。若無致命紅線 [紅色] 警告，請決策 WRITE_ALL_CHAPTERS 開始寫作或 CONTINUE 正常往下推進！"
            
    elif current_stage in ["writer", "writer_review"]:
        suggested_agent = "正文寫作姬 (Novel Writer Agent) / 全書完成"
        status_summary = f"正文已撰寫 {written_count} 章節。"
        suggestion = "若已寫正文無明顯漏洞且完成度高，可決策 CONTINUE 或 FINISH；若個別章節存在嚴重問題，可決策 AUTO_REGENERATE target='writer' 並指定卷章號重寫該章。"
        
    else:
        suggested_agent = "系統流程控制"
        status_summary = "未知或自訂階段。"
        suggestion = "請根據專案現狀做出最優下一步決策。"
        
    return f"""【程式基本判斷結果（總監決策前預檢）】：
- 🎯 當前階段：{current_stage}
- 準備呼叫的下一個 Agent：{suggested_agent}
- 📊 資料庫當前設定狀態：{status_summary}
- 💡 程式建議總監動作：{suggestion}"""'''

new_pre_check = '''def pre_check_next_agent(novel_id, current_stage):
    """
    在總監決定前，透過程式對當前資料狀態進行基本健康度判斷，並識別即將準備呼叫的下一個 Agent。
    """
    from db import get_latest_worldbuilding, get_latest_characters, get_stitched_plot, get_all_chapters_latest, get_volumes
    
    wb = get_latest_worldbuilding(novel_id)
    has_wb = wb and len(wb.get("content", "").strip()) > 100
    
    char = get_latest_characters(novel_id)
    has_char = char and len(char.get("json_data", "").strip()) > 100
    
    vols = get_volumes(novel_id)
    volumes_count = len(vols)
    has_volumes = volumes_count > 0
    
    plot_data = get_stitched_plot(novel_id)
    has_plot = plot_data and len(plot_data) > 0
    
    from db import get_all_volume_skeletons
    skeletons = get_all_volume_skeletons(novel_id) if hasattr(db, "get_all_volume_skeletons") else []
    has_skeletons = skeletons and len(skeletons) > 0
    
    has_foreshadowing_alloc = False
    if has_plot:
        for ch in plot_data.get("chapters", []):
            alloc = ch.get("allocated_tasks", {}) or {}
            if (alloc.get("foreshadowing_plants") or alloc.get("foreshadowing_payoffs") or alloc.get("turning_points")):
                has_foreshadowing_alloc = True
                break
                
    chapters = get_all_chapters_latest(novel_id)
    written_count = len(chapters)
    
    suggested_agent = ""
    status_summary = ""
    suggestion = ""
    
    if current_stage == "init":
        if not has_wb:
            suggested_agent = "世界觀架構師 (Story Architect Agent)"
            status_summary = "世界觀目前為空白。"
            suggestion = "請做出 CONTINUE 正常流向 worldview 的決策，以便開始規劃底層世界觀。"
        elif not has_char:
            suggested_agent = "角色設計師 (Character Designer Agent)"
            status_summary = "世界觀已就緒，但尚未生成角色聖經。"
            suggestion = "請做出 CONTINUE 進度到 characters 的決策，以便生成角色設計。"
        elif not has_volumes:
            suggested_agent = "篇卷結構規劃師 (Volumes Planner Agent)"
            status_summary = "世界觀與角色已就緒，但尚未規劃篇卷結構。"
            suggestion = "請做出 CONTINUE 進度到 volumes 的決策，以便規劃全書篇卷結構。"
        elif not has_skeletons:
            suggested_agent = "篇卷骨架規劃師 (Volume Skeleton Planner)"
            status_summary = "世界觀、角色與篇卷已就緒，但尚未拆解篇卷章節骨架。"
            suggestion = "請做出 CONTINUE 進度到 volume_skeleton 的決策，以便為各卷章生成簡易大綱骨架。"
        elif not has_foreshadowing_alloc:
            suggested_agent = "伏筆編織導演 (Foreshadowing Orchestrator)"
            status_summary = "簡易大綱已生成，但尚未進行全局伏筆編織與對齊。"
            suggestion = "請做出 CONTINUE 進度到 foreshadowing_orchestration 的決策，將世界觀伏筆與轉折均勻分配到各章。"
        else:
            suggested_agent = "大綱規劃師 (Plot Planner Agent)"
            status_summary = "全書骨架與伏筆分配皆已就緒。"
            suggestion = "🚨 【當前重點】：請審查當前骨架與伏筆分佈演進。若無誤請 CONTINUE 進度到 plot 進行微觀大綱詳細展開。"
            
    elif current_stage in ["worldview", "worldview_review", "worldview_go_back"]:
        suggested_agent = "角色設計師 (Character Designer Agent)"
        if has_wb:
            status_summary = f"世界觀設定已就緒（字數：{len(wb.get('content', ''))} 字）。"
            suggestion = "若評估世界觀架構完整，請做出 CONTINUE 進度到 characters 的決策。"
        else:
            status_summary = "⚠️ 警報！資料庫中未檢測到有效世界觀設定！"
            suggestion = "不可繼續！必須決策 AUTO_REGENERATE target='worldview' 重新規劃世界觀！"
            
    elif current_stage in ["characters", "characters_review", "characters_go_back"]:
        suggested_agent = "篇卷結構規劃師 (Volumes Planner Agent)"
        if not has_wb:
            status_summary = "⚠️ 警報！缺失上游世界觀資料！"
            suggestion = "必須決策 GO_BACK_TO_WORLDVIEW 退回補全世界觀。"
        elif not has_char:
            status_summary = "⚠️ 警報！資料庫中角色聖經資料為空！"
            suggestion = "不可繼續！必須決策 AUTO_REGENERATE target='characters' 重新生成角色聖經！"
        else:
            status_summary = f"角色聖經已就緒（資料長度：{len(char.get('json_data', ''))} 字符）。"
            suggestion = "若角色設計滿意，請做出 CONTINUE 進度到 volumes 的決策。"
            
    elif current_stage in ["volumes", "volumes_review", "volumes_go_back"]:
        suggested_agent = "篇卷骨架規劃師 (Volume Skeleton Planner)"
        if not has_wb or not has_char:
            status_summary = "⚠️ 警報！缺失上游世界觀或角色資料！"
            suggestion = "必須決策 GO_BACK_TO_WORLDVIEW 或 GO_BACK_TO_CHARACTERS 退回修正。"
        elif not has_volumes:
            status_summary = "⚠️ 警報！資料庫中篇卷規劃資料為空！"
            suggestion = "不可繼續！必須決策 AUTO_REGENERATE target='volumes' 重新生成篇卷劃分！"
        else:
            status_summary = f"篇卷劃分已就緒，共 {volumes_count} 卷。"
            suggestion = "若篇卷劃分滿意，請做出 CONTINUE 進度到 volume_skeleton 的決策。"
            
    elif current_stage in ["volume_skeleton", "skeleton_review"]:
        suggested_agent = "伏筆編織導演 (Foreshadowing Orchestrator)"
        if not has_skeletons:
            status_summary = "⚠️ 警報！尚未生成 any 篇卷大綱骨架！"
            suggestion = "必須決策 AUTO_REGENERATE target='volume_skeleton' 重新生成各卷簡易章大綱。"
        else:
            status_summary = f"簡易大綱骨架已生成，共 {len(skeletons)} 章。"
            suggestion = "若簡易大綱骨架結構完整，請做出 CONTINUE 進度到 foreshadowing_orchestration 的決策。"
            
    elif current_stage in ["foreshadowing_orchestration", "foreshadowing_review", "foreshadowing_align"]:
        suggested_agent = "大綱規劃師 (Plot Planner Agent)"
        if not has_foreshadowing_alloc:
            status_summary = "⚠️ 警告：資料庫尚未包含 any 伏筆或轉折的分配描述！"
            suggestion = "不可進行下一步！請決策 AUTO_REGENERATE target='foreshadowing_orchestration' 重新進行伏筆編織對齊。"
        else:
            status_summary = "全局伏筆與關鍵轉折分配任務已完成並順利儲存。"
            suggestion = "若伏筆分配佈局滿意，請做出 CONTINUE 進度到 plot 的決策，以啟動微觀大綱詳細展開。"
            
    elif current_stage in ["plot", "plot_review", "plot_go_back"]:
        suggested_agent = "正文寫作姬 (Novel Writer Agent)"
        if not has_wb or not has_char:
            status_summary = "⚠️ 警報！上游世界觀或角色資料不完整！"
            suggestion = "請做出 GO_BACK_TO_WORLDVIEW 或 GO_BACK_TO_CHARACTERS 決策退回修正。"
        elif not has_plot:
            status_summary = "⚠️ 警報！資料庫中尚未生成章節大綱！"
            suggestion = "不可寫作！必須決策 AUTO_REGENERATE target='plot' 重新生成大綱。"
        else:
            try:
                vol_count = len(set(c.get("volume_index", 1) for c in plot_data))
                status_summary = f"大綱已生成，共 {vol_count} 卷，{len(plot_data)} 章。"
            except Exception:
                status_summary = "大綱已生成但解析異常。"
            suggestion = "請仔細審核下方的情節完整性校驗報告。若無致命紅線 [紅色] 警告，請決策 WRITE_ALL_CHAPTERS 開始寫作或 CONTINUE 正常往下推進！"
            
    elif current_stage in ["writer", "writer_review"]:
        suggested_agent = "正文寫作姬 (Novel Writer Agent) / 全書完成"
        status_summary = f"正文已撰寫 {written_count} 章節。"
        suggestion = "若已寫正文無明顯漏洞且完成度高，可決策 CONTINUE 或 FINISH；若個別章節存在嚴重問題，可決策 AUTO_REGENERATE target='writer' 並指定卷章號重寫該章。"
        
    else:
        suggested_agent = "系統流程控制"
        status_summary = "未知或自訂階段。"
        suggestion = "請根據專案現狀做出最優下一步決策。"
        
    return f"""【程式基本判斷結果（總監決策前預檢）】：
- 🎯 當前階段：{current_stage}
- 準備呼叫的下一個 Agent：{suggested_agent}
- 📊 資料庫當前設定狀態：{status_summary}
- 💡 程式建議總監動作：{suggestion}"""'''

if old_pre_check in content:
    content = content.replace(old_pre_check, new_pre_check)
    print("Success: pre_check_next_agent replaced.")
else:
    print("Error: old_pre_check not found!")

# 3. Replace get_simplified_director_prompt
# First let's extract the start of the function and replace until the end
old_func_start = 'def get_simplified_director_prompt(current_stage, has_wb_and_char_at_init=False):'
new_simplified_prompt_func = '''def get_simplified_director_prompt(current_stage, has_wb_and_char_at_init=False):
    """
    根據總監評估的當前階段，動態生成極簡特化的 system prompt。
    重構版：引入「階梯式審查指引」、「篇卷規劃評估」與「細部修改語句提示說明」，確保總監能夠給出 100% 精準可執行的修改 hint。
    """
    common_header = """你是 AI 小說創作系統的【創意總監】，負責把控整個小說創作管道的品質與流程。
⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容（包含評估回應和JSON指令區塊）。

## 重要：你的回應將被系統自動解析並執行
- 你的回應末尾必須包含一個 JSON 格式的【執行指令區塊】
- 系統會解析你的 JSON 指令來決定下一步動作
- 你必須做出【果斷決策】，不可含糊

## 當前任務評估
你目前正在評估「{current_stage}」階段完成後的成果，判斷下一步動作。

## 當前已完成的工作成果（精簡 Context 視圖）
【世界觀】：{worldbuilding}
【角色 Bible】：{characters}
【章節大綱】：{plot}
【已寫作章節】：{written_chapters}
"""

    common_footer = """
## 可點擊可用的 ACTION 指令（嚴格選擇一個）

| ACTION | 用途 | 必要欄位 |
|--------|------|----------|
| `CONTINUE` | 當前階段品質合格，繼續下一階段 | `target`（下一階段名稱） |
| `AUTO_REGENERATE` | 當前階段品質不足，需要重新生成 | `target`（要重跑的階段）, `hint` (要修改的細項描述), `volume_index`（若與特定卷相關，填入整數；否則填 null）, `chapter_index`（若與特定章相關，填入整數；否則填 null） |
| `GO_BACK_TO_WORLDVIEW` | 發現世界觀需要調整（角色/大綱/正文暴露的問題） | `hint`（具體要修改的世界觀內容）, `volume_index`（若與特定卷相關，填入整數；否則填 null） |
| `GO_BACK_TO_CHARACTERS` | 發現角色設定需要調整 | `hint`（具體要修改的角色內容） |
| `GO_BACK_TO_PLOT` | 發現大綱需要調整 | `hint`（具體要修改大綱內容）, `volume_index`（若有，填入整數；否則填 null）, `chapter_index`（若有，填入整數；否則填 null） |
| `WRITE_ALL_CHAPTERS` | 大綱已就緒，開始自動撰寫所有章節正文 | 無 |
| `GO_BACK_TO_SKELETON_EXPANSION` | 發現章節缺漏、序號中斷或空殼章節，退回至骨架增生 (volume_skeleton) 重新生成大綱骨架 | 無 |
| `ADD_BRIDGE_CONTENT` | 【第一級修補】在當前第 N 章前後插入橋接大綱，補足連貫性與邏輯漏洞 | `chapter_index`（目前正文有問題的當前章 index $N$） |
| `MODIFY_CURRENT_CHAPTER` | 【第二級修補】調用編輯姬對當前第 N 章正文正篇進行局部微調與精修拋光 | `chapter_index`（欲精修的當前章 index $N$）, `hint`（具體微調精修的方向引導） |
| `GO_BACK_TO_PREVIOUS_STEP` | 【第三級修補】多次修補仍不符，徹底刪除前後 +-3 章大綱與正文，回退大綱重新編寫 | `chapter_index`（受損中心章 index $N$） |
| `help_worldview` | 請求調閱完整的世界觀詳細設定與結構 | `reason`（為什麼需要調閱此細項，請在此詳細寫下你摘要的問題） |
| `help_characters` | 請求調閱角色 Bible 完整的詳細 JSON 數據 | `reason`（為什麼需要調閱此細項，請在此詳細寫下你摘要的問題） |
| `help_plot` | 請求調閱完整的劇情大綱細部 JSON 數據 | `reason`（為什麼需要調閱此細項，請在此詳細寫下你摘要的問題） |
| `WAIT_USER` | 遇到重大歧義或需要用戶確認的決策 | `reason`（原因） |
| `FINISH` | 全部任務已完成 | 無 |

## 回應格式（嚴格遵守，否則解析出錯）
請用繁體中文提供簡潔的評估分析，然後在末尾輸出 JSON 指令區塊：

```
【總監評估】
- 當前階段：「{current_stage}」
- 完成品質：[優秀/良好/需要修改]
- 主要發現：[1-3 句具體評估]

【決策理由】
[簡要說明為什麼選擇這個 ACTION]
```

然後必須在回應最後輸出以下 JSON 區塊（系統靠此解析）：

```json
{{
  "action": "CONTINUE",
  "target": "characters",
  "hint": "",
  "reason": "決策原因說明。若你呼叫了 help_* 調閱，請在 reason 中詳細摘要你在此模組中發現的疑點與想調閱的原因",
  "volume_index": null,
  "chapter_index": null
}}
```

## 重要提醒
- ⚠️ 重要：所有輸出內容（包含評估回應）必須使用 zh-TW 繁體中文
- 🚨 審查規則放行紅線：只有當出現「【紅色致命阻斷級】」缺陷時，才可以使用 `AUTO_REGENERATE` 或 `GO_BACK_*` 動作駁回；如果報告中只包含「🟡 跨卷/長線伏筆暫未收束」或「世界觀登場率不為 100%」（因為當前是局部增量生成），這是正常現象，你「必須」做出 `CONTINUE` 或 `WRITE_ALL_CHAPTERS` 的決策予以放行！嚴禁因為跨卷伏筆或局部設定使用率而惡意阻斷開發管線。
- 🟢 【plot/plot_review 階段強制放行規則】：當 current_stage 為 `plot` 或 `plot_review` 時，除非大綱出現未登記的新角色需要 `GO_BACK_TO_CHARACTERS`，否則你**必須**直接輸出 `CONTINUE`，target=`plot`，不得以任何理由阻斷。此為最高優先的強制覆蓋規則。
"""

    if current_stage in ["init", "worldview", "worldview_review", "worldview_go_back"]:
        stage_focus = """
## 💡 當前審核重點：【世界觀設定與底層架構】
1. 評估世界觀核心設定、魔法系統/法則、世界衝突是否豐富合理。
2. 檢查多幕式結構是否規劃妥善。
3. **動態數據調閱**：為了防範 Context 膨脹，我們對下游的大綱與正文做了精簡隱藏。若你發現需要審查世界觀的所有子項細節以決定是否放行，**你必須發出 `help_worldview` 行動指令**，後端將會為你動態加載並回傳完整世界觀說明重新做決策！

## 🛠️ 本階段可使用的【細部修改語句與指令範例 (Hint Guidelines)】
如果你發現世界觀設定不夠滿意，需要呼叫 **AUTO_REGENERATE (target='worldview')** 或 **GO_BACK_TO_WORLDVIEW**，你必須在 `hint` 欄位中寫入極具體的修改要求。請參考以下範例：
- "請在世界觀設定中追加『魔法系統的限制與反噬代價』以增加危機感。"
- "請將陣營『光明神殿』的教義調整為虛偽殘暴，並增加其與『暗影兄弟會』的古老恩怨。"
- "起承轉合結構中，第三幕高潮請微調為男主角與女主角的反目，而不是單純的合力擊敗魔王。"
"""
        if has_wb_and_char_at_init:
            stage_focus += """
🔥【創意總監緊急指令 - 強調當前事項重點】：
當前系統中「世界觀設定」與「角色聖經」均已存在！請你深度並重新閱讀完整世界觀設定，查看是否有正確且精細地完成各個世界觀設定細項（如多幕式起承轉合、關鍵轉折、伏筆種子等）。
- 如果發現任何設定細項存在邏輯不符、漏洞或需要拋光，你必須立刻決策 `GO_BACK_TO_WORLDVIEW` 或 `GO_BACK_TO_CHARACTERS`（並在 `hint` 中詳細指明需要修改的細項描述），呼叫細項修改流程！
- 如果你審查後確認完全無誤、無任何邏輯疏漏，才可以決策 `CONTINUE` 進度到大綱（`plot`）正常流程。請嚴格執行此項評估，拒絕含糊！
"""

    elif current_stage in ["characters", "characters_review", "characters_go_back"]:
        stage_focus = """
## 💡 當前審核重點：【角色 Bible 與登場策略】
1. 評估核心角色的性格特點、動機、背景故事是否生動。
2. 審查角色漸進登場策略 (progressive_character_plan) 是否合理（是否避免了一開始出場太多角色）。
3. **動態數據調閱**：下游的大綱伏筆與描述已隱藏。若需要審查全套角色聖經完整 JSON，**你必須發出 `help_characters` 指令**，後端會為你動態加載並回傳完整數據重新決策！

## 🛠️ 本階段可使用的【細部修改語句與指令範例 (Hint Guidelines)】
如果你發現角色設定不夠滿意，需要呼叫 **AUTO_REGENERATE (target='characters')** 或 **GO_BACK_TO_CHARACTERS**，你必須在 `hint` 欄位中填寫精準修改方向。請參考以下範例：
- "角色『林楓』的 Want 與 Need 衝突不夠強烈，請將 Need 微調為『尋求家人的認可』，並增加『過度自負』的 Flaw。"
- "請新增一位女配角『蘇紫衣』，設定為林楓的師姐，冷若冰霜但身懷冰系秘術，在中期為林楓提供助力。"
- "修改『趙鐵柱』的漸進登場時機，將他從第 1 卷延後至第 2 卷登場，避免前期角色過多。"
"""

    elif current_stage in ["volumes", "volumes_review", "volumes_go_back"]:
        stage_focus = """
## 💡 當前審核重點：【全書篇卷結構劃分 (Volumes Planner)】
1. 評估整部書的篇卷切分是否合理（通常 5-15 卷）。
2. 每卷的標題是否具有足夠的張力，情節概要是否清晰且呼應世界觀發展。
3. 每卷規劃的章節數量是否得當，活躍勢力/陣營分配是否與世界觀一致。

## 🛠️ 本階段可使用的【細部修改語句與指令範例 (Hint Guidelines)】
如果你發現篇卷規劃切分不合理，需要呼叫 **AUTO_REGENERATE (target='volumes')**，你必須在 `hint` 欄位中寫入明確的改寫指示：
- "將第 2 卷『潛龍出淵』的章節數從 50 章縮減至 40 章，並將最後 10 章的情節高潮合併到第 3 卷。"
- "請在第 1 卷和第 2 卷之間，微創新增一卷『宗門大比』，著重描寫林楓奪冠並暴露天賦的情節，規劃 30 章。"
- "調整第 3 卷『魔界入侵』的活躍陣營，刪除『白馬書院』，改為『萬毒門』與『天道盟』的交鋒。"
"""

    elif current_stage in ["macro_skeleton", "skeleton_review", "foreshadowing_align", "volume_skeleton", "foreshadowing_orchestration"]:
        stage_focus = """
## 💡 當前審核重點：【全書千章宏觀大綱骨架與伏筆部署】
1. **規模校驗**：檢查小說是否已經完整拆解出各卷章的簡易骨架（標題與里程碑宣言）。
2. **素材厚度審計**：若發現大綱情節開始陷入重複、枯竭，說明上游世界觀與角色不夠用。你必須下達決策引導系統進行【增量創意膨脹（Creative Swelling）】，為故事注入全新人物角色！
3. **伏筆紅線**：每個伏筆的埋設與回收之間必須有足夠的戲劇跨度（跨卷張力）。

## 🎯 你的核心決策導向：
- 若全書骨架規模已足夠且長線佈局合理 ➔ 決策 `CONTINUE` 進入 `plot`（微觀大綱詳細展開階段）。
- 若情節枯竭、素材不足 ➔ 決策 `GO_BACK_TO_WORLDVIEW` 並在 `hint` 中給出具體的「世界觀膨脹/催生補丁」文學指導方針。

## 🛠️ 本階段可使用的【細部修改語句與指令範例 (Hint Guidelines)】
如果你發現簡易骨架或伏筆分配有瑕疵，需呼叫 **AUTO_REGENERATE**（針對 `volume_skeleton` 或 `foreshadowing_orchestration`），請使用具體提示語：
- 【骨架調整範例】："重新生成第 2 卷的簡易大綱骨架，在第 15 章和第 18 章之間插入『林楓誤入藏經閣發現禁忌殘卷』的情節。"
- 【伏筆調整範例】："加強伏筆『斷劍的來歷』的鋪陳：請在第 5 章、第 12 章增加該伏筆的蛛絲馬跡，並在第 35 章林楓突破時回收該伏筆。"
- 【轉折調整範例】："調整轉折點『大長老叛變』的爆發時機，將其從第 45 章提前到第 38 章，並在第 20 章和第 28 章增加大長老與外敵密信往來的伏筆。"
"""

    elif current_stage in ["plot", "plot_review", "plot_go_back"]:
        stage_focus = """
## 💡 當前審核重點：【大綱角色登記自動觸發】

> 🔒 **此階段你只有兩個允許的動作：`GO_BACK_TO_CHARACTERS` 或 `CONTINUE`（必選其一）。禁止使用任何其他 ACTION。**

### 決策流程（嚴格照做，不得繞過）：

**步驟 1 - 掃描新角色**：瀏覽大綱中 `characters_introduced` 欄位，檢查是否有任何角色名字**尚未出現在當前角色聖經（Character Bible）中**。

**步驟 2A - 若發現未登記新角色**：
- 立即決策 `GO_BACK_TO_CHARACTERS`
- 在 `hint` 中填寫：「大綱中出現新角色：[角色名稱]，請為其生成完整設定卡」
- 不需要做任何其他評估，直接執行

**步驟 2B - 若沒有未登記新角色（或大綱沒有角色介紹）**：
- 立即決策 `CONTINUE`，target 設為 `plot`
- 不需要做任何其他評估，直接放行

> ⚠️ 嚴格禁止：在此階段使用 `AUTO_REGENERATE`、`GO_BACK_TO_WORLDVIEW`、`GO_BACK_TO_PLOT`、`WAIT_USER`、`help_*` 等任何其他動作。大綱品質不在此審核範圍內。

## 🛠️ 本階段可使用的【細部修改語句與指令範例 (Hint Guidelines)】
（注：本階段在一般流程中只接受 CONTINUE 轉入寫作。但若在其他相關大綱精修或手動模式下，你需要指示 Plot Planner 增量修改時，以下為 hint 指導範例）：
- "精細重寫第 8 章的詳細大綱：增加多角色互動，讓『蘇紫衣』與『林楓』在藏經閣有一次因爭奪武技而起的心靈交鋒，並追加懸念結尾。"
- "在第 22 章大綱中增量追加『林楓的妹妹林雪』的細部行動，描寫她被反派擄走的驚險過程，強化救援任務的緊迫感。"
"""

    elif current_stage in ["writer", "writer_review"]:
        stage_focus = """
## 💡 當前審核重點：【正文正篇寫作品質與自癒】
1. 審核正篇小說寫作風格、對話自然度與鋪陳節奏。
2. 核對已寫正文是否與大綱情節、伏筆種子對齊，有無產生情節衝突。
3. 局部校驗連貫性：檢查當前已寫章節與前文的過渡是否自然，有無情節斷層。

## 🛠️ 本階段可使用的【細部修改語句與指令範例 (Hint Guidelines)】
正文正篇寫作階段擁有最細緻的「三級修補機制」。你必須根據品質判定，發出無比明確的修補 hint 與執行動作：
- **【第一級修補：ADD_BRIDGE_CONTENT】**：當檢測到章節與前文不連貫或情節突變時使用。
  - *範例*：若第 16 章與第 17 章情節跳躍，決策 `ADD_BRIDGE_CONTENT` (chapter_index=17)，系統會自動在中間插入橋接過渡大綱並生成正文。
- **【第二級修補：MODIFY_CURRENT_CHAPTER】**：當前章正文大綱合理，但細節筆觸、戰鬥張力或對白需要潤色時使用。
  - *範例*：決策 `MODIFY_CURRENT_CHAPTER` (chapter_index=15)，hint="林楓在擂台上的戰鬥描寫過於平淡，請加強施展『九天雷神訣』時的視覺特效與圍觀群眾的震撼反應。"
- **【第三級修補：GO_BACK_TO_PREVIOUS_STEP】**：多輪微調後仍存在嚴重邏輯崩塌或情節硬傷時使用。
  - *範例*：決策 `GO_BACK_TO_PREVIOUS_STEP` (chapter_index=20)，徹底刪除前後 +-3 章的大綱與正文，退回大綱規劃階段重跑。
"""

    else:
        stage_focus = """
## 💡 當前審核重點：【常規階段把關】
1. 檢查目前產出的資料是否合格。若無誤請決策 `CONTINUE`。
"""

    return common_header + stage_focus + "\\n{pre_check}\\n\\n## 系統底層結構完整性與情節邏輯校驗報告\\n{validation_report}\\n\\n## 用戶原始創作需求\\n{user_prompt}\\n" + common_footer'''

# To locate get_simplified_director_prompt and replace it, we can find:
start_idx = content.find(old_func_start)
if start_idx != -1:
    # Now let's find the end of this function. The next def is run_director_decision
    next_def = 'def run_director_decision(novel_id, current_stage, user_prompt):'
    end_idx = content.find(next_def)
    if end_idx != -1:
        content = content[:start_idx] + new_simplified_prompt_func + "\n\n" + content[end_idx:]
        print("Success: get_simplified_director_prompt replaced.")
    else:
        print("Error: next def run_director_decision not found!")
else:
    print("Error: get_simplified_director_prompt start not found!")

# 4. Add the effective_plot and effective_written_chapters handling for volumes stage
old_effective_slice = '''    elif current_stage in ["characters", "characters_review", "characters_go_back"]:
        effective_plot = "（大綱尚未規劃，隱藏大綱詳細設定，避免角色評審模糊焦點）"
        effective_written_chapters = "（正文寫作未開始，隱藏正文數據）"'''

new_effective_slice = '''    elif current_stage in ["characters", "characters_review", "characters_go_back"]:
        effective_plot = "（大綱尚未規劃，隱藏大綱詳細設定，避免角色評審模糊焦點）"
        effective_written_chapters = "（正文寫作未開始，隱藏正文數據）"
        
    elif current_stage in ["volumes", "volumes_review", "volumes_go_back"]:
        effective_plot = "（大綱尚未規劃，隱藏大綱詳細設定，避免篇卷評審模糊焦點）"
        effective_written_chapters = "（正文寫作未開始，隱藏正文數據）"'''

if old_effective_slice in content:
    content = content.replace(old_effective_slice, new_effective_slice)
    print("Success: effective_plot logic for volumes added.")
else:
    print("Error: old_effective_slice not found!")

# 5. Replace stage_labels in run_director_decision
old_stage_labels = '''    # Determine next stage label
    stage_labels = {
        "worldview": "世界觀設定",
        "characters": "角色設計",
        "plot": "章節大綱",
        "writer": "正文寫作"
    }'''

new_stage_labels = '''    # Determine next stage label
    stage_labels = {
        "worldview": "世界觀設定",
        "characters": "角色設計",
        "volumes": "篇卷規劃",
        "volume_skeleton": "篇卷骨架",
        "foreshadowing_orchestration": "分配伏筆轉折",
        "plot": "章節大綱",
        "writer": "正文寫作"
    }'''

if old_stage_labels in content:
    content = content.replace(old_stage_labels, new_stage_labels)
    print("Success: stage_labels replaced.")
else:
    print("Error: old_stage_labels not found!")

# Write back
with open(target_path, "w", encoding="utf-8") as f:
    f.write(content)
print("File successfully written.")
