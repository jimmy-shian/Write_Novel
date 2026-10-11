# 完本質檢 Skill：novel-qc

> 一句話：書寫完 → 跑一次 → 拿到「總分＋缺陷清單＋修稿上下文包」。
> 對應本次《禁咒法師》人工抽查的方法論沉澱：分層抽樣、全書掃描、合併整理、總結輸出。

## 1. 何時觸發（完本後）

- 管線 `pipeline_task_checkpoints` 全 `COMPLETED` 且 `current_chapter == 大綱總章數`；或
- `generation_tasks` 無 `pending/failed`、`volumes` 全卷寫完；或
- 人工判定完本。觸發後跑一次，修稿後可再跑（對比兩次總分即修稿驗收）。

## 2. 怎麼跑

```bash
python tools/novel_qc/cli.py audit --novel "禁咒法師" --out .review/qc-<novel_id> \
  --watch "陸萬雄,塞拉菲娜,卡爾修斯,拜蒙"
```

`--novel` 可填小說 id 或書名關鍵字；`--watch` 追加盯防人名（建議填主要反派）。

## 3. 輸出（上下文傳輸格式）

輸出目錄含兩個文件，即「工具＋上下文傳輸」的全部契約：

- `report.md`：人類可讀總結（總分／五維／缺陷清單／抽樣章／統計）。
- `context_pack.json`：機器可消費，結構：
  ```json
  {
    "novel_id": "...", "title": "...", "chapters_total": 550,
    "sample": {"strata": {"前期": [..], ..}, "pairs": [[1,2],..]},
    "stats": {"opener_templates": {}, "synopsis": {}, "audit_stats": {}},
    "scoring": {"scores": {"A":..,"B":..,"C":..,"D":..,"E":..,"TOTAL":..}, "grade": ".."},
    "findings": [{
      "id": "DEATH-01", "check": "death_resurrection_multi",
      "severity": "critical", "title": "...", "chapters": [260, 305, ...],
      "evidence": [{"chapter": "260", "quote": "..."}],
      "analysis": "...", "suggested_fix": "...", "confidence": "high",
      "editor_context": {"instruction": "...", "targets": [
        {"chapter": 260, "excerpt": "...", "prev_excerpt": {...}}]}
    }]
  }
  ```

## 4. 修稿迴路（消費端接線）

- `editor_context.targets[].excerpt`（目標章正文前 1500 字）＋`prev_excerpt`（前章尾 600 字）＋`instruction`（改寫指令），直接餵給定向改寫（`backend/agents/editor` 的 targeted rewriter 或 `narrative/fix.py` 的 `fix_chapter_from_audits`，把 `instruction` 作為審計意見傳入）。
- `severity=critical` 的 finding 未清零前，匯出閘門應拒絕放行（對應 `backend/api/export/routes.py` 只認 `is_dirty` 的缺口）。
- 複跑：`audit → 修稿 → audit`，以 `TOTAL` 回升為驗收標準。

## 5. 檢查器一覽（與人工抽查的對應）

| 檢查器 | 對應人工方法 | 原理要點 |
|---|---|---|
| `stratify`＋`adjacent_pairs` | 分層抽樣＋連續章抽查 | 五等分均勻取章＋相鄰組，供複核 |
| `check_death_resurrection` | 跨章節生死比對 | 死亡動詞句→後章行動句→無復活標記即嫌疑；引用 `temporal_entities` 人名＋`--watch` |
| `check_date_monotonicity` | 時間線檢查 | 日期錨點單調性，有閃回詞降級為 minor |
| `check_adjacent_duplication` | 章節交接／重寫檢查 | Jaccard 4-gram≥0.5 或開篇重合≥0.5 |
| `check_opener_templates` | 文風機械化 | 首 60 字標記命中率＋最常見開頭前綴 |
| 種子兌現（orchestrator §六） | 伏筆回收檢查 | 載入序前 10（正典種子）逐條：全名/編號/≥2 語義塊命中，或罕見詞在場（改寫存活）才算兌現；其餘微粒種子進複核池 |
| 人物蒸發（orchestrator §五） | 支線爛尾檢查 | 中期前登場≥5 章、後 15% 缺席、且最後 3 出場章無定論式死亡＝嫌疑；已有死亡結論（含重名變體）的不算 |
| 人物蒸發（orchestrator §五） | 支線爛尾檢查 | 中期前登場≥5 章、後 30% 缺席、無死亡即嫌疑 |
| `check_synopsis_health` | 出品檢查 | 提要＝首句＋尾句拼接即無資訊價值 |

## 6. 已知邊界（誠實聲明）

- 死亡檢測是啟發式（主語判定＋將字句病人排除＋器物排除＋投影排除＋否定語境），`confidence=high` 僅限逐字引證的定論式死亡；黑暗奇幻等頻繁描寫屍體的題材誤報率會上升，可用 `--watch` 縮小到要角。
- `temporal_entities` 中的泛稱實體（敵方首領）與重名變體（塞拉菲娜·梵）已做排除與合併，但仍建議 `--watch` 填主要人物全名。
- 日期只認「X 月 X 日／魔法歷／新紀元」三式錨點且只比同紀年體系，相對時間（「三天後」）不追蹤。
- 分數是缺陷扣分制代理指標（同類封頂防風暴），用於修稿前後對比，不等於文學價值判斷；B/C 維對「同一病灶多實例」比人工更嚴， grade 一致即可。
- 資料庫在連載生長時快照會漂移；完本後跑最準。

## 7. 驗證記錄（v1，2026-10-10，《禁咒法師》574 章）

- 工具 63/100（待改善）vs 人工抽查 63/100（待改善），同分同級。
- 召回：陸萬雄 8 死（人工 6 死＋同病灶 268/276 章 2 例）、塞拉菲娜 3 死、日期倒流 17 組（含人工發現的 264 章）、相鄰重複 26 組、10 正典種子逐條、正典級蒸發（卡爾修斯）。
- 精度：林夜／卡爾修斯／陸雲天／拜蒙／敵方首領等誤報已清零；拜蒙 247 章之死被正確識別為正常退場（未報蒸發）。
- 回歸：`tests/unit/test_novel_qc.py` 8 項全過。
