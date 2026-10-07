# -*- coding: utf-8 -*-
"""
Scale & Dynamic Multi-Act Architect.
Calculates and constructs multi-act narrative structure based on target volume/chapter scale.
Eliminates rigid 3-act limitations by expanding to 6~32 dynamic acts.
"""

from __future__ import annotations
import math
from typing import Dict, Any, List, Optional
from backend import persistence as db
from backend.generation.core.flow_spec import compute_dynamic_acts
from backend.generation.core.contracts import ActSpec, NarrativeScaleSpec
from backend.schemas.genre_presets import get_genre_preset


ACT_THEME_TEMPLATES = [
    ("啟蒙與異動", "日常秩序打破，隱秘危機初現，命運轉折點", 0.25),
    ("門檻與陣營初立", "踏入未知領域，試探各方勢力，建立初步同盟與敵對", 0.40),
    ("交鋒與阻抗上升", "利益碰撞激化，初嚐慘痛代價，防線被迫收縮", 0.55),
    ("中局反轉與至暗前夕", "真相裂解，核心支柱崩解，核心動機發生根本性位移", 0.70),
    ("重組與全面對決", "整合所有線索與殘餘力量，發動總反攻", 0.85),
    ("終局裁決與新秩序", "根本矛盾徹底解決，代價償付，新秩序落定", 0.95),
]


def build_narrative_scale_spec(novel_id: str, target_volumes: Optional[int] = None) -> NarrativeScaleSpec:
    """Constructs a deterministic multi-act scale specification for the novel."""
    novel = db.get_novel(novel_id) or {}
    genre = novel.get("genre") or "general_fiction"
    preset = get_genre_preset(genre)

    # Determine volume count and chapters
    volumes = db.get_volumes(novel_id) or []
    if volumes:
        vol_count = len(volumes)
        ch_per_vol = int(volumes[0].get("chapter_count") or 50)
    elif target_volumes:
        vol_count = max(1, int(target_volumes))
        ch_per_vol = 40
    else:
        vol_range = preset.get("target_volume_count_range", (8, 12))
        vol_count = vol_range[0]
        ch_per_vol = preset.get("target_chapters_per_volume", (30, 50))[1]

    total_chapters = vol_count * ch_per_vol
    act_count = compute_dynamic_acts(vol_count, total_chapters)

    acts: List[ActSpec] = []
    # Distribute acts across volumes
    vol_per_act = vol_count / act_count
    for i in range(1, act_count + 1):
        act_id = f"ACT-{i:02d}"
        # Determine covered volume range
        start_v = max(1, math.floor((i - 1) * vol_per_act) + 1)
        end_v = min(vol_count, math.ceil(i * vol_per_act))
        if start_v > end_v:
            end_v = start_v
        v_range = list(range(start_v, end_v + 1))

        # Assign title, tension, and goal from template or dynamic interpolation
        t_idx = min(len(ACT_THEME_TEMPLATES) - 1, int(((i - 1) / max(1, act_count - 1)) * (len(ACT_THEME_TEMPLATES) - 1)))
        base_title, base_goal, base_tension = ACT_THEME_TEMPLATES[t_idx]
        title = f"第 {i} 幕：{base_title} (涵蓋卷 {start_v}~{end_v})"
        tension = min(1.0, round(0.2 + 0.75 * (i / act_count), 2))

        acts.append(ActSpec(
            act_id=act_id,
            act_index=i,
            title=title,
            theme_goal=base_goal,
            tension_target=tension,
            expected_volume_range=v_range,
            key_turning_points=[f"TP-ACT{i:02d}-01", f"TP-ACT{i:02d}-02"],
        ))

    return NarrativeScaleSpec(
        novel_id=novel_id,
        total_volumes=vol_count,
        chapters_per_volume=ch_per_vol,
        total_chapters=total_chapters,
        act_count=act_count,
        acts=acts,
    )
