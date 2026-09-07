# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, Dict, Any, List
from backend import persistence as db

router = APIRouter(tags=["terms"])

@router.get("/novels/{novel_id}/terms")
def list_story_terms(novel_id: str, category: Optional[str] = Query(None)):
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    terms = db.get_terms(novel_id, category)
    return {"novel_id": novel_id, "terms": terms}

@router.post("/novels/{novel_id}/terms")
def create_story_term(novel_id: str, payload: Dict[str, Any] = Body(...)):
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    term = payload.get("term", "").strip()
    category = payload.get("category", "通用術語").strip()
    definition = payload.get("definition", "").strip()
    notes = payload.get("notes", "").strip()
    if not term:
        raise HTTPException(status_code=422, detail="Term is required")
    if not definition:
        raise HTTPException(status_code=422, detail="Definition is required")
    res = db.create_term(novel_id, category, term, definition, notes)
    return res

@router.put("/novels/{novel_id}/terms/{term_id}")
def update_story_term(novel_id: str, term_id: str, payload: Dict[str, Any] = Body(...)):
    term = payload.get("term", "").strip()
    category = payload.get("category", "通用術語").strip()
    definition = payload.get("definition", "").strip()
    notes = payload.get("notes", "").strip()
    if not term or not definition:
        raise HTTPException(status_code=422, detail="Term and definition are required")
    success = db.update_term(term_id, category, term, definition, notes)
    if not success:
        raise HTTPException(status_code=404, detail="Term not found")
    return {"status": "success", "updated_id": term_id}

@router.delete("/novels/{novel_id}/terms/{term_id}")
def delete_story_term(novel_id: str, term_id: str):
    success = db.delete_term(term_id)
    if not success:
        raise HTTPException(status_code=404, detail="Term not found")
    return {"status": "success", "deleted_id": term_id}
