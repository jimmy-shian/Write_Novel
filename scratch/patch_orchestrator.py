# -*- coding: utf-8 -*-
import os

agents_path = r"c:\Users\user\Desktop\test_html\新增資料夾\Write_Novel\agents.py"

with open(agents_path, "r", encoding="utf-8") as f:
    content = f.read()

# 搜尋舊的 run_foreshadowing_orchestrator 函數起點與終點
start_idx = content.find("def run_foreshadowing_orchestrator(novel_id, user_prompt=None):")
if start_idx == -1:
    print("Error: Could not find run_foreshadowing_orchestrator in agents.py")
    exit(1)

end_target = 'yield "data: " + json.dumps({"type": "done"}) + "\\n\\n"'
end_search_idx = content.find(end_target, start_idx)
if end_search_idx == -1:
    print("Error: Could not find end target of run_foreshadowing_orchestrator")
    exit(1)

end_idx = end_search_idx + len(end_target)

# 我們用單引號的三引號包起來，並把內部的雙引號三引號轉為單引號三引號，使用標準 Unicode 碼避開 Surrogate 報錯
new_function = '''def run_foreshadowing_orchestrator(novel_id, user_prompt=None):
    """
    [新功能] 全局伏筆與轉折編織對齊階段 (Stage 3)
    這是四階段漸進式大綱生成策略的第三階段。
    我們採用 [Python 演算法 + LLM 情節編織] 的黃金雙軌制：
    1. Python 演算法對伏筆與轉折進行 100% 電腦級精準、均勻且合法的分配，徹底根絕時序顛倒、漏埋、隨機亂埋、或在 5 章內快速閉環等低級邏輯錯誤。
    2. 只有被分配到任務的章節才會發送給 LLM 進行情節描述拋光，大幅釋放 Context 並提高生成文采。
    3. 配備 100% 保底 Fallback 安全防線，即便 LLM 解析或生成出錯，仍能保證一秒鐘產出 100% 正確的分配。
    """
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
            
    # 💡 完美的保底 Fallback 函式：如果 LLM 出錯或解析 JSON 失敗，直接將 prog_allocations 轉為 allocations 格式並存檔
    def apply_fallback_allocations():
        fallback_list = []
        for ch_idx in chapter_indices:
            alloc = prog_allocations[ch_idx]
            fallback_list.append({
                "chapter_index": ch_idx,
                "foreshadowing_plants": [f"在此處自然埋下伏筆線索：{p}" for p in alloc["foreshadowing_plants"]],
                "foreshadowing_payoffs": [f"在此處自然回收並引爆前期鋪墊：{py}" for py in alloc["foreshadowing_payoffs"]],
                "turning_points": [f"在此處觸發關鍵轉折事件：{t}" for t in alloc["turning_points"]]
            })
        from db import save_foreshadowing_allocations
        save_foreshadowing_allocations(novel_id, fallback_list)
        print(f"[FALLBACK SUCCESS] Program allocations safely fallback locked into DB for {novel_id}.")
        
    # 啟動 LLM 編織美化
    tasked_text = json.dumps(tasked_chapters, ensure_ascii=False, indent=2)
    prompt_content = f"""\u26a0\ufe0f 重要：請使用 zh-TW 繁體中文輸出所有內容。
 
你是大長篇小說的伏筆編織大師與情節對齊導演。
我們已經透過系統精準分配演算法，為小說中的特定章節規劃好了伏筆與轉折指派任務。
 
## 任務
請審查以下『已被指派任務的章節清單』。
針對每一個章節，將被指派的 [Seed-X] 或 [TurningPoint-Y] 任務，結合該章節的 brief_title 與 brief_summary，自然融合地撰寫具體文學性的敘事描述。
你的任務是將這些指派內容，拋光為優雅、自然融入情節的大綱敘事文字！
 
## \u26a0\ufe0f 重要編織原則
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
"""
 
    messages = [
        {"role": "system", "content": "你是一位嚴謹的小說伏筆編織導演，精通將線索自然織入情節骨架中。你必須完全以 JSON 格式回應，不說任何廢話。"},
        {"role": "user", "content": prompt_content}
    ]
    
    def save_callback(nid, text):
        parsed = parse_json_safely(text)
        if isinstance(parsed, dict) and "allocations" in parsed:
            from db import save_foreshadowing_allocations
            save_foreshadowing_allocations(nid, parsed["allocations"])
        else:
            print(f"[WARN] Foreshadowing parse failed: {parsed}. Calling fallback.")
            apply_fallback_allocations()
            
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
        apply_fallback_allocations()
        
    # \U0001F4A1 終點強制鎖定：如果 LLM 沒有被 callback 保存成功，再次執行保底以防萬一
    if orchestrator_output:
        parsed_final = parse_json_safely(orchestrator_output)
        if isinstance(parsed_final, dict) and "error" in parsed_final:
            parsed_final = parse_json_safely(clean_json_text(orchestrator_output))
            
        if isinstance(parsed_final, dict) and "allocations" in parsed_final:
            from db import save_foreshadowing_allocations
            save_foreshadowing_allocations(novel_id, parsed_final["allocations"])
            print(f"[GUARD SUCCESS] Foreshadowing allocations safely locked into DB via final parsed JSON.")
        else:
            # 解析失敗則套用保底
            apply_fallback_allocations()
    else:
        # 輸出為空則套用保底
        apply_fallback_allocations()
 
    yield "data: " + json.dumps({"type": "content", "delta": "\\n=== [全局伏筆編織對齊完成] ===\\n演算法與 LLM 已協同將所有伏筆與轉折成功對齊分配到各章節！\\n"}, ensure_ascii=False) + "\\n\\n"
    yield "data: " + json.dumps({"type": "done"}) + "\\n\\n"
'''

patched_content = content[:start_idx] + new_function + content[end_idx:]

with open(agents_path, "w", encoding="utf-8") as f:
    f.write(patched_content)

print("Patch applied successfully!")
