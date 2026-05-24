# -*- coding: utf-8 -*-
"""
整合測試腳本 - 驗證動態篇卷、對齊、總監救援與局部修正的完整閉環
"""
import sys
import os
import json
import uuid
import unittest

# 強制將標準輸出設為 utf-8 避免 Windows CP950 報錯
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 加入當前路徑以導入專案模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import db
import llm
from agents import run_plot_planner
from agents_incremental import run_volume_jit_alignment

class TestDynamicNovelPipeline(unittest.TestCase):
    def setUp(self):
        # 初始化資料庫
        db.db_init()
        self.novel_id = f"test-novel-{uuid.uuid4()}"
        db.create_novel(self.novel_id, "測試仙俠小說", "仙俠", "史詩")
        
        # 建立動態篇卷結構：
        # 第一卷 3章，第二卷 5章，第三卷 2章 (總共 10章)
        self.volumes_setup = [
            {
                "volume_index": 1,
                "title": "測試卷一：青雲開篇",
                "summary": "主角在青雲山谷獲得神秘靈根碎片",
                "factions": ["青雲門"],
                "chapter_count": 3,
                "time_timeline": "天啟元年春 - 天啟元年夏",
                "sequence_context": "第一部故事引入開卷",
                "applicable_rules": ["世界法則：修仙者燃燒壽命可獲得極限爆發力", "魔門秘法：奪舍需心魔契合"]
            },
            {
                "volume_index": 2,
                "title": "測試卷二：正魔風雲",
                "summary": "正魔大會爆發激烈衝突，師尊陰謀初現",
                "factions": ["青雲門", "血影魔門"],
                "chapter_count": 5,
                "time_timeline": "天啟元年秋 - 天啟二年春",
                "sequence_context": "中期衝突對抗與升級",
                "applicable_rules": ["大典限制：正邪金丹期以上禁止在會盟期間動武"]
            },
            {
                "volume_index": 3,
                "title": "測試卷三：太上收束",
                "summary": "主角封印神魔，完成最終突破",
                "factions": ["青雲門", "魔界"],
                "chapter_count": 2,
                "time_timeline": "天啟二年夏 - 天啟二年冬",
                "sequence_context": "全書終極大收束篇",
                "applicable_rules": ["終極法則：凡踏入魔界深淵者，修為減半"]
            }
        ]
        
        db.save_volumes(self.novel_id, self.volumes_setup)
        
        # 初始化簡易世界觀與角色，以通過 Planner 的 prereq 驗證
        db.save_worldbuilding(self.novel_id, json.dumps({
            "theme": "宿命與抗爭",
            "main_conflict": "正邪大戰",
            "worldview": "一個靈氣復甦的修真世界",
            "macro_outline": "主角一路修仙最終封印神魔的故事",
            "three_act_structure": [{"title": "開篇", "content": "第一幕劇情"}],
            "progressive_character_plan": [{"title": "階段一", "content": "角色初始成長"}],
            "foreshadowing_seeds": ["[Seed-1] 師尊的反水伏筆"],
            "key_turning_points": ["[TurningPoint-1] 師尊反水時刻"]
        }, ensure_ascii=False))
        
        db.save_characters(self.novel_id, json.dumps({
            "characters": [
                {
                    "name": "雲澈",
                    "role": "主角",
                    "entry_phase": "第一章",
                    "personality": ["堅韌", "冷靜"],
                    "want": "修得大道以救母",
                    "need": "斬斷因果",
                    "fatal_flaw": "重情重義",
                    "motivation": "家族被滅的血海深仇",
                    "arc": "從凡人蛻變為太上斬仙者"
                }
            ]
        }, ensure_ascii=False))

    def tearDown(self):
        # 清理測試小說數據
        db.delete_novel(self.novel_id)

    def test_database_volume_calculations(self):
        """測試 db.py 中的篇卷章節範圍與歸屬索引動態計算"""
        volumes = db.get_volumes(self.novel_id)
        
        # 1. 驗證 volumes 資料讀寫包含我們新加的欄位
        self.assertEqual(len(volumes), 3)
        self.assertEqual(int(volumes[0]["chapter_count"]), 3)
        self.assertEqual(volumes[0]["time_timeline"], "天啟元年春 - 天啟元年夏")
        self.assertEqual(volumes[0]["sequence_context"], "第一部故事引入開卷")
        
        # 2. 驗證 get_volume_chapter_range
        # 第一卷：第 1 章 至 第 3 章
        start1, end1 = db.get_volume_chapter_range(volumes, 1)
        self.assertEqual((start1, end1), (1, 3))
        
        # 第二卷：第 4 章 至 第 8 章
        start2, end2 = db.get_volume_chapter_range(volumes, 2)
        self.assertEqual((start2, end2), (4, 8))
        
        # 第三卷：第 9 章 至 第 10 章
        start3, end3 = db.get_volume_chapter_range(volumes, 3)
        self.assertEqual((start3, end3), (9, 10))
        
        # 3. 驗證 get_chapter_volume_index
        self.assertEqual(db.get_chapter_volume_index(volumes, 1), 1)
        self.assertEqual(db.get_chapter_volume_index(volumes, 3), 1)
        self.assertEqual(db.get_chapter_volume_index(volumes, 4), 2)
        self.assertEqual(db.get_chapter_volume_index(volumes, 8), 2)
        self.assertEqual(db.get_chapter_volume_index(volumes, 9), 3)
        self.assertEqual(db.get_chapter_volume_index(volumes, 10), 3)
        
        # 4. 驗證 get_total_chapter_count
        self.assertEqual(db.get_total_chapter_count(volumes), 10)
        
        # 5. 驗證超出範圍的 Fallback 機制 (依最後一卷的預設 chapter_count=2 進行動態推導)
        # 第四卷：應該是從 11 開始，包含 2 章，即 (11, 12)
        start4, end4 = db.get_volume_chapter_range(volumes, 4)
        self.assertEqual((start4, end4), (11, 12))
        self.assertEqual(db.get_chapter_volume_index(volumes, 12), 4)

    def test_run_plot_planner_interface(self):
        """測試大綱規劃師呼叫介面與總監評判指令/篇卷時間法則對接"""
        # 1. 不帶總監指令直接生成 (會讀取第一卷的青雲開篇設定)
        generator = run_plot_planner(self.novel_id, user_prompt="請注重雲澈在青雲山谷與魔門遇襲的情節")
        self.assertIsNotNone(generator)
        
        # 2. 傳入總監評判指令，確保支援 signature 對接
        generator_with_directive = run_plot_planner(
            self.novel_id, 
            user_prompt="無", 
            planner_directive="總監評判：第一章情節過於平淡，必須增加雲澈燃燒壽命施展禁忌爆發逃生的具體動作場景"
        )
        self.assertIsNotNone(generator_with_directive)

    def test_volume_jit_alignment_dynamic_count(self):
        """測試微觀 JIT 篇卷對齊的動態 chapter_count 生成呼叫"""
        # 為第三卷 (規劃了 2 章) 發起對齊，確認其動態計算出章節區間與數量
        generator = run_volume_jit_alignment(self.novel_id, 3)
        self.assertIsNotNone(generator)

    def test_incremental_volumes_modification(self):
        """測試 volumes 篇卷與時間軸的增量局部修改與同步"""
        mock_llm_output = json.dumps({
            "volumes": [
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
                    "time_timeline": "天啟元年秋 - 天啟三年春",  # 修改時間軸
                    "sequence_context": "系列中期大高潮",  # 修改定位
                    "applicable_rules": ["法則二"]
                },
                {
                    "volume_index": 3,
                    "title": "測試卷三：神魔收束",
                    "summary": "大收尾",
                    "factions": ["修真界"],
                    "chapter_count": 2,
                    "time_timeline": "天啟三年夏",
                    "sequence_context": "大結局",
                    "applicable_rules": ["法則三"]
                }
            ]
        }, ensure_ascii=False)
        
        # 1. 取得原有世界觀 JSON
        wb = db.get_latest_worldbuilding(self.novel_id)
        current_json = db.parse_worldview_to_json(wb["content"])
        
        # 2. 解析 mock LLM 吐出的內容
        parsed = json.loads(mock_llm_output)
        
        # 3. 執行我們的 volumes 縫合與資料庫同步邏輯
        volumes_data = parsed.get("volumes", parsed)
        self.assertTrue(isinstance(volumes_data, list))
        
        current_json["volumes"] = volumes_data
        db.save_worldbuilding(self.novel_id, json.dumps(current_json, ensure_ascii=False, indent=2))
        db.save_volumes(self.novel_id, volumes_data)
        
        # 4. 驗證資料庫與 JSON 是否已同步更新
        updated_volumes = db.get_volumes(self.novel_id)
        self.assertEqual(len(updated_volumes), 3)
        self.assertEqual(int(updated_volumes[1]["chapter_count"]), 8)
        self.assertEqual(updated_volumes[1]["time_timeline"], "天啟元年秋 - 天啟三年春")
        self.assertEqual(updated_volumes[1]["sequence_context"], "系列中期大高潮")

if __name__ == '__main__':
    unittest.main()
