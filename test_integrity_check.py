# -*- coding: utf-8 -*-
import os
import sys
import io
import json

# Force UTF-8 encoding on standard streams to prevent cp950 errors on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Ensure we can import from workspace directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import db
from agents import verify_novel_integrity, parse_json_safely

def run_tests():
    print("====================================================")
    print("[TEST] 開始執行「總監大綱與情節邏輯校驗機制」單一完整測試")
    print("====================================================")
    
    # 1. 初始化資料庫
    db.db_init()
    
    # 建立測試小說 ID
    novel_id = "test_integrity_novel_id"
    
    # 清理已有舊測試資料
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
    cursor.execute("DELETE FROM worldbuilding WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM characters WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM plot_chapters WHERE novel_id = ?", (novel_id,))
    cursor.execute("DELETE FROM volumes WHERE novel_id = ?", (novel_id,))
    conn.commit()
    conn.close()
    
    # 建立測試小說
    db.create_novel(novel_id, "測試永夜之光", "奇幻", "史詩文風")
    
    # 2. 定義測試用世界觀設定 (JSON 格式)
    worldview_data = {
        "theme": "生命的代價與光明的追尋",
        "main_conflict": "燈火城邦與永夜荒原的對立，以及守夜人內部的燃壽抉擇",
        "worldview": "一個被永夜籠罩的世界，人類只能依賴命燈散發出的微弱光芒建立城邦，而點燃命燈需要消耗人的壽命。",
        "macro_outline": "主角林澤從一個普通荒原拾荒者，逐步發掘出古神留下的電路晶片，點燃不朽命燈，最終終結永夜的故事。",
        "three_act_structure": [
            {"title": "第一幕 (Setup)", "content": "林澤在荒原邊緣拾荒，意外點燃了自己靈魂深處的神秘命燈碎片，引起守夜人注意。"},
            {"title": "第二幕 (Confrontation)", "content": "林澤加入守夜人，在燈火城邦中與妖魔對抗，並面對高層為了維持城邦不惜犧牲平民壽命的殘酷真相。"},
            {"title": "第三幕 (Resolution)", "content": "林澤深入永夜核心，以自身殘壽與古神晶片共鳴，打破永夜封印，將太陽重新帶回人間。"}
        ],
        "progressive_character_plan": [
            {"title": "第一波開篇 (Wave 1)", "content": "林澤登場，初始狀態為懦弱、只求苟活的荒原流民。"},
            {"title": "第二波發展 (Wave 2)", "content": "林澤在守夜人訓練中成長，目睹犧牲，產生守護他人的堅定決心。"},
            {"title": "第三波高潮 (Wave 3)", "content": "林澤最終蛻變，捨生取義，達成靈魂的最終昇華。"}
        ],
        "foreshadowing_seeds": [
            "Seed-1: 點燃不朽命燈需要特定的古神電路紋路晶片作為媒介（早期暗示）",
            "Seed-2: 守夜人高層長老其實都是點燃了邪惡命燈、靠吸取平民壽命維持生存的叛徒",
            "Seed-3: 林澤身上佩戴的黑石吊墜，其實是古神的核心啟動鑰匙"
        ],
        "key_turning_points": [
            "TurningPoint-1: 林澤在荒原廢墟中挖出晶片，首次引發天地異象",
            "TurningPoint-2: 林澤的好明在一次妖魔潮中為了保護城邦，被迫超載命燈燃盡壽命而死",
            "TurningPoint-3: 林澤發現黑石吊墜與永夜大門的凹槽完美契合，得知自己身世"
        ]
    }
    
    db.save_worldbuilding(novel_id, json.dumps(worldview_data, ensure_ascii=False, indent=2))
    
    # 建立篇卷
    volumes_list = [
        {
            "volume_index": 1,
            "title": "第一卷：荒原之火",
            "summary": "描述林澤在荒原的生活與命燈啟蒙",
            "factions": ["荒原流民部族", "城邦守夜人先鋒隊"]
        },
        {
            "volume_index": 2,
            "title": "第二卷：燈火之影",
            "summary": "林澤進入城邦，觸碰守夜人權力核心的秘密",
            "factions": ["城邦長老會", "守夜人兄弟會", "永夜議會"]
        }
    ]
    db.save_volumes(novel_id, volumes_list)
    
    print("[SUCCESS] 測試小說、世界觀與篇卷資料建立完成。")
    print("----------------------------------------------------")
    
    # ----------------------------------------------------
    # 測試情境一：無 any 邏輯錯誤的完美大綱 (Perfect Case)
    # ----------------------------------------------------
    print("[SCENARIO 1] 測試情境一：邏輯完美對齊的章節大綱")
    
    perfect_chapters = [
        {
            "chapter_index": 1,
            "title": "黑石吊墜 the秘密",
            "events": [
                {"scene": "荒原廢墟", "action": "林澤在荒原拾荒，摩挲著胸前的黑石吊墜（Seed-3）並遇見怪物", "consequence": "死裡逃生"}
            ],
            "purpose": "引入黑石吊墜設定與荒原危險氣氛",
            "foreshadowing_plant": ["鋪設 Seed-3：黑石吊墜似乎在黑暗中發出微弱藍光。"],
            "foreshadowing_payoff": [],
            "scene": "荒原",
            "cliffhanger": "林澤發現廢墟深處有一道奇異的古神紋路壁畫。"
        },
        {
            "chapter_index": 2,
            "title": "廢墟中的晶片",
            "events": [
                {"scene": "古神壁畫前", "action": "林澤在壁畫下的沙土中挖出了一枚奇特的晶片（Seed-1），觸發了 TurningPoint-1", "consequence": "晶片融入其體內"}
            ],
            "purpose": "完成不朽晶片的引入與首次力量覺醒",
            "foreshadowing_plant": ["鋪設 Seed-1：這枚晶片擁有古神電路紋路。"],
            "foreshadowing_payoff": [],
            "scene": "古神废墟",
            "cliffhanger": "林澤感到體內的血液開始沸騰，一股神秘的光芒在胸口凝聚。"
        },
        {
            "chapter_index": 3,
            "title": "守夜人的招募",
            "events": [
                {"scene": "城邦邊哨", "action": "守夜人先鋒隊（登場陣營）發現了林澤體內強大的命燈波動，決定帶其回城邦", "consequence": "林澤踏上新旅程"}
            ],
            "purpose": "引導主角進入第二階段燈火城邦",
            "foreshadowing_plant": [],
            "foreshadowing_payoff": [],
            "scene": "邊哨哨卡",
            "cliffhanger": "林澤回首望向黑暗的荒原，有股預感自己再也回不來了。"
        },
        {
            "chapter_index": 4,
            "title": "不朽燈火的重燃",
            "events": [
                {"scene": "守夜人總部大殿", "action": "林澤利用體內融入的古神電路紋路晶片，成功回收 Seed-1並重燃不朽命燈", "consequence": "全場震撼，高層矚目"}
            ],
            "purpose": "林澤實力第一次大幅突破，回收 Seed-1 晶片設定",
            "foreshadowing_plant": [],
            "foreshadowing_payoff": ["回收 Seed-1：利用晶片作為媒介重燃不朽命燈。"],
            "scene": "總部大殿",
            "cliffhanger": "長老會的陰冷目光從垂簾後射出，落在林澤身上。"
        },
        {
            "chapter_index": 5,
            "title": "吊墜與巨門",
            "events": [
                {"scene": "城邦地下聖所", "action": "林澤在聖所發現了通往永夜深處的巨門，他解下黑石吊墜（Seed-3）發現與鑰匙孔完美重合（TurningPoint-3）", "consequence": "巨門顫動，引發古神回音"}
            ],
            "purpose": "揭示最終主線秘密，回收黑石吊墜設定",
            "foreshadowing_plant": [],
            "foreshadowing_payoff": ["回收 Seed-3：解下黑石吊墜對齊大門鑰匙凹槽。"],
            "scene": "地下聖所",
            "cliffhanger": "巨門後面傳來了一聲沉重而古老的嘆息。"
        }
    ]
    
    # 建立 context 對象
    context_perfect = {
        "worldbuilding": json.dumps(worldview_data, ensure_ascii=False),
        "characters": "[]",
        "plot": json.dumps({"chapters": perfect_chapters}, ensure_ascii=False),
        "written_chapters": "[]"
    }
    
    # 執行校驗
    perfect_report = verify_novel_integrity(novel_id, context_perfect)
    print(perfect_report)
    
    # 驗證完美情境下是否無紅色錯誤
    assert "🔴" not in perfect_report, "測試失敗：完美情境大綱中不應包含紅色錯誤警告標記！"
    print("[SUCCESS] 測試情境一通過！完美對齊大綱完全通過校驗。")
    print("----------------------------------------------------")
    
    # ----------------------------------------------------
    # 測試情境二：漏洞百出的大綱 (Violation Case)
    # ----------------------------------------------------
    print("[SCENARIO 2] 測試情境二：包含多項邏輯錯誤的大綱（有中斷、伏筆未回收、憑空回收、時序顛倒、卷數不足）")
    
    flawed_chapters = [
        {
            "chapter_index": 1,
            "title": "黑石吊墜的秘密",
            "events": [],
            "foreshadowing_plant": [
                "鋪設 Seed-3：林澤佩戴吊墜。",
                "鋪設 Seed-2：長老們高高在上，似乎有秘密" # 🔴 埋設了 Seed-2 但在後文沒有回收 (Dangling)
            ],
            "foreshadowing_payoff": []
        },
        # 故意缺失第 2 章 (Gaps Check)
        {
            "chapter_index": 3,
            "title": "命燈重燃與回收",
            "events": [],
            "foreshadowing_plant": [],
            "foreshadowing_payoff": [
                "回收 Seed-1：利用古神晶片重燃命燈", # 🔴 這裡 Seed-1 後文第 4 章才鋪設，所以是時序顛倒 (Out of Order)
                "回收 Seed-5：神兵天降" # 🔴 憑空回收：從未在任何地方鋪設過 Seed-5！ (Baseless)
            ]
        },
        {
            "chapter_index": 4,
            "title": "吊墜與巨門",
            "events": [],
            "foreshadowing_plant": [
                "鋪設 Seed-1：林澤發現晶片" # 🔴 埋設了 Seed-1 (配合第 3 章回收形成時序顛倒)
            ],
            "foreshadowing_payoff": [
                "回收 Seed-3：在第 4 章完成黑石吊墜回收" # 🟢 正常回收
            ]
        },
        # 故意規劃出超大章節 index 觸發卷數不足警告
        {
            "chapter_index": 125, # 🔴 卷數不足：125章對應第 3 卷，但只有 2 卷
            "title": "大結局",
            "events": [],
            "foreshadowing_plant": [],
            "foreshadowing_payoff": []
        }
    ]
    
    context_flawed = {
        "worldbuilding": json.dumps(worldview_data, ensure_ascii=False),
        "characters": "[]",
        "plot": json.dumps({"chapters": flawed_chapters}, ensure_ascii=False),
        "written_chapters": "[]"
    }
    
    # 執行校驗
    flawed_report = verify_novel_integrity(novel_id, context_flawed)
    print("Flawed Report:")
    print(flawed_report)
    
    # 驗證是否抓出所有邏輯警告
    assert "🔴" in flawed_report, "測試失敗：未抓出邏輯警告標記！"
    assert "章節序號不連續" in flawed_report, "測試失敗：未抓出章節中斷序號！"
    assert "卷數不足警告" in flawed_report, "測試失敗：未抓出卷數不足問題！"
    assert "伏筆未回收" in flawed_report, "測試失敗：未抓出 Dangling Plants！"
    assert "伏筆憑空回收" in flawed_report, "測試失敗：未抓出 Baseless Payoffs！"
    assert "伏筆時序顛倒" in flawed_report, "測試失敗：未抓出 Out of Order！"
    
    print("[SUCCESS] 測試情境二通過！成功精確捕捉到所有邏輯漏洞與缺陷。")
    print("====================================================")
    print("[SUCCESS] 所有測試已完整執行且 100% 通過！證明本校驗機制完全正確！")
    print("====================================================")

if __name__ == "__main__":
    run_tests()
