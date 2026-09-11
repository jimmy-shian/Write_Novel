import { AppPreferences, getPreferences, savePreferencesApi } from '../api/settings';

export type ThemeMode = 'light' | 'neutral' | 'dark';

export interface PreferencesState {
  theme: ThemeMode;
  editor_font_size: number;
}

export const DEFAULT_PREFERENCES: PreferencesState = {
  theme: 'dark',
  editor_font_size: 16,
};

const THEME_KEY = 'ai_novel_theme';
const FONT_SIZE_KEY = 'editor_font_size';

type PreferencesListener = (prefs: PreferencesState) => void;
const listeners: Set<PreferencesListener> = new Set();

/**
 * 訂閱偏好變更通知
 */
export function subscribePreferences(listener: PreferencesListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notifyListeners(prefs: PreferencesState) {
  listeners.forEach((fn) => {
    try {
      fn(prefs);
    } catch (e) {
      console.error('Preferences listener error:', e);
    }
  });
}

/**
 * 【讀取 / 紀錄】(Load / Read) - 從 localStorage 讀取快取之偏好設定
 */
export function getCachedPreferences(): PreferencesState {
  if (typeof window === 'undefined') return { ...DEFAULT_PREFERENCES };
  const rawTheme = localStorage.getItem(THEME_KEY);
  const theme: ThemeMode = (rawTheme === 'dark' || rawTheme === 'neutral' || rawTheme === 'light')
    ? rawTheme
    : DEFAULT_PREFERENCES.theme;

  const rawFontSize = localStorage.getItem(FONT_SIZE_KEY);
  const parsedSize = rawFontSize ? parseInt(rawFontSize, 10) : NaN;
  const editor_font_size = (!isNaN(parsedSize) && parsedSize >= 12 && parsedSize <= 32)
    ? parsedSize
    : DEFAULT_PREFERENCES.editor_font_size;

  return { theme, editor_font_size };
}

/**
 * 【使用】(Apply / Use) - 套用主題色彩至 DOM 根節點與 meta theme-color
 */
export function applyTheme(theme: ThemeMode): void {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-theme', theme);
  const themeColorMeta = document.querySelector('meta[name="theme-color"]');
  if (themeColorMeta) {
    const bgColors: Record<ThemeMode, string> = {
      dark: '#141210',
      neutral: '#ebe6de',
      light: '#f7f4ee',
    };
    themeColorMeta.setAttribute('content', bgColors[theme] || '#141210');
  }
}

/**
 * 【使用】(Apply / Use) - 套用文字大小至 CSS 變數
 */
export function applyFontSize(size: number): void {
  if (typeof document === 'undefined') return;
  document.documentElement.style.setProperty('--editor-font-size', `${size}px`);
}

/**
 * 【使用】(Apply / Use) - 套用全量偏好設定
 */
export function applyAllPreferences(prefs: PreferencesState): void {
  applyTheme(prefs.theme);
  applyFontSize(prefs.editor_font_size);
}

/**
 * 【儲存】(Save / Persist) - 模組化儲存：同步更新快取與 DOM，異步持久化至後端 SQLite
 */
export async function savePreferences(
  patch: Partial<PreferencesState>,
  persistToBackend: boolean = true
): Promise<PreferencesState> {
  const current = getCachedPreferences();
  const updated: PreferencesState = {
    ...current,
    ...patch,
  };

  if (patch.theme !== undefined) {
    localStorage.setItem(THEME_KEY, patch.theme);
    applyTheme(patch.theme);
  }
  if (patch.editor_font_size !== undefined) {
    localStorage.setItem(FONT_SIZE_KEY, String(patch.editor_font_size));
    applyFontSize(patch.editor_font_size);
  }

  notifyListeners(updated);

  if (persistToBackend) {
    try {
      const payload: Record<string, any> = {};
      if (patch.theme !== undefined) payload.theme = patch.theme;
      if (patch.editor_font_size !== undefined) payload.editor_font_size = patch.editor_font_size;
      await savePreferencesApi(payload);
    } catch (err) {
      console.warn('[Preferences] 儲存至後端失敗 (已保存在本地快取):', err);
    }
  }

  return updated;
}

/**
 * 【同步】(Sync / Startup) - 從後端拉取偏好設定並全域套用
 */
export async function syncPreferencesFromServer(): Promise<PreferencesState> {
  try {
    const res = await getPreferences();
    const serverPrefs = res?.preferences;
    if (serverPrefs) {
      const local = getCachedPreferences();
      const newTheme: ThemeMode = (serverPrefs.theme === 'dark' || serverPrefs.theme === 'neutral' || serverPrefs.theme === 'light')
        ? serverPrefs.theme
        : local.theme;
      const parsedSize = parseInt(String(serverPrefs.editor_font_size), 10);
      const newFontSize = (!isNaN(parsedSize) && parsedSize >= 12 && parsedSize <= 32)
        ? parsedSize
        : local.editor_font_size;

      const synced: PreferencesState = {
        theme: newTheme,
        editor_font_size: newFontSize,
      };

      localStorage.setItem(THEME_KEY, newTheme);
      localStorage.setItem(FONT_SIZE_KEY, String(newFontSize));
      applyAllPreferences(synced);
      notifyListeners(synced);
      return synced;
    }
  } catch (err) {
    console.warn('[Preferences] 無法自後端拉取偏好 (使用本地快取):', err);
  }
  const fallback = getCachedPreferences();
  applyAllPreferences(fallback);
  return fallback;
}
