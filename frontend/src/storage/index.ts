/**
 * Storage Abstraction Layer with Minimal I/O Principle.
 * Implements in-memory caching, change detection (dirty checks), and debounced writes.
 */

class StorageManager {
  private static instance: StorageManager;
  private memoryCache: Map<string, { value: any; hash: string; timestamp: number }>;
  private writeTimers: Map<string, number>;

  private constructor() {
    this.memoryCache = new Map();
    this.writeTimers = new Map();
  }

  public static getInstance(): StorageManager {
    if (!StorageManager.instance) {
      StorageManager.instance = new StorageManager();
    }
    return StorageManager.instance;
  }

  private hashData(data: any): string {
    try {
      return typeof data === 'string' ? data : JSON.stringify(data);
    } catch {
      return String(data);
    }
  }

  /**
   * Reads data with in-memory caching to prevent high-frequency disk/storage reads.
   */
  public get<T>(key: string, defaultValue: T): T {
    if (this.memoryCache.has(key)) {
      return this.memoryCache.get(key)!.value as T;
    }

    if (typeof localStorage === 'undefined') {
      return defaultValue;
    }

    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return defaultValue;
      const parsed = JSON.parse(raw);
      this.memoryCache.set(key, {
        value: parsed,
        hash: this.hashData(parsed),
        timestamp: Date.now(),
      });
      return parsed as T;
    } catch {
      return defaultValue;
    }
  }

  /**
   * Writes data ONLY if changed (change detection), debounced to protect persistence layer.
   */
  public set<T>(key: string, value: T, debounceMs: number = 300): void {
    const hash = this.hashData(value);
    const existing = this.memoryCache.get(key);

    // If memory cache already has exact same hash, skip write entirely
    if (existing && existing.hash === hash) {
      return;
    }

    // Update memory cache immediately
    this.memoryCache.set(key, { value, hash, timestamp: Date.now() });

    if (typeof localStorage === 'undefined') return;

    // Clear existing debounce timer
    if (this.writeTimers.has(key)) {
      window.clearTimeout(this.writeTimers.get(key));
    }

    // Debounce disk persistence
    const timer = window.setTimeout(() => {
      try {
        localStorage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value));
      } catch (err) {
        console.warn(`[Storage] Failed to persist key ${key}:`, err);
      } finally {
        this.writeTimers.delete(key);
      }
    }, debounceMs);

    this.writeTimers.set(key, timer);
  }

  public remove(key: string): void {
    this.memoryCache.delete(key);
    if (this.writeTimers.has(key)) {
      window.clearTimeout(this.writeTimers.get(key));
      this.writeTimers.delete(key);
    }
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem(key);
    }
  }

  /**
   * Cleans up all pending timers to prevent memory leaks during unmount.
   */
  public destroy(): void {
    for (const timer of this.writeTimers.values()) {
      window.clearTimeout(timer);
    }
    this.writeTimers.clear();
    this.memoryCache.clear();
  }
}

export const storage = StorageManager.getInstance();
