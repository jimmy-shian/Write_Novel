# -*- coding: utf-8 -*-
"""
 Consolidated Fast Unit Tests (合併測試腳本 - unittest 版)
"""

import sys
import os
import io
import json
import sqlite3
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

# 強制 UTF-8 編碼
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

# 確保路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import db
import agents
import llm
from agents import (
    pre_check_next_agent,
    get_simplified_director_prompt,
    verify_novel_integrity,
    parse_json_safely
)
from incremental_patch_engine import filter_and_sanitize_content


class NoCloseConnection:
    """單一記憶體資料庫連線包裝器，防止呼叫 close() 時關閉資料庫"""
    def __init__(self, conn):
        object.__setattr__(self, "_conn", conn)
    def __getattr__(self, name):
        if name == 'close':
            return lambda: None
        return getattr(self._conn, name)
    def __setattr__(self, name, value):
        setattr(self._conn, name, value)
    def close_actual(self):
        self._conn.close()


class TestNovelFactoryBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 建立一個全域共享的 SQLite 記憶體資料庫
        raw_conn = sqlite3.connect(":memory:")
        raw_conn.execute("PRAGMA foreign_keys = ON;")
        raw_conn.row_factory = sqlite3.Row
        cls.shared_conn = NoCloseConnection(raw_conn)
        
        # 攔截 get_db_connection，使其一律回傳此記憶體連線
        cls.db_conn_patcher = patch('db.get_db_connection', return_value=cls.shared_conn)
        cls.db_conn_patcher.start()
        
        # 初始化資料庫結構
        db.db_init()
        
    @classmethod
    def tearDownClass(cls):
        cls.db_conn_patcher.stop()
        cls.shared_conn.close_actual()

    def setUp(self):
        # 每次測試前清理表資料
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novels")
        cursor.execute("DELETE FROM worldbuilding")
        cursor.execute("DELETE FROM characters")
        cursor.execute("DELETE FROM plot_chapters")
        cursor.execute("DELETE FROM chapters")
        cursor.execute("DELETE FROM chat_memory")
        cursor.execute("DELETE FROM volumes")
        conn.commit()


class TestDirectorIntegrity(TestNovelFactoryBase):
    """測試總監預檢查與提示生成功能"""

    def test_pre_check_next_agent(self):
        novel_id = "test-director-novel"
        db.create_novel(novel_id, "測試小說", "科幻", "硬核")
        
        # 測試各階段的預檢回傳結果
        stages = ["init", "worldview", "characters", "plot", "writer"]
        for stage in stages:
            res = pre_check_next_agent(novel_id, stage)
            self.assertIn("當前階段", res)
            self.assertIn(stage, res)

    def test_get_simplified_director_prompt(self):
        stages = ["init", "worldview", "characters", "volumes", "volume_skeleton", "foreshadowing_orchestration", "plot", "writer"]
        for stage in stages:
            prompt_tpl = get_simplified_director_prompt(stage, has_wb_and_char_at_init=(stage == "init"))
            self.assertTrue(len(prompt_tpl) > 100)
            self.assertIn("創意總監", prompt_tpl)


class TestDynamicPipeline(TestNovelFactoryBase):
    """測試動態篇卷與章節序號範圍計算"""

    def test_volume_chapter_calculations(self):
        novel_id = "test-pipeline-novel"
        db.create_novel(novel_id, "測試篇卷小說", "仙俠", "史詩")
        
        volumes_setup = [
            {"volume_index": 1, "title": "卷一", "summary": "開篇", "chapter_count": 3},
            {"volume_index": 2, "title": "卷二", "summary": "中局", "chapter_count": 5},
            {"volume_index": 3, "title": "卷三", "summary": "收尾", "chapter_count": 2}
        ]
        db.save_volumes(novel_id, volumes_setup)
        
        volumes = db.get_volumes(novel_id)
        self.assertEqual(len(volumes), 3)
        
        # 驗證章節範圍計算 (get_volume_chapter_range)
        # 第一卷：1 - 3
        start1, end1 = db.get_volume_chapter_range(volumes, 1)
        self.assertEqual((start1, end1), (1, 3))
        
        # 第二卷：4 - 8
        start2, end2 = db.get_volume_chapter_range(volumes, 2)
        self.assertEqual((start2, end2), (4, 8))
        
        # 第三卷：9 - 10
        start3, end3 = db.get_volume_chapter_range(volumes, 3)
        self.assertEqual((start3, end3), (9, 10))
        
        # 驗證章節所屬卷 (get_chapter_volume_index)
        self.assertEqual(db.get_chapter_volume_index(volumes, 1), 1)
        self.assertEqual(db.get_chapter_volume_index(volumes, 3), 1)
        self.assertEqual(db.get_chapter_volume_index(volumes, 4), 2)
        self.assertEqual(db.get_chapter_volume_index(volumes, 8), 2)
        self.assertEqual(db.get_chapter_volume_index(volumes, 9), 3)
        self.assertEqual(db.get_chapter_volume_index(volumes, 10), 3)
        
        # 驗證總章節數
        self.assertEqual(db.get_total_chapter_count(volumes), 10)


class TestFeedbackLoop(TestNovelFactoryBase):
    """測試反饋環路與懶惰對齊功能"""

    def test_feedback_loop_dirty_mechanism(self):
        novel_id = "test-feedback-novel"
        db.create_novel(novel_id, "反饋測試", "科幻", "寫實")
        
        volumes_list = [
            {"volume_index": 1, "title": "第一卷", "summary": "描述一", "chapter_count": 10, "is_dirty": 0},
            {"volume_index": 2, "title": "第二卷", "summary": "描述二", "chapter_count": 10, "is_dirty": 0}
        ]
        db.save_volumes(novel_id, volumes_list)
        
        # 測試世界觀修補與標記下游為髒 (Lazy Realignment)
        db.add_worldview_patch(novel_id, "Physics", "Sector 7 gravity is reversed.", 1)
        db.mark_downstream_dirty(novel_id, 1)
        
        # 驗證 worldview_patches
        patches = db.get_worldview_patches(novel_id)
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]["category"], "Physics")
        
        # 驗證 Volumes dirty 標記 (Volume 2 應為 dirty, Volume 1 應為 clean)
        volumes = db.get_volumes(novel_id)
        vol1 = next(v for v in volumes if v["volume_index"] == 1)
        vol2 = next(v for v in volumes if v["volume_index"] == 2)
        
        self.assertEqual(vol1["is_dirty"], 0)
        self.assertEqual(vol2["is_dirty"], 1)


class TestIntegrityCheck(TestNovelFactoryBase):
    """測試總監大綱與情節邏輯校驗機制"""

    def test_verify_novel_integrity_all_scenarios(self):
        novel_id = "test-integrity-novel"
        db.create_novel(novel_id, "測試永夜之光", "奇幻", "史詩")
        
        worldview_data = {
            "theme": "光明的追尋",
            "main_conflict": "燈火城與永夜",
            "worldview": "人類依賴命燈建立城邦。",
            "macro_outline": "主角林澤從一個拾荒者點燃命燈的故事。",
            "multi_act_structure": [
                {"title": "第一幕", "content": "起"},
                {"title": "第二幕", "content": "承轉"},
                {"title": "第三幕", "content": "合"}
            ],
            "progressive_character_plan": [
                {"title": "第一波", "content": "主角登場"},
                {"title": "第二波", "content": "對手登場"},
                {"title": "第三波", "content": "大戰"}
            ],
            "foreshadowing_seeds": [
                "Seed-1: 命燈需要電路晶片",
                "Seed-2: 守夜人高層叛變",
                "Seed-3: 吊墜是鑰匙"
            ],
            "key_turning_points": [
                "TurningPoint-1: 挖出晶片",
                "TurningPoint-2: 好友犧牲",
                "TurningPoint-3: 吊墜契合巨門"
            ]
        }
        db.save_worldbuilding(novel_id, json.dumps(worldview_data, ensure_ascii=False))
        
        volumes_list = [
            {"volume_index": 1, "title": "第一卷", "summary": "概要一", "chapter_count": 3},
            {"volume_index": 2, "title": "第二卷", "summary": "概要二", "chapter_count": 3}
        ]
        db.save_volumes(novel_id, volumes_list)
        
        # 1. 測試情境一：完美大綱
        perfect_chapters = [
            {
                "chapter_index": 1,
                "title": "黑石吊墜的秘密",
                "purpose": "引入吊墜設定",
                "summary": "主角林澤在荒原廢墟中偶然撿到了一個古老而斑駁的黑石吊墜，吊墜上隱隱約約散發著不尋常的光芒與能量起伏。",
                "foreshadowing_plant": ["Seed-3: 吊墜發光"],
                "foreshadowing_payoff": [],
                "scene": "荒原",
                "cliffhanger": "留下懸念"
            },
            {
                "chapter_index": 2,
                "title": "廢墟中的晶片",
                "purpose": "晶片引入",
                "summary": "林澤利用吊墜的引導深入荒原核心地帶，在坍塌的儀器深處挖出了一枚珍貴的命燈晶片，並成功將其安全帶回。",
                "foreshadowing_plant": ["Seed-1: 發現晶片"],
                "foreshadowing_payoff": [],
                "scene": "荒原",
                "cliffhanger": "覺醒"
            },
            {
                "chapter_index": 3,
                "title": "不朽燈火的重燃",
                "purpose": "實力突破",
                "summary": "在避難所的集體見證下，林澤成功接駁了古老的命燈，一時間璀璨的火光重燃，照亮了整個黑暗的避難所大堂。",
                "foreshadowing_plant": [],
                "foreshadowing_payoff": ["Seed-1: 重燃命燈"],
                "scene": "城邦",
                "cliffhanger": "震撼"
            }
        ]
        context_perfect = {
            "worldbuilding": json.dumps(worldview_data, ensure_ascii=False),
            "characters": "[]",
            "plot": json.dumps({"chapters": perfect_chapters}, ensure_ascii=False),
            "written_chapters": "[]"
        }
        perfect_report = verify_novel_integrity(novel_id, context_perfect)
        self.assertNotIn("🔴", perfect_report)

        # 2. 測試情境二：漏洞百出的大綱
        flawed_chapters = [
            {
                "chapter_index": 1,
                "title": "第一章",
                "foreshadowing_plant": ["Seed-2: 埋設"],
                "foreshadowing_payoff": []
            },
            # 缺失第 2 章 (Gaps)
            {
                "chapter_index": 3,
                "title": "第三章",
                "foreshadowing_plant": [],
                "foreshadowing_payoff": ["Seed-1: 顛倒", "Seed-5: 憑空"]
            },
            {
                "chapter_index": 4,
                "title": "第四章",
                "foreshadowing_plant": ["Seed-1: 埋設"],
                "foreshadowing_payoff": []
            },
            {
                "chapter_index": 125,  # 🔴 卷數不足
                "title": "大結局",
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
        self.assertIn("🔴", flawed_report)
        self.assertIn("章節序號不連續", flawed_report)
        self.assertIn("伏筆未回收", flawed_report)
        self.assertIn("伏筆憑空回收", flawed_report)
        self.assertIn("伏筆時序顛倒", flawed_report)


class TestContentFiltering(unittest.TestCase):
    """測試高品質外部內容與佔位符過濾攔截"""

    def test_filter_and_sanitize_content(self):
        # 1. 測試含有 TODO 佔位符
        bad_todo = {
            "chapters": [
                {"chapter_index": 1, "title": "TODO: 第一章主角出發", "events": []}
            ]
        }
        ok, err = filter_and_sanitize_content("plot", bad_todo)
        self.assertFalse(ok)
        self.assertIn("低品質佔位符", err)
        
        # 2. 測試含有大綱模板廢話 "推動大綱情節發展"
        bad_boilerplate = {
            "chapters": [
                {"chapter_index": 1, "title": "第一章", "summary": "推動大綱情節發展"}
            ]
        }
        ok, err = filter_and_sanitize_content("plot", bad_boilerplate)
        self.assertFalse(ok)
        self.assertIn("大綱模板套用廢話", err)

        # 3. 測試大綱重複標題退化
        bad_repeat = {
            "chapters": [
                {"chapter_index": 1, "title": "新的旅程", "events": []},
                {"chapter_index": 2, "title": "新的旅程", "events": []},
                {"chapter_index": 3, "title": "新的旅程", "events": []}
            ]
        }
        ok, err = filter_and_sanitize_content("plot", bad_repeat)
        self.assertFalse(ok)
        self.assertIn("情節語意退化", err)


if __name__ == '__main__':
    unittest.main()
