# -*- coding: utf-8 -*-
"""完本質檢 CLI：python tools/novel_qc/cli.py audit --novel <id或書名> --out <目錄>"""
from __future__ import annotations

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from tools.novel_qc import db_reader
from tools.novel_qc.orchestrator import run_audit


def cmd_audit(args: argparse.Namespace) -> int:
    conn = db_reader.open_conn()
    try:
        novel = db_reader.resolve_novel(conn, args.novel)
        chapters = db_reader.load_chapters_latest(conn, novel["id"])
        if not chapters:
            print(f"[-] 小說《{novel['title']}》無章節")
            return 2
        entities = db_reader.load_entities(conn, novel["id"])
        seeds = db_reader.load_seeds(conn, novel["id"])
        audit_stats = db_reader.load_audit_stats(conn, novel["id"])
    finally:
        conn.close()

    print(f"[*] 《{novel['title']}》：{len(chapters)} 章／{len(entities)} 實體／{len(seeds)} 伏筆種子")
    pack = run_audit(
        novel["id"], novel["title"], chapters, entities, seeds, audit_stats,
        sample_per_stratum=args.sample,
        extra_watch=(args.watch or "").split(",") if args.watch else [],
    )
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write(pack.pop("report_md"))
    with open(os.path.join(args.out, "context_pack.json"), "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=1)
    sc = pack["scoring"]["scores"]
    print(f"[+] 總分 {sc['TOTAL']}/100（{pack['scoring']['grade']}） "
          f"A{sc['A']} B{sc['B']} C{sc['C']} D{sc['D']} E{sc['E']}")
    print(f"[+] 缺陷 {len(pack['findings'])} 項 → {args.out}")
    for fd in pack["findings"][:12]:
        print(f"    [{fd['severity']}] {fd['title']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="novel_qc",
                                 description="完本質檢：分層抽查＋全書掃描＋合併整理＋總結")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="對完本小說做質檢並輸出報告＋修稿上下文包")
    a.add_argument("--novel", required=True, help="小說 id 或書名關鍵字")
    a.add_argument("--out", required=True, help="輸出目錄")
    a.add_argument("--sample", type=int, default=4, help="每區段抽樣章數（預設4）")
    a.add_argument("--watch", default="", help="追加盯防的人名，逗號分隔")
    a.set_defaults(func=cmd_audit)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
