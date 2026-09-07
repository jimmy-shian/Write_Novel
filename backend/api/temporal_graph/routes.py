# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, Dict, Any, List
from backend import persistence as db
from backend.services.graphiti import TemporalGraphService, ChapterFactExtractor

router = APIRouter(tags=["temporal_graph"])

@router.get("/novels/{novel_id}/temporal-graph")
def get_temporal_graph(
    novel_id: str,
    chapter: Optional[int] = Query(None, description="Slice at specific chapter index")
):
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    entities = db.get_entities(novel_id)
    episodes = db.get_episodes(novel_id)
    
    if chapter is not None:
        facts = db.get_facts_at_chapter(novel_id, chapter)
    else:
        facts = db.get_all_facts(novel_id)

    return {
        "novel_id": novel_id,
        "chapter_slice": chapter,
        "entities": entities,
        "facts": facts,
        "episodes": episodes
    }

@router.post("/novels/{novel_id}/temporal-graph/entities")
def upsert_temporal_entity(novel_id: str, payload: Dict[str, Any] = Body(...)):
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Entity name is required")
    entity_type = payload.get("entity_type", "character")
    summary = payload.get("summary", "")
    attributes = payload.get("attributes")
    chapter_index = int(payload.get("chapter_index", 1))

    res = db.upsert_entity(
        novel_id=novel_id,
        name=name,
        entity_type=entity_type,
        summary=summary,
        attributes=attributes,
        chapter_index=chapter_index
    )
    return res

@router.delete("/novels/{novel_id}/temporal-graph/entities/{entity_id}")
def delete_temporal_entity(novel_id: str, entity_id: str):
    success = db.delete_entity(entity_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"status": "success", "deleted_id": entity_id}

@router.post("/novels/{novel_id}/temporal-graph/facts")
def add_temporal_fact(novel_id: str, payload: Dict[str, Any] = Body(...)):
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    statement = payload.get("fact_statement", "").strip()
    if not statement:
        raise HTTPException(status_code=422, detail="fact_statement is required")
    valid_from = int(payload.get("valid_from_chapter", 1))
    
    res = db.add_fact(
        novel_id=novel_id,
        fact_statement=statement,
        valid_from_chapter=valid_from,
        source_entity_id=payload.get("source_entity_id"),
        target_entity_id=payload.get("target_entity_id"),
        relation_type=payload.get("relation_type"),
        episode_id=payload.get("episode_id")
    )
    return res

@router.post("/novels/{novel_id}/temporal-graph/facts/{fact_id}/invalidate")
def invalidate_temporal_fact(novel_id: str, fact_id: str, payload: Dict[str, Any] = Body(...)):
    invalid_from = int(payload.get("invalid_from_chapter", 1))
    superseded_by = payload.get("superseded_by")
    success = db.invalidate_fact(fact_id, invalid_from, superseded_by)
    if not success:
        raise HTTPException(status_code=404, detail="Fact not found or already invalidated")
    return {"status": "success", "invalidated_id": fact_id, "invalid_from_chapter": invalid_from}

@router.delete("/novels/{novel_id}/temporal-graph/facts/{fact_id}")
def delete_temporal_fact(novel_id: str, fact_id: str):
    success = db.delete_fact(fact_id)
    if not success:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"status": "success", "deleted_id": fact_id}

@router.post("/novels/{novel_id}/temporal-graph/extract-from-chapter")
def extract_temporal_facts_endpoint(novel_id: str, payload: Dict[str, Any] = Body(...)):
    chapter_index = int(payload.get("chapter_index", 1))
    text = payload.get("content")
    if not text:
        # Load from chapters table
        chapter_row = db.get_chapter(novel_id, chapter_index)
        if chapter_row:
            text = chapter_row.get("content", "")
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="Chapter text is empty")
    
    res = ChapterFactExtractor.process_chapter_prose(
        novel_id=novel_id,
        chapter_index=chapter_index,
        chapter_text=text
    )
    return res
