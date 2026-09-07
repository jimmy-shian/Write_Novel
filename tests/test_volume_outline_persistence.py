import pytest
import json
import uuid
from backend.persistence.connection import get_db_connection
from backend.persistence.repositories.novels import create_novel, delete_novel
from backend.persistence.repositories.volumes import save_volumes, get_volumes
from backend.persistence.repositories.chapters import save_plot_chapters

def test_volume_chapters_outline_persistence():
    novel_id = str(uuid.uuid4())
    create_novel(novel_id, "測試小說", "仙俠", "熱血")

    try:
        # 1. 建立 2 卷，各帶章綱
        volumes_payload = [
            {
                "volume_index": 1,
                "title": "第 1 卷 起源",
                "summary": "第一卷概述",
                "chapter_count": 2,
                "chapters_outline": [
                    {"chapter_index": 1, "chapter_title": "第 1 章 覺醒", "chapter_summary": "第一章摘要"},
                    {"chapter_index": 2, "chapter_title": "第 2 章 離鄉", "chapter_summary": "第二章摘要"}
                ]
            },
            {
                "volume_index": 2,
                "title": "第 2 卷 征途",
                "summary": "第二卷概述",
                "chapter_count": 2,
                "chapters_outline": [
                    {"chapter_index": 3, "chapter_title": "第 3 章 入門", "chapter_summary": "第三章摘要"},
                    {"chapter_index": 4, "chapter_title": "第 4 章 考驗", "chapter_summary": "第四章摘要"}
                ]
            }
        ]

        # 透過 save_volumes 存入
        save_volumes(novel_id, volumes_payload)

        # 讀取檢驗
        saved_vols = get_volumes(novel_id)
        assert len(saved_vols) == 2
        assert saved_vols[0]["chapters_outline"] is not None
        assert len(saved_vols[0]["chapters_outline"]) == 2
        assert saved_vols[0]["chapters_outline"][0]["chapter_title"] == "第 1 章 覺醒"
        assert saved_vols[1]["chapters_outline"][1]["chapter_title"] == "第 4 章 考驗"

        # 2. 測試透過 save_plot_chapters 傳遞 volumes 陣列
        # 模擬使用者在第二卷刪除第 3 章，第 4 章自動重排為第 3 章
        modified_volumes = [
            {
                "volume_index": 1,
                "title": "第 1 卷 起源",
                "summary": "第一卷概述",
                "chapter_count": 2,
                "chapters_outline": [
                    {"chapter_index": 1, "chapter_title": "第 1 章 覺醒", "chapter_summary": "第一章摘要"},
                    {"chapter_index": 2, "chapter_title": "第 2 章 離鄉", "chapter_summary": "第二章摘要"}
                ]
            },
            {
                "volume_index": 2,
                "title": "第 2 卷 征途",
                "summary": "第二卷概述",
                "chapter_count": 1,
                "chapters_outline": [
                    {"chapter_index": 3, "chapter_title": "第 3 章 考驗", "chapter_summary": "第四章重排為第三章"}
                ]
            }
        ]

        save_plot_chapters(novel_id, modified_volumes)

        # 重新讀取驗證重排後的章綱是否成功持久化
        reloaded_vols = get_volumes(novel_id)
        assert len(reloaded_vols) == 2
        assert len(reloaded_vols[1]["chapters_outline"]) == 1
        assert reloaded_vols[1]["chapters_outline"][0]["chapter_index"] == 3
        assert reloaded_vols[1]["chapters_outline"][0]["chapter_title"] == "第 3 章 考驗"

    finally:
        delete_novel(novel_id)
from fastapi.testclient import TestClient
from backend.app import app

def test_api_save_volumes_route():
    client = TestClient(app)
    novel_id = str(uuid.uuid4())
    create_novel(novel_id, "API測試小說", "科幻", "冷峻")

    try:
        payload = {
            "volumes": [
                {
                    "volume_index": 1,
                    "title": "第 1 卷 矩陣",
                    "chapters_outline": [
                        {"chapter_index": 1, "chapter_title": "第 1 章 覺醒"}
                    ]
                }
            ]
        }
        res = client.post(f"/api/novels/{novel_id}/volumes", json=payload)
        assert res.status_code == 200
        assert res.json()["status"] == "success"

        vols = get_volumes(novel_id)
        assert len(vols) == 1
        assert vols[0]["chapters_outline"][0]["chapter_title"] == "第 1 章 覺醒"
    finally:
        delete_novel(novel_id)
