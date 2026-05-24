# -*- coding: utf-8 -*-
"""
測試 retrospective API 的終端機日誌輸出功能
"""
import sys
import os
import unittest
import uuid
from io import StringIO
from unittest.mock import patch, MagicMock

# 確保 UTF-8 編碼
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import db
from app import api_novel_retrospective

class TestRetrospectiveLogging(unittest.TestCase):
    def setUp(self):
        """設置測試數據"""
        db.db_init()
        self.novel_id = str(uuid.uuid4())
        db.create_novel(self.novel_id, "測試小說", "奇幻", "史詩")
        
        # 建立最小的世界觀和角色數據以通過驗證
        db.save_worldbuilding(self.novel_id, '{"theme": "測試主題"}')
        db.save_characters(self.novel_id, '{"characters": []}')
        db.save_plot_chapters(self.novel_id, '{"chapters": []}')
        db.save_chapter(self.novel_id, 1, "測試章節內容")
        
    def tearDown(self):
        db.delete_novel(self.novel_id)
    
    def test_director_output_logged_to_terminal(self):
        """
        測試總監的回答是否會被輸出到終端機 (stdout)
        通過 patch ThreadPoolExecutor 來控制异步執行結果
        """
        # 定義每個 agent 的模擬回答
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
            # 建立 mock executor
            with patch('app.concurrent.futures.ThreadPoolExecutor') as MockExecutor:
                mock_executor = MagicMock()
                MockExecutor.return_value = mock_executor
                
                # 設定 __enter__ 回傳 mock executor
                mock_executor.__enter__ = MagicMock(return_value=mock_executor)
                mock_executor.__exit__ = MagicMock(return_value=False)
                
                # 設定 submit 回傳對應 agent 的 future
                def mock_submit(func, agent_key, config):
                    return create_mock_future(agent_key)
                mock_executor.submit = mock_submit
                
                # 設定 as_completed 回傳所有 futures (順序可以任意)
                futures = [create_mock_future(key) for key in agent_responses.keys()]
                mock_executor.as_completed.return_value = futures
                
                # 執行 retrospective API
                result = api_novel_retrospective(self.novel_id)
                
                # 檢查輸出內容
                output_text = captured_output.getvalue()
                
                # 驗證終端機有輸出總監回答的標題和分隔線
                self.assertIn("=" * 60, output_text)
                self.assertIn("Co-pilot Director 總監回答", output_text)
                self.assertIn("這是模擬的總監回答內容，包含重要的全局創作金律。", output_text)
                
                # 驗證 API 回傳結果正確
                self.assertEqual(result["status"], "success")
                self.assertIn("filepath", result)
                self.assertIn("markdown", result)
                
                # 驗證 markdown 包含所有 agent 的回答
                markdown = result["markdown"]
                for agent_name in agent_responses:
                    self.assertIn(agent_name, markdown)
                    self.assertIn(agent_responses[agent_name], markdown)
                
        finally:
            sys.stdout = original_stdout

if __name__ == '__main__':
    unittest.main()
