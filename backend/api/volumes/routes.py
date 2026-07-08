"""Volume management endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter()

class VolumeCreatePayload(BaseModel):
    title: str
    summary: Optional[str] = ""
    factions: Optional[str] = ""
    chapter_count: Optional[int] = 50

@router.post("/novels/{novel_id}/volumes/{vol_idx}")
def api_create_volume(novel_id: str, vol_idx: int, payload: VolumeCreatePayload):
    from backend import persistence as db
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    vols = db.get_volumes(novel_id)
    existing_vol = next((v for v in vols if v.get("volume_index") == vol_idx), None)

    if existing_vol:
        existing_vol["title"] = payload.title
        existing_vol["summary"] = payload.summary or ""
        existing_vol["factions"] = payload.factions or ""
        existing_vol["chapter_count"] = payload.chapter_count or 50
        volume_data = existing_vol
    else:
        new_vol = {
            "id": str(uuid.uuid4()),
            "volume_index": vol_idx,
            "title": payload.title,
            "summary": payload.summary or "",
            "factions": payload.factions or "",
            "chapter_count": payload.chapter_count or 50
        }
        vols.append(new_vol)
        volume_data = new_vol

    vols.sort(key=lambda x: x.get("volume_index", 0))
    db.save_volumes(novel_id, vols)
    return {"status": "success", "volume": volume_data}

@router.delete("/novels/{novel_id}/volumes/{vol_idx}")
def api_delete_volume(novel_id: str, vol_idx: int):
    from backend import persistence as db
    if not db.get_novel(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")
    try:
        db.delete_volume(novel_id, vol_idx)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/novels/{novel_id}/volumes/{vol_idx}/align")
def api_align_volume(novel_id: str, vol_idx: int):
    from backend import persistence as db
    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    plot = db.get_stitched_plot(novel_id)
    if plot and "chapters" in plot:
        vol_chapters = [ch for ch in plot["chapters"] if ch.get("volume_index", 0) == vol_idx]
        vol_chapters.sort(key=lambda x: x.get("chapter_in_volume", 0))
        for idx, ch in enumerate(vol_chapters):
            ch["chapter_in_volume"] = idx + 1
        db.save_plot_chapters(novel_id, plot)
    return {"status": "success"}