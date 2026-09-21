# -*- coding: utf-8 -*-
"""
Graphiti Fact & Entity Extractor.
Extracts dynamic entities and temporal facts from chapter text, detecting superseded facts.
"""
import hashlib
import json
import traceback
from typing import Dict, Any, List, Optional
from backend import persistence as db
from backend.common.llm import call_llm
from backend.models.parsers import extract_json_block

EXTRACTION_SYSTEM_PROMPT = """你是一位精通長篇小說故事設定與動態時序追蹤的架構分析師（Graphiti Temporal Knowledge Extractor）。
你的任務是閱讀最新章節正文，提取出「新建立的時序事實」、「實體狀態變更」以及「被覆蓋或作廢的舊事實」。

請回傳標準 JSON 格式：
{
  "entities": [
    {
      "name": "實體名稱",
      "entity_type": "character|item|location|faction|concept",
      "summary": "當前最新狀態簡述",
      "attributes": {"key": "value"}
    }
  ],
  "new_facts": [
    {
      "source_name": "主體名稱 (可選)",
      "target_name": "客體名稱 (可選)",
      "relation_type": "關係類型 (例如: 持有, 敵對, 習得, 抵達, 盟友)",
      "fact_statement": "清楚簡要的事實陳述 (例如: 蕭炎在第5章獲得青蓮地心火)"
    }
  ],
  "invalidated_fact_ids_or_statements": [
    "被本章劇情推翻、作廢或改變的舊事實敘述"
  ],
  "conflict_signature": {
    "pressure_type": "本章對立勢力施加的主要壓力類型（限以下枚舉擇一）: oppression(階層壓迫)|suppression(特權打壓)|blockade(資源封鎖)|humiliation(公開羞辱)|assassination(暗殺圍殺)|frame_up(構陷誣告)|legal_strangulation(律法絞殺)|manipulation(情報操弄)|emotional_coercion(情感勒索)|exclusion(體制排擠)|other(其他或無明顯衝突)",
    "protagonist_strategy": "主角本章主要應對策略（限以下枚舉擇一）: play_dumb_or_weak(裝傻示弱)|asymmetric_wit(非對稱智鬥)|rules_loophole(規則漏洞)|direct_clash(正面硬撼)|strategic_retreat(戰略撤退)|negotiation(談判交易)|investigation(調查取證)|damage_control(止損善後)|recuperation(休養沉澱)|groundwork(鋪墊經營)|adaptive_response(臨機應變)|payoff_execution(收束爆發)",
    "outcome": "本章衝突結局模式（限以下枚舉擇一）: public_shock(震驚全場)|uneasy_truce(暫時休戰)|costly_victory(慘勝)|setback(受挫)|escape(脫身)|reversal(反轉)|progression(推進)|revelation(真相揭露)",
    "initiator": "發起施壓的勢力或人物名稱",
    "antagonist_goal": "對手的目的簡述",
    "power_used": "主角動用的關鍵力量或手段",
    "cost": "主角付出的實質代價（若無則填空字串）",
    "emotional_effect": "本章帶給讀者的主要情緒效果",
    "setting_used": "本章運用的世界觀設定名稱（若無則填空字串）"
  },
  "setting_usage": ["本章實際調用的世界觀設定名稱清單"],
  "terms": [
    {
      "term": "專有名詞或術語 (例如: 滅世晨星、星輝門閥)",
      "category": "術語分類 (例如: 功法、勢力、道具、地點、角色)",
      "definition": "術語定義或設定簡述"
    }
  ]
}

注意：「terms」為選填。若省略，系統會自動以實體清單整理術語庫。
"""

ENTITY_TYPE_TO_CATEGORY = {
    "character": "角色",
    "item": "道具",
    "location": "地點",
    "faction": "勢力",
    "concept": "概念",
}


def _attributes_to_notes(attributes) -> str:
    """將實體 attributes 轉為術語 notes（手動術語不受影響，僅自動同步使用）。"""
    if not attributes:
        return ""
    if isinstance(attributes, dict):
        parts = [f"{k}: {v}" for k, v in attributes.items() if v not in (None, "")]
        return "；".join(parts)[:500]
    return str(attributes)[:500]


class ChapterFactExtractor:
    """Extracts temporal facts and manages fact invalidation."""

    @staticmethod
    def process_chapter_prose(
        novel_id: str,
        chapter_index: int,
        chapter_text: str,
        active_facts: Optional[List[Dict[str, Any]]] = None,
        agent_name: str = "copilot"
    ) -> Dict[str, Any]:
        """Analyzes chapter prose, extracts facts, invalidates old facts, and updates DB."""
        if not chapter_text or not chapter_text.strip():
            return {"status": "skipped", "reason": "empty_text"}

        content_hash = hashlib.sha256(chapter_text.encode("utf-8")).hexdigest()[:16]
        
        # Save episode
        episode = db.save_episode(
            novel_id=novel_id,
            chapter_index=chapter_index,
            summary=f"Chapter {chapter_index} prose",
            content_hash=content_hash
        )

        existing_facts = active_facts or db.get_facts_at_chapter(novel_id, chapter_index)
        existing_facts_desc = "\n".join([
            f"- [ID:{f['id']}] {f.get('fact_statement', '')}" for f in existing_facts[:20]
        ])

        user_prompt = f"""【當前已有之生效事實清單 (供比對是否作廢)】:
{existing_facts_desc or '（目前尚無舊事實）'}

【第 {chapter_index} 章正文內容】:
{chapter_text[:4000]}

請分析上述正文，提取新事實並指出被作廢的舊事實。"""

        used_fallback = False
        fallback_reason = ""
        try:
            raw_response = call_llm(
                agent_name=agent_name,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                force_json=True,
            )
            if not raw_response or not raw_response.strip():
                raise ValueError("LLM returned empty response")
            # 1) 先試原生 JSON（相容開啟 response_format 的模型）
            try:
                data = json.loads(raw_response)
            except Exception:
                # 2) 相容 ```json ... ``` / <think> / 前後贅字（gemini-web/pro 常見）
                data = extract_json_block(raw_response)
            if not isinstance(data, dict):
                raise ValueError(f"Parsed JSON is not a dict: {type(data).__name__}")
            if "entities" not in data and "new_facts" not in data:
                raise ValueError(f"Parsed JSON missing keys: {list(data.keys())[:5]}")
            data.setdefault("entities", [])
            data.setdefault("new_facts", [])
            data.setdefault("invalidated_fact_ids_or_statements", [])
            data.setdefault("conflict_signature", {})
            data.setdefault("setting_usage", [])
            data.setdefault("terms", [])
        except Exception as e:
            # Fallback for mock or failure（保留舊行為，但加上可觀測性）
            print(f"[Graphiti Extractor] Chapter {chapter_index} LLM parse failed, using fallback. Reason: {e}")
            print(f"[Graphiti Extractor] raw head: {(locals().get('raw_response') or '')[:500]!r}")
            traceback.print_exc()
            used_fallback = True
            fallback_reason = str(e)[:500]
            data = {
                "entities": [],
                "new_facts": [{
                    "source_name": "",
                    "target_name": "",
                    "relation_type": "event",
                    "fact_statement": f"第 {chapter_index} 章順利完成寫作與推進。"
                }],
                "invalidated_fact_ids_or_statements": []
            }

        # 0. 歸一化 Story Engine 2.0 衝突簽名（LLM 枚舉值優先，非法值直接丟棄
        #    交給離線啟發式兜底；此處絕不拋錯）
        conflict_signature: Dict[str, Any] = {}
        setting_usage: List[str] = []
        try:
            from backend.services.narrative.conflict_ledger import ConflictLedger as _CL
            _raw_sig = data.get("conflict_signature") or {}
            if isinstance(_raw_sig, dict):
                def _enum(v: Any, allowed: tuple) -> str:
                    s = str(v or "").strip().lower()
                    return s if s in allowed else ""
                _p = _enum(_raw_sig.get("pressure_type"), _CL.PRESSURE_TYPES)
                _s = _enum(_raw_sig.get("protagonist_strategy"), _CL.PROTAGONIST_STRATEGIES)
                _o = _enum(_raw_sig.get("outcome"), _CL.OUTCOMES)
                if _p or _s or _o:
                    conflict_signature = {
                        "pressure_type": _p or None,
                        "protagonist_strategy": _s or None,
                        "outcome": _o or None,
                        "initiator": str(_raw_sig.get("initiator") or "").strip()[:40] or None,
                        "antagonist_goal": str(_raw_sig.get("antagonist_goal") or "").strip()[:120] or None,
                        "power_used": str(_raw_sig.get("power_used") or "").strip()[:120] or None,
                        "cost": str(_raw_sig.get("cost") or "").strip()[:120] or None,
                        "emotional_effect": str(_raw_sig.get("emotional_effect") or "").strip()[:120] or None,
                        "setting_used": str(_raw_sig.get("setting_used") or "").strip()[:40] or None,
                    }
            _raw_su = data.get("setting_usage") or []
            if isinstance(_raw_su, list):
                for _item in _raw_su:
                    if isinstance(_item, str) and _item.strip():
                        setting_usage.append(_item.strip()[:40])
                    elif isinstance(_item, dict) and (_item.get("system_name") or _item.get("name")):
                        setting_usage.append(str(_item.get("system_name") or _item.get("name")).strip()[:40])
        except Exception:
            conflict_signature = {}
            setting_usage = []

        # 1. Upsert Entities
        entity_id_map = {}
        for ent in data.get("entities", []):
            name = ent.get("name", "").strip()
            etype = ent.get("entity_type", "character").strip()
            if name:
                res = db.upsert_entity(
                    novel_id=novel_id,
                    name=name,
                    entity_type=etype,
                    summary=ent.get("summary", ""),
                    attributes=ent.get("attributes"),
                    chapter_index=chapter_index
                )
                entity_id_map[name] = res["id"]

        # 2. Add New Facts
        added_facts = []
        for fact in data.get("new_facts", []):
            stmt = fact.get("fact_statement", "").strip()
            if not stmt:
                continue
            src_name = fact.get("source_name", "").strip()
            tgt_name = fact.get("target_name", "").strip()
            src_id = entity_id_map.get(src_name)
            tgt_id = entity_id_map.get(tgt_name)
            
            res_fact = db.add_fact(
                novel_id=novel_id,
                fact_statement=stmt,
                valid_from_chapter=chapter_index,
                source_entity_id=src_id,
                target_entity_id=tgt_id,
                relation_type=fact.get("relation_type"),
                episode_id=episode["id"]
            )
            added_facts.append(res_fact)

        # 3. Handle Invalidation
        invalidated_statements = data.get("invalidated_fact_ids_or_statements", [])
        for old_fact in existing_facts:
            f_id = old_fact["id"]
            f_stmt = old_fact.get("fact_statement", "")
            for inv in invalidated_statements:
                if (f_id in str(inv)) or (len(f_stmt) > 4 and f_stmt in str(inv)):
                    db.invalidate_fact(fact_id=f_id, invalid_from_chapter=chapter_index)
                    break

        # 4. Sync Story Terms together with the temporal graph (same pass).
        #    LLM-provided terms first, then entities auto-organized into the
        #    glossary so the two stay linked (terms carry source_chapter and
        #    are removed automatically when the chapter is cleared).
        terms_created = 0
        terms_updated = 0
        terms_kept_manual = 0
        synced_term_names = set()
        if not used_fallback:
            for t in data.get("terms", []) or []:
                name = (t.get("term") or "").strip()
                if not name or name in synced_term_names:
                    continue
                try:
                    res = db.upsert_term(
                        novel_id=novel_id,
                        category=(t.get("category") or "通用術語").strip(),
                        term=name,
                        definition=(t.get("definition") or "").strip(),
                        notes=(t.get("notes") or "").strip(),
                        source_chapter=chapter_index,
                        updated_chapter=chapter_index,
                    )
                    synced_term_names.add(name)
                    if res.get("action") == "created":
                        terms_created += 1
                    elif res.get("action") == "updated":
                        terms_updated += 1
                    else:
                        terms_kept_manual += 1
                except Exception as te:
                    print(f"[Graphiti Extractor] Chapter {chapter_index} term sync skipped for {name!r}: {te}")
            for ent in data.get("entities", []) or []:
                name = (ent.get("name") or "").strip()
                if not name or name in synced_term_names:
                    continue
                try:
                    res = db.upsert_term(
                        novel_id=novel_id,
                        category=ENTITY_TYPE_TO_CATEGORY.get(
                            (ent.get("entity_type") or "character").strip(), "通用術語"),
                        term=name,
                        definition=(ent.get("summary") or "").strip(),
                        notes=_attributes_to_notes(ent.get("attributes")),
                        source_chapter=chapter_index,
                        updated_chapter=chapter_index,
                    )
                    synced_term_names.add(name)
                    if res.get("action") == "created":
                        terms_created += 1
                    elif res.get("action") == "updated":
                        terms_updated += 1
                    else:
                        terms_kept_manual += 1
                except Exception as te:
                    print(f"[Graphiti Extractor] Chapter {chapter_index} entity-term sync skipped for {name!r}: {te}")

        return {
            "episode_id": episode["id"],
            "entities_updated": len(entity_id_map),
            "facts_added": len(added_facts),
            "terms_created": terms_created,
            "terms_updated": terms_updated,
            "terms_kept_manual": terms_kept_manual,
            "conflict_signature": conflict_signature,
            "setting_usage": setting_usage,
            "status": "fallback" if used_fallback else "success",
            "used_fallback": used_fallback,
            "fallback_reason": fallback_reason,
        }
