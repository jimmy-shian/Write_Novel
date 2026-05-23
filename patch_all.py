import os
import re
import json

raise SystemExit(
    "patch_all.py is a deprecated one-shot migration script. "
    "Do not run it: it contains an obsolete Plot Planner template with physical fallback placeholders."
)

workspace_dir = r"c:\Users\user\Desktop\test_html\新增資料夾\Write_Novel"
agents_path = os.path.join(workspace_dir, "agents.py")
agents_inc_path = os.path.join(workspace_dir, "agents_incremental.py")

# ==========================================
# 1. READ FILES WITH ROBUST ERROR HANDLING
# ==========================================
print("Reading agents.py...")
with open(agents_path, "r", encoding="utf-8", errors="ignore") as f:
    agents_content = f.read()

print("Reading agents_incremental.py...")
with open(agents_inc_path, "r", encoding="utf-8", errors="ignore") as f:
    agents_inc_content = f.read()

# ==========================================
# 2. PATCH agents.py STORY_ARCHITECT_PROMPT
# ==========================================
print("Updating STORY_ARCHITECT_PROMPT in agents.py...")

# We will locate the STORY_ARCHITECT_PROMPT definition and replace it.
new_story_architect = '''STORY_ARCHITECT_PROMPT = """你是一位頂尖的故事架構師（Story Architect）。
你的核心職責是設計整部小說的宏觀骨架。你專注於構建世界觀、提煉核心主題、設計戲劇衝突、規劃整體大綱以及角色的出場策略。你的任務是「搭骨架」而非「寫血肉」，因此請勿撰寫任何正文散文。

## 💡 設定無上限擴充原則（極致膨脹 30+ 規模）
為配合後續 1500 至 2000 章的小說情節縱向裂變，你的基礎設定層必須全面打破傳統百章級規模上限，每項核心指標均需動態膨脹至 **20 至 30 個以上** 的深度矩陣：

1. **🎯 核心主題與哲學命題**：由單一母題擴展為「多維主題矩陣」，包含核心衝突衍生出的次級社會學、倫理學或力量體系哲學思辨。
2. **⚔️ 核心衝突**：引入「多陣營、多情節線並行張力網」，將大衝突拆解為數十個環環相扣的階段性對抗與權力博弈。
3. **🌍 世界觀設定**：地理基調、力量層級、社會結構、氛圍符號必須進行增量擴充，提供極高密度的設定背景。
4. **📖 整體故事大綱**：擴展為「多段連續弧線」，讓主線在千章跨度中具備多次高潮疊起、波瀾壯闊的能力。
5. **📐 多幕式結構細化（不再局限於三幕）**：你必須規劃出包含自定義多個幕次/情節起落階段的「多幕式結構」（如：起、承、轉、合等多個動態階段，或第一幕、第二幕前段、第二幕後段、第三幕等），每幕內部必須各自細分出至少 6-8 個亞結構與階段性門檻目標，提供足夠的情節支撐力。
6. **👥 角色多階段漸進規劃策略**：分批次引入角色。設定明確的多個登場波次或階段（不限於三波，如起、承、轉、合、變、化等配合劇情的動態登場階段），防止數百個角色一次性載入導致過載。
7. **🔄 關鍵轉折點（無上限，強制 20-30 個以上）**：依據故事跨度，你必須設計出由大到小、環環相扣的不可逆【關鍵轉折點清單（Key Turning Points）】，**數量至少 20 至 30 個**。每個轉折必須明確標注「觸發條件」、「涉及角色」與「對世界/角色的不可逆質變影響」。
8. **🌱 伏筆種子庫（無上限，強制 20-30 個以上）**：精心設計豐富的【伏筆種子庫（Foreshadowing Seeds）】，**數量至少 20 至 30 個**。包含命運線索、背景道具、角色身世、歷史真相等。每個種子必須包含「早期埋設方式」與「中後期多階段收束/反轉方式」，拒絕任何漏網之魚。

## 輸出格式（嚴格遵守 JSON）
```json
{
  "worldview": "世界觀詳細描述（地理、力量體系、社會結構、氛圍基調）",
  "theme": "核心主題與多維哲學命題矩陣",
  "main_conflict": "多陣營、多情節線並行的核心衝突張力網",
  "macro_outline": "整體故事大綱（多段連續完整弧線）",
  "three_act_structure": [
    {
      "title": "幕次名稱 (例如：第一幕 起/Setup 或 第一幕 鋪墊)",
      "content": "詳細解構：包含鋪墊事件、世界引入、導火索與跨越門檻"
    },
    {
      "title": "幕次名稱 (例如：第二幕 承/Confrontation 或 第二幕 升級)",
      "content": "詳細解構：包含升級衝突、核心阻礙、中點反轉與不歸路節點"
    }
    // ... 允許並鼓勵你根據情節需要，自由擴展為任意多個幕次/起落階段的陣列 ...
  ],
  "progressive_character_plan": [
    {
      "title": "波次名稱 (例如：第一波 登場/Wave 1 或 核心登場期)",
      "content": "開篇登場的核心角色群及定位（包括登場時機與 Want/Need 預設）"
    },
    {
      "title": "波次名稱 (例如：第二波 發展/Wave 2 或 盟友對手期)",
      "content": "第二波引入的盟友、對手及登場時機與張力設定"
    }
    // ... 允許並鼓勵你根據角色成長及情節推進需要，自由設計更多階段 (如起、承、轉、合、變、化等步驟) ...
  ],
  "foreshadowing_seeds": [
    "伏筆種子 1：早期埋設點 -> 中期干擾/誤導 -> 後期震撼收束（請列出至少 20 至 30 個伏筆種子，以字串陣列呈現）",
    "伏筆種子 2：早期埋設點 -> 中期干擾/誤導 -> 後期震撼收束"
    // ... 強制擴展至 20 - 30+ 個項目 ...
  ],
  "key_turning_points": [
    "轉折點 1：觸發條件 + 涉及角色 + 不可逆事件描述 + 對主線的全局影響（請列出至少 20 至 30 個轉折點，以字串陣列呈現）",
    "轉折點 2：觸發條件 + 涉及角色 + 不可逆事件描述 + 對主線的全局影響"
    // ... 強制擴展至 20 - 30+ 個項目 ...
  ]
}
```"""'''

prompt_start_idx = agents_content.find('STORY_ARCHITECT_PROMPT = """你')
prompt_end_idx = agents_content.find('"""', prompt_start_idx + 100) if prompt_start_idx != -1 else -1

if prompt_start_idx != -1 and prompt_end_idx != -1:
    agents_content = agents_content[:prompt_start_idx] + new_story_architect + agents_content[prompt_end_idx + 3:]
    print("[SUCCESS] STORY_ARCHITECT_PROMPT replaced!")
else:
    print("[ERROR] STORY_ARCHITECT_PROMPT start/end index not found!")

# ==========================================
# 3. PATCH PROMPTS FOR AUTONOMOUS CHARACTER
# ==========================================
print("Patching autonomous character directives...")

# Define the directive string to append
char_directive_prose = """
5. **👥 角色自主擴充授權（新規則）**：在生成小說散文時，請以提供的主要角色為核心。允許並鼓勵你根據情節需要，自由創作並加入必要的次要角色（如：路人、市井小民、特定功能的敵手、帶路人等）。新角色需在登場時於括號內簡述其外貌與核心動機（例如：(老張-客棧老闆，貪財但心軟)），並確保其行為符合世界觀設定。"""

# Chapter Writer Prompt integration
writer_search = "4. **角色靈魂（Character Voice & Consistency）**："
writer_idx = agents_content.find(writer_search)
if writer_idx != -1:
    target_polish = "4. **角色靈魂（Character Voice & Consistency）**：本章登場角色的遣詞造句、語氣習慣、行為邏輯必須與其設定高度統一。"
    if target_polish in agents_content:
        agents_content = agents_content.replace(target_polish, target_polish + char_directive_prose)
        print("[SUCCESS] CHAPTER_WRITER_PROMPT updated!")
    else:
        idx = agents_content.find("\n", writer_idx)
        agents_content = agents_content[:idx] + char_directive_prose + agents_content[idx:]
        print("[SUCCESS] CHAPTER_WRITER_PROMPT updated (fallback)!")
else:
    print("[ERROR] CHAPTER_WRITER_PROMPT target not found!")

# ==========================================
# 4. REWRITE run_plot_planner (CHUNK GENERATOR)
# ==========================================
print("Replacing run_plot_planner with a highly robust 5-chapter chunk generator...")

new_plot_planner_code = """def run_plot_planner(novel_id, user_prompt=None):
    \"\"\"
    重構優化版：滾動式 5 章大綱生成器 (Chunk Generator)
    每次生成約 5 個章節大綱，避免一次性生成過多資訊導致上下文超載與幻覺。
    \"\"\"
    import json
    import re
    import db
    from llm import call_llm_stream

    context = compile_context(novel_id)

    ok_wb, _ = validate_worldview(context.get("worldbuilding", ""))
    ok_char, _ = validate_characters(context.get("characters", ""))
    if not ok_wb:
        for line in _sse_error_done("無法生成章節大綱：缺少世界觀設定。請先完成世界觀（worldview）。"):
            yield line
        return
    if not ok_char:
        for line in _sse_error_done("無法生成章節大綱：缺少角色設定（Character Bible）。請先完成角色設計（characters）。"):
            yield line
        return

    # 1. 載入現有大綱以決定起始章節
    plot = db.get_latest_plot_chapters(novel_id)
    existing_chapters = []
    if plot and "parsed_data" in plot:
        existing_chapters = plot["parsed_data"].get("chapters", [])
    
    last_chapter_index = 0
    if existing_chapters:
        last_chapter_index = existing_chapters[-1].get("chapter_index", 0)
        
    start_chapter = last_chapter_index + 1
    end_chapter = start_chapter + 4 # 每次生成剛好 5 章
    
    yield "data: " + json.dumps({"type": "content", "delta": f"=== [滾動式大綱生成] ===\\n目前已規劃 {last_chapter_index} 章。正在規劃接下來的第 {start_chapter} 章至第 {end_chapter} 章大綱...\\n\\n"}, ensure_ascii=False) + "\\n\\n"

    # 2. 構建前文銜接上下文 (最後 3 章)
    prev_chapters_context = ""
    if existing_chapters:
        last_few = existing_chapters[-3:]
        prev_chapters_context = "【前文已生成的章節大綱銜接參考】:\\n"
        for ch in last_few:
            prev_chapters_context += f"- 第 {ch.get('chapter_index')} 章《{ch.get('title')}》: {ch.get('summary')} (懸念: {ch.get('cliffhanger')})\\n"

    # 3. 呼叫大綱設計大師
    planner_prompt = f\"\"\"以下是已確立的世界觀與角色聖經：
【世界觀設定】
{context['worldbuilding']}

【角色聖經】
{context['characters']}

{prev_chapters_context or "這是整部小說的前 5 章，為開篇大綱。"}

現在，請繼續為這部小說精細規劃**接下來的 5 個章節大綱**（項目數量必須精確為 5 個，章節序號必須是第 {start_chapter} 章至第 {end_chapter} 章）：

## 💡 深度編織與消耗指令（硬性紅線）
1. **強行編織入章**：你規劃的每一個章節大綱，**必須主動挑選並填入**當前最適合埋設的世界觀伏筆種子或關鍵轉折點。
2. **👥 角色自主擴充授權（新規則）**：在大綱生成時，請以主要角色為核心。允許並鼓勵你根據情節需要，自由創作並加入必要的次要角色（如：路人、市井小民、特定功能的敵手、帶路人等），並在 characters_active / characters_introduced 中列出。新角色需在登場的 events 中於括號內簡述其外貌與核心動機（例如：(老張-客棧老闆，貪財但心軟)），並確保其行為符合世界觀設定。
3. **因果銜接**：必須保持時間線的完美連續性，情節衝突飽滿，並在 cliffhanger 中引爆懸念。

請嚴格包裹在 ```json ... ``` 區塊中輸出，格式如下：
```json
{{
  "chapters": [
    {{
      "chapter_index": {start_chapter},
      "title": "章節標題",
      "time_setting": "故事內時間座標",
      "time_span": "距前章時間跨度",
      "events": [
        {{"scene": "場景描述", "action": "核心動作/衝突 (新登場的次要角色請括號簡述)", "consequence": "帶來的後果或轉變"}}
      ],
      "purpose": "本章敘事目的",
      "foreshadowing_plant": ["本章埋設的具體伏筆"],
      "foreshadowing_payoff": ["精準對接並回收的舊伏筆"],
      "characters_active": ["活躍主要或次要角色"],
      "characters_introduced": ["本章新登場的主要或次要角色 (若有，如 老張)"],
      "scene": "主要場景",
      "emotional_tone": "情緒基調",
      "cliffhanger": "強烈懸念鉤子"
    }}
  ]
}}
```
\"\"\"
    messages_expander = [
        {"role": "system", "content": "你是一位頂尖的微觀劇情規劃大師。你只輸出嚴格、合法、無多餘寒暄的標準 JSON 數據。"},
        {"role": "user", "content": planner_prompt}
    ]

    expanded_output = ""
    for sse_line in call_llm_stream("plot", messages_expander):
        yield sse_line
        if sse_line.startswith("data:"):
            try:
                data_str = sse_line[5:].strip()
                if data_str == "[DONE]":
                    continue
                data = json.loads(data_str)
                if data.get("type") == "content":
                    expanded_output += data.get("delta", "")
            except:
                pass

    # 4. 解析生成的微觀章節
    parsed_node = parse_json_safely(expanded_output)
    if isinstance(parsed_node, dict) and "error" in parsed_node:
        parsed_node = parse_json_safely(clean_json_text(expanded_output))

    node_chapters = []
    if isinstance(parsed_node, dict) and "chapters" in parsed_node:
        node_chapters = parsed_node["chapters"]
    elif isinstance(parsed_node, list):
        node_chapters = parsed_node

    if not node_chapters:
        yield "data: " + json.dumps({"type": "content", "delta": f"  ⚠️ 解析失敗，系統啟動物理保底分裂引擎...\\n"}, ensure_ascii=False) + "\\n\\n"
        # 物理保底生成 5 章
        for sub_idx in range(5):
            ch_idx = start_chapter + sub_idx
            node_chapters.append({
                "chapter_index": ch_idx,
                "title": f"命運波折之章 (保底)",
                "time_setting": "緊接前章",
                "time_span": "緊接前章",
                "summary": "推進核心衝突與轉折點發展。",
                "events": [{"scene": "主場景", "action": "推動大綱情節發展，主角面臨新考驗。", "consequence": "推動大綱情節發展"}],
                "purpose": "推進劇情",
                "foreshadowing_plant": [],
                "foreshadowing_payoff": [],
                "characters_active": [],
                "scene": "主場景",
                "emotional_tone": "均衡",
                "cliffhanger": "留下懸念引發期待"
            })

    # 5. 確保 chapter_index 的連續性與正確性
    for idx, ch in enumerate(node_chapters):
        ch["chapter_index"] = start_chapter + idx

    # 6. 👥 反向增量動態縫合 (Lore Unbounded) - 檢查新角色並縫合回資料庫
    newly_emerged_characters = []
    worldview_content = context["worldbuilding"]
    worldview_json = db.parse_worldview_to_json(worldview_content)
    
    for ch in node_chapters:
        introduced = ch.get("characters_introduced") or ch.get("characters_active", [])
        for c in introduced:
            if isinstance(c, str) and c:
                char_bible = db.get_latest_characters(novel_id)
                char_list = char_bible["parsed_data"].get("characters", []) if char_bible else []
                if not any(x.get("name") == c for x in char_list):
                    newly_emerged_characters.append(c)

    if newly_emerged_characters:
        newly_emerged_characters = list(set(newly_emerged_characters))
        yield "data: " + json.dumps({"type": "content", "delta": f"  🧵 [反向縫合] 偵測到新湧現的次要角色 {', '.join(newly_emerged_characters)}，精準增量追加回角色 Bible 設定末尾...\\n"}, ensure_ascii=False) + "\\n\\n"
        
        char_bible = db.get_latest_characters(novel_id)
        pd = char_bible["parsed_data"] if char_bible else {"characters": []}
        if "characters" not in pd:
            pd["characters"] = []
            
        for nc in newly_emerged_characters:
            desc = "新登場的次要角色"
            for ch in node_chapters:
                for ev in ch.get("events", []):
                    action_text = ev.get("action", "")
                    match = re.search(r'[\\(（]' + re.escape(nc) + r'[-－:：\\s]+([^）\\)]+)[\\)）]', action_text)
                    if match:
                        desc = match.group(1).strip()
                        break
            
            pd["characters"].append({
                "name": nc,
                "role": "配角",
                "entry_phase": f"第 {start_chapter} 章登場",
                "personality": [desc.split("，")[0] if "，" in desc else desc],
                "speech_style": "符合人設說話風格",
                "want": "隨劇情展開的外在目標",
                "need": "隨劇情展開的內在需求",
                "fatal_flaw": "未知缺陷",
                "motivation": desc,
                "arc": "待演變的弧線",
                "relationships": []
            })
        db.save_characters(novel_id, pd)

    # 7. 合併並保存整本大綱到 SQLite
    all_micro_chapters = list(existing_chapters)
    
    for new_ch in node_chapters:
        ch_idx = new_ch["chapter_index"]
        all_micro_chapters = [c for c in all_micro_chapters if c.get("chapter_index") != ch_idx]
        all_micro_chapters.append(new_ch)
        
    all_micro_chapters.sort(key=lambda x: x.get("chapter_index", 0))

    final_dict = {"chapters": all_micro_chapters}
    db.save_plot_chapters(novel_id, final_dict)

    yield "data: " + json.dumps({"type": "content", "delta": f"\\n\\n=== [大綱生成完成] ===\\n第 {start_chapter} 章至第 {end_chapter} 章大綱已規劃完成！目前全書共 {len(all_micro_chapters)} 章。已成功保存！\\n\\n"}, ensure_ascii=False) + "\\n\\n"
    yield "data: " + json.dumps({"type": "done"}) + "\\n\\n"
"""

# Replace run_plot_planner in agents.py using index search
planner_start_idx = agents_content.find("def run_plot_planner(novel_id,")
planner_end_idx = agents_content.find("def generate_chapter_synopsis(", planner_start_idx)
if planner_end_idx == -1:
    planner_end_idx = agents_content.find("def run_chapter_writer(", planner_start_idx)

if planner_start_idx != -1 and planner_end_idx != -1:
    agents_content = agents_content[:planner_start_idx] + new_plot_planner_code + "\n\n" + agents_content[planner_end_idx:]
    print("[SUCCESS] run_plot_planner replaced with 5-chapter rolling chunk generator!")
else:
    print("[ERROR] run_plot_planner start/end index not found!")

# ==========================================
# 5. WRITE BACK AGENTS.PY AS UTF-8
# ==========================================
print("Writing patched agents.py back in pure UTF-8...")
with open(agents_path, "w", encoding="utf-8") as f:
    f.write(agents_content)
print("agents.py saved successfully!")

# ==========================================
# 6. PATCH agents_incremental.py FOR LISTS
# ==========================================
print("Patching agents_incremental.py dynamic lists...")

inc_search = """        elif target_section == "three_act_structure":
            act_data = parsed.get("three_act_structure", parsed)
            if isinstance(act_data, dict):
                for key in ["act1_setup", "act2_confrontation", "act3_resolution"]:
                    if key in act_data:
                        current_json["three_act_structure"][key] = act_data[key]
                        
        elif target_section == "progressive_character_plan":
            plan_data = parsed.get("progressive_character_plan", parsed)
            if isinstance(plan_data, dict):
                for key in ["wave_1_opening", "wave_2_development", "wave_3_climax"]:
                    if key in plan_data:
                        current_json["progressive_character_plan"][key] = plan_data[key]"""

inc_replace = """        elif target_section == "three_act_structure":
            act_data = parsed.get("three_act_structure", parsed)
            if isinstance(act_data, list):
                current_json["three_act_structure"] = act_data
            elif isinstance(act_data, dict):
                current_json["three_act_structure"] = [
                    {"title": "第一幕 (Setup)", "content": act_data.get("act1_setup", act_data.get("act1", ""))},
                    {"title": "第二幕 (Confrontation)", "content": act_data.get("act2_confrontation", act_data.get("act2", ""))},
                    {"title": "第三幕 (Resolution)", "content": act_data.get("act3_resolution", act_data.get("act3", ""))}
                ]
                        
        elif target_section == "progressive_character_plan":
            plan_data = parsed.get("progressive_character_plan", parsed)
            if isinstance(plan_data, list):
                current_json["progressive_character_plan"] = plan_data
            elif isinstance(plan_data, dict):
                current_json["progressive_character_plan"] = [
                    {"title": "第一波開篇 (Wave 1)", "content": plan_data.get("wave_1_opening", "")},
                    {"title": "第二波發展 (Wave 2)", "content": plan_data.get("wave_2_development", "")},
                    {"title": "第三波高潮 (Wave 3)", "content": plan_data.get("wave_3_climax", "")}
                ]"""

if inc_search in agents_inc_content:
    agents_inc_content = agents_inc_content.replace(inc_search, inc_replace)
    print("agents_incremental.py patched!")
else:
    normalized_inc_search = inc_search.replace("\r\n", "\n")
    if normalized_inc_search in agents_inc_content.replace("\r\n", "\n"):
        agents_inc_content = agents_inc_content.replace("\r\n", "\n").replace(normalized_inc_search, inc_replace)
        print("agents_incremental.py patched (normalized)!")
    else:
        print("[ERROR] agents_incremental.py target not found!")

# Write back agents_incremental.py in pure UTF-8
print("Writing patched agents_incremental.py back in pure UTF-8...")
with open(agents_inc_path, "w", encoding="utf-8") as f:
    f.write(agents_inc_content)
print("agents_incremental.py saved successfully!")

# Remove temporary patch.py
if os.path.exists(os.path.join(workspace_dir, "patch.py")):
    os.remove(os.path.join(workspace_dir, "patch.py"))

print("=== ALL PYTHON BACKEND & PROMPT PATCHES COMPLETED SUCCESSFULY ===")
