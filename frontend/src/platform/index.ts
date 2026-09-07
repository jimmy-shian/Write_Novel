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
    // In Android APK/Capacitor, allow override or fallback to stored server URL
    const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('NOVEL_FACTORY_API_HOST') : null;
    return stored || '';
  }

  public setBaseApiUrl(url: string): void {
    if (typeof localStorage !== 'undefined') {
      if (url) localStorage.setItem('NOVEL_FACTORY_API_HOST', url);
      else localStorage.removeItem('NOVEL_FACTORY_API_HOST');
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
