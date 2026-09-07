/**
 * Time and timezone utilities for frontend display.
 * Accurately parses UTC timestamps (e.g. SQLite CURRENT_TIMESTAMP without 'Z')
 * and converts to the client's local timezone / Taiwan time (UTC+8).
 */

export function parseUtcTimestamp(ts?: string): Date | null {
  if (!ts || typeof ts !== 'string') return null;
  const trimmed = ts.trim();
  if (!trimmed) return null;

  // If already contains Z or timezone offset (+08:00, -05:00, etc.)
  if (/Z$|[+-]\d{2}(?::?\d{2})?$/.test(trimmed)) {
    const d = new Date(trimmed);
    return isNaN(d.getTime()) ? null : d;
  }

  // SQLite CURRENT_TIMESTAMP format: "YYYY-MM-DD HH:MM:SS" (stored in UTC)
  const isoUtc = trimmed.replace(' ', 'T') + 'Z';
  const d = new Date(isoUtc);
  if (!isNaN(d.getTime())) return d;

  const fallback = new Date(trimmed);
  return isNaN(fallback.getTime()) ? null : fallback;
}

/**
 * Format timestamp in local browser / Taiwan timezone.
 * Defaults to Taiwan time (Asia/Taipei) or client local time.
 */
export function formatTaiwanTime(ts?: string): string {
  const d = parseUtcTimestamp(ts);
  if (!d) return ts || '';
  try {
    return d.toLocaleTimeString('zh-TW', {
      timeZone: 'Asia/Taipei',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    });
  } catch {
    return d.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    });
  }
}

/**
 * Format full date + time in Taiwan timezone.
 */
export function formatTaiwanDateTime(ts?: string): string {
  const d = parseUtcTimestamp(ts);
  if (!d) return ts || '';
  try {
    return d.toLocaleString('zh-TW', {
      timeZone: 'Asia/Taipei',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return d.toLocaleString();
  }
}
