# -*- coding: utf-8 -*-
"""
合併測試腳本 - 統一管理所有測試模組

使用方法:
    python all_tests.py                    # 執行所有測試
    python all_tests.py --test director    # 僅執行總監整合測試
    python all_tests.py --test pipeline    # 僅執行管線測試
    python all_tests.py --test feedback    # 僅執行反饋環路測試
    python all_tests.py --test integrity   # 僅執行完整性校驗測試
    python all_tests.py --test rebound     # 僅執行管線反彈測試
    python all_tests.py --test retrospective  # 僅執行回溯日誌測試
    python all_tests.py --test simple      # 僅執行簡單日誌測試
    python all_tests.py --list             # 列出所有可用測試
"""

import sys
import os
import io
import json
import uuid
import sqlite3
import unittest
from datetime import datetime
from argparse import ArgumentParser
from io import StringIO
from unittest.mock import patch, MagicMock

# ============================================================================
# 全域設定
# ============================================================================

# 強制 UTF-8 編碼
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# 確保路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ============================================================================
# 匯入專案模組
# ============================================================================

import db
import agents
import llm
from agents import (
    pre_check_next_agent,
    get_simplified_director_prompt,
    run_plot_planner,
    verify_novel_integrity,
    parse_json_safely
)
from agents_incremental import run_volume_jit_alignment
from app import api_novel_retrospective

# ============================================================================
# 超參數設定
# ============================================================================

TEST_CONFIGS = {
    "director": {
        "name": "總監整合測試 (Director Integrity)",
        "description": "測試總監預檢查與提示生成功能",
        "db_path": "novel_factory.db"
    },
    "pipeline": {
        "name": "動態篇卷管線測試 (Dynamic Pipeline)",
        "description": "測試動態篇卷、對齊、總監救援與局部修正的完整閉環",
        "requires_mocks": False,
        "requires_llm": True  # 需要呼叫 LLM API
    },
    "feedback": {
        "name": "反饋環路測試 (Feedback Loop)",
        "description": "測試反饋環路與懶惰對齊功能",
        "requires_mocks": False
    },
    "integrity": {
        "name": "完整性校驗測試 (Integrity Check)",
        "description": "測試總監大綱與情節邏輯校驗機制",
        "requires_mocks": False
    },
    "rebound": {
        "name": "管線反彈測試 (Pipeline Rebound)",
        "description": "測試創作管線對齊與強健狀態同步",
        "requires_mocks": False
    },
    "retrospective": {
        "name": "回溯日誌測試 (Retrospective Logging)",
        "description": "測試回溯 API 的終端機日誌輸出功能",
        "requires_mocks": True
    },
    "simple": {
        "name": "簡單日誌測試 (Simple Logging)",
        "description": "手動呼叫 retrospective 並觀察終端機輸出",
        "requires_mocks": False
    }
}

# ============================================================================
# 測試類別與函數定義
# ============================================================================

# --------------------------------------------------------------------------
# 測試 1: 總監整合測試 (Director Integrity)
# --------------------------------------------------------------------------

class TestDirectorIntegrity:
    """總監整合測試"""
    
    @staticmethod
    def run(db_path="novel_factory.db"):
        """執行總監整合測試"""
        print("\n" + "=" * 60)
        print("【測試 1】總監整合測試 (Director Integrity)")
        print("=" * 60)
        
        if not os.path.exists(db_path):
            print(f"⚠️  Database {db_path} not found in current directory.")
            print("   跳過此測試（需要真實資料庫）")
            return False
            
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 取得小說列表
        novels = cursor.execute("SELECT id, title FROM novels LIMIT 5").fetchall()
        if not novels:
            print("⚠️  No novels found in database.")
            conn.close()
            return False
            
        print(f"Found {len(novels)} novels in database.")
        for idx, (nid, title) in enumerate(novels):
            print(f"[{idx}] ID: {nid}, Title: {title}")
            
        novel_id = novels[0][0]
        print(f"\nTesting with Novel ID: {novel_id}")
        
        # 1. 測試 pre_check_next_agent
        stages = ["init", "worldview", "characters", "plot", "writer"]
        print("\n--- Testing pre_check_next_agent ---")
        all_passed = True
        for stage in stages:
            try:
                res = pre_check_next_agent(novel_id, stage)
                print(f"\n[Stage: {stage}]")
                print(res)
                print("✅ OK")
            except Exception as e:
                print(f"❌ Error in stage {stage}: {e}")
                all_passed = False
                
        # 2. 測試 get_simplified_director_prompt
        print("\n--- Testing get_simplified_director_prompt ---")
        for stage in stages:
            try:
                prompt_tpl = get_simplified_director_prompt(stage, has_wb_and_char_at_init=(stage == "init"))
                print(f"✅ Stage: {stage} -> Prompt generated (length: {len(prompt_tpl)})")
            except Exception as e:
                print(f"❌ Error generating prompt for {stage}: {e}")
                all_passed = False
                
        conn.close()
        return all_passed


# --------------------------------------------------------------------------
# 測試 2: 動態篇卷管線測試 (Dynamic Pipeline)
# --------------------------------------------------------------------------

class TestDynamicPipeline:
    """動態篇卷管線測試"""
    
    @staticmethod
    def run():
        """執行動態篇卷管線測試"""
        print("\n" + "=" * 60)
        print("【測試 2】動態篇卷管線測試 (Dynamic Pipeline)")
        print("=" * 60)
        
        # 初始化資料庫
        db.db_init()
        test_novel_id = f"test-dynamic-{uuid.uuid4()}"
        
        try:
            # 建立測試小說
            db.create_novel(test_novel_id, "測試仙俠小說", "仙俠", "史詩")
            
            # 建立動態篇卷結構
            volumes_setup = [
                {
                    "volume_index": 1,
                    "title": "測試卷一：青雲開篇",
                    "summary": "主角在青雲山谷獲得神秘靈根碎片",
                    "factions": ["青雲門"],
                    "chapter_count": 3,
                    "time_timeline": "天啟元年春 - 天啟元年夏",
                    "sequence_context": "第一部故事引入開卷",
                    "applicable_rules": ["世界法則：修仙者燃燒壽命可獲得極限爆發力"]
                },
                {
                    "volume_index": 2,
                    "title": "測試卷二：正魔風雲",
                    "summary": "正魔大會爆發激烈衝突",
                    "factions": ["青雲門", "血影魔門"],
                    "chapter_count": 5,
                    "time_timeline": "天啟元年秋 - 天啟二年春",
                    "sequence_context": "中期衝突對抗與升級",
                    "applicable_rules": []
                },
                {
                    "volume_index": 3,
                    "title": "測試卷三：太上收束",
                    "summary": "主角封印神魔",
                    "factions": ["青雲門", "魔界"],
                    "chapter_count": 2,
                    "time_timeline": "天啟二年夏 - 天啟二年冬",
                    "sequence_context": "全書終極大收束篇",
                    "applicable_rules": []
                }
            ]
            
            db.save_volumes(test_novel_id, volumes_setup)
            
            # 測試 2.1: 篇卷章節範圍計算
            print("\n--- 2.1 測試篇卷章節範圍計算 ---")
            volumes = db.get_volumes(test_novel_id)
            
            assert len(volumes) == 3, f"預期 3 卷，實際 {len(volumes)}"
            
            # 第一卷：第 1 章 至 第 3 章
            start1, end1 = db.get_volume_chapter_range(volumes, 1)
            assert (start1, end1) == (1, 3), f"第一卷範圍應為 (1, 3)，實際 ({start1}, {end1})"
            print(f"✅ 第一卷章節範圍: {start1} - {end1}")
            
            # 第二卷：第 4 章 至 第 8 章
            start2, end2 = db.get_volume_chapter_range(volumes, 2)
            assert (start2, end2) == (4, 8), f"第二卷範圍應為 (4, 8)，實際 ({start2}, {end2})"
            print(f"✅ 第二卷章節範圍: {start2} - {end2}")
            
            # 第三卷：第 9 章 至 第 10 章
            start3, end3 = db.get_volume_chapter_range(volumes, 3)
            assert (start3, end3) == (9, 10), f"第三卷範圍應為 (9, 10)，實際 ({start3}, {end3})"
            print(f"✅ 第三卷章節範圍: {start3} - {end3}")
            
            # 測試 2.2: 章節所屬卷索引
            print("\n--- 2.2 測試章節所屬卷索引 ---")
            assert db.get_chapter_volume_index(volumes, 1) == 1, "第 1 章應屬於第 1 卷"
            assert db.get_chapter_volume_index(volumes, 3) == 1, "第 3 章應屬於第 1 卷"
            assert db.get_chapter_volume_index(volumes, 4) == 2, "第 4 章應屬於第 2 卷"
            assert db.get_chapter_volume_index(volumes, 8) == 2, "第 8 章應屬於第 2 卷"
            assert db.get_chapter_volume_index(volumes, 9) == 3, "第 9 章應屬於第 3 卷"
            assert db.get_chapter_volume_index(volumes, 10) == 3, "第 10 章應屬於第 3 卷"
            print("✅ 章節所屬卷索引計算正確")
            
            # 測試 2.3: 總章節數計算
            print("\n--- 2.3 測試總章節數計算 ---")
            total = db.get_total_chapter_count(volumes)
            assert total == 10, f"總章節數應為 10，實際 {total}"
            print(f"✅ 總章節數: {total}")
            
            # 測試 2.4: 超出範圍 Fallback
            print("\n--- 2.4 測試超出範圍 Fallback ---")
            start4, end4 = db.get_volume_chapter_range(volumes, 4)
            assert (start4, end4) == (11, 12), f"第四卷應為 (11, 12)，實際 ({start4}, {end4})"
            print(f"✅ 超出範圍 Fallback: {start4} - {end4}")
            
            # 測試 2.5: 增量修改
            print("\n--- 2.5 測試增量局部修改 ---")
            modified_volumes = [
                {
                    "volume_index": 1,
                    "title": "測試卷一：青雲起風",
                    "summary": "主角獲得神秘碎片",
                    "factions": ["青雲門"],
                    "chapter_count": 3,
                    "time_timeline": "天啟元年春",
                    "sequence_context": "第一部引入",
                    "applicable_rules": ["法則一"]
                },
                {
                    "volume_index": 2,
                    "title": "測試卷二：風起雲湧",
                    "summary": "正邪大戰大爆發",
                    "factions": ["青雲門", "魔門"],
                    "chapter_count": 8,  # 修改為 8 章
                    "time_timeline": "天啟元年秋 - 天啟三年春",
                    "sequence_context": "系列中期大高潮",
                    "applicable_rules": ["法則二"]
                }
            ]
            
            db.save_volumes(test_novel_id, modified_volumes)
            updated_volumes = db.get_volumes(test_novel_id)
            assert len(updated_volumes) == 2, "修改後應有 2 卷"
            assert int(updated_volumes[1]["chapter_count"]) == 8, "第二卷章節數應為 8"
            assert updated_volumes[1]["time_timeline"] == "天啟元年秋 - 天啟三年春", "時間軸應更新"
            print("✅ 增量局部修改成功")
            
            print("\n✅ 【測試 2】動態篇卷管線測試全部通過！")
            return True
            
        except Exception as e:
            print(f"\n❌ 測試失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 清理測試數據
            db.delete_novel(test_novel_id)


# --------------------------------------------------------------------------
# 測試 3: 反饋環路測試 (Feedback Loop)
# --------------------------------------------------------------------------

class TestFeedbackLoop:
    """反饋環路測試"""
    
    @staticmethod
    def run():
        """執行反饋環路測試"""
        print("\n" + "=" * 60)
        print("【測試 3】反饋環路測試 (Feedback Loop)")
        print("=" * 60)
        
        # 初始化資料庫
        db.db_init()
        novel_id = "test-loop-novel"
        
        try:
            # 清理舊數據
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
            cursor.execute("DELETE FROM volumes WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM plot_chapters WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM chapters WHERE novel_id = ?", (novel_id,))
            conn.commit()
            conn.close()
            
            # 建立測試小說
            db.create_novel(novel_id, "反饋環路測試史詩", "科幻", "史詩殘酷")
            print("[OK] Novel created successfully.")
            
            # 建立篇卷
            volumes_list = [
                {"volume_index": 1, "title": "開端：磁帶之謎", "summary": "林浩發現了古神電路磁帶。", "factions": "流浪者同盟", "is_dirty": 0},
                {"volume_index": 2, "title": "中局：多世界奇異點", "summary": "多陣營在 Sector 7 激戰。", "factions": "黑星財閥, 機械教廷", "is_dirty": 0}
            ]
            db.save_volumes(novel_id, volumes_list)
            print("[OK] Volumes saved.")
            
            # 建立情節章節
            initial_outline = [
                {"chapter_index": 1, "title": "磁帶開啟", "summary": "林浩買到了古神磁帶。", "time_setting": "第4天", "scene": "Scrap Iron Alley"},
                {"chapter_index": 51, "title": "Sector 7 會戰", "summary": "黑星財閥突然發動總攻。", "time_setting": "第10天", "scene": "Sector 7"}
            ]
            db.save_plot_chapters(novel_id, {"chapters": initial_outline})
            print("[OK] Plot chapters saved.")
            
            # 模擬世界觀修補
            print("\n[Simulating chapter writing worldview tag interception...]")
            new_law_category = "Physics"
            new_law_details = "Gravity is reversed in Sector 7 when electromagnetic activity peaks."
            source_chapter = 1
            
            db.add_worldview_patch(novel_id, new_law_category, new_law_details, source_chapter)
            db.mark_downstream_dirty(novel_id, source_chapter)
            print("[OK] Worldview patch added & downstream marked dirty.")
            
            # 驗證數據庫狀態
            patches = db.get_worldview_patches(novel_id)
            assert len(patches) > 0, "Error: Worldview patches not saved."
            print(f"[OK] Worldview Patches Verified: {json.dumps(patches, ensure_ascii=False)}")
            
            volumes = db.get_volumes(novel_id)
            vol2 = next(v for v in volumes if v["volume_index"] == 2)
            vol1 = next(v for v in volumes if v["volume_index"] == 1)
            
            assert vol2["is_dirty"] == 1, "Error: Volume 2 should be marked dirty."
            assert vol1["is_dirty"] == 0, "Error: Volume 1 should NOT be marked dirty."
            print("[OK] Volume dirty states verified (Volume 2 is dirty, Volume 1 is clean).")
            
            # 測試 JIT 對齊
            aligned_chapters = [
                {"chapter_index": 51, "title": "Sector 7 重力顛倒會戰", "summary": "重力突然反轉，黑星財閥戰車升空懸浮，戰局劇變。", "time_setting": "第10天", "scene": "Sector 7"}
            ]
            db.update_volume_outline(novel_id, 2, aligned_chapters)
            print("[OK] JIT Volume alignment output stitched to DB.")
            
            # 驗證更新
            plot = db.get_latest_plot_chapters(novel_id)
            chapters = plot["parsed_data"].get("chapters", [])
            
            ch51 = next(c for c in chapters if c["chapter_index"] == 51)
            assert "重力突然反轉" in ch51["summary"], "Error: Chapter 51 summary was not updated with aligned outline."
            print(f"[OK] Aligned outline verified: {json.dumps(ch51, ensure_ascii=False)}")
            
            # 檢查 Volume 2 是否清除 dirty 標記
            volumes_after = db.get_volumes(novel_id)
            vol2_after = next(v for v in volumes_after if v["volume_index"] == 2)
            assert vol2_after["is_dirty"] == 0, "Error: Volume 2 should be marked clean after alignment."
            print("[OK] Volume 2 dirty state cleared successfully.")
            
            print("\n✅ 【測試 3】反饋環路測試全部通過！")
            return True
            
        except Exception as e:
            print(f"\n❌ 測試失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 清理
            db.delete_novel(novel_id)


# --------------------------------------------------------------------------
# 測試 4: 完整性校驗測試 (Integrity Check)
# --------------------------------------------------------------------------

class TestIntegrityCheck:
    """完整性校驗測試"""
    
    @staticmethod
    def run():
        """執行完整性校驗測試"""
        print("\n" + "=" * 60)
        print("【測試 4】完整性校驗測試 (Integrity Check)")
        print("=" * 60)
        
        # 初始化資料庫
        db.db_init()
        novel_id = "test_integrity_novel_id"
        
        try:
            # 清理舊數據
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
            
            # 建立世界觀
            worldview_data = {
                "theme": "生命的代價與光明的追尋",
                "main_conflict": "燈火城邦與永夜荒原的對立",
                "worldview": "一個被永夜籠罩的世界，人類只能依賴命燈散發出的微弱光芒建立城邦。",
                "macro_outline": "主角林澤從一個普通荒原拾荒者，逐步發掘古神留下的電路晶片，點燃不朽命燈的故事。",
                "three_act_structure": [
                    {"title": "第一幕 (Setup)", "content": "林澤在荒原邊緣拾荒，意外點燃命燈碎片。"},
                    {"title": "第二幕 (Confrontation)", "content": "林澤加入守夜人，面對殘酷真相。"},
                    {"title": "第三幕 (Resolution)", "content": "林澤深入永夜核心，打破永夜封印。"}
                ],
                "progressive_character_plan": [
                    {"title": "第一波開篇", "content": "林澤登場，初始狀態為懦弱的荒原流民。"},
                    {"title": "第二波發展", "content": "林澤在守夜人訓練中成長。"},
                    {"title": "第三波高潮", "content": "林澤最終蛻變，捨生取義。"}
                ],
                "foreshadowing_seeds": [
                    "Seed-1: 點燃不朽命燈需要古神電路紋路晶片",
                    "Seed-2: 守夜人高層長老都是靠吸取平民壽命維持生存的叛徒",
                    "Seed-3: 林澤身上佩戴的黑石吊墜是古神的核心啟動鑰匙"
                ],
                "key_turning_points": [
                    "TurningPoint-1: 林澤在荒原廢墟中挖出晶片，引發天地異象",
                    "TurningPoint-2: 林澤的好友被迫超載命燈燃盡壽命而死",
                    "TurningPoint-3: 林澤發現黑石吊墜與永夜大門的凹槽完美契合"
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
            
            # ----------------------------------------------------
            # 測試情境一：完美大綱
            # ----------------------------------------------------
            print("\n[SCENARIO 1] 測試情境一：邏輯完美對齊的章節大綱")
            
            perfect_chapters = [
                {
                    "chapter_index": 1,
                    "title": "黑石吊墜的秘密",
                    "events": [
                        {"scene": "荒原廢墟", "action": "林澤在荒原拾荒，摩挲著胸前的黑石吊墜並遇見怪物", "consequence": "死裡逃生"}
                    ],
                    "purpose": "引入黑石吊墜設定與荒原危險氣氛",
                    "foreshadowing_plant": ["Seed-3: 黑石吊墜似乎在黑暗中發出微弱藍光。"],
                    "foreshadowing_payoff": [],
                    "scene": "荒原",
                    "cliffhanger": "林澤發現廢墟深處有一道奇異的古神紋路壁畫。"
                },
                {
                    "chapter_index": 2,
                    "title": "廢墟中的晶片",
                    "events": [
                        {"scene": "古神壁畫前", "action": "林澤在壁畫下的沙土中挖出了一枚奇特的晶片，觸發 TurningPoint-1", "consequence": "晶片融入其體內"}
                    ],
                    "purpose": "完成晶片引入與力量覺醒",
                    "foreshadowing_plant": ["Seed-1: 這枚晶片擁有古神電路紋路。"],
                    "foreshadowing_payoff": [],
                    "scene": "古神废墟",
                    "cliffhanger": "林澤感到體內的血液開始沸騰。"
                },
                {
                    "chapter_index": 3,
                    "title": "守夜人的招募",
                    "events": [
                        {"scene": "城邦邊哨", "action": "守夜人先鋒隊發現了林澤體內強大的命燈波動", "consequence": "林澤踏上新旅程"}
                    ],
                    "purpose": "引導主角進入第二階段",
                    "foreshadowing_plant": [],
                    "foreshadowing_payoff": [],
                    "scene": "邊哨哨卡",
                    "cliffhanger": "林澤回首望向黑暗的荒原。"
                },
                {
                    "chapter_index": 4,
                    "title": "不朽燈火的重燃",
                    "events": [
                        {"scene": "守夜人總部大殿", "action": "林澤利用古神電路紋路晶片，成功回收 Seed-1 並重燃不朽命燈", "consequence": "全場震撼，高層矚目"}
                    ],
                    "purpose": "林澤實力第一次大幅突破",
                    "foreshadowing_plant": [],
                    "foreshadowing_payoff": ["Seed-1: 利用晶片作為媒介重燃不朽命燈。"],
                    "scene": "總部大殿",
                    "cliffhanger": "長老會的陰冷目光從垂簾後射出。"
                },
                {
                    "chapter_index": 5,
                    "title": "吊墜與巨門",
                    "events": [
                        {"scene": "城邦地下聖所", "action": "林澤發現通往永夜深處的巨門，他解下黑石吊墜與鑰匙孔完美重合，觸發 TurningPoint-3", "consequence": "巨門顫動，引發古神回音"}
                    ],
                    "purpose": "揭示最終主線秘密",
                    "foreshadowing_plant": [],
                    "foreshadowing_payoff": ["Seed-3: 解下黑石吊墜對齊大門鑰匙凹槽。"],
                    "scene": "地下聖所",
                    "cliffhanger": "巨門後面傳來了一聲沉重而古老的嘆息。"
                }
            ]
            
            context_perfect = {
                "worldbuilding": json.dumps(worldview_data, ensure_ascii=False),
                "characters": "[]",
                "plot": json.dumps({"chapters": perfect_chapters}, ensure_ascii=False),
                "written_chapters": "[]"
            }
            
            perfect_report = verify_novel_integrity(novel_id, context_perfect)
            print("完美報告:")
            print(perfect_report)
            
            assert "🔴" not in perfect_report, "測試失敗：完美情境大綱中不應包含紅色錯誤警告標記！"
            print("[SUCCESS] 測試情境一通過！完美對齊大綱完全通過校驗。")
            
            # ----------------------------------------------------
            # 測試情境二：漏洞百出的大綱
            # ----------------------------------------------------
            print("\n[SCENARIO 2] 測試情境二：包含多項邏輯錯誤的大綱")
            
            flawed_chapters = [
                {
                    "chapter_index": 1,
                    "title": "黑石吊墜的秘密",
                    "events": [],
                    "foreshadowing_plant": [
                        "Seed-3: 林澤佩戴吊墜。",
                        "Seed-2: 長老們高高在上，似乎有秘密"  # 🔴 埋設了 Seed-2 但後文沒有回收 (Dangling)
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
                        "Seed-1: 利用古神晶片重燃命燈",  # 🔴 Seed-1 後文第 4 章才鋪設 (時序顛倒)
                        "Seed-5: 神兵天降"  # 🔴 憑空回收 (Baseless)
                    ]
                },
                {
                    "chapter_index": 4,
                    "title": "吊墜與巨門",
                    "events": [],
                    "foreshadowing_plant": [
                        "Seed-1: 林澤發現晶片"  # 🔴 埋設了 Seed-1
                    ],
                    "foreshadowing_payoff": [
                        "Seed-3: 完成黑石吊墜回收"  # 🟢 正常回收
                    ]
                },
                {
                    "chapter_index": 125,  # 🔴 卷數不足
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
            
            flawed_report = verify_novel_integrity(novel_id, context_flawed)
            print("\n缺陷報告:")
            print(flawed_report)
            
            assert "🔴" in flawed_report, "測試失敗：未抓出邏輯警告標記！"
            assert "章節序號不連續" in flawed_report, "測試失敗：未抓出章節中斷序號！"
            assert "卷數不足警告" in flawed_report, "測試失敗：未抓出卷數不足問題！"
            assert "伏筆未回收" in flawed_report, "測試失敗：未抓出 Dangling Plants！"
            assert "伏筆憑空回收" in flawed_report, "測試失敗：未抓出 Baseless Payoffs！"
            assert "伏筆時序顛倒" in flawed_report, "測試失敗：未抓出 Out of Order！"
            
            print("[SUCCESS] 測試情境二通過！成功精確捕捉到所有邏輯漏洞與缺陷。")
            
            # ----------------------------------------------------
            # 測試情境三：早期設定階段（init 階段）
            # ----------------------------------------------------
            print("\n[SCENARIO 3] 測試情境三：早期設定階段（init 階段）不應包含紅色錯誤警告標記")
            context_init = {
                "worldbuilding": "No worldview defined yet.",
                "characters": "No characters designed yet.",
                "plot": "No plot chapters designed yet.",
                "written_chapters": "No chapters written yet."
            }
            init_report = verify_novel_integrity(novel_id, context_init, current_stage="init")
            print("早期報告:")
            print(init_report)
            assert "當前階段不適用" in init_report, "測試失敗：早期報告未包含不適用提示！"
            assert "🔴" not in init_report, "測試失敗：早期報告不應包含紅色警報標記！"
            print("[SUCCESS] 測試情境三通過！早期設定階段報告處理正確。")
            
            print("\n✅ 【測試 4】完整性校驗測試全部通過！")
            return True
            
        except Exception as e:
            print(f"\n❌ 測試失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 清理
            db.delete_novel(novel_id)


# --------------------------------------------------------------------------
# 測試 5: 管線反彈測試 (Pipeline Rebound)
# --------------------------------------------------------------------------

class TestPipelineRebound:
    """管線反彈測試"""
    
    @staticmethod
    def run():
        """執行管線反彈測試"""
        print("\n" + "=" * 60)
        print("【測試 5】管線反彈測試 (Pipeline Rebound)")
        print("=" * 60)
        
        # 初始化資料庫
        db.db_init()
        test_novel_id = "test-rebound-novel-999"
        
        try:
            # 清理舊數據
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM novels WHERE id = ?", (test_novel_id,))
            cursor.execute("DELETE FROM worldbuilding WHERE novel_id = ?", (test_novel_id,))
            cursor.execute("DELETE FROM characters WHERE novel_id = ?", (test_novel_id,))
            cursor.execute("DELETE FROM plot_chapters WHERE novel_id = ?", (test_novel_id,))
            cursor.execute("DELETE FROM volumes WHERE novel_id = ?", (test_novel_id,))
            conn.commit()
            conn.close()
            
            # 建立測試小說
            db.create_novel(test_novel_id, "測試霓虹都市", "Cyberpunk", "Classic Modernism")
            print("✓ Created test novel in SQLite.")
            
            # 測試 5.1: 世界觀結構持久化
            print("\n--- 5.1 測試世界觀結構持久化 ---")
            
            raw_architect_output = """```json
{
  "worldview": "霓虹城是一個高科技低生活的賽博都市。",
  "theme": "人性的機械化與靈魂的救贖",
  "main_conflict": "人類、合成人與時間術能的權力網格爭奪戰",
  "three_act_structure": [
    { "title": "第一幕：起", "content": "主角林澤在校園實驗室意外觸發零點回聲" },
    { "title": "第二幕：承", "content": "結識夥伴，遭遇反派阻擊" },
    { "title": "第三幕：合", "content": "終極決戰，釋放時間核心" }
  ],
  "progressive_character_plan": [
    { "title": "開篇合流", "content": "主角與黑客艾莉絲相遇" },
    { "title": "中期發展", "content": "時間研究員凱爾加入團隊" },
    { "title": "高潮蛻變", "content": "全員心靈共鳴" }
  ],
  "volumes": [
    {
      "volume_index": 1,
      "title": "第一卷：裂縫的回聲",
      "summary": "林澤意外解鎖時間天賦，被BAR追捕並結識艾莉絲。",
      "factions": ["BAR", "Veiled Syndicate"]
    },
    {
      "volume_index": 2,
      "title": "第二卷：霓虹深處的低語",
      "summary": "探索地下術能網格，解密ChronoDyne陰謀。",
      "factions": ["ChronoDyne", "Rogue Covenant"]
    }
  ],
  "foreshadowing_seeds": ["Seed 1: 林澤口袋裡的古舊懷錶在倒數計時"],
  "key_turning_points": ["TP 1: 第一卷末，林澤觸發時間回溯逃離追捕"]
}
```"""
            
            def architect_callback(nid, text):
                parsed = agents.parse_json_safely(text)
                if isinstance(parsed, dict) and ("worldview" in parsed or "theme" in parsed):
                    wb_data = {
                        "theme": parsed.get("theme", ""),
                        "main_conflict": parsed.get("main_conflict", ""),
                        "worldview": parsed.get("worldview", ""),
                        "three_act_structure": parsed.get("three_act_structure", []),
                        "progressive_character_plan": parsed.get("progressive_character_plan", []),
                        "foreshadowing_seeds": parsed.get("foreshadowing_seeds", []),
                        "key_turning_points": parsed.get("key_turning_points", []),
                        "macro_outline": parsed.get("macro_outline", "")
                    }
                    db.save_worldbuilding(nid, json.dumps(wb_data, ensure_ascii=False, indent=2))
                    
                    volumes_list = parsed.get("volumes", [])
                    if isinstance(volumes_list, list) and len(volumes_list) > 0:
                        db.save_volumes(nid, volumes_list)
            
            architect_callback(test_novel_id, raw_architect_output)
            
            wb_record = db.get_latest_worldbuilding(test_novel_id)
            assert wb_record is not None, "Worldbuilding record should exist!"
            
            wb_json = json.loads(wb_record["content"])
            assert "three_act_structure" in wb_json, "Missing three_act_structure!"
            assert "progressive_character_plan" in wb_json, "Missing progressive_character_plan!"
            assert len(wb_json["three_act_structure"]) == 3, "Should have 3 acts"
            print("✓ Worldview structure persisted correctly!")
            
            # 驗證篇卷
            volumes = db.get_volumes(test_novel_id)
            assert len(volumes) == 2, f"Should have saved 2 volumes, got {len(volumes)}"
            print(f"✓ Saved {len(volumes)} volumes in database.")
            
            # 測試 5.2: 多態角色解析
            print("\n--- 5.2 測試多態角色解析 ---")
            
            raw_characters_array = """```json
[
  {
    "name": "凱 (Kai)",
    "role": "主角",
    "entry_phase": "開篇第一章",
    "personality": ["堅韌", "冷靜"],
    "want": "尋找失蹤的妹妹",
    "need": "建立與他人的信任紐帶",
    "arc": "從孤僻行者轉變為團隊守護神"
  }
]
```"""
            
            def character_callback(nid, text):
                parsed = agents.parse_json_safely(text)
                if isinstance(parsed, list):
                    parsed = {"characters": parsed}
                elif isinstance(parsed, dict):
                    for key in list(parsed.keys()):
                        if key.lower() in ["characters", "character"]:
                            val = parsed[key]
                            if isinstance(val, list):
                                parsed = {"characters": val}
                                break
                
                if isinstance(parsed, dict) and "characters" in parsed:
                    db.save_characters(nid, parsed)
            
            character_callback(test_novel_id, raw_characters_array)
            char_record = db.get_latest_characters(test_novel_id)
            assert char_record is not None
            assert "characters" in char_record["parsed_data"]
            assert char_record["parsed_data"]["characters"][0]["name"] == "凱 (Kai)"
            print("✓ Polymorphic character parsing works!")
            
            # 測試 5.3: 進度比例映射
            print("\n--- 5.3 測試進度比例映射 ---")
            
            ta_list = [
                {"title": "第一幕：霓虹覺醒", "content": "第1幕內容"},
                {"title": "第二幕：暗流洶湧", "content": "第2幕內容"},
                {"title": "第三幕：核心重啟", "content": "第3幕內容"}
            ]
            cp_list = [
                {"title": "階段一：獨行與交會", "content": "第1階段"},
                {"title": "階段二：信任與並肩", "content": "第2階段"},
                {"title": "階段三：犧牲與超脫", "content": "第3階段"}
            ]
            
            def emulate_mapping(start_chapter, total_chapters):
                progress_percentage = min(max((start_chapter - 1) / total_chapters, 0.0), 1.0)
                active_act_index = min(int(progress_percentage * len(ta_list)), len(ta_list) - 1)
                active_stage_index = min(int(progress_percentage * len(cp_list)), len(cp_list) - 1)
                return progress_percentage, active_act_index, active_stage_index
            
            # 測試不同章節位置
            pct, act_idx, stg_idx = emulate_mapping(1, 1000)
            assert act_idx == 0 and stg_idx == 0, "At chapter 1, should map to Act 1 and Stage 1"
            print(f"✓ Chapter 1 mapping: Act {act_idx}, Stage {stg_idx}")
            
            pct, act_idx, stg_idx = emulate_mapping(400, 1000)
            assert act_idx == 1 and stg_idx == 1, "At chapter 400, should map to Act 2 and Stage 2"
            print(f"✓ Chapter 400 mapping: Act {act_idx}, Stage {stg_idx}")
            
            pct, act_idx, stg_idx = emulate_mapping(750, 1000)
            assert act_idx == 2 and stg_idx == 2, "At chapter 750, should map to Act 3 and Stage 3"
            print(f"✓ Chapter 750 mapping: Act {act_idx}, Stage {stg_idx}")
            
            print("✓ Progress mapping successfully scales!")
            
            # 清理測試數據
            db.delete_novel(test_novel_id)
            
            print("\n✅ 【測試 5】管線反彈測試全部通過！")
            return True
            
        except Exception as e:
            print(f"\n❌ 測試失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 清理
            db.delete_novel(test_novel_id)


# --------------------------------------------------------------------------
# 測試 6: 回溯日誌測試 (Retrospective Logging) - 需要 Mock
# --------------------------------------------------------------------------

class TestRetrospectiveLogging:
    """回溯日誌測試"""
    
    @staticmethod
    def run():
        """執行回溯日誌測試"""
        print("\n" + "=" * 60)
        print("【測試 6】回溯日誌測試 (Retrospective Logging)")
        print("=" * 60)
        
        # 初始化資料庫
        db.db_init()
        test_novel_id = str(uuid.uuid4())
        
        try:
            # 建立測試數據
            db.create_novel(test_novel_id, "測試小說", "奇幻", "史詩")
            db.save_worldbuilding(test_novel_id, '{"theme": "測試主題"}')
            db.save_characters(test_novel_id, '{"characters": []}')
            db.save_plot_chapters(test_novel_id, '{"chapters": []}')
            db.save_chapter(test_novel_id, 1, "測試章節內容")
            
            # 定義模擬回應
            agent_responses = {
                "Story Architect": "故事架構師的心得",
                "Character Designer": "角色設計師的心得",
                "Plot Planner": "劇情規劃師的心得",
                "Chapter Writer": "章節寫作的心得",
                "Editor Agent": "編輯agent的心得",
                "Co-pilot Director": "這是模擬的總監回答內容，包含重要的全局創作金律。"
            }
            
            # 建立 mock future
            def create_mock_future(agent_key):
                mock_future = MagicMock()
                mock_future.result.return_value = agent_responses[agent_key]
                return mock_future
            
            # 捕獲 stdout
            captured_output = StringIO()
            original_stdout = sys.stdout
            sys.stdout = captured_output
            
            try:
                # Mock ThreadPoolExecutor
                with patch('app.concurrent.futures.ThreadPoolExecutor') as MockExecutor:
                    mock_executor = MagicMock()
                    MockExecutor.return_value = mock_executor
                    
                    mock_executor.__enter__ = MagicMock(return_value=mock_executor)
                    mock_executor.__exit__ = MagicMock(return_value=False)
                    
                    def mock_submit(func, agent_key, config):
                        return create_mock_future(agent_key)
                    mock_executor.submit = mock_submit
                    
                    futures = [create_mock_future(key) for key in agent_responses.keys()]
                    mock_executor.as_completed.return_value = futures
                    
                    # 執行 API
                    result = api_novel_retrospective(test_novel_id)
                    
                    # 檢查輸出
                    output_text = captured_output.getvalue()
                    
                    assert "=" * 60 in output_text, "Missing separator in output"
                    assert "Co-pilot Director 總監回答" in output_text, "Missing director output"
                    assert "這是模擬的總監回答內容" in output_text, "Missing director content"
                    
                    # 驗證 API 回傳
                    assert result["status"] == "success", f"API should return success, got {result['status']}"
                    assert "filepath" in result, "Missing filepath in result"
                    assert "markdown" in result, "Missing markdown in result"
                    
                    # 驗證 markdown 包含所有 agent 回應
                    markdown = result["markdown"]
                    for agent_name in agent_responses:
                        assert agent_name in markdown, f"Missing {agent_name} in markdown"
                        assert agent_responses[agent_name] in markdown, f"Missing {agent_name} response in markdown"
                    
                    print("✓ Terminal output verified")
                    print("✓ API response verified")
                    print("✓ Markdown content verified")
                    
            finally:
                sys.stdout = original_stdout
            
            print("\n✅ 【測試 6】回溯日誌測試全部通過！")
            return True
            
        except Exception as e:
            print(f"\n❌ 測試失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 清理
            db.delete_novel(test_novel_id)


# --------------------------------------------------------------------------
# 測試 7: 簡單日誌測試 (Simple Logging)
# --------------------------------------------------------------------------

class TestSimpleLogging:
    """簡單日誌測試"""
    
    @staticmethod
    def run():
        """執行簡單日誌測試"""
        print("\n" + "=" * 60)
        print("【測試 7】簡單日誌測試 (Simple Logging)")
        print("=" * 60)
        print("⚠️  此測試需要實際執行 retrospective API，可能需要較長時間")
        print("   若不想執行真實 API，請使用 --skip-simple 參數跳過")
        
        test_novel_id = str(uuid.uuid4())
        print(f"建立測試小說，ID: {test_novel_id}")
        
        try:
            # 建立測試數據
            db.create_novel(test_novel_id, "測試輸出日誌", "奇幻", "史詩")
            
            db.save_worldbuilding(test_novel_id, json.dumps({
                "theme": "測試",
                "main_conflict": "對抗",
                "worldview": "魔法世界",
                "macro_outline": "主角冒險",
                "three_act_structure": [{"title": "開始", "content": "遇到危機"}],
                "progressive_character_plan": [{"title": "成長", "content": "學習魔法"}],
                "foreshadowing_seeds": ["伏筆1"],
                "key_turning_points": ["轉折1"]
            }, ensure_ascii=False))
            
            db.save_characters(test_novel_id, json.dumps({
                "characters": [{"name": "主角", "role": "英雄", "personality": ["勇敢"], "want": "拯救世界", "need": "接納自我", "arc": "成長為英雄"}]
            }, ensure_ascii=False))
            
            db.save_plot_chapters(test_novel_id, json.dumps({
                "chapters": [{"chapter_index": 1, "title": "第一章", "event": "開始旅程", "foreshadowing": "神秘符號", "characters_involved": ["主角"], "time_event": "早晨"}]
            }, ensure_ascii=False))
            
            db.save_chapter(test_novel_id, 1, "這是最初的章節內容，描述主角如何踏上冒險之旅。")
            
            print("開始執行 retrospective...")
            print("=" * 80)
            
            result = api_novel_retrospective(test_novel_id)
            
            print("=" * 80)
            print(f"執行完成！狀態: {result.get('status')}")
            print(f"檔案儲存至: {result.get('filepath')}")
            
            print("\n✅ 【測試 7】簡單日誌測試完成！")
            return True
            
        except Exception as e:
            print(f"\n❌ 測試失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 清理
            db.delete_novel(test_novel_id)


# ============================================================================
# 主執行函數
# ============================================================================

def list_tests():
    """列出所有可用測試"""
    print("\n" + "=" * 60)
    print("可用測試項目")
    print("=" * 60)
    for key, config in TEST_CONFIGS.items():
        print(f"\n  {key}")
        print(f"    名稱: {config['name']}")
        print(f"    說明: {config['description']}")


def run_all_tests(skip_tests=None):
    """執行所有測試"""
    if skip_tests is None:
        skip_tests = []
    
    print("\n" + "=" * 70)
    print("🚀 開始執行合併測試腳本 - 所有測試")
    print("=" * 70)
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"工作目錄: {os.getcwd()}")
    print(f"Python 版本: {sys.version}")
    print("=" * 70)
    
    results = {}
    
    # 測試 1: 總監整合測試
    if "director" not in skip_tests:
        results["director"] = TestDirectorIntegrity.run()
    else:
        results["director"] = None
        print("\n[跳過] 總監整合測試 (--skip-director)")
    
    # 測試 2: 動態篇卷管線測試
    if "pipeline" not in skip_tests:
        results["pipeline"] = TestDynamicPipeline.run()
    else:
        results["pipeline"] = None
        print("\n[跳過] 動態篇卷管線測試 (--skip-pipeline)")
    
    # 測試 3: 反饋環路測試
    if "feedback" not in skip_tests:
        results["feedback"] = TestFeedbackLoop.run()
    else:
        results["feedback"] = None
        print("\n[跳過] 反饋環路測試 (--skip-feedback)")
    
    # 測試 4: 完整性校驗測試
    if "integrity" not in skip_tests:
        results["integrity"] = TestIntegrityCheck.run()
    else:
        results["integrity"] = None
        print("\n[跳過] 完整性校驗測試 (--skip-integrity)")
    
    # 測試 5: 管線反彈測試
    if "rebound" not in skip_tests:
        results["rebound"] = TestPipelineRebound.run()
    else:
        results["rebound"] = None
        print("\n[跳過] 管線反彈測試 (--skip-rebound)")
    
    # 測試 6: 回溯日誌測試
    if "retrospective" not in skip_tests:
        results["retrospective"] = TestRetrospectiveLogging.run()
    else:
        results["retrospective"] = None
        print("\n[跳過] 回溯日誌測試 (--skip-retrospective)")
    
    # 測試 7: 簡單日誌測試
    if "simple" not in skip_tests:
        results["simple"] = TestSimpleLogging.run()
    else:
        results["simple"] = None
        print("\n[跳過] 簡單日誌測試 (--skip-simple)")
    
    # 總結
    print("\n" + "=" * 70)
    print("📊 測試執行結果總結")
    print("=" * 70)
    
    passed = 0
    failed = 0
    skipped = 0
    
    test_names = {
        "director": "總監整合測試",
        "pipeline": "動態篇卷管線測試",
        "feedback": "反饋環路測試",
        "integrity": "完整性校驗測試",
        "rebound": "管線反彈測試",
        "retrospective": "回溯日誌測試",
        "simple": "簡單日誌測試"
    }
    
    for key, result in results.items():
        name = test_names.get(key, key)
        if result is None:
            print(f"  ⏭️  {name}: 跳過")
            skipped += 1
        elif result:
            print(f"  ✅ {name}: 通過")
            passed += 1
        else:
            print(f"  ❌ {name}: 失敗")
            failed += 1
    
    print("-" * 70)
    print(f"總計: {passed} 通過, {failed} 失敗, {skipped} 跳過")
    print("=" * 70)
    
    return failed == 0


def run_specific_test(test_name):
    """執行指定的單一測試"""
    test_map = {
        "director": TestDirectorIntegrity.run,
        "pipeline": TestDynamicPipeline.run,
        "feedback": TestFeedbackLoop.run,
        "integrity": TestIntegrityCheck.run,
        "rebound": TestPipelineRebound.run,
        "retrospective": TestRetrospectiveLogging.run,
        "simple": TestSimpleLogging.run
    }
    
    if test_name not in test_map:
        print(f"\n❌ 未知測試名稱: {test_name}")
        print("可用測試: " + ", ".join(test_map.keys()))
        return False
    
    # 執行單一測試
    result = test_map[test_name]()
    
    print("\n" + "=" * 70)
    if result:
        print(f"✅ 【{test_name}】測試通過！")
    else:
        print(f"❌ 【{test_name}】測試失敗！")
    print("=" * 70)
    
    return result


# ============================================================================
# 命令列入口
# ============================================================================

if __name__ == "__main__":
    parser = ArgumentParser(description="合併測試腳本 - 統一管理所有測試模組")
    parser.add_argument("--test", "-t", type=str, default=None,
                        help="指定要執行的測試 (director/pipeline/feedback/integrity/rebound/retrospective/simple)")
    parser.add_argument("--list", "-l", action="store_true",
                        help="列出所有可用測試")
    parser.add_argument("--skip-director", action="store_true",
                        help="跳過總監整合測試")
    parser.add_argument("--skip-pipeline", action="store_true",
                        help="跳過動態篇卷管線測試")
    parser.add_argument("--skip-feedback", action="store_true",
                        help="跳過反饋環路測試")
    parser.add_argument("--skip-integrity", action="store_true",
                        help="跳過完整性校驗測試")
    parser.add_argument("--skip-rebound", action="store_true",
                        help="跳過管線反彈測試")
    parser.add_argument("--skip-retrospective", action="store_true",
                        help="跳過回溯日誌測試")
    parser.add_argument("--skip-simple", action="store_true",
                        help="跳過簡單日誌測試")
    
    args = parser.parse_args()
    
    if args.list:
        list_tests()
    elif args.test:
        success = run_specific_test(args.test)
        sys.exit(0 if success else 1)
    else:
        # 執行所有測試（可選擇性跳過）
        skip_tests = []
        if args.skip_director:
            skip_tests.append("director")
        if args.skip_pipeline:
            skip_tests.append("pipeline")
        if args.skip_feedback:
            skip_tests.append("feedback")
        if args.skip_integrity:
            skip_tests.append("integrity")
        if args.skip_rebound:
            skip_tests.append("rebound")
        if args.skip_retrospective:
            skip_tests.append("retrospective")
        if args.skip_simple:
            skip_tests.append("simple")
        
        success = run_all_tests(skip_tests if skip_tests else None)
        sys.exit(0 if success else 1)