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

# Dynamic path resolution
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
backend_dir = os.path.join(root_dir, "backend")
sys.path.insert(0, current_dir)
sys.path.insert(0, root_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, os.path.join(root_dir, "_archive", "legacy"))
for r_dir, dirs, files in os.walk(backend_dir):
    sys.path.insert(0, r_dir)

import db
import llm
import agents
from app import app
from models.parsers import extract_json_block, validate_plot_quality

# Import modular tools for testing
from backend.services.tools.sub_agent import invoke_sub_agent, SubAgentGenerator
from backend.services.tools.evaluator import evaluate_output
from backend.services.tools.supplement import supplement_content
from backend.services.tools.inspect import inspect_content_block, expand_collapsed_json
from backend.services.tools.navigator import goto_generation_position
from backend.services.tools.registry import TOOL_REGISTRY, export_tools
from backend.prompts.prompt_builder import compact_context_text, compact_json_data


class BaseTestClass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.db_init()
        cls.client = TestClient(app)
        cls.novel_id = "test-novel-uuid-12345"
        
    def setUp(self):
        db.delete_novel(self.novel_id)
        db.release_pipeline_lock(self.novel_id)
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


# ==========================================
# CATEGORY 1: Database & Core Functions Tests
# ==========================================
class TestDatabaseCRUD(BaseTestClass):
    def test_database_crud(self):
        novel = db.get_novel(self.novel_id)
        self.assertIsNotNone(novel)
        self.assertEqual(novel["title"], "測試史詩大作")
        self.assertEqual(novel["genre"], "Fantasy")
        self.assertEqual(novel["style"], "Classic Modernism")
        
        novels = db.list_novels()
        self.assertTrue(len(novels) > 0)
        self.assertTrue(any(n["id"] == self.novel_id for n in novels))


class TestWorldviewAndVersioning(BaseTestClass):
    def test_worldview_and_patches(self):
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
        
        version = db.save_worldbuilding(self.novel_id, wv_content, validate=False)
        self.assertEqual(version, 1)
        
        wb = db.get_latest_worldbuilding(self.novel_id)
        self.assertIsNotNone(wb)
        self.assertEqual(wb["version"], 1)
        self.assertIn("命運與反抗", wb["content"])
        
        db.add_worldview_patch(self.novel_id, "力量體系", "新增了混沌魔法設定", 1)
        patches = db.get_worldview_patches(self.novel_id)
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]["category"], "力量體系")
        self.assertEqual(patches[0]["details"], "新增了混沌魔法設定")


class TestCharactersBible(BaseTestClass):
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
        
        latest_char = db.get_latest_characters(self.novel_id)
        self.assertIsNotNone(latest_char)
        self.assertEqual(latest_char["parsed_data"]["characters"][0]["name"], "林澤")


class TestJsonParsers(BaseTestClass):
    def test_json_parsers(self):
        raw_text_1 = "Here is the output ```json\n{\"theme\": \"測試主題\"}\n``` And some text."
        parsed_1 = extract_json_block(raw_text_1)
        self.assertEqual(parsed_1.get("theme"), "測試主題")
        
        raw_text_2 = "{\n  \"main_conflict\": \"測試衝突\"\n}"
        parsed_2 = extract_json_block(raw_text_2)
        self.assertEqual(parsed_2.get("main_conflict"), "測試衝突")
        
        plot_invalid = {"events": [{"scene": "短", "consequence": "太短"}]}
        self.assertFalse(validate_plot_quality(plot_invalid))
        
        plot_valid = {
            "events": [
                {"scene": "主角在酒館遇到神秘老者", "consequence": "獲得重要地圖與寫作線索"}
            ]
        }
        self.assertTrue(validate_plot_quality(plot_valid))


# ==========================================
# CATEGORY 2: Director Tools Tests (Categorized By Module)
# ==========================================

class TestRegistryTool(BaseTestClass):
    def test_tool_registry_structure(self):
        self.assertIn("inspect_content_block", TOOL_REGISTRY)
        self.assertIn("evaluate_output", TOOL_REGISTRY)
        self.assertIn("supplement_content", TOOL_REGISTRY)
        self.assertIn("expand_collapsed_json", TOOL_REGISTRY)
        self.assertEqual(export_tools(), TOOL_REGISTRY)


class TestNavigatorTool(BaseTestClass):
    def test_goto_generation_position_decision(self):
        res = goto_generation_position(
            target="writer",
            novel_id=self.novel_id,
            volume_index=2,
            chapter_index=15,
            reason="Test Navigation",
            agent_prompt="Write carefully",
            agent_context="Context info"
        )
        self.assertTrue(res["success"])
        dec = res["decision"]
        self.assertEqual(dec["action"], "CONTINUE")
        self.assertEqual(dec["target"], "writer")
        self.assertEqual(dec["volume_index"], 2)
        self.assertEqual(dec["chapter_index"], 15)
        self.assertEqual(dec["hint"], "Write carefully")


class TestInspectTool(BaseTestClass):
    def test_expand_collapsed_json_failure(self):
        # Empty worldview
        res = expand_collapsed_json("worldview", "foreshadowing_seeds", 1, 10, self.novel_id)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "世界觀設定為空")

    def test_expand_collapsed_json_success(self):
        # Setup worldview with seeds
        wv = {"foreshadowing_seeds": [{"id": i, "name": f"seed_{i}"} for i in range(1, 21)]}
        db.save_worldbuilding(self.novel_id, json.dumps(wv), validate=False)
        res = expand_collapsed_json("worldview", "foreshadowing_seeds", 1, 10, self.novel_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["total_count"], 20)
        self.assertEqual(res["returned_count"], 10)
        self.assertEqual(len(res["items"]), 10)

    def test_inspect_content_block_characters(self):
        char_data = {"characters": [{"name": f"角色{i}"} for i in range(1, 21)]}
        db.save_characters(self.novel_id, char_data)
        res = inspect_content_block(stage_name="characters", block_name="characters", novel_id=self.novel_id, start_index=1, end_index=10)
        self.assertTrue(res["success"])
        self.assertEqual(res["total_count"], 20)
        self.assertEqual(res["returned_count"], 10)


class TestEvaluatorTool(BaseTestClass):
    def test_evaluate_output_worldview(self):
        # Unpassed case
        res = evaluate_output("worldview", json.dumps({"theme": ""}), self.novel_id)
        self.assertFalse(res["passed"])
        self.assertIn("缺少必填欄位", res["message"])

        # Passed case
        res_ok = evaluate_output("worldview", json.dumps({
            "theme": "A", "main_conflict": "B", "worldview": "C", "macro_outline": "D"
        }), self.novel_id)
        self.assertTrue(res_ok["passed"])


class TestSubAgentTool(BaseTestClass):
    def test_sub_agent_generator_iterable(self):
        def dummy_gen():
            yield "chunk1"
            yield "chunk2"
            return {"success": True}
        
        gen = SubAgentGenerator(dummy_gen())
        chunks = list(gen)
        self.assertEqual(chunks, ["chunk1", "chunk2"])
        self.assertEqual(gen.result, {"success": True})


class TestSupplementTool(BaseTestClass):
    def test_supplement_content_call(self):
        # We can't easily perform a live LLM call inside unit tests,
        # but we can verify it builds the generator correctly.
        import unittest.mock as mock
        with mock.patch("backend.services.tools.supplement.call_llm_stream") as mocked_stream:
            mocked_stream.return_value = ["chunk"]
            gen = supplement_content("worldview", "orig", "fix", self.novel_id, stream=False)
            res = list(gen)
            self.assertEqual(res, ["chunk"])


# ==========================================
# CATEGORY 3: Prompt Collapsing & Truncation Tests
# ==========================================

class TestPromptTrimmer(BaseTestClass):
    def test_compact_context_text_short(self):
        short_val = "This is short"
        res = compact_context_text(short_val, limit=100, label="test")
        self.assertEqual(res, short_val)

    def test_compact_context_text_long_collapsed(self):
        long_val = "A" * 5000
        res = compact_context_text(long_val, limit=2000, label="上一輪 Agent output")
        # Should be a valid JSON
        parsed = json.loads(res)
        self.assertEqual(parsed["director_payload_view"], "collapsed_json")
        self.assertEqual(parsed["payload_kind"], "上一輪 Agent output")
        self.assertEqual(parsed["char_count"], 5000)
        self.assertIn("已由後端收合以防止原始截斷", parsed["message"])
        
        tool_call = parsed["tool_call_instruction"]["tool_call"]
        self.assertEqual(tool_call["tool_name"], "inspect_content_block")
        self.assertEqual(tool_call["parameters"]["stage_name"], "last_agent_run")
        self.assertEqual(tool_call["parameters"]["block_name"], "output_data")

    def test_compact_json_data_paging_summary(self):
        data = [{"id": i} for i in range(50)]
        compacted = compact_json_data(data, max_list_items=10)
        self.assertEqual(len(compacted), 11)
        self.assertIn("...摘要...", compacted[5])


if __name__ == "__main__":
    unittest.main()
