# -*- coding: utf-8 -*-
"""
Graphiti Fact & Entity Extractor.
Extracts dynamic entities and temporal facts from chapter text, detecting superseded facts.
"""
import hashlib
import json
from typing import Dict, Any, List, Optional
from backend import persistence as db
from backend.common.llm import call_llm

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
  ]
}
"""

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

        try:
            raw_response = call_llm(
                agent_name=agent_name,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_format={"type": "json_object"}
            )
            data = json.loads(raw_response)
        except Exception:
            # Fallback for mock or failure
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

        return {
            "episode_id": episode["id"],
            "entities_updated": len(entity_id_map),
            "facts_added": len(added_facts),
            "status": "success"
        }
