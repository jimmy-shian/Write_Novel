/**
 * 幾何與語義 4 階段導覽：步驟定義 + localStorage 持久化。
 * 零依賴 Spotlight Tour（B 方案）。
 */

export interface StageGuideStep {
  /** CSS selector，高亮目標；留空則置中顯示 */
  selector?: string;
  title: string;
  desc: string;
  tip?: string;
}

export const STAGE_GUIDE_STEPS: StageGuideStep[] = [
  {
    title: '這 4 顆是「給總監的標籤」',
    desc: '先選標籤（要改哪一層），再在下方輸入框寫調整要求，最後按「送出」。總監會把指令分派給對應的流水線，不是按了就直接改完。',
    tip: '接下來會依序高亮：4 顆按鈕 → 中央看板 → 輸入框 → 送出。',
  },
  {
    selector: '[data-stage="geometry"]',
    title: '① 幾何拓撲：先建骨架',
    desc: '全書結構骨架、主線/副線/主題線與長距伏筆邊。永遠先跑這顆，後面三顆都需要它存在。',
    tip: '結果看中央「結構 → 幾何拓撲」的心智圖。',
  },
  {
    selector: '[data-stage="macro_semantic"]',
    title: '② 宏觀語義：卷主題＋線程劇情',
    desc: 'Pass 1+2：填每卷主題、衝突核心與每條敘事線的懸念目標。若還沒建骨架，按了只會報錯，看起來像沒作用。',
    tip: '前置：必須先有幾何圖。',
  },
  {
    selector: '[data-stage="character_semantic"]',
    title: '③ 角色語義：人物綁上弧線',
    desc: 'Pass 3：把角色聖經的人物綁到角色弧線，並填心境轉折節點。人物要先在「角色聖經」立卡，效果才明顯。',
    tip: '前置：幾何圖 ＋ 角色聖經。',
  },
  {
    selector: '[data-stage="cross_relation"]',
    title: '④ 跨線合流：多線碰撞因果',
    desc: 'Pass 4：填跨線邊（匯聚、呼應、對比、回收）的碰撞動機與因果。成功後只在右側吐 JSON，要回中央看板整理才看得到。',
    tip: '前置：幾何圖（最好先跑過②③）。',
  },
  {
    selector: '.architecture-board, .workspace-body',
    title: '結果在這裡看：中央結構看板',
    desc: '四顆按鈕都會切到同一個「結構」視圖，所以你會覺得畫面沒動——那是正常的。語義填充完記得按看板內的「重新整理」，才看得到新內容。',
  },
  {
    selector: '[data-tour="copilot-input"]',
    title: '在這裡寫調整要求（可空）',
    desc: '例如對②寫「第 2 卷主題改為復仇與救贖的對比」；留空就跑預設流程。每顆按鈕下方輸入框的提示字會換，照著寫就行。',
  },
  {
    selector: '[data-tour="copilot-send"]',
    title: '按送出才真正執行',
    desc: '執行中右側會顯示思考過程與即時內容，跑完可到「總監評斷紀錄」頁籤回看。這份導覽只會自動出現一次，可在設定重新開啟。',
  },
];

const ENABLED_KEY = 'writenovel_stage_guide_enabled';
const SEEN_KEY = 'writenovel_stage_guide_seen_v1';

function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* 忽略無痕/儲存體滿等偶發失敗 */
  }
}

function safeRemove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    /* 忽略 */
  }
}

/** 設定開關：預設開啟（沒存過視為開）。 */
export function getGuideEnabled(): boolean {
  return safeGet(ENABLED_KEY) !== '0';
}

/**
 * 設定開關切換。重新開啟（true）時一併清除已看記號，
 * 保證「設定可以再次開啟」後下次會自動播放。
 */
export function setGuideEnabled(enabled: boolean): void {
  safeSet(ENABLED_KEY, enabled ? '1' : '0');
  if (enabled) {
    safeRemove(SEEN_KEY);
  }
}

/** 是否已看過（跳過/走完都算）。 */
export function hasGuideSeen(): boolean {
  return safeGet(SEEN_KEY) === '1';
}

export function markGuideSeen(): void {
  safeSet(SEEN_KEY, '1');
}

/** 清除已看記號 → 下次自動播放（設定頁「重新播放」用）。 */
export function resetGuideSeen(): void {
  safeRemove(SEEN_KEY);
}

/** 啟動時是否自動播放：開關開著 且 還沒看過。 */
export function shouldAutoShowGuide(): boolean {
  return getGuideEnabled() && !hasGuideSeen();
}
