# -*- coding: utf-8 -*-
"""
AI 小說工廠流程 JSON Schema 定義

可直接引用使用的各流程 JSON 格式模組
"""

# =============================================================================
# 1. worldview (世界觀架構師 Story Architect Agent)
# =============================================================================

WORLDVIEW_SCHEMA = {
    "theme": "",
    "main_conflict": "",
    "worldview": "",
    "macro_outline": "",
    "multi_act_structure": [
        {"title": "第一幕 (Setup)", "content": ""},
        {"title": "第二幕 (Confrontation)", "content": ""},
        {"title": "第三幕 (Resolution)", "content": ""}
    ],
    "progressive_character_plan": [
        {"title": "第一波開篇 (Wave 1)", "content": ""},
        {"title": "第二波發展 (Wave 2)", "content": ""},
        {"title": "第三波高潮 (Wave 3)", "content": ""}
    ],
    "foreshadowing_seeds": [],
    "key_turning_points": []
}

WORLDVIEW_CHAPTER_PATCH = {
    "category": "",
    "details": "",
    "source_chapter": 0,
    "created_at": ""
}


# =============================================================================
# 2. characters (角色設計師 Character Designer Agent)
# =============================================================================

CHARACTER_SCHEMA = {
    "name": "",
    "role": "",
    "entry_phase": "",
    "personality": [],
    "want": "",
    "need": "",
    "fatal_flaw": "",
    "motivation": "",
    "arc": "",
    "speech_style": "",
    "appearance": "",
    "background": "",
    "relationships": []
}

CHARACTER_RELATIONSHIP_SCHEMA = {
    "with": "",
    "type": "",
    "evolution": ""
}

CHARACTERS_ROOT_SCHEMA = {
    "characters": []
}


# =============================================================================
# 3. volumes (篇卷規劃師 Volumes Planner Agent)
# =============================================================================

VOLUME_SCHEMA = {
    "volume_index": 1,
    "title": "",
    "summary": "",
    "factions": [],
    "chapter_count": 50,
    "time_timeline": "",
    "sequence_context": "",
    "applicable_rules": []
}

VOLUMES_LIST_SCHEMA = []


# =============================================================================
# 4. volume_skeleton (篇卷骨架規劃師 Volume Skeleton Planner)
# =============================================================================

CHAPTER_SKELETON_SCHEMA = {
    "chapter_index": 1,
    "chapter_title": "",
    "chapter_summary": ""
}

CHAPTER_SKELETON_WITH_ALLOC_SCHEMA = {
    "chapter_index": 1,
    "chapter_title": "",
    "chapter_summary": "",
    "volume_index": 1,
    "volume_title": "",
    "allocated_tasks": {
        "foreshadowing_plants": [],
        "foreshadowing_payoffs": [],
        "turning_points": []
    }
}

VOLUME_SKELETON_LIST_SCHEMA = []

# =============================================================================
# 5. plot (大綱規劃師 Plot Planner Agent)
# =============================================================================

PLOT_CHAPTER_SCHEMA = {
    "chapter_index": 1,
    "chapter_title": "",
    "chapter_summary": "",
    "scenes": [],
    "allocated_tasks": {
        "foreshadowing_plants": [],
        "foreshadowing_payoffs": [],
        "turning_points": []
    }
}

PLOT_SCENE_SCHEMA = {
    "scene_index": 1,
    "location": "",
    "characters": [],
    "content": ""
}

PLOT_ROOT_SCHEMA = {
    "chapters": []
}


# =============================================================================
# 6. writer (正文寫作作家 Chapter Writer Agent)
# =============================================================================

WRITER_OUTPUT_SCHEMA = {
    "novel_id": "",
    "chapter_index": 1,
    "content": "",
    "synopsis": "",
    "thinking": ""
}

WRITER_INPUT_SCHEMA = {
    "chapter_index": 1,
    "chapter_title": "",
    "chapter_summary": "",
    "scenes": [],
    "allocated_tasks": {
        "foreshadowing_plants": [],
        "foreshadowing_payoffs": [],
        "turning_points": []
    }
}


# =============================================================================
# 7. editor (編輯姬 Editor Agent)
# =============================================================================

EDITOR_INPUT_SCHEMA = {
    "novel_id": "",
    "chapter_index": 1,
    "content": "",
    "synopsis": ""
}

EDITOR_OUTPUT_SCHEMA = {
    "novel_id": "",
    "chapter_index": 1,
    "content": "",
    "synopsis": ""
}


# =============================================================================
# 輔助函數
# =============================================================================

def get_worldview_default():
    """取得世界觀預設結構"""
    return WORLDVIEW_SCHEMA.copy()


def get_character_default():
    """取得角色預設結構"""
    return CHARACTER_SCHEMA.copy()


def get_volume_default(volume_index=1):
    """取得篇卷預設結構"""
    vol = VOLUME_SCHEMA.copy()
    vol["volume_index"] = volume_index
    vol["title"] = f"第 {volume_index} 卷"
    return vol


def get_chapter_skeleton_default(chapter_index=1):
    """取得章節骨架預設結構"""
    skel = CHAPTER_SKELETON_SCHEMA.copy()
    skel["chapter_index"] = chapter_index
    return skel


def get_plot_chapter_default(chapter_index=1):
    """取得大綱章節預設結構"""
    ch = PLOT_CHAPTER_SCHEMA.copy()
    ch["chapter_index"] = chapter_index
    return ch


def create_plot_structure(chapters_list):
    """建立大綱結構"""
    return {"chapters": chapters_list}


def create_characters_structure(characters_list):
    """建立角色結構"""
    return {"characters": characters_list}


def create_volume_list(volumes_list):
    """建立篇卷列表"""
    return volumes_list


def create_skeleton_list(skeletons_list):
    """建立骨架列表"""
    return skeletons_list


def create_foreshadowing_allocations(allocations_list):
    """建立伏筆分配列表"""
    return allocations_list