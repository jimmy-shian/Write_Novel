"""Novel export endpoints."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from urllib.parse import quote

router = APIRouter()

@router.get("/novels/{novel_id}/export")
def api_export_novel(novel_id: str, format: str = "txt"):
    from backend import persistence as db
    import json

    novel = db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    wb = db.get_latest_worldbuilding(novel_id)
    char = db.get_latest_characters(novel_id)
    plot_data = db.get_stitched_plot(novel_id)
    plot = {"parsed_data": plot_data} if plot_data else None
    chapters = db.get_all_chapters_latest(novel_id)

    title = novel.get("title", "未命名小說")
    genre = novel.get("genre", "未分類")
    style = novel.get("style", "預設風格")

    if format == "txt":
        content = f"《{title}》\n"
        content += f"題材：{genre}\n"
        content += f"風格基調：{style}\n"
        content += "=========================================\n\n"

        chapter_titles = {}
        if plot and plot.get("parsed_data") and "chapters" in plot["parsed_data"]:
            for c in plot["parsed_data"]["chapters"]:
                if "chapter_index" in c:
                    chapter_titles[c["chapter_index"]] = c.get("chapter_title", "").strip()

        if not chapters:
            content += "（正文尚無章節內容）\n"
        else:
            sorted_ch = sorted(chapters, key=lambda x: x.get("chapter_index", 0))
            for ch in sorted_ch:
                idx = ch.get("chapter_index", 0)
                real_title = chapter_titles.get(idx, "")

                if real_title and real_title != f"第 {idx} 章" and real_title != f"第{idx}章":
                    ch_title = f"第 {idx} 章：{real_title}"
                else:
                    ch_title = f"第 {idx} 章"

                content += f"【{ch_title}】\n\n"
                content += f"{ch.get('content', '')}\n\n"
                content += "-----------------------------------------\n\n"

        filename = f"{title}_完整正文.txt"
        headers = {"Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"}
        return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)

    elif format == "markdown":
        content = f"# 《{title}》\n\n"
        content += f"- **題材**: {genre}\n"
        content += f"- **風格基調**: {style}\n\n"
        content += "---\n\n"
        content += "## 世界觀與核心設定\n\n"
        content += f"{wb['content'] if wb else '*尚無設定*'}\n\n"
        content += "---\n\n"
        content += "## 角色聖經 (Character Bible)\n\n"
        content += f"{char['json_data'] if char else '*尚無角色設定*'}\n\n"
        content += "---\n\n"
        content += "## 劇情章節大綱\n\n"
        content += f"{json.dumps(plot['parsed_data'], ensure_ascii=False, indent=2) if plot else '*尚無章節大綱*'}\n\n"
        content += "---\n\n"
        content += "## 小說完整正文\n\n"

        chapter_titles = {}
        if plot and plot.get("parsed_data") and "chapters" in plot["parsed_data"]:
            for c in plot["parsed_data"]["chapters"]:
                if "chapter_index" in c:
                    chapter_titles[c["chapter_index"]] = c.get("chapter_title", "").strip()

        if not chapters:
            content += "*尚未撰寫任何章節*\n\n"
        else:
            sorted_ch = sorted(chapters, key=lambda x: x.get("chapter_index", 0))
            for ch in sorted_ch:
                idx = ch.get("chapter_index", 0)
                real_title = chapter_titles.get(idx, "")

                if real_title and real_title != f"第 {idx} 章" and real_title != f"第{idx}章":
                    ch_title = f"第 {idx} 章：{real_title}"
                else:
                    ch_title = f"第 {idx} 章"

                content += f"### {ch_title}\n\n"
                content += f"{ch.get('content', '')}\n\n"

        filename = f"{title}_小說設定與全書正文.md"
        headers = {"Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"}
        return Response(content=content, media_type="text/markdown; charset=utf-8", headers=headers)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")