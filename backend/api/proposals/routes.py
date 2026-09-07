# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, Dict, Any, List
from backend import persistence as db

router = APIRouter(tags=["proposals"])

@router.get("/novels/{novel_id}/proposals")
def list_draft_proposals(
    novel_id: str,
    chapter: Optional[int] = Query(None),
    status: Optional[str] = Query(None)
):
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    proposals = db.get_proposals(novel_id, chapter, status)
    return {"novel_id": novel_id, "proposals": proposals}

@router.post("/novels/{novel_id}/proposals")
def create_draft_proposal(novel_id: str, payload: Dict[str, Any] = Body(...)):
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    chapter_index = int(payload.get("chapter_index", 1))
    proposed_text = payload.get("proposed_text", "")
    original_text = payload.get("original_text", "")
    review_comments = payload.get("review_comments", [])
    
    if not proposed_text:
        raise HTTPException(status_code=422, detail="proposed_text is required")
    
    res = db.create_proposal(
        novel_id=novel_id,
        chapter_index=chapter_index,
        proposed_text=proposed_text,
        original_text=original_text,
        review_comments=review_comments
    )
    return res

@router.get("/novels/{novel_id}/proposals/{proposal_id}")
def get_single_draft_proposal(novel_id: str, proposal_id: str):
    prop = db.get_proposal(proposal_id)
    if not prop or prop.get("novel_id") != novel_id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return prop

@router.put("/novels/{novel_id}/proposals/{proposal_id}/status")
def update_proposal_status_endpoint(novel_id: str, proposal_id: str, payload: Dict[str, Any] = Body(...)):
    status = payload.get("status")
    if not status:
        raise HTTPException(status_code=422, detail="Status is required")
    success = db.update_proposal_status(proposal_id, status)
    if not success:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return {"status": "success", "proposal_id": proposal_id, "new_status": status}

@router.post("/novels/{novel_id}/proposals/{proposal_id}/apply")
def apply_draft_proposal(novel_id: str, proposal_id: str):
    prop = db.get_proposal(proposal_id)
    if not prop or prop.get("novel_id") != novel_id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    
    chapter_index = prop["chapter_index"]
    new_content = prop["proposed_text"]
    
    # Save into authoritative chapters table
    saved_ch = db.save_chapter(novel_id, chapter_index, new_content, is_dirty=True)
    
    # Update proposal status to accepted
    db.update_proposal_status(proposal_id, "accepted")
    
    return {
        "status": "applied",
        "chapter_index": chapter_index,
        "proposal_id": proposal_id,
        "saved_chapter": saved_ch
    }

@router.delete("/novels/{novel_id}/proposals/{proposal_id}")
def delete_draft_proposal(novel_id: str, proposal_id: str):
    success = db.delete_proposal(proposal_id)
    if not success:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return {"status": "success", "deleted_id": proposal_id}
