# -*- coding: utf-8 -*-
"""
AI  JSON Schema 

 JSON 
"""

# =============================================================================
# 1. worldview ( Story Architect Agent)
# =============================================================================

WORLDVIEW_SCHEMA = {
    "theme": "",
    "main_conflict": "",
    "worldview": "",
    "macro_outline": "",
    "multi_act_structure": [
        {"title": " (Setup)", "content": ""},
        {"title": " (Confrontation)", "content": ""},
        {"title": " (Resolution)", "content": ""}
    ],
    "progressive_character_plan": [
        {"title": " (Wave 1)", "content": ""},
        {"title": " (Wave 2)", "content": ""},
        {"title": " (Wave 3)", "content": ""}
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

# 
WORLDVIEW_APPROVAL_CRITERIA = {
    "name": "worldview",
    "display_name": "",
    "criteria": {
        "structure": {
            "required_fields": ["theme", "main_conflict", "worldview", "macro_outline", "multi_act_structure", "progressive_character_plan", "foreshadowing_seeds", "key_turning_points"],
            "description": ""
        },
        "theme": {
            "min_length": 50,
            "max_length": 500,
            "description": ""
        },
        "main_conflict": {
            "min_length": 100,
            "max_length": 800,
            "description": ""
        },
        "worldview": {
            "min_length": 300,
            "description": ""
        },
        "macro_outline": {
            "min_length": 200,
            "description": ""
        },
        "multi_act_structure": {
            "description": ""
        },
        "progressive_character_plan": {
            "description": ""
        },
        "foreshadowing_seeds": {
            "description": ""
        },
        "key_turning_points": {
            "description": ""
        },
        "consistency": {
            "description": ""
        }
    },
}


# =============================================================================
# 2. characters ( Character Designer Agent)
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

# 
CHARACTER_APPROVAL_CRITERIA = {
    "name": "characters",
    "display_name": "",
    "criteria": {
        "required_fields": {
            "per_character": ["name", "role", "entry_phase", "personality", "want", "need", "fatal_flaw", "motivation", "arc", "speech_style", "background", "relationships"],
            "description": ""
        },
        "name_validity": {
            "description": "name /"
        },
        "character_count": {
            "description": "/"
        },
        "psychological_depth": {
            "want_min_length": 20,
            "need_min_length": 20,
            "fatal_flaw_min_length": 15,
            "description": "(Want)(Need)(Fatal Flaw)"
        },
        "character_arc": {
            "min_length": 30,
            "description": "(Arc)"
        },
        "speech_style": {
            "min_length": 15,
            "description": ""
        },
        "relationships": {
            "description": "typeevolution"
        },
        "entry_phases": {
            "description": "multi_act_structure"
        },
        "consistency": {
            "description": ""
        }
    },
    "incremental_hint": " hint ",
    "modify_with_full_content_hint": " hint "
}


# =============================================================================
# 3. volumes ( Volumes Planner Agent)
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

# 
VOLUME_APPROVAL_CRITERIA = {
    "name": "volumes",
    "display_name": "",
    "criteria": {
        "volume_count": {
            "description": " 8 >= 8 "
        },
        "required_fields": {
            "per_volume": ["volume_index", "title", "summary", "chapter_count", "factions", "time_timeline", "sequence_context", "applicable_rules"],
            "description": ""
        },
        "title": {
            "min_length": 3,
            "description": ""
        },
        "summary": {
            "min_length": 200,
            "max_length": 300,
            "description": ""
        },
        "chapter_count": {
            "description": "chapter_count 50  45  42  48 "
        },
        "structure_coherence": {
            "description": ""
        },
        "character_progression": {
            "description": "(Progressive Character Plan)"
        },
        "turning_points_distribution": {
            "description": ""
        },
        "volume_function": {
            "description": ""
        }
    },
    "patch_hint": " {idx}  hint "
}


# =============================================================================
# 4. volume_skeleton ( Volume Skeleton Planner)
# =============================================================================

CHAPTER_SKELETON_SCHEMA = {
    "chapter_index": 1,
    "chapter_title": "",
    "chapter_summary": "",
    "time_setting": "",
    "scene_setting": "",
    "events": [
        {
            "scene_index": 1,
            "location": "",
            "characters": [],
            "content": ""
        }
    ],
    "characters_active": [],
    "emotional_tone": "",
    "cliffhanger": ""
}

CHAPTER_SKELETON_WITH_ALLOC_SCHEMA = {
    "chapter_index": 1,
    "chapter_title": "",
    "chapter_summary": "",
    "time_setting": "",
    "scene_setting": "",
    "events": [
        {
            "scene_index": 1,
            "location": "",
            "characters": [],
            "content": ""
        }
    ],
    "characters_active": [],
    "emotional_tone": "",
    "cliffhanger": "",
    "volume_index": 1,
    "volume_title": "",
    "allocated_tasks": {
        "foreshadowing_plants": [],
        "foreshadowing_payoffs": [],
        "turning_points": []
    }
}

VOLUME_SKELETON_LIST_SCHEMA = []

# 
SKELETON_APPROVAL_CRITERIA = {
    "name": "volume_skeleton",
    "display_name": "",
    "criteria": {
        "chapter_completeness": {
            "description": "4, 5 writer  volume_skeleton "
        },
        "chapter_structure": {
            "required_fields": ["chapter_index", "chapter_title", "chapter_summary", "events", "time_setting", "scene_setting", "characters_active", "emotional_tone", "cliffhanger", "allocated_tasks"],
            "description": " eventsallocated_tasks "
        },
        "time_setting": {
            "description": ""
        },
        "events": {
            "min_scenes": 0,
            "max_scenes": 4,
            "description": "0-4 events  scene_index, location, characters, content"
        },
        "foreshadowing_sync": {
            "description": "(foreshadowing_plants)(foreshadowing_payoffs)allocated_tasks"
        },
        "turning_points_alignment": {
            "description": "turning_pointskey_turning_points"
        },
        "cliffhanger": {
            "description": "(Cliffhanger)"
        },
        "character_consistency": {
            "description": ""
        },
        "plot_drive": {
            "description": ""
        },
        "character_presence": {
            "description": ""
        }
    },
}



# =============================================================================
# 6. writer ( Chapter Writer Agent)
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

# 
WRITER_APPROVAL_CRITERIA = {
    "name": "writer",
    "display_name": "",
    "criteria": {
        "content_length": {
            "min_words": 1500,
            "description": ""
        },
        "structure_compliance": {
            "description": ""
        },
        "show_dont_tell": {
            "description": ""
        },
        "character_consistency": {
            "description": ""
        },
        "foreshadowing_execution": {
            "description": ""
        },
        "turning_point_execution": {
            "description": ""
        },
        "prose_quality": {
            "description": ""
        },
        "cliffhanger_effectiveness": {
            "description": ""
        }
    },
}


# =============================================================================
# 7. editor ( Editor Agent)
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

# 
EDITOR_APPROVAL_CRITERIA = {
    "name": "editor",
    "display_name": "",
    "criteria": {
        "content_quality_improvement": {
            "description": ""
        },
        "character_consistency_preserved": {
            "description": ""
        },
        "plot_integrity": {
            "description": ""
        },
        "foreshadowing_integrity": {
            "description": ""
        },
        "synopsis_accuracy": {
            "description": "synopsis"
        },
        "polish_level": {
            "description": ""
        }
    },
}


# =============================================================================
# 
# =============================================================================

APPROVAL_CRITERIA_REGISTRY = {
    "worldview": WORLDVIEW_APPROVAL_CRITERIA,
    "characters": CHARACTER_APPROVAL_CRITERIA,
    "volumes": VOLUME_APPROVAL_CRITERIA,
    "volume_skeleton": SKELETON_APPROVAL_CRITERIA,
    "writer": WRITER_APPROVAL_CRITERIA,
    "editor": EDITOR_APPROVAL_CRITERIA,
}


def get_approval_criteria(stage_name):
    """
    
    
    Args:
        stage_name:  (worldview, characters, volumes, volume_skeleton, writer, editor)
    
    Returns:
        dictNone
    """
    return APPROVAL_CRITERIA_REGISTRY.get(stage_name)


def format_criteria_for_prompt(stage_name):
    """
    LLM
    
    Args:
        stage_name: 
    
    Returns:
        
    """
    criteria = get_approval_criteria(stage_name)
    if not criteria:
        return ""
    
    lines = [
        f"\n## {criteria['display_name']} ",
        f"### \n"
    ]
    
    for key, value in criteria["criteria"].items():
        if isinstance(value, dict):
            lines.append(f"- **{key}**: {value.get('description', '')}")
        else:
            lines.append(f"- **{key}**: {value}")
    
    # if "auto_regenerate_hint" in criteria:
    #     lines.append(f"\n### ")
    #     lines.append(f"{criteria['auto_regenerate_hint']}")
    
    return "\n".join(lines)


# =============================================================================
# 
# =============================================================================

def get_worldview_default():
    """"""
    return WORLDVIEW_SCHEMA.copy()


def get_character_default():
    """"""
    return CHARACTER_SCHEMA.copy()


def get_volume_default(volume_index=1):
    """"""
    vol = VOLUME_SCHEMA.copy()
    vol["volume_index"] = volume_index
    vol["title"] = f" {volume_index} "
    return vol


def get_chapter_skeleton_default(chapter_index=1):
    """"""
    skel = CHAPTER_SKELETON_SCHEMA.copy()
    skel["chapter_index"] = chapter_index
    return skel



def create_characters_structure(characters_list):
    """"""
    return {"characters": characters_list}


def create_volume_list(volumes_list):
    """"""
    return volumes_list


def create_skeleton_list(skeletons_list):
    """"""
    return skeletons_list


def create_foreshadowing_allocations(allocations_list):
    """"""
    return allocations_list