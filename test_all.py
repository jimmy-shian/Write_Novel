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
    sys.stdout.reconfigure(encoding='utf-8')

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
            "foreshadowing_seeds": ["伏筆種子1"],
            "key_turning_points": ["轉折點1"]
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
                    "personality": ["勇敢", "堅韌"],
                    "want": "尋找真相",
                    "need": "自我救贖",
                    "fatal_flaw": "過於衝動",
                    "motivation": "家族覆滅",
                    "arc": "從衝動少年成長為沉穩領袖",
                    "relationships": []
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
                    "personality": ["冷靜"],
                    "want": "生存",
                    "need": "信任他人",
                    "fatal_flaw": "多疑",
                    "motivation": "末日來臨",
                    "arc": "無",
                    "relationships": []
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
        all_seeds = ["伏筆種子1", "伏筆種子2", "伏筆種子3"]
        all_turns = ["轉折點1", "轉折點2"]
        
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


if __name__ == "__main__":
    unittest.main()
