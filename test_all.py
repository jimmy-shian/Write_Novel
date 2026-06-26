# -*- coding: utf-8 -*-
"""
AI Novel Factory Complete Integrated Unit Tests
Run with: C:\\Users\\user\\venv\\Scripts\\python.exe test_all.py
Force UTF-8 encoding.
"""

import sys
import os
import unittest
import json
import time
from fastapi.testclient import TestClient

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Mock standard modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import db
import llm
import agents
from app import app
from models.parsers import extract_json_block, validate_plot_quality


class TestAINovelFactory(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Initialize DB in case it doesn't exist
        db.db_init()
        cls.client = TestClient(app)
        cls.novel_id = "test-novel-uuid-12345"
        
    def setUp(self):
        # Clear out existing test novel
        db.delete_novel(self.novel_id)
        # Create fresh test novel
        db.create_novel(self.novel_id, "測試史詩大作", "Fantasy", "Classic Modernism")
        
    def tearDown(self):
        db.delete_novel(self.novel_id)

    def _foreshadowing_seeds(self, count=50):
        return [
            {
                "id": i + 1,
                "name": f"伏筆種子{i + 1}",
                "description": f"伏筆描述{i + 1}",
                "setup_hint": f"第{i + 1}個埋設提示",
                "payoff_hint": f"第{i + 1}個回收提示",
                "related_characters": ["主角A"],
                "thematic_link": "命運與選擇"
            }
            for i in range(count)
        ]

    def _turning_points(self, count=50):
        return [
            {
                "id": i + 1,
                "turning_point_name": f"轉折點{i + 1}",
                "description": f"轉折描述{i + 1}",
                "trigger_condition": "主角做出關鍵選擇",
                "structural_impact": "改變局勢與角色關係",
                "emotional_stakes": "信任與失去的代價",
                "related_characters": ["主角A"]
            }
            for i in range(count)
        ]

    def _valid_volumes(self, count=10, chapter_count=40):
        return [
            {
                "volume_index": i + 1,
                "title": f"第{i + 1}卷",
                "summary": f"第{i + 1}卷概要" * 20,
                "chapter_count": chapter_count,
                "factions": [],
                "time_timeline": "",
                "sequence_context": "",
                "applicable_rules": []
            }
            for i in range(count)
        ]

    # --- 1. Database and CRUD Tests ---
    def test_database_crud(self):
        novel = db.get_novel(self.novel_id)
        self.assertIsNotNone(novel)
        self.assertEqual(novel["title"], "測試史詩大作")
        self.assertEqual(novel["genre"], "Fantasy")
        self.assertEqual(novel["style"], "Classic Modernism")
        
        # Test List Novels
        novels = db.list_novels()
        self.assertTrue(len(novels) > 0)
        self.assertTrue(any(n["id"] == self.novel_id for n in novels))

    # --- 2. Worldview and Versioning Tests ---
    def test_worldview_and_patches(self):
        # Save worldview
        wv_content = json.dumps({
            "theme": "命運與反抗",
            "main_conflict": "光明與黑暗",
            "worldview": "一個古老的魔法世界",
            "macro_outline": "主角歷經磨難最終拯救世界",
            "multi_act_structure": [{"title": "第一幕", "content": "開端"}],
            "progressive_character_plan": [{"title": "第一波", "content": "登場"}],
            "foreshadowing_seeds": [
                {
                    "name": "隱蔽的傳承鑰匙",
                    "description": "主角隨身攜帶的銅戒，其實是開啟遠古遺跡的鑰匙",
                    "setup_hint": "第一卷開頭由主角父親贈予",
                    "payoff_hint": "第五卷在遺跡大門前插入解鎖",
                    "related_characters": ["林澤"],
                    "thematic_link": "象徵命運的傳承與責任"
                }
            ],
            "key_turning_points": [
                {
                    "turning_point_name": "家族覆滅的真相揭曉",
                    "description": "林澤發現幕後黑手竟是自己一直信任的導師",
                    "structural_impact": "師徒關係破裂，林澤徹底走向獨立反抗之路",
                    "trigger_condition": "在密室中找到導師與敵對陣營來往的密信",
                    "related_characters": ["林澤", "導師"]
                }
            ]
        }, ensure_ascii=False)
        
        version = db.save_worldbuilding(self.novel_id, wv_content)
        self.assertEqual(version, 1)
        
        # Check latest worldview
        wb = db.get_latest_worldbuilding(self.novel_id)
        self.assertIsNotNone(wb)
        self.assertEqual(wb["version"], 1)
        self.assertIn("命運與反抗", wb["content"])
        
        # Add a patch
        db.add_worldview_patch(self.novel_id, "力量體系", "新增了混沌魔法設定", 1)
        patches = db.get_worldview_patches(self.novel_id)
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]["category"], "力量體系")
        self.assertEqual(patches[0]["details"], "新增了混沌魔法設定")

    # --- 3. Characters Bible JSON Tests ---
    def test_characters_bible(self):
        char_data = {
            "characters": [
                {
                    "name": "林澤",
                    "role": "主角",
                    "entry_phase": "第一幕",
                    "personality": ["勇敢", "堅韌"],
                    "want": "尋找真相",
                    "need": "自我救贖",
                    "fatal_flaw": "過於衝動",
                    "want_need_conflict": "在尋求復仇的快感與內心道德的救贖之間苦苦掙扎",
                    "secret": "他曾在無意中放走了滅門慘案中的一個幫兇",
                    "motivation": "家族覆滅",
                    "arc": "從衝動少年成長為沉穩領袖",
                    "speech_style": "言辭簡練，語氣堅定，常用口頭禪『真相就在迷霧之後』",
                    "appearance": "身穿灰色布衣，眼神堅毅，左手戴有一枚古舊銅戒",
                    "background": "原本是落魄貴族之子，因家族遭遇神秘勢力屠殺而流亡",
                    "relationships": [
                        {
                            "with": "配角A",
                            "type": "生死摯友",
                            "evolution": "從猜忌逐步建立無條件信任"
                        }
                    ],
                    "relationship_matrix": ["與仇人B處於宿命的敵對狀態", "與配角A是生死之交"]
                }
            ]
        }
        
        v = db.save_characters(self.novel_id, char_data)
        self.assertEqual(v, 1)
        
        # Read characters
        latest_char = db.get_latest_characters(self.novel_id)
        self.assertIsNotNone(latest_char)
        self.assertEqual(latest_char["parsed_data"]["characters"][0]["name"], "林澤")

    # --- 4. JSON Extract Parsers and Verification Engine ---
    def test_json_parsers(self):
        raw_text_1 = "Here is the output ```json\n{\"theme\": \"測試主題\"}\n``` And some text."
        parsed_1 = extract_json_block(raw_text_1)
        self.assertEqual(parsed_1.get("theme"), "測試主題")
        
        raw_text_2 = "{\n  \"main_conflict\": \"測試衝突\"\n}"
        parsed_2 = extract_json_block(raw_text_2)
        self.assertEqual(parsed_2.get("main_conflict"), "測試衝突")

        # Test plot quality equation validator
        plot_invalid = {"events": [{"scene": "短", "consequence": "太短"}]}
        self.assertFalse(validate_plot_quality(plot_invalid))
        
        plot_valid = {
            "events": [
                {"scene": "主角在酒館遇到神秘老者", "consequence": "獲得重要地圖與寫作線索"}
            ]
        }
        self.assertTrue(validate_plot_quality(plot_valid))

    # --- 5. Exponential Backoff and Retry calculations ---
    def test_retry_backoff_equation(self):
        # Test exponential delays calculation with attempts
        base_delay = 1.0
        multiplier = 1.5
        max_delay = 10.0
        
        delays = []
        for attempt in range(1, 6):
            delay = min(max_delay, base_delay * (multiplier ** (attempt - 1)))
            delays.append(delay)
            
        self.assertListEqual(delays, [1.0, 1.5, 2.25, 3.375, 5.0625])

    # --- 6. FastAPI Client Integration Endpoints Tests ---
    def test_fastapi_endpoints(self):
        # Save settings test
        settings_payload = {
            "agent_name": "architect",
            "api_key": "test-key-abc",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "model": "google/gemma-3n-e4b-it",
            "temperature": 0.35,
            "top_p": 0.95,
            "max_tokens": 8192,
            "enable_thinking": True
        }
        resp = self.client.post("/api/settings", json=settings_payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")
        
        # Expose and read settings
        resp_get = self.client.get("/api/settings")
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp_get.json()["architect"]["api_key"], "test-key-abc")

    # --- 7. Programmatic JSON Adjustments with Code-based Retries ---
    def test_programmatic_json_adjustments(self):
        # Save a character first
        char_data = {
            "characters": [
                {
                    "name": "陳飛",
                    "role": "配角",
                    "entry_phase": "第二幕",
                    "personality": ["冷靜"],
                    "want": "生存",
                    "need": "信任他人",
                    "fatal_flaw": "多疑",
                    "want_need_conflict": "在求生本能與信任同伴的渴望中掙扎",
                    "secret": "曾經背叛過前任隊友",
                    "motivation": "末日來臨",
                    "arc": "無",
                    "speech_style": "語速極快，常帶有戒備的語氣",
                    "appearance": "瘦削，戴著黑框眼鏡",
                    "background": "前科研所研究員",
                    "relationships": [],
                    "relationship_matrix": []
                }
            ]
        }
        db.save_characters(self.novel_id, char_data)
        
        # Test character adjustment endpoint
        payload = {
            "char_index": 0,
            "field_name": "personality",
            "value": ["冷靜", "機智", "善解人意"]
        }
        resp = self.client.post(f"/api/novels/{self.novel_id}/characters/adjust", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")
        
        # Read back and verify update
        latest_char = db.get_latest_characters(self.novel_id)
        self.assertListEqual(latest_char["parsed_data"]["characters"][0]["personality"], ["冷靜", "機智", "善解人意"])

        # Test index out of bounds error handler
        payload_invalid = {
            "char_index": 99,
            "field_name": "want",
            "value": "無"
        }
        resp_invalid = self.client.post(f"/api/novels/{self.novel_id}/characters/adjust", json=payload_invalid)
        self.assertEqual(resp_invalid.status_code, 500)

    # --- 8. Deterministic Seeding and Chessboard Scattering Algorithm ---
    def test_deterministic_seeding_and_scattering_algorithm(self):
        import hashlib
        import random
        
        novel_id = "test-deterministic-novel-id-12345"
        T = 120
        all_seeds = [
            {"name": "伏筆種子1", "description": "描述1"},
            {"name": "伏筆種子2", "description": "描述2"},
            {"name": "伏筆種子3", "description": "描述3"}
        ]
        all_turns = [
            {"turning_point_name": "轉折點1", "description": "描述1"},
            {"turning_point_name": "轉折點2", "description": "描述2"}
        ]
        
        def run_scattering(nid, tot_ch, seeds, turns):
            h_seed = int(hashlib.md5(f"global_blueprint_{nid}".encode('utf-8')).hexdigest(), 16) % (2**32)
            r = random.Random(h_seed)
            
            foreshadowing_allocations = []
            min_span = max(1, tot_ch // 10)
            for idx, seed in enumerate(seeds):
                if tot_ch <= 2:
                    P = 1
                    R = tot_ch
                else:
                    P = r.randint(1, max(1, tot_ch - min_span))
                    R = r.randint(P + min_span, tot_ch)
                foreshadowing_allocations.append((P, R))
                
            turning_allocations = []
            for jdx, turn in enumerate(turns):
                K = r.randint(1, tot_ch)
                turning_allocations.append(K)
                
            return foreshadowing_allocations, turning_allocations
            
        alloc1_seeds, alloc1_turns = run_scattering(novel_id, T, all_seeds, all_turns)
        alloc2_seeds, alloc2_turns = run_scattering(novel_id, T, all_seeds, all_turns)
        
        self.assertListEqual(alloc1_seeds, alloc2_seeds)
        self.assertListEqual(alloc1_turns, alloc2_turns)
        
        # Verify that planting is strictly before payoff
        for P, R in alloc1_seeds:
            self.assertTrue(P < R)
            self.assertTrue(1 <= P <= T)
            self.assertTrue(1 <= R <= T)

    # --- 9. Global Foreshadowing Precomputation Tests ---
    def test_global_foreshadowing_precomputation(self):
        # 1. Save worldview with seeds and turning points
        wv_content = json.dumps({
            "theme": "伏筆測試",
            "main_conflict": "衝突",
            "worldview": "世界觀",
            "macro_outline": "大綱",
            "multi_act_structure": [],
            "progressive_character_plan": [],
            "foreshadowing_seeds": [
                {"name": "伏筆A", "description": "描述A"},
                {"name": "伏筆B", "description": "描述B"},
                {"name": "伏筆C", "description": "描述C"}
            ],
            "key_turning_points": [
                {"turning_point_name": "轉折X", "description": "描述X"},
                {"turning_point_name": "轉折Y", "description": "描述Y"}
            ]
        }, ensure_ascii=False)
        db.save_worldbuilding(self.novel_id, wv_content)
        
        # 2. Save some volumes with specified chapter count (e.g. Vol 1 has 30 chapters, Vol 2 has 40 chapters)
        volumes_list = [
            {
                "volume_index": 1, 
                "title": "第一卷", 
                "summary": "摘要1", 
                "chapter_count": 30,
                "factions": ["陣營1"],
                "time_timeline": "時間線1",
                "sequence_context": "背景1",
                "applicable_rules": []
            },
            {
                "volume_index": 2, 
                "title": "第二卷", 
                "summary": "摘要2", 
                "chapter_count": 40,
                "factions": ["陣營2"],
                "time_timeline": "時間線2",
                "sequence_context": "背景2",
                "applicable_rules": []
            }
        ]
        db.save_volumes(self.novel_id, volumes_list)
        
        # 3. Read precomputed blueprint from DB (since save_volumes triggers auto-precompute)
        blueprint = db.get_global_foreshadowing_blueprint(self.novel_id)
        self.assertIsNotNone(blueprint)
        
        # T should be 30 + 40 = 70 chapters
        self.assertEqual(blueprint["T"], 70)
        self.assertEqual(len(blueprint["foreshadowing_allocations"]), 3)
        self.assertEqual(len(blueprint["turning_allocations"]), 2)
        
        # Verify allocations ranges
        for P, R in blueprint["foreshadowing_allocations"]:
            self.assertTrue(1 <= P < R <= 70)
        for K in blueprint["turning_allocations"]:
            self.assertTrue(1 <= K <= 70)
            
        # 4. Modify worldview (add a new seed) and test automatic self-healing precomputation
        wv_content_updated = json.dumps({
            "theme": "伏筆測試",
            "main_conflict": "衝突",
            "worldview": "世界觀",
            "macro_outline": "大綱",
            "multi_act_structure": [],
            "progressive_character_plan": [],
            "foreshadowing_seeds": [
                {"name": "伏筆A", "description": "描述A"},
                {"name": "伏筆B", "description": "描述B"},
                {"name": "伏筆C", "description": "描述C"},
                {"name": "新增伏筆D", "description": "描述D"}
            ],
            "key_turning_points": [
                {"turning_point_name": "轉折X", "description": "描述X"},
                {"turning_point_name": "轉折Y", "description": "描述Y"}
            ]
        }, ensure_ascii=False)
        db.save_worldbuilding(self.novel_id, wv_content_updated)
        
        # Calling get_global_foreshadowing_blueprint should auto-detect seed count mismatch (4 seeds vs 3 in old blueprint) and heal it
        blueprint_updated = db.get_global_foreshadowing_blueprint(self.novel_id)
        self.assertEqual(len(blueprint_updated["foreshadowing_allocations"]), 4)
        self.assertEqual(blueprint_updated["T"], 70)

    # --- 10. Rigid Validation Report and Stage Detection Tests ---
    def test_validation_report_and_stage_detection(self):
        # 1. Initially it should detect "worldview" stage for a new novel with no worldview
        db.delete_novel(self.novel_id)
        db.create_novel(self.novel_id, "剛性測試小說", "Fantasy", "Classic")
        
        stage = db.detect_current_stage(self.novel_id)
        self.assertEqual(stage, "worldview")
        
        # 2. Save worldview (without foreshadowing) -> stage should advance to "characters"
        wv_content = json.dumps({
            "theme": "主線" * 25,
            "main_conflict": "對立" * 50,
            "worldview": "規則" * 150,
            "macro_outline": "故事大綱" * 100,
            "multi_act_structure": [
                {"title": "第一幕 (Setup)", "content": "開端描述..."},
                {"title": "第二幕 (Confrontation)", "content": "衝突描述..."},
                {"title": "第三幕 (Resolution)", "content": "收尾描述..."}
            ],
            "progressive_character_plan": [
                {"title": "第一波開篇 (Wave 1)", "content": "第一波人設..."},
                {"title": "第二波發展 (Wave 2)", "content": "第二波人設..."},
                {"title": "第三波高潮 (Wave 3)", "content": "第三波人設..."}
            ]
        }, ensure_ascii=False)
        db.save_worldbuilding(self.novel_id, wv_content)
        
        stage = db.detect_current_stage(self.novel_id)
        self.assertEqual(stage, "characters")
        
        # 3. Save characters -> stage should advance to "foreshadowing"
        char_data = {
            "characters": [
                {
                    "name": "主角A",
                    "role": "主角",
                    "entry_phase": "第一幕",
                    "personality": ["堅毅"],
                    "want": "生存" * 10,
                    "need": "救贖" * 10,
                    "fatal_flaw": "衝動" * 10,
                    "want_need_conflict": "在復仇的怒火與靈魂的救贖之間反覆掙扎" * 2,
                    "secret": "他是當年家族慘案的唯一倖存者" * 2,
                    "motivation": "復仇",
                    "arc": "無" * 15,
                    "speech_style": "沉穩" * 10,
                    "appearance": "精神",
                    "background": "普通",
                    "relationships": [],
                    "relationship_matrix": ["與仇人B處於宿命的敵對狀態"]
                }
            ]
        }
        db.save_characters(self.novel_id, char_data)
        stage = db.detect_current_stage(self.novel_id)
        self.assertEqual(stage, "foreshadowing")
        
        # 3.5. Save worldview with foreshadowing seeds -> stage should advance to "volumes"
        wv_content_with_seeds = json.dumps({
            "theme": "主線" * 25,
            "main_conflict": "對立" * 50,
            "worldview": "規則" * 150,
            "macro_outline": "故事大綱" * 100,
            "multi_act_structure": [
                {"title": "第一幕 (Setup)", "content": "開端描述..."},
                {"title": "第二幕 (Confrontation)", "content": "衝突描述..."},
                {"title": "第三幕 (Resolution)", "content": "收尾描述..."}
            ],
            "progressive_character_plan": [
                {"title": "第一波開篇 (Wave 1)", "content": "第一波人設..."},
                {"title": "第二波發展 (Wave 2)", "content": "第二波人設..."},
                {"title": "第三波高潮 (Wave 3)", "content": "第三波人設..."}
            ],
            "foreshadowing_seeds": self._foreshadowing_seeds(),
            "key_turning_points": self._turning_points()
        }, ensure_ascii=False)
        db.save_worldbuilding(self.novel_id, wv_content_with_seeds)
        stage = db.detect_current_stage(self.novel_id)
        self.assertEqual(stage, "volumes")
        
        # 4. Save volumes -> stage should advance to "volume_skeleton"
        volumes_list = self._valid_volumes()
        db.save_volumes(self.novel_id, volumes_list)
        stage = db.detect_current_stage(self.novel_id)
        self.assertEqual(stage, "volume_skeleton")
        
        # 5. Save all volume skeleton outlines -> stage should advance to "writer"
        for vol in db.get_volumes(self.novel_id):
            vol_idx = int(vol["volume_index"])
            start_ch, end_ch = db.get_volume_chapter_range(db.get_volumes(self.novel_id), vol_idx)
            skeleton_outline = []
            for chapter_index in range(start_ch, end_ch + 1):
                skeleton_outline.append({
                    "chapter_index": chapter_index,
                    "chapter_title": f"第{chapter_index}章",
                    "chapter_summary": "介紹",
                    "time_setting": "第1天",
                    "scene_setting": "酒館",
                    "events": [{"scene_index": 1, "location": "酒館", "characters": ["主角A"], "content": "遇見神秘人"}],
                    "characters_active": ["主角A"],
                    "emotional_tone": "緊張",
                    "cliffhanger": "留下懸念",
                    "allocated_tasks": {"foreshadowing_plants": [], "foreshadowing_payoffs": [], "turning_points": []}
                })
            db.update_volume_outline(self.novel_id, vol_idx, skeleton_outline)
        stage = db.detect_current_stage(self.novel_id)
        self.assertEqual(stage, "writer")
        
        # 6. Generate validation report and check format
        report = db.generate_validation_report(self.novel_id)
        self.assertIn("🤖 系統底層剛性資料結構與進度校驗報告", report)
        self.assertIn("【1. 世界觀與核心設定層】", report)
        self.assertIn("【2. 角色聖經層】", report)
        self.assertIn("【3. 篇卷規劃與骨架大綱層】", report)
        self.assertIn("[Seed-1]", report)
        self.assertIn("伏筆種子1", report)
        self.assertIn("[主角A] (主角) ✅ 核心欄位足夠", report)
        self.assertIn("卷 1《第1卷》：✅ 骨架已建立", report)

    # --- 11. Volume and Chapter Hard Constraints Tests ---
    def test_volume_and_chapter_constraints(self):
        import unittest.mock as mock
        
        wv_content = json.dumps({
            "theme": "主線",
            "main_conflict": "對立",
            "worldview": "規則",
            "macro_outline": "故事大綱",
            "multi_act_structure": [],
            "progressive_character_plan": [],
            "foreshadowing_seeds": self._foreshadowing_seeds(),
            "key_turning_points": self._turning_points()
        }, ensure_ascii=False)
        db.save_worldbuilding(self.novel_id, wv_content)
        
        mock_raw_output = {
            "volumes": [
                {
                    "volume_index": 1, 
                    "title": "第一卷", 
                    "summary": "概要1", 
                    "chapter_count": 100,
                    "factions": [],
                    "time_timeline": "",
                    "sequence_context": "",
                    "applicable_rules": []
                },
                {
                    "volume_index": 2, 
                    "title": "第二卷", 
                    "summary": "概要2", 
                    "chapter_count": 0,
                    "factions": [],
                    "time_timeline": "",
                    "sequence_context": "",
                    "applicable_rules": []
                },
                {
                    "volume_index": 3, 
                    "title": "第三卷", 
                    "summary": "概要3", 
                    "chapter_count": 42,
                    "factions": [],
                    "time_timeline": "",
                    "sequence_context": "",
                    "applicable_rules": []
                }
            ]
        }
        
        mock_stream = [
            f"data: {json.dumps({'type': 'content', 'delta': json.dumps(mock_raw_output, ensure_ascii=False)}, ensure_ascii=False)}"
        ]
        
        with mock.patch("agents.call_llm_stream", return_value=mock_stream):
            list(agents.run_volumes_planner(self.novel_id, mode="generate"))
            
        vols = db.get_volumes(self.novel_id)
        self.assertEqual(len(vols), 0)
        
        valid_raw_output = {"volumes": self._valid_volumes()}
        valid_stream = [
            f"data: {json.dumps({'type': 'content', 'delta': json.dumps(valid_raw_output, ensure_ascii=False)}, ensure_ascii=False)}"
        ]
        with mock.patch("agents.call_llm_stream", return_value=valid_stream):
            list(agents.run_volumes_planner(self.novel_id, mode="generate"))
        vols = db.get_volumes(self.novel_id)
        self.assertEqual(len(vols), 10)
        self.assertEqual(vols[0]["chapter_count"], 40)
        self.assertEqual(vols[-1]["volume_index"], 10)

    def test_volume_skeleton_planner_generates_only_missing_batch(self):
        import unittest.mock as mock

        wv_content = json.dumps({
            "theme": "主線",
            "main_conflict": "對立",
            "worldview": "規則",
            "macro_outline": "故事大綱",
            "multi_act_structure": [],
            "progressive_character_plan": [],
            "foreshadowing_seeds": self._foreshadowing_seeds(),
            "key_turning_points": self._turning_points()
        }, ensure_ascii=False)
        db.save_worldbuilding(self.novel_id, wv_content)
        db.save_volumes(self.novel_id, self._valid_volumes(count=10, chapter_count=40))

        existing = []
        for chapter_index in range(1, 33):
            existing.append({
                "chapter_index": chapter_index,
                "chapter_title": f"既有第{chapter_index}章",
                "chapter_summary": "既有摘要",
                "time_setting": "第1天",
                "events": [{"scene_index": 1, "location": "測試地點", "characters": ["主角A"], "content": "既有事件"}],
                "cliffhanger": "既有懸念",
                "allocated_tasks": {"foreshadowing_plants": [], "foreshadowing_payoffs": [], "turning_points": []}
            })
        db.update_volume_outline(self.novel_id, 1, existing)

        generated = {
            "volume_index": 1,
            "chapters_skeleton": [
                {
                    "chapter_index": chapter_index,
                    "chapter_title": f"補全第{chapter_index}章",
                    "chapter_summary": "補全摘要",
                    "time_setting": "第2天",
                    "events": [{"scene_index": 1, "location": "補全地點", "characters": ["主角A"], "content": "補全事件"}],
                    "cliffhanger": "補全懸念",
                    "allocated_tasks": {"foreshadowing_plants": [], "foreshadowing_payoffs": [], "turning_points": []}
                }
                for chapter_index in range(33, 41)
            ]
        }
        mock_stream = [
            f"data: {json.dumps({'type': 'content', 'delta': json.dumps(generated, ensure_ascii=False)}, ensure_ascii=False)}\n\n",
            f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        ]

        with mock.patch("agents.call_llm_stream", return_value=mock_stream) as mocked_stream:
            list(agents.run_volume_skeleton_planner(self.novel_id, 1))

        self.assertEqual(mocked_stream.call_count, 1)
        prompt_text = json.dumps(mocked_stream.call_args.args[1], ensure_ascii=False)
        self.assertIn("第 33 至第 40 章", prompt_text)
        self.assertIn("不得輸出範圍外章節", prompt_text)

        vol = next(v for v in db.get_volumes(self.novel_id) if int(v["volume_index"]) == 1)
        chapters = vol["chapters_outline"]
        indexes = sorted(int(ch["chapter_index"]) for ch in chapters)
        self.assertEqual(indexes, list(range(1, 41)))
        self.assertEqual(chapters[0]["chapter_title"], "既有第1章")
        self.assertTrue(any(ch["chapter_title"] == "補全第40章" for ch in chapters))

    # --- 12. Incremental Patch Engine Foreshadowing Dict Tests ---
    def test_incremental_patch_engine_foreshadowing(self):
        from incremental_patch_engine import validate_and_merge_incremental_patch
        
        # 1. Setup initial worldview in DB
        wv_content = json.dumps({
            "theme": "主線",
            "main_conflict": "對立",
            "worldview": "規則",
            "macro_outline": "故事大綱",
            "multi_act_structure": [],
            "progressive_character_plan": [],
            "foreshadowing_seeds": [
                {
                    "name": "舊伏筆",
                    "description": "舊描述"
                }
            ],
            "key_turning_points": [
                {
                    "turning_point_name": "舊轉折點",
                    "description": "舊描述"
                }
            ]
        }, ensure_ascii=False)
        db.save_worldbuilding(self.novel_id, wv_content)
        
        # 2. Try to append structured foreshadowing seeds dict payload
        patch_seeds = {
            "foreshadowing_seeds": [
                {
                    "name": "新伏筆物件",
                    "description": "新描述內容"
                }
            ]
        }
        success, version, err = validate_and_merge_incremental_patch(self.novel_id, "foreshadowing_seeds", "PATCH", json.dumps(patch_seeds, ensure_ascii=False))
        self.assertTrue(success, f"Merge failed: {err}")
        
        # Verify saved result
        wb = db.get_latest_worldbuilding(self.novel_id)
        parsed = json.loads(wb["content"])
        self.assertEqual(len(parsed["foreshadowing_seeds"]), 2)
        self.assertEqual(parsed["foreshadowing_seeds"][1]["name"], "新伏筆物件")
        
        # 3. Try to append structured key turning points dict payload
        patch_turns = {
            "key_turning_points": [
                {
                    "turning_point_name": "新轉折物件",
                    "description": "新轉折內容"
                }
            ]
        }
        success, version, err = validate_and_merge_incremental_patch(self.novel_id, "key_turning_points", "PATCH", json.dumps(patch_turns, ensure_ascii=False))
        self.assertTrue(success, f"Merge failed: {err}")
        
        # Verify saved result
        wb = db.get_latest_worldbuilding(self.novel_id)
        parsed = json.loads(wb["content"])
        self.assertEqual(len(parsed["key_turning_points"]), 2)
        self.assertEqual(parsed["key_turning_points"][1]["turning_point_name"], "新轉折物件")


    def test_task_relevant_context_selection(self):
        from prompts.prompt_builder import (
            build_chapter_writer_messages,
            build_relevant_character_context,
            select_worldview_context,
        )

        characters = {
            "characters": [
                {
                    "name": "林夜",
                    "role": "主角",
                    "background": "林夜的完整背景：禁咒事故倖存者，身上藏有移動核彈級祕密。",
                    "relationships": [{"target": "莫白", "relation": "表面盟友，實為監視者"}],
                    "speech_style": "克制、短句、帶壓迫感"
                },
                {
                    "name": "莫白",
                    "role": "情報販子",
                    "background": "莫白長篇背景不應在未命中時完整塞入 prompt。",
                    "relationships": [{"target": "林夜", "relation": "交易對象"}]
                }
            ]
        }
        outline = {
            "chapter_index": 7,
            "chapter_title": "禁咒殘響",
            "chapter_summary": "林夜在地下車站暴露禁咒殘響，必須壓住失控徵兆。",
            "events": [{"scene": "地下車站", "action": "林夜拒絕交出核心"}]
        }

        selected = build_relevant_character_context(characters, query_text=json.dumps(outline, ensure_ascii=False))
        self.assertEqual(selected["matched_full_character_names"], ["林夜"])
        self.assertEqual(selected["full_characters"][0]["background"], "林夜的完整背景：禁咒事故倖存者，身上藏有移動核彈級祕密。")
        self.assertEqual(selected["other_characters_basic_relationships"][0]["name"], "莫白")
        self.assertIn("relationships", selected["other_characters_basic_relationships"][0])
        self.assertNotIn("background", selected["other_characters_basic_relationships"][0])

        messages = build_chapter_writer_messages(
            "世界觀摘要",
            json.dumps(characters, ensure_ascii=False),
            outline,
            "",
            "",
            "",
            "Classic Modernism",
            7,
        )
        prompt_text = messages[0]["content"] + "\n" + messages[1]["content"]
        self.assertIn("_needs_director_context", prompt_text)
        self.assertIn("林夜的完整背景", prompt_text)
        self.assertIn("莫白", prompt_text)
        self.assertNotIn("莫白長篇背景不應", prompt_text)

        worldview = {
            "theme": "權力與代價",
            "main_conflict": "禁咒治理與個體自由",
            "worldview": "城邦以咒能維生。",
            "macro_outline": "林夜一路追查核心真相。",
            "multi_act_structure": [{"act": 1, "purpose": "揭露規則"}],
            "timeline": "百年前禁咒戰爭。",
            "foreshadowing_seeds": [{"id": 1, "name": "不應進入 volumes 預設上下文"}]
        }
        selected_worldview = select_worldview_context(json.dumps(worldview, ensure_ascii=False), "volumes")
        self.assertIn("macro_outline", selected_worldview)
        self.assertIn("multi_act_structure", selected_worldview)
        self.assertNotIn("foreshadowing_seeds", selected_worldview)



if __name__ == "__main__":
    unittest.main()


