/**
 * Platform Abstraction Layer.
 * Decouples platform-specific implementations (Web, Android APK, Desktop).
 */

export type PlatformType = 'web' | 'android' | 'desktop';

export interface PlatformCapabilities {
  type: PlatformType;
  isMobile: boolean;
  hasHardwareBackButton: boolean;
  canVibrate: boolean;
  supportsTouch: boolean;
}

class PlatformService {
  private static instance: PlatformService;
  private capabilities: PlatformCapabilities;

  private constructor() {
    this.capabilities = this.detectPlatform();
  }

  public static getInstance(): PlatformService {
    if (!PlatformService.instance) {
      PlatformService.instance = new PlatformService();
    }
    return PlatformService.instance;
  }

  private detectPlatform(): PlatformCapabilities {
    const ua = typeof navigator !== 'undefined' ? navigator.userAgent.toLowerCase() : '';
    const isCapacitor = typeof (window as any)?.Capacitor !== 'undefined';
    const isAndroid = /android/.test(ua) || isCapacitor;
    const isDesktop = /electron/.test(ua) || (!isAndroid && !/iphone|ipad|ipod/.test(ua) && typeof window !== 'undefined' && window.innerWidth >= 1024);
    const supportsTouch = typeof window !== 'undefined' && ('ontouchstart' in window || navigator.maxTouchPoints > 0);

    let type: PlatformType = 'web';
    if (isAndroid) type = 'android';
    else if (/electron/.test(ua)) type = 'desktop';

    return {
      type,
      isMobile: isAndroid || /iphone|ipad|ipod/.test(ua),
      hasHardwareBackButton: isAndroid,
      canVibrate: typeof navigator !== 'undefined' && 'vibrate' in navigator,
      supportsTouch,
    };
  }

  public getCapabilities(): PlatformCapabilities {
    return this.capabilities;
  }

  public vibrate(durationMs: number = 20): void {
    if (this.capabilities.canVibrate) {
      try {
        navigator.vibrate(durationMs);
      } catch {
        // Ignore fallback
      }
    }
  }

  public getBaseApiUrl(): string {
    if (typeof localStorage !== 'undefined') {
      const stored = localStorage.getItem('NOVEL_FACTORY_API_HOST');
      if (stored) return stored.trim().replace(/\/+$/, '');
    }
    // 若於 GitHub Pages (無後端靜態託管) 運行，預設指向 Hugging Face Space 雲端後端
    if (typeof window !== 'undefined' && (
      window.location.hostname.includes('github.io') ||
      window.location.hostname.includes('pages.dev')
    )) {
      return 'https://botsz-writenovel.hf.space';
    }
    return '';
  }

  public setBaseApiUrl(url: string): void {
    if (typeof localStorage !== 'undefined') {
      const trimmed = url.trim().replace(/\/+$/, '');
      if (trimmed) localStorage.setItem('NOVEL_FACTORY_API_HOST', trimmed);
      else localStorage.removeItem('NOVEL_FACTORY_API_HOST');
    }
  }

  public getApiToken(): string {
    if (typeof localStorage !== 'undefined') {
      return localStorage.getItem('NOVEL_FACTORY_API_TOKEN') || '';
    }
    return '';
  }

  public setApiToken(token: string): void {
    if (typeof localStorage !== 'undefined') {
      const trimmed = token.trim();
      if (trimmed) localStorage.setItem('NOVEL_FACTORY_API_TOKEN', trimmed);
      else localStorage.removeItem('NOVEL_FACTORY_API_TOKEN');
    }
  }

  public getCloudBucket(): string {
    if (typeof localStorage !== 'undefined') {
      return localStorage.getItem('NOVEL_FACTORY_CLOUD_BUCKET') || '';
    }
    return '';
  }

  public setCloudBucket(bucket: string): void {
    if (typeof localStorage !== 'undefined') {
      const trimmed = bucket.trim();
      if (trimmed) localStorage.setItem('NOVEL_FACTORY_CLOUD_BUCKET', trimmed);
      else localStorage.removeItem('NOVEL_FACTORY_CLOUD_BUCKET');
    }
  }
}

export const platform = PlatformService.getInstance();

export function getPlatformAdapter() {
  return {
    get apiBaseUrl(): string {
      return platform.getBaseApiUrl();
    },
    platform,
  };
}

/**
 * 智慧解析使用者輸入的雲端端點字串（支援 URL、Space 名稱或 Storage Bucket 名稱）
 */
export function parseCloudEndpoint(input: string): { host: string; bucket: string } {
  const trimmed = input.trim();
  if (!trimmed) {
    return { host: '', bucket: '' };
  }
  // 1. 完整 URL 格式 (http:// 或 https://)
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return { host: trimmed.replace(/\/+$/, ''), bucket: 'botsz/writenovel-storage-bucket' };
  }
  // 2. 域名格式 (如 botsz-writenovel.hf.space)
  if (trimmed.includes('.hf.space')) {
    return { host: `https://${trimmed.replace(/\/+$/, '')}`, bucket: 'botsz/writenovel-storage-bucket' };
  }
  // 3. 儲存庫命名格式 (如 username/repo-name)
  if (trimmed.includes('/')) {
    const [user, repo] = trimmed.split('/');
    if (repo.toLowerCase().includes('bucket') || repo.toLowerCase().includes('storage')) {
      return { host: 'https://botsz-writenovel.hf.space', bucket: trimmed };
    } else {
      const spaceHost = `https://${user.toLowerCase()}-${repo.toLowerCase().replace(/_/g, '-')}.hf.space`;
      return { host: spaceHost, bucket: `${user}/writenovel-storage-bucket` };
    }
  }
  return { host: '', bucket: trimmed };
}

/**
 * 建構完整的 API 請求 URL（針對 Hugging Face Space 自動繞過 Gradio 308 重定向）
 */
export function buildApiUrl(endpoint: string): string {
  const adapter = getPlatformAdapter();
  const baseUrl = adapter.apiBaseUrl.replace(/\/+$/, '');
  let cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;

  if (baseUrl.includes('hf.space') && cleanEndpoint.startsWith('/api/')) {
    cleanEndpoint = cleanEndpoint.replace(/^\/api\//, '/gradio_api/novel/');
  }

  return `${baseUrl}${cleanEndpoint}`;
}

/**
 * 取得全域認證 HTTP 標頭
 */
export function getAuthHeaders(): Record<string, string> {
  const token = platform.getApiToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
