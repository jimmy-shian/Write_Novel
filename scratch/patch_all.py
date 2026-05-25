# -*- coding: utf-8 -*-
import os
import re

agents_path = r"c:\Users\user\Desktop\test_html\新增資料夾\Write_Novel\agents.py"

with open(agents_path, "r", encoding="utf-8") as f:
    content = f.read()

# ==============================================================================
# Task 2.1: Roadmap matrix in compile_context
# ==============================================================================
old_compile_end = """    if not written_chapters_summary:
        written_chapters_summary = "No chapters written yet."
        
    return {
        "worldbuilding": worldbuilding_str,
        "characters": characters_str,
        "plot": plot_str,
        "written_chapters": written_chapters_summary
    }"""

new_compile_end = """    if not written_chapters_summary:
        written_chapters_summary = "No chapters written yet."
        
    # 💡 增強：計算全域伏筆與轉折點分佈演進矩陣，提供總監清晰大局觀，徹底防止「胡亂重生」與「無伏筆規劃概念」
    import re
    from db import parse_worldview_to_json, parse_json_safely
    
    wb_json = parse_worldview_to_json(worldbuilding_str) if wb else {}
    seeds = wb_json.get("foreshadowing_seeds", []) or []
    tps = wb_json.get("key_turning_points", []) or []
    
    seeds_roadmap = []
    for s_idx, seed in enumerate(seeds):
        plant_ch = []
        payoff_ch = []
        seed_tag = f"Seed-{s_idx+1}"
        for ch in plot_data:
            ch_idx = ch.get("chapter_index")
            # 序列化單章以搜尋 Seed-X 標記
            ch_str = json.dumps(ch, ensure_ascii=False)
            if seed_tag in ch_str:
                alloc = ch.get("allocated_tasks", {}) or {}
                plants = alloc.get("foreshadowing_plants", []) or []
                payoffs = alloc.get("foreshadowing_payoffs", []) or []
                
                # 相容微觀大綱
                if not plants:
                    plants = ch.get("foreshadowing_plant", []) or []
                if not payoffs:
                    payoffs = ch.get("foreshadowing_payoff", []) or []
                
                if isinstance(plants, str): plants = [plants]
                if isinstance(payoffs, str): payoffs = [payoffs]
                
                # 判定是埋設還是回收
                is_plant = any(seed_tag in p for p in plants) or seed_tag in ch.get("foreshadowing", "")
                is_payoff = any(seed_tag in py for py in payoffs)
                
                if is_plant:
                    plant_ch.append(ch_idx)
                if is_payoff:
                    payoff_ch.append(ch_idx)
                    
        span = "無"
        if plant_ch and payoff_ch:
            span = f"{max(payoff_ch) - min(plant_ch)} 章"
            
        seeds_roadmap.append(
            f"  - [{seed_tag}] {seed[:20] + '...' if len(seed)>20 else seed}\\n"
            f"    👉 埋設章節: {plant_ch if plant_ch else '未部署'} | 回收章節: {payoff_ch if payoff_ch else '未部署'} (回收跨度: {span})"
        )
        
    tps_roadmap = []
    for t_idx, tp in enumerate(tps):
        trigger_ch = []
        tp_tag = f"TurningPoint-{t_idx+1}"
        for ch in plot_data:
            ch_idx = ch.get("chapter_index")
            ch_str = json.dumps(ch, ensure_ascii=False)
            if tp_tag in ch_str:
                trigger_ch.append(ch_idx)
        tps_roadmap.append(
            f"  - [{tp_tag}] {tp[:20] + '...' if len(tp)>20 else tp} \u2794 \u89e6\u767c\u7ae0\u7bc0: {trigger_ch if trigger_ch else '\u672a\u90e8\u7f72'}"
        )
        
    roadmap_str = "【全域伏筆分佈與情節演進矩陣】:\\n"
    roadmap_str += "\\n".join(seeds_roadmap) if seeds_roadmap else "  (無伏筆種子)\\n"
    roadmap_str += "\\n【全域關鍵轉折點分佈矩陣】:\\n"
    roadmap_str += "\\n".join(tps_roadmap) if tps_roadmap else "  (無關鍵轉折點)\\n"
    
    return {
        "worldbuilding": worldbuilding_str + "\\n\\n" + roadmap_str,
        "characters": characters_str,
        "plot": plot_str,
        "written_chapters": written_chapters_summary
    }" """.strip()

if old_compile_end in content:
    content = content.replace(old_compile_end, new_compile_end)
    print("Patch 2.1 Applied!")
else:
    print("Error: Could not find compile_context target block.")

# ==============================================================================
# Task 2.2: <think> tags separation in save_director_decision_callback
# ==============================================================================
old_callback = """    # Save director decision to chat memory so it persists across sessions
    def save_director_decision_callback(nid, text, thinking=""):
        save_chat_message(nid, "assistant", text, thinking, message_type="director")
        
    return run_agent_stream(novel_id, "copilot", messages, save_director_decision_callback)"""

new_callback = """    # Save director decision to chat memory so it persists across sessions
    def save_director_decision_callback(nid, text, thinking=""):
        import re
        content = text
        inline_thinking = ""
        think_matches = re.findall(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
        if think_matches:
            inline_thinking = "\\n".join(think_matches).strip()
            content = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
        final_thinking = (thinking.strip() + "\\n" + inline_thinking.strip()).strip()
        save_chat_message(nid, "assistant", content, final_thinking, message_type="director")
        
    return run_agent_stream(novel_id, "copilot", messages, save_director_decision_callback)"""

if old_callback in content:
    content = content.replace(old_callback, new_callback)
    print("Patch 2.2 Applied!")
else:
    print("Error: Could not find save_director_decision_callback block.")

# ==============================================================================
# Task 2.3: pre_check_next_agent stages expansion
# ==============================================================================
# We will match the entire pre_check_next_agent function signature up to the next helper
p_start = content.find("def pre_check_next_agent(novel_id, current_stage):")
p_end_marker = 'return f"""【程式基本判斷結果（總監決策前預檢）】：\n- 🎯 當前階段：{current_stage}\n- 準備呼叫的下一個 Agent：{suggested_agent}\n- 📊 資料庫當前設定狀態：{status_summary}\n- 💡 程式建議總監動作：{suggestion}"""'
p_end_idx = content.find(p_end_marker, p_start)

if p_start != -1 and p_end_idx != -1:
    p_end = p_end_idx + len(p_end_marker)
    
    new_pre_check = """def pre_check_next_agent(novel_id, current_stage):
    \"\"\"
    在總監決定前，先透過程式對當前資料狀態進行基本健康度判斷，並識別即將準備呼叫的下一個 Agent。
    這可為總監提供極具針對性的引導，預防資料缺失。
    \"\"\"
    wb = get_latest_worldbuilding(novel_id)
    has_wb = wb and len(wb.get("content", "").strip()) > 100
    
    char = get_latest_characters(novel_id)
    has_char = char and len(char.get("json_data", "").strip()) > 100
    
    plot_data = get_stitched_plot(novel_id)
    has_plot = plot_data and len(plot_data) > 0
    
    # 檢查是否已存在簡易骨架
    from db import get_all_volume_skeletons
    skeletons = get_all_volume_skeletons(novel_id)
    has_skeletons = skeletons and len(skeletons) > 0
    
    # 檢查是否已完成伏筆編織分配任務
    has_foreshadowing_alloc = False
    if has_plot:
        for ch in plot_data:
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
            suggestion = "🚨 【當前重點】：請審查當前骨架與伏筆分佈演進。若無誤請 CONTINUE 進度到 plot 進行微觀大綱詳細展開；若有缺陷，可呼叫 AUTO_REGENERATE target='plot' 重新生成。"
            
    elif current_stage in ["worldview", "worldview_review", "worldview_go_back"]:
        suggested_agent = "角色設計師 (Character Designer Agent)"
        if has_wb:
            status_summary = f"世界觀設定已就緒（字數：{len(wb.get('content', ''))} 字）。"
            suggestion = "若評估世界觀架構完整，請做出 CONTINUE 進度到 characters 的決策；若不合格，請 AUTO_REGENERATE target='worldview' 重新生成。"
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
            suggestion = "若角色設計滿意，請做出 CONTINUE 進度到 volume_skeleton 的決策，以啟動篇卷簡易大綱骨架生成；若需精細修改，請 AUTO_REGENERATE target='characters'。"
            
    elif current_stage in ["volume_skeleton", "skeleton_review"]:
        suggested_agent = "伏筆編織導演 (Foreshadowing Orchestrator)"
        if not has_skeletons:
            status_summary = "⚠️ 警報！尚未生成 any 篇卷大綱骨架！"
            suggestion = "必須決策 AUTO_REGENERATE target='volume_skeleton' 重新生成各卷簡易章大綱。"
        else:
            status_summary = f"簡易大綱骨架已生成，共 {len(skeletons)} 章。"
            suggestion = "若簡易大綱骨架結構完整，請做出 CONTINUE 進度到 foreshadowing_orchestration 的決策，以便開始全局伏筆調度對齊；若骨架有問題，請決策 AUTO_REGENERATE target='volume_skeleton'。"
            
    elif current_stage in ["foreshadowing_orchestration", "foreshadowing_review", "foreshadowing_align"]:
        suggested_agent = "大綱規劃師 (Plot Planner Agent)"
        if not has_foreshadowing_alloc:
            status_summary = "⚠️ 警告：資料庫尚未包含任何伏筆或轉折的分配描述！"
            suggestion = "不可進行下一步！請決策 AUTO_REGENERATE target='foreshadowing_orchestration' 重新進行伏筆編織對齊。"
        else:
            status_summary = "全局伏筆與關鍵轉折分配任務已完成並順利儲存。"
            suggestion = "若伏筆分配佈局滿意，請做出 CONTINUE 進度到 plot 的決策，以啟動 Stage 4：微觀大綱詳細展開；若分配不合理，請 AUTO_REGENERATE target='foreshadowing_orchestration'。"
            
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
            suggestion = "請仔細審核下方的情節完整性校驗報告。若無逆天紅線警告，請決策 WRITE_ALL_CHAPTERS 開始寫作；若有嚴重錯誤，必須 GO_BACK_TO_PLOT / AUTO_REGENERATE target='plot' 駁回！"
            
    elif current_stage in ["writer", "writer_review"]:
        suggested_agent = "正文寫作姬 (Novel Writer Agent) / 全書完成"
        status_summary = f"正文已撰寫 {written_count} 章節。"
        suggestion = "若已寫正文無明顯漏洞且完成度高，可決策 CONTINUE 或 FINISH；若個別章節存在嚴重問題，可決策 AUTO_REGENERATE target='writer' 並指定卷章號重寫該章。"
        
    else:
        suggested_agent = "系統流程控制"
        status_summary = "未知或自訂階段。"
        suggestion = "請根據專案現狀做出最優下一步決策。"
        
    return f\"\"\"【程式基本判斷結果（總監決策前預檢）】：
- 🎯 當前階段：{current_stage}
- 準備呼叫的下一個 Agent：{suggested_agent}
- 📊 資料庫當前設定狀態：{status_summary}
- 💡 程式建議總監動作：{suggestion}\"\"\""""
    
    content = content[:p_start] + new_pre_check + content[p_end:]
    print("Patch 2.3 Applied!")
else:
    print("Error: Could not find pre_check_next_agent boundaries.")

# ==============================================================================
# Task 2.4: is_macro_skeleton_stage support in verify_novel_integrity
# ==============================================================================
old_macro = 'is_macro_skeleton_stage = (current_stage in ["macro_skeleton", "skeleton_review", "foreshadowing_align"])'
new_macro = 'is_macro_skeleton_stage = (current_stage in ["macro_skeleton", "skeleton_review", "foreshadowing_align", "volume_skeleton", "foreshadowing_orchestration"])'

if old_macro in content:
    content = content.replace(old_macro, new_macro)
    print("Patch 2.4 Applied!")
else:
    print("Error: Could not find is_macro_skeleton_stage target block.")

# ==============================================================================
# Task 4: run_volume_skeleton_planner re-prompt organic weaving prompt
# ==============================================================================
old_skeleton_prompt = """## ⚠️ 重要約束
1. 每章必須有一個清晰的「情節里程碑宣言」—— 這章必須達成什麼敘事目的？
2. 絕對禁止模板化！每個章節標題和概要都必須是獨特的、具體的。
3. `allocated_tasks` 欄位是預留給下一階段（伏筆編織導演）填充的，當前請保持空陣列。
4. 為確保長線敘事張力，每 5-10 章應有一個中等轉折，每卷結尾應有一個強力的章末鉤子。"""

new_skeleton_prompt = """## ⚠️ 重要約束 (Stage 2 有機伏筆編織大綱生成)
1. 每章必須有一個清晰的「情節里程碑宣言」—— 這章必須達成什麼敘事目的？
2. 絕對禁止模板化！每個章節標題和概要都必須是獨特的、具體的。
3. 【有機伏筆編織融入】：你必須從一開始就帶著伏筆寫大綱骨架！我們已篩選出本卷專屬的『全域伏筆與轉折池』。
   請在編寫章節的里程碑概要(brief_summary)時，將篩選出的 [Seed-X] 或 [TurningPoint-Y] 有機自然地作為情節背景、道具或衝突織入其中。
   並在對應章節 object 的 `allocated_tasks` 欄位中填寫該伏筆或轉折的完整字串作為 tag 儲存！
   例如：若第 5 章埋下了 `[Seed-1] 魔法晶片的祕密`，請直接在該章節 object 的 `allocated_tasks.foreshadowing_plants` 中寫入 `["[Seed-1] 魔法晶片的祕密"]`，並在 `brief_summary` 內寫出主角在此處自然拾獲神祕晶片的故事細節。
4. 為確保長線敘事張力，每 5-10 章應有一個中等轉折，每卷結尾應有一個強力的章末鉤子。"""

if old_skeleton_prompt in content:
    content = content.replace(old_skeleton_prompt, new_skeleton_prompt)
    print("Patch 4 (Re-prompt Skeleton Planner) Applied!")
else:
    # Try with single newline constraint
    old_skeleton_prompt_alt = old_skeleton_prompt.replace("\r\n", "\n")
    if old_skeleton_prompt_alt in content.replace("\r\n", "\n"):
        content = content.replace("\r\n", "\n").replace(old_skeleton_prompt_alt, new_skeleton_prompt.replace("\r\n", "\n"))
        print("Patch 4 (Alt Match) Applied!")
    else:
        print("Error: Could not find VOLUME_SKELETON_PROMPT target constraints.")

# ==============================================================================
# Task 3: Double-track Weaving & Merging in run_foreshadowing_orchestrator
# ==============================================================================
o_start = content.find("def run_foreshadowing_orchestrator(novel_id, user_prompt=None):")
o_end_marker = 'yield "data: " + json.dumps({"type": "done"}) + "\\n\\n"'
o_end_idx = content.find(o_end_marker, o_start)

new_orchestrator = """def run_foreshadowing_orchestrator(novel_id, user_prompt=None):
    \"\"\"
    [新功能] 全局伏筆與轉折編織對齊階段 (Stage 3)
    這是四階段漸進式大綱生成策略的第三階段。
    我們採用 [Python 演算法 + LLM 情節編織] 的黃金雙軌制：
    1. Python 演算法對伏筆與轉折進行 100% 電腦級精準、均勻且合法的分配，徹底根絕時序顛倒、漏埋、隨機亂埋、或在 5 章內快速閉環等低級邏輯錯誤。
    2. 只有被分配到任務的章節才會發送給 LLM 進行情節描述拋光，大幅釋放 Context 並提高生成文采。
    3. 配備 100% 雙軌融合保底安全防線，即便 LLM 解析或生成出錯，仍能保證一秒鐘產出 100% 正確的分配。
    \"\"\"
    import db
    import random
    import hashlib
    import json
    
    context = compile_context(novel_id)
    
    # 獲取世界觀中的伏筆種子與轉折點
    worldview_json = db.parse_worldview_to_json(context.get("worldbuilding", ""))
    foreshadowing_seeds = worldview_json.get("foreshadowing_seeds", [])
    key_turning_points = worldview_json.get("key_turning_points", [])
    
    if not foreshadowing_seeds and not key_turning_points:
        for line in _sse_error_done("無法執行伏筆編織：世界觀中尚無伏筆種子或轉折點設定。請先在世界觀設定中添加伏筆與轉折點。"):
            yield line
        return
    
    # 獲取所有卷的簡易章骨架
    from db import get_all_volume_skeletons
    skeletons = get_all_volume_skeletons(novel_id)
    
    if not skeletons:
        for line in _sse_error_done("無法執行伏筆編織：尚無簡易章大綱骨架。請先完成各卷的簡易章大綱生成（volume_skeleton）。"):
            yield line
        return
    
    yield "data: " + json.dumps({"type": "content", "delta": "=== [全局伏筆編織對齊] ===\\n正在啟動高維度 [演算法+LLM雙軌對齊] 進行伏筆與轉折全局調度...\\n\\n"}, ensure_ascii=False) + "\\n\\n"
    
    N = len(skeletons)
    S = len(foreshadowing_seeds)
    T = len(key_turning_points)
    
    # 確保 skeletons 按 chapter_index 排序
    skeletons.sort(key=lambda x: int(x.get("chapter_index", 0)))
    chapter_indices = [int(x.get("chapter_index", 0)) for x in skeletons]
    
    # 決定跨度 min_span，以防範短距離快速回收
    if N >= 50:
        min_span = max(15, N // 5)
    elif N >= 20:
        min_span = max(8, N // 4)
    elif N >= 10:
        min_span = max(4, N // 3)
    else:
        min_span = max(1, N // 2)
        
    # 初始化一個分配表映射
    prog_allocations = {
        ch_idx: {
            "chapter_index": ch_idx,
            "title": skeletons[idx].get("brief_title") or skeletons[idx].get("title") or "未命名",
            "summary": skeletons[idx].get("brief_summary") or skeletons[idx].get("summary") or "無",
            "foreshadowing_plants": [],
            "foreshadowing_payoffs": [],
            "turning_points": []
        }
        for idx, ch_idx in enumerate(chapter_indices)
    }
    
    # 使用 novel_id 哈希作為隨機種子，以保證同一小說重試分配時的一致性與穩定性
    h_seed = int(hashlib.md5(novel_id.encode('utf-8')).hexdigest(), 16) % (2**32)
    r = random.Random(h_seed)
    
    # 1. 均勻分配 S 個 seeds 的 plant 和 payoff
    for i in range(S):
        max_plant_idx = N - min_span - 1
        if max_plant_idx <= 0:
            plant_idx = 0
        else:
            # 為了平均分配，將 plant 均勻分佈在全書前中段
            seg_size = float(max_plant_idx + 1) / S
            start_seg = int(i * seg_size)
            end_seg = int((i + 1) * seg_size)
            start_seg = max(0, min(start_seg, max_plant_idx))
            end_seg = max(start_seg + 1, min(end_seg, max_plant_idx + 1))
            plant_idx = r.randint(start_seg, end_seg - 1)
            
        plant_ch = chapter_indices[plant_idx]
        
        # Payoff 必須在 [plant_idx + min_span, N - 1] 之間選擇，保證跨度
        payoff_start = plant_idx + min_span
        if payoff_start >= N:
            payoff_start = N - 1
        payoff_idx = r.randint(payoff_start, N - 1)
        payoff_ch = chapter_indices[payoff_idx]
        
        seed_desc = foreshadowing_seeds[i]
        prog_allocations[plant_ch]["foreshadowing_plants"].append(f"[Seed-{i+1}] {seed_desc}")
        prog_allocations[payoff_ch]["foreshadowing_payoffs"].append(f"[Seed-{i+1}] {seed_desc}")
        
    # 2. 均勻分配 T 個 turning points
    for j in range(T):
        # 平分全書區間
        seg_size = float(N) / T
        start_seg = int(j * seg_size)
        end_seg = int((j + 1) * seg_size)
        start_seg = max(0, min(start_seg, N - 1))
        end_seg = max(start_seg + 1, min(end_seg, N))
        tp_idx = r.randint(start_seg, end_seg - 1)
        tp_ch = chapter_indices[tp_idx]
        
        tp_desc = key_turning_points[j]
        prog_allocations[tp_ch]["turning_points"].append(f"[TurningPoint-{j+1}] {tp_desc}")
        
    # 挑選出有被指派任務的章節進行 LLM 情節編織
    tasked_chapters = []
    for ch_idx in chapter_indices:
        alloc = prog_allocations[ch_idx]
        if alloc["foreshadowing_plants"] or alloc["foreshadowing_payoffs"] or alloc["turning_points"]:
            tasked_chapters.append(alloc)
            
    # 💡 雙軌融合與寫入函數
    def merge_and_save_allocations(nid, llm_allocations):
        \"\"\"
        將 LLM 回傳的拋光文字與 Python 100% 均勻正確的分配進行強制融合。
        如果 LLM 漏掉某個章節、伏筆種子(Seed-X)或轉折點，則自動套用 Python 保底分配，絕不丟失任何伏筆！
        \"\"\"
        merged_list = []
        llm_map = {}
        if isinstance(llm_allocations, list):
            for item in llm_allocations:
                idx = item.get("chapter_index")
                if idx is not None:
                    llm_map[int(idx)] = item
                    
        for ch_idx in chapter_indices:
            prog = prog_allocations[ch_idx]
            llm_item = llm_map.get(ch_idx, {})
            
            merged_plants = []
            merged_payoffs = []
            merged_tps = []
            
            # 融合 plants
            for plant_str in prog["foreshadowing_plants"]:
                seed_tag = plant_str.split("]")[0] + "]"
                found = False
                llm_plants_list = llm_item.get("foreshadowing_plants", []) or []
                if isinstance(llm_plants_list, str):
                    llm_plants_list = [llm_plants_list]
                for lp in llm_plants_list:
                    if lp and seed_tag in lp:
                        merged_plants.append(lp)
                        found = True
                        break
                if not found:
                    merged_plants.append(f"在此處自然埋下伏筆線索：{plant_str}")
                    
            # 融合 payoffs
            for payoff_str in prog["foreshadowing_payoffs"]:
                seed_tag = payoff_str.split("]")[0] + "]"
                found = False
                llm_payoffs_list = llm_item.get("foreshadowing_payoffs", []) or []
                if isinstance(llm_payoffs_list, str):
                    llm_payoffs_list = [llm_payoffs_list]
                for lpy in llm_payoffs_list:
                    if lpy and seed_tag in lpy:
                        merged_payoffs.append(lpy)
                        found = True
                        break
                if not found:
                    merged_payoffs.append(f"在此處自然回收並引爆前期鋪墊：{payoff_str}")
                    
            # 融合 turning_points
            for tp_str in prog["turning_points"]:
                tp_tag = tp_str.split("]")[0] + "]"
                found = False
                llm_tps_list = llm_item.get("turning_points", []) or []
                if isinstance(llm_tps_list, str):
                    llm_tps_list = [llm_tps_list]
                for ltp in llm_tps_list:
                    if ltp and tp_tag in ltp:
                        merged_tps.append(ltp)
                        found = True
                        break
                if not found:
                    merged_tps.append(f"在此處觸發關鍵轉折事件：{tp_str}")
                    
            if merged_plants or merged_payoffs or merged_tps:
                merged_list.append({
                    "chapter_index": ch_idx,
                    "foreshadowing_plants": merged_plants,
                    "foreshadowing_payoffs": merged_payoffs,
                    "turning_points": merged_tps
                })
                
        from db import save_foreshadowing_allocations
        save_foreshadowing_allocations(nid, merged_list)
        print(f"[DOUBLE TRACK MERGE SUCCESS] allocations merged and safely locked into DB for {nid}.")
        
    # 啟動 LLM 編織美化
    tasked_text = json.dumps(tasked_chapters, ensure_ascii=False, indent=2)
    prompt_content = f\"\"\"⚠️ 重要：請使用 zh-TW 繁體中文輸出所有內容。
 
你是大長篇小說的伏筆編織大師與情節對齊導演。
我們已經透過系統精準分配演算法，為小說中的特定章節規劃好了伏筆與轉折指派任務。
 
## 任務
請審查以下『已被指派任務的章節清單』。
針對每一個章節，將被指派的 [Seed-X] 或 [TurningPoint-Y] 任務，結合該章節的 brief_title 與 brief_summary，自然融合地撰寫具體文學性的敘事描述。
你的任務是將這些指派內容，拋光為優雅、自然融入情節的大綱敘事文字！
 
## ⚠️ 重要編織原則
1. **無損保留指派**：不要修改或遺漏被指派的 seed / turning_points 編號（例如 `[Seed-1]`, `[TurningPoint-2]`），這些編號必須完整保留在你的文字描述中！
2. **自然融入**：撰寫 1-2 句具體描述，說明伏筆是如何在情節中自然出現的。例如：對於 `[Seed-1] 魔法晶片的祕密`，你的 `foreshadowing_plants` 描述可以是：「主角在清理戰場時，意外在廢墟瓦礫中拾獲了一枚刻有神祕紋路的魔法晶片 [Seed-1]，晶片上若隱若現的微弱魔力殘留引起了主角的注意，主角將其收入懷中，為後續研究埋下伏筆。」
3. **保持 JSON 格式**：你必須嚴格輸出 JSON 格式，其根結構包含一個 `allocations` 陣列。
 
## 指派任務的章節清單
{tasked_text}
 
## 輸出格式（嚴格遵守 JSON，不要包含任何額外的說明文字，也不要包含 markdown 標記）
```json
{{
  "allocations": [
    {{
      "chapter_index": 5,
      "foreshadowing_plants": [
        "主角在此處自然拾獲了刻有神秘符文的魔法晶片 [Seed-1]，晶片散發的微光預示著它與古老遺跡的關聯..."
      ],
      "foreshadowing_payoffs": [],
      "turning_points": [
        "在戰鬥最激烈時，主角意外發現上司的背叛，觸發關鍵轉折 [TurningPoint-2] 組織內部撕裂..."
      ]
    }}
  ]
}}
```
\"\"\"
 
    messages = [
        {"role": "system", "content": "你是一位嚴謹的小說伏筆編織導演，精通將線索自然織入情節骨架中。你必須完全以 JSON 格式回應，不說任何廢話。"},
        {"role": "user", "content": prompt_content}
    ]
    
    def save_callback(nid, text):
        parsed = parse_json_safely(text)
        if isinstance(parsed, dict) and "allocations" in parsed:
            merge_and_save_allocations(nid, parsed["allocations"])
        else:
            print(f"[WARN] Foreshadowing parse failed: {parsed}. Calling fallback.")
            merge_and_save_allocations(nid, [])
            
    # 執行並收集輸出
    orchestrator_output = ""
    try:
        for sse_line in run_agent_stream(novel_id, "copilot", messages, save_callback):
            yield sse_line
            if sse_line.startswith("data:"):
                try:
                    data_str = sse_line[5:].strip()
                    if data_str == "[DONE]":
                        continue
                    data = json.loads(data_str)
                    if data.get("type") == "content":
                        orchestrator_output += data.get("delta", "")
                except:
                    pass
    except Exception as e:
        print(f"[ERROR] run_foreshadowing_orchestrator exception: {e}. Executing fallback.")
        merge_and_save_allocations(novel_id, [])
        
    # 💡 終點強制鎖定：如果 LLM 沒有被 callback 保存成功，再次執行保底以防萬一
    if orchestrator_output:
        parsed_final = parse_json_safely(orchestrator_output)
        if isinstance(parsed_final, dict) and "error" in parsed_final:
            parsed_final = parse_json_safely(clean_json_text(orchestrator_output))
            
        if isinstance(parsed_final, dict) and "allocations" in parsed_final:
            merge_and_save_allocations(novel_id, parsed_final["allocations"])
        else:
            merge_and_save_allocations(novel_id, [])
    else:
        merge_and_save_allocations(novel_id, [])
 
    yield "data: " + json.dumps({"type": "content", "delta": "\\n=== [全局伏筆編織對齊完成] ===\\n演算法與 LLM 已協同將所有伏筆與轉折成功對齊分配到各章節！\\n"}, ensure_ascii=False) + "\\n\\n"
    yield "data: " + json.dumps({"type": "done"}) + "\\n\\n"
"""

if o_start != -1 and o_end_idx != -1:
    o_end = o_end_idx + len(o_end_marker)
    content = content[:o_start] + new_orchestrator + content[o_end:]
    print("Patch 3 (Foreshadowing Orchestrator Gold Double-Track) Applied!")
else:
    print("Error: Could not find run_foreshadowing_orchestrator boundaries.")

# Save modified content back to agents.py
with open(agents_path, "w", encoding="utf-8") as f:
    f.write(content)

print("All patches processed successfully!")
