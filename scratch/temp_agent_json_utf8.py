# -*- coding: utf-8 -*-
"""
AI 撠牧撌亙?瘚? JSON Schema 摰儔

?舐?亙??其蝙?函???蝔?JSON ?澆?璅∠?
"""

# =============================================================================
# 1. worldview (銝?閫?嗆?撣?Story Architect Agent)
# =============================================================================

WORLDVIEW_SCHEMA = {
    "theme": "",
    "main_conflict": "",
    "worldview": "",
    "macro_outline": "",
    "multi_act_structure": [
        {"title": "蝚砌?撟?(Setup)", "content": ""},
        {"title": "蝚砌?撟?(Confrontation)", "content": ""},
        {"title": "蝚砌?撟?(Resolution)", "content": ""}
    ],
    "progressive_character_plan": [
        {"title": "蝚砌?瘜ａ?蝭?(Wave 1)", "content": ""},
        {"title": "蝚砌?瘜Ｙ撅?(Wave 2)", "content": ""},
        {"title": "蝚砌?瘜ａ?瞏?(Wave 3)", "content": ""}
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

# 銝?閫??璅?嚗蜇????斤嚗?WORLDVIEW_APPROVAL_CRITERIA = {
    "name": "worldview",
    "display_name": "銝?閫?嗆?撣?,
    "criteria": {
        "structure": {
            "required_fields": ["theme", "main_conflict", "worldview", "macro_outline", "multi_act_structure", "progressive_character_plan", "foreshadowing_seeds", "key_turning_points"],
            "description": "???憛急?雿????游‵撖恬?銝??箇征"
        },
        "theme": {
            "min_length": 50,
            "max_length": 500,
            "description": "?詨?銝駁???瑕?瘛勗漲?摮詨憿?
        },
        "main_conflict": {
            "min_length": 100,
            "max_length": 800,
            "description": "?詨?銵???Ⅱ?膩憭?撐??
        },
        "worldview": {
            "min_length": 300,
            "description": "銝?閫???啁?????蝟颯冗??瑽???閬?"
        },
        "macro_outline": {
            "min_length": 200,
            "description": "摰?憭抒雇?摰?膩??韏啣?"
        },
        "multi_act_structure": {
            "min_acts": 5,
            "max_acts": 10,
            "description": "憭?蝯??5-10撟?瘥????蝣箇?韏瑟頧???摰寞?餈?
        },
        "progressive_character_plan": {
            "min_waves": 5,
            "description": "閫瞍賊脰???5瘜Ｖ誑銝???閫??畾菜抒?渲??"
        },
        "foreshadowing_seeds": {
            "min_count": 30,
            "description": "隡?蝔桀???喳?30??瘥?璅??拇??身暺葉?僕?整????
        },
        "key_turning_points": {
            "min_count": 40,
            "description": "?頧?暺??喳?40??瘥?璅?閫貊璇辣?撅敶梢"
        },
        "consistency": {
            "description": "??雿???摩銝?湛?隡???????訾??潭?"
        }
    },
    "auto_regenerate_hint": "隢?蝙?刻?靘???閮剖?嚗??啁????渡?銝?閫?嗆???
}


# =============================================================================
# 2. characters (閫閮剛?撣?Character Designer Agent)
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

# 閫??璅?嚗蜇????斤嚗?CHARACTER_APPROVAL_CRITERIA = {
    "name": "characters",
    "display_name": "閫閮剛?撣?,
    "criteria": {
        "required_fields": {
            "per_character": ["name", "role", "entry_phase", "personality", "want", "need", "fatal_flaw", "motivation", "arc", "speech_style", "background", "relationships"],
            "description": "瘥??脣?憛急?雿????湛?銝??箇征??雿泵"
        },
        "name_validity": {
            "description": "name 甈?敹??航??脩??琿?憪?/隞??嚗?撠?甇Ｖ蝙?函?蝜雿?蝷暹?頨思遢雿憪?"
        },
        "character_count": {
            "min_protagonist": 1,
            "min_antagonist": 1,
            "min_total": 5,
            "description": "?喳??閬?雿蜓閫?雿?瘣?摰踵?蜇閮?雿誑銝???
        },
        "psychological_depth": {
            "want_min_length": 20,
            "need_min_length": 20,
            "fatal_flaw_min_length": 15,
            "description": "瘥??脤??瑕?摰???函璅?Want)??券?瘙?Need)??賜撩??Fatal Flaw)"
        },
        "character_arc": {
            "min_length": 30,
            "description": "?撘抒?(Arc)?皜?膩閫????頝?
        },
        "speech_style": {
            "min_length": 15,
            "description": "隤芾店憸冽??琿??膩??蝳芥?瘞?敺?
        },
        "relationships": {
            "min_relationships": 2,
            "description": "瘥?閫??喳???畾菜?蝣箇???閮剖?嚗type?volution"
        },
        "entry_phases": {
            "description": "閫?餃?挾??Ⅱ璅酉嚗?撣???multi_act_structure?郭甈∪???
        },
        "consistency": {
            "description": "閫閮剖??????靽?銝?湛???蝬脤??摩??疵"
        }
    },
    "auto_regenerate_hint": "隢???????脫??殷???/?游?摰???脰身閮?,
    "incremental_hint": "隢??hint ?批捆嚗憓?靽格?????脯?,
    "modify_with_full_content_hint": "隢??hint ?批捆嚗蒂?喳閰脰??脩?摰?批捆嚗脰?撅?其耨?嫘?
}


# =============================================================================
# 3. volumes (蝭閬?撣?Volumes Planner Agent)
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

# ?琿?璅?嚗蜇????斤嚗?VOLUME_APPROVAL_CRITERIA = {
    "name": "volumes",
    "display_name": "蝭閬?撣?,
    "criteria": {
        "volume_count": {
            "min_count": 10,
            "max_count": 15,
            "description": "?瑟撱箄降10-15?瘀????????撟?瑽??
        },
        "required_fields": {
            "per_volume": ["volume_index", "title", "summary", "chapter_count", "factions", "time_timeline", "sequence_context", "applicable_rules"],
            "description": "瘥敹‵甈?敹?摰嚗?敺蝛?
        },
        "title": {
            "min_length": 3,
            "description": "瘥璅??蝎曄?銝?????
        },
        "summary": {
            "min_length": 200,
            "max_length": 300,
            "description": "瘥璁???膩?詨?????瞏桅?"
        },
        "chapter_count": {
            "min_per_volume": 50,
            "max_per_volume": 200,
            "description": "瘥蝡??賊?50-200蝡?靽?摰寥?敺"
        },
        "structure_coherence": {
            "description": "?琿?摨????嚗??舫瞍??瑟?嚗?啣????蝭?"
        },
        "character_progression": {
            "description": "???閫?餃?挾(Progressive Character Plan)嚗??????脣銝??瑞?瘣餉?摨?
        },
        "turning_points_distribution": {
            "description": "?摰??頧?暺?拍?瑚?嚗Ⅱ靽撐???餃?撣?
        },
        "volume_function": {
            "description": "瘥???蝣箏??賢?雿?韏瑯????嚗??瑕偏???嗥?擃蔭?敹?
        }
    },
    "auto_regenerate_hint": "隢????閮剖????脫??殷????冽???瑞?瑽???瑟嚗遣霅?10-15 ?瘀????瑟?憿?閬?隞亙?????萎?隞嗉???銝餉?閫?餃摰???,
    "patch_hint": "隢??蝚?{idx} ?瑞??批捆嚗??hint ?內??
}


# =============================================================================
# 4. volume_skeleton (蝭撉冽閬?撣?Volume Skeleton Planner)
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

# 撉冽??璅?嚗蜇????斤嚗?SKELETON_APPROVAL_CRITERIA = {
    "name": "volume_skeleton",
    "display_name": "蝭撉冽閬?撣?,
    "criteria": {
        "chapter_completeness": {
            "description": "閰脣???蝭撉冽敹?摰??嚗??舐撩瞍遙雿?蝡?
        },
        "chapter_title": {
            "min_length": 3,
            "description": "瘥?璅??蝎曄?銝?????
        },
        "chapter_summary": {
            "min_length": 50,
            "max_length": 100,
            "description": "瘥?????膩?祉??詨?????蝣?
        },
        "foreshadowing_allocation": {
            "min_plants": 1,
            "description": "瘥??????隡??身隞餃?嚗?琿???蝑車璊?
        },
        "turning_point_placement": {
            "description": "?頧?暺??券?嗡?蝵殷??瑕偏/擃蔭蝡???????
        },
        "chapter_sequence": {
            "description": "蝡?摨?????嚗??臭葉?瑟?頝唾?"
        },
        "allocated_tasks_structure": {
            "foreshadowing_plants": "array of strings",
            "foreshadowing_payoffs": "array of strings",
            "turning_points": "array of strings",
            "description": "瘥??llocated_tasks銝??摮嚗?箇征???"
        },
        "character_exclusion": {
            "description": "?爸?嗆扔蝪∪??爸?園?畾萄?撠釣?澆?砍??粥????蝣脣?嚗?撠??閬恣閫?餃???脫暑頨?鈭箇??蝑敦蝭??鈭箄身蝝啁????啗底蝝啣之蝬梢?畾菔???
        }
    },
    "auto_regenerate_hint": "隢???????????瑞?憭抒雇嚗??啁????渡??嗅??琿爸?嗚?
}


# =============================================================================
# 5. plot (憭抒雇閬?撣?Plot Planner Agent)
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

# 憭抒雇??璅?嚗蜇????斤嚗?PLOT_APPROVAL_CRITERIA = {
    "name": "plot",
    "display_name": "憭抒雇閬?撣?,
    "criteria": {
        "chapter_completeness": {
            "description": "???蝭憭抒雇敹?摰??嚗??舐撩瞍?
        },
        "chapter_structure": {
            "required_fields": ["chapter_index", "title", "chapter_summary", "events", "foreshadowing_plant", "foreshadowing_payoff", "turning_points", "characters_active", "emotional_tone", "cliffhanger"],
            "description": "瘥???瑕?摰蝯?嚗???雿??舐蝛?
        },
        "time_setting": {
            "description": "瘥?????啁???閮剖????????楊摨?
        },
        "events": {
            "min_scenes": 0,
            "max_scenes": 4,
            "description": "瘥???0-4?擃?臭?隞塚??膩??銵?????
        },
        "foreshadowing_sync": {
            "description": "隡?蝔格?(foreshadowing_plant)????foreshadowing_payoff)??爸?嗅???allocated_tasks銝??
        },
        "turning_points_alignment": {
            "description": "turning_points?????閮剖??ey_turning_points?潭?"
        },
        "cliffhanger": {
            "description": "蝡??敹菟摮?Cliffhanger)嚗Ⅱ靽霈撘萄?"
        },
        "character_consistency": {
            "description": "瘣餉?閫?蝚血?閫??閮剖?嚗??臬?曇??脰??箄?蝒?
        },
        "plot_drive": {
            "description": "瘥????蝣箇????桃?嚗?蝯?瘞游董"
        },
        "character_presence": {
            "description": "???脣?湔楛摨西??底蝝啣之蝬梢?畾萄??底蝝啗??蒂?Ｙ?閰喟敦?批捆嚗?閬Ⅱ撖血????脫暑頨?臭誑皛輯雲?典?鈭箄身??嚗?憒?蝣箔??詨?銝餉????菟?閫暑頨?拍???瑁???嚗??銝剜?蝣箏?蝷箄??脣?渲????脣?撘萄?嚗?
        }
    },
    "auto_regenerate_hint": "隢??????????蝡?撉冽憭抒雇嚗??啁????渡??嗅?憭抒雇??
}


# =============================================================================
# 6. writer (甇??撖思?雿振 Chapter Writer Agent)
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

# 撖思???璅?嚗蜇????斤嚗?WRITER_APPROVAL_CRITERIA = {
    "name": "writer",
    "display_name": "甇??撖思?雿振",
    "criteria": {
        "content_length": {
            "min_words": 1500,
            "description": "瘥?甇???蝣箔?頞喳???鈭楛摨?
        },
        "structure_compliance": {
            "description": "甇????湔?憭抒雇???身摰?胯?蝑?摨???
        },
        "show_dont_tell": {
            "description": "????啣?皜脫??擃?雿閰???撖怠??暹?蝭嚗???膩"
        },
        "character_consistency": {
            "description": "閫?啗???瘞??雿???蝚血?閫??"
        },
        "foreshadowing_execution": {
            "description": "隡???芰???嚗??嗆??????????
        },
        "turning_point_execution": {
            "description": "頧?暺??雲憭??芷????"
        },
        "prose_quality": {
            "description": "???瘚?芷?嚗泵??摰?憸?
        },
        "cliffhanger_effectiveness": {
            "description": "蝡?詨艙????支?霈??
        }
    },
    "auto_regenerate_hint": "隢???????????瑞?閰喟敦憭抒雇嚗誑??銝??喳??嗅???蝑摰對????甇????
}


# =============================================================================
# 7. editor (蝺刻摩憪?Editor Agent)
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

# 蝺刻摩??璅?嚗蜇????斤嚗?EDITOR_APPROVAL_CRITERIA = {
    "name": "editor",
    "display_name": "蝺刻摩憪?,
    "criteria": {
        "content_quality_improvement": {
            "description": "瞏方敺摰寥?瘥????＊??嚗??祆?蝑??Ｗ漲??憟?
        },
        "character_consistency_preserved": {
            "description": "瞏方銝?寡?閫??摰儔?犖閮哨?銝??閫銵銵?"
        },
        "plot_integrity": {
            "description": "銝?寡?憭抒雇?Ｗ???蝭韏啣????萎?隞?
        },
        "foreshadowing_integrity": {
            "description": "銝?芷?隤支耨?孵歇????蝑摰?
        },
        "synopsis_accuracy": {
            "description": "?湔敺?synopsis?皞Ⅱ???祉??批捆"
        },
        "polish_level": {
            "description": "?靽格迤隤??航炊??撘?璅?扼??文?閰?
        }
    },
    "auto_regenerate_hint": "隢?楊頛舀?蝷綽??瞏方?祉?甇????
}


# =============================================================================
# 蝯曹???璅??亥岷隞
# =============================================================================

APPROVAL_CRITERIA_REGISTRY = {
    "worldview": WORLDVIEW_APPROVAL_CRITERIA,
    "characters": CHARACTER_APPROVAL_CRITERIA,
    "volumes": VOLUME_APPROVAL_CRITERIA,
    "volume_skeleton": SKELETON_APPROVAL_CRITERIA,
    "plot": PLOT_APPROVAL_CRITERIA,
    "writer": WRITER_APPROVAL_CRITERIA,
    "editor": EDITOR_APPROVAL_CRITERIA,
}


def get_approval_criteria(stage_name):
    """
    ?????挾??璅?
    
    Args:
        stage_name: ?挾?迂 (worldview, characters, volumes, volume_skeleton, plot, writer, editor)
    
    Returns:
        ??璅?dict嚗?∪???畾萄?餈?None
    """
    return APPROVAL_CRITERIA_REGISTRY.get(stage_name)


def format_criteria_for_prompt(stage_name):
    """
    ?澆???璅??箏靘LM?梯???蝷箄??澆?
    
    Args:
        stage_name: ?挾?迂
    
    Returns:
        ?澆?????銝?    """
    criteria = get_approval_criteria(stage_name)
    if not criteria:
        return ""
    
    lines = [
        f"\n## ?criteria['display_name']} ??璅???,
        f"### 敹炎?仿??殷?\n"
    ]
    
    for key, value in criteria["criteria"].items():
        if isinstance(value, dict):
            lines.append(f"- **{key}**: {value.get('description', '')}")
        else:
            lines.append(f"- **{key}**: {value}")
    
    if "auto_regenerate_hint" in criteria:
        lines.append(f"\n### ????內嚗?)
        lines.append(f"{criteria['auto_regenerate_hint']}")
    
    return "\n".join(lines)


# =============================================================================
# 頛?賣
# =============================================================================

def get_worldview_default():
    """??銝?閫?身蝯?"""
    return WORLDVIEW_SCHEMA.copy()


def get_character_default():
    """??閫?身蝯?"""
    return CHARACTER_SCHEMA.copy()


def get_volume_default(volume_index=1):
    """??蝭?身蝯?"""
    vol = VOLUME_SCHEMA.copy()
    vol["volume_index"] = volume_index
    vol["title"] = f"蝚?{volume_index} ??
    return vol


def get_chapter_skeleton_default(chapter_index=1):
    """??蝡?撉冽?身蝯?"""
    skel = CHAPTER_SKELETON_SCHEMA.copy()
    skel["chapter_index"] = chapter_index
    return skel


def get_plot_chapter_default(chapter_index=1):
    """??憭抒雇蝡??身蝯?"""
    ch = PLOT_CHAPTER_SCHEMA.copy()
    ch["chapter_index"] = chapter_index
    return ch


def create_plot_structure(chapters_list):
    """撱箇?憭抒雇蝯?"""
    return {"chapters": chapters_list}


def create_characters_structure(characters_list):
    """撱箇?閫蝯?"""
    return {"characters": characters_list}


def create_volume_list(volumes_list):
    """撱箇?蝭?”"""
    return volumes_list


def create_skeleton_list(skeletons_list):
    """撱箇?撉冽?”"""
    return skeletons_list


def create_foreshadowing_allocations(allocations_list):
    """撱箇?隡????”"""
    return allocations_list
