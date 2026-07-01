#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小說資料匯出工具

此腳本用於直接從資料庫中提取小說資料並匯出為檔案，
無需透過 Web 界面，適合後台處理或批量匯出需求。

使用方法：
    python export_novel.py --novel-id <小說ID> [--format txt|markdown] [--output <輸出路徑>]
    
examples:
    python export_novel.py --novel-id abc123 --format markdown
    python export_novel.py --list  # 列出所有小說
"""

import sys
import os
import argparse
import json
from urllib.parse import quote

# 添加專案根目錄到 Python 路徑，以便導入 db 模組
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from utils import safe_filename

def list_all_novels():
    """列出所有小說"""
    novels = db.list_novels()
    if not novels:
        print("資料庫中尚無小說資料")
        return []
    
    print(f"共找到 {len(novels)} 部小說：")
    print("-" * 80)
    for novel in novels:
        print(f"ID: {novel['id']}")
        print(f"  標題: {novel['title']}")
        print(f"  題材: {novel.get('genre', '未指定')}")
        print(f"  風格: {novel.get('style', '未指定')}")
        print(f"  建立時間: {novel.get('created_at', '未知')}")
        print()
    return novels

def get_full_novel_data(novel_id):
    """
    獲取小說的完整資料
    
    對應 FastAPI 端點：GET /api/novels/{novel_id}
    此函數複刻了 app.py 中 api_get_novel 的資料收集邏輯
    """
    # 檢查小說是否存在
    novel = db.get_novel(novel_id)
    if not novel:
        raise ValueError(f"找不到 ID 為 '{novel_id}' 的小說")
    
    # 收集各模組資料
    wb = db.get_latest_worldbuilding(novel_id)
    char = db.get_latest_characters(novel_id)
    plot_data = db.get_stitched_plot(novel_id)
    written_ch = db.get_all_chapters_latest(novel_id)
    volumes = db.get_volumes(novel_id)
    
    # 構築回傳結構（與 API 一致）
    result = {
        "novel": novel,
        "worldbuilding": wb["content"] if wb else "",
        "worldbuilding_version": wb["version"] if wb else 0,
        "characters": char["parsed_data"] if char else None,
        "characters_raw": char["json_data"] if char else "",
        "characters_version": char["version"] if char else 0,
        "plot": plot_data if plot_data else {"chapters": []},
        "plot_raw": json.dumps(plot_data, ensure_ascii=False, indent=2) if plot_data else "{}",
        "plot_version": 1,
        "chapters": written_ch,
        "volumes": volumes,
        "worldview_patches": db.get_worldview_patches(novel_id)
    }
    
    return result

def export_as_txt(novel_data, output_path=None):
    """
    匯出為 TXT 格式
    
    格式結構：
    《標題》
    題材：類型
    風格基調：風格
    =========================================
    
    【第 X 章：章節標題】
    
    正文內容
    
    ------------------------------------------
    """
    novel = novel_data["novel"]
    title = novel.get("title", "未命名小說")
    genre = novel.get("genre", "未分類")
    style = novel.get("style", "預設風格")
    chapters = novel_data["chapters"]
    
    # 開始構建內容
    lines = []
    lines.append(f"《{title}》")
    lines.append(f"題材：{genre}")
    lines.append(f"風格基調：{style}")
    lines.append("=" * 48)
    lines.append("")
    
    if not chapters:
        lines.append("（正文尚無章節內容）")
    else:
        # 按章節索引排序
        sorted_ch = sorted(chapters, key=lambda x: x.get("chapter_index", 0))
        for ch in sorted_ch:
            idx = ch.get("chapter_index", 0)
            synopsis = ch.get('synopsis', '')
            ch_title = f"第 {idx} 章：{synopsis or ''}"
            
            lines.append(f"【{ch_title}】")
            lines.append("")
            lines.append(ch.get('content', ''))
            lines.append("")
            lines.append("-" * 48)
            lines.append("")
    
    content = "\n".join(lines)
    
    # 輸出到檔案或返回內容
    if output_path:
        filename = output_path
    else:
        safe_title = safe_filename(title)
        filename = f"{safe_title}_完整正文.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"✓ 已匯出 TXT 格式：{filename}")
    print(f"  總字數：{len(content)} 字元")
    print(f"  章節數：{len(chapters)} 章")
    return filename

def export_as_markdown(novel_data, output_path=None):
    """
    匯出為 Markdown 格式
    
    格式結構：
    # 《標題》
    
    - **題材**: 類型
    - **風格基調**: 風格
    
    ---
    
    ## 📖 世界觀與核心設定
    
    {世界觀內容}
    
    ---
    
    ## 👥 角色聖經 (Character Bible)
    
    {JSON 格式角色資料}
    
    ---
    
    ## 🗺️ 劇情章節大綱
    
    {JSON 格式章節大綱}
    
    ---
    
    ## 📝 小說完整正文
    
    ### 第 X 章：章節標題
    
    正文內容
    """
    novel = novel_data["novel"]
    title = novel.get("title", "未命名小說")
    genre = novel.get("genre", "未分類")
    style = novel.get("style", "預設風格")
    wb = novel_data.get("worldbuilding", "")
    char = novel_data.get("characters_raw", "")
    plot = novel_data.get("plot", {})
    chapters = novel_data["chapters"]
    
    # 開始構建 Markdown 內容
    lines = []
    lines.append(f"# 《{title}》")
    lines.append("")
    lines.append(f"- **題材**: {genre}")
    lines.append(f"- **風格基調**: {style}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 世界觀
    lines.append("## 📖 世界觀與核心設定")
    lines.append("")
    lines.append(wb or "*尚無設定*")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 角色
    lines.append("## 👥 角色聖經 (Character Bible)")
    lines.append("")
    lines.append(char or "*尚無角色設定*")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 大綱
    lines.append("## 🗺️ 劇情章節大綱")
    lines.append("")
    plot_json = plot.get("parsed_data", plot) if isinstance(plot, dict) else plot
    lines.append(json.dumps(plot_json, ensure_ascii=False, indent=2) if plot_json else "*尚無章節大綱*")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 正文
    lines.append("## 📝 小說完整正文")
    lines.append("")
    
    if not chapters:
        lines.append("*尚未撰寫任何章節*")
    else:
        sorted_ch = sorted(chapters, key=lambda x: x.get("chapter_index", 0))
        for ch in sorted_ch:
            idx = ch.get("chapter_index", 0)
            synopsis = ch.get('synopsis', '')
            lines.append(f"### 第 {idx} 章：{synopsis or ''}")
            lines.append("")
            lines.append(ch.get('content', ''))
            lines.append("")
    
    content = "\n".join(lines)
    
    # 輸出到檔案或返回內容
    if output_path:
        filename = output_path
    else:
        safe_title = safe_filename(title)
        filename = f"{safe_title}_小說設定與全書正文.md"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"✓ 已匯出 Markdown 格式：{filename}")
    print(f"  總字數：{len(content)} 字元")
    print(f"  章節數：{len(chapters)} 章")
    return filename

def main():
    parser = argparse.ArgumentParser(
        description="小說資料匯出工具 - 從資料庫提取小說並匯出為檔案",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例：
  %(prog)s --list                    # 列出所有小說
  %(prog)s --novel-id abc123         # 匯出為預設 TXT 格式
  %(prog)s --novel-id abc123 --format markdown  # 匯出為 Markdown
  %(prog)s --novel-id abc123 --format txt --output my_novel.txt  # 指定輸出檔名
        """
    )
    
    parser.add_argument("--novel-id", help="小說 ID（可從 --list 取得）")
    parser.add_argument("--format", choices=["txt", "markdown"], default="txt",
                        help="匯出格式，預設為 txt")
    parser.add_argument("--output", help="輸出檔案路徑（可選）")
    parser.add_argument("--list", action="store_true", help="列出所有小說")
    
    args = parser.parse_args()
    
    try:
        # 僅列出小說
        if args.list:
            list_all_novels()
            return 0
        
        # 必須提供 novel-id
        if not args.novel_id:
            parser.error("請提供 --novel-id 參數，或使用 --list 列出所有小說")
        
        # 初始化資料庫（如果還沒初始化）
        db.db_init()
        
        # 獲取小說資料
        print(f"正在提取小說資料 (ID: {args.novel_id})...")
        novel_data = get_full_novel_data(args.novel_id)
        
        novel_title = novel_data["novel"]["title"]
        print(f"找到小說：《{novel_title}》")
        print(f"  題材：{novel_data['novel'].get('genre', '未指定')}")
        print(f"  風格：{novel_data['novel'].get('style', '未指定')}")
        print(f"  世界觀版本：{novel_data.get('worldbuilding_version', 0)}")
        print(f"  角色版本：{novel_data.get('characters_version', 0)}")
        print(f"  章節數：{len(novel_data['chapters'])}")
        print()
        
        # 根據格式匯出
        if args.format == "txt":
            export_as_txt(novel_data, args.output)
        else:  # markdown
            export_as_markdown(novel_data, args.output)
        
        print()
        print("匯出完成！")
        return 0
        
    except ValueError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"執行失敗：{e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())