import { buildApiUrl, getAuthHeaders } from '../platform';
import { request } from './client';

export interface GenerationTaskEvent {
  type: 'thinking' | 'content' | 'status' | 'retrying' | 'error' | 'done' | 'reset';
  delta?: string;
  message?: string;
  stage?: string;
  status?: string;
  output?: any;
  ok?: boolean;
  [key: string]: any;
}

export interface StreamGenerationOptions {
  onThinking?: (delta: string | null) => void;
  onContent?: (delta: string | null) => void;
  onStatus?: (message: string) => void;
  onError?: (error: string) => void;
  onDone?: (envelope: any) => void;
  signal?: AbortSignal;
}

export function parseGenerationTaskEventLine(line: string): GenerationTaskEvent | null {
  if (!line) return null;
  const trimmed = line.trim();
  if (!trimmed.startsWith('data:')) return null;
  const payload = trimmed.slice(5).trim();
  if (!payload || payload === '[DONE]') {
    return { type: 'done' };
  }
  try {
    return JSON.parse(payload);
  } catch (error) {
    return null;
  }
}

export async function streamGenerationTask(
  payload: {
    novel_id: string;
    task_type?: string;
    stage?: string;
    scope?: string;
    target?: Record<string, any>;
    prompt?: string;
    user_prompt?: string;
    instruction?: string;
    frontend_state?: Record<string, any>;
    options?: { stream?: boolean; batch?: boolean; overwrite?: boolean };
  },
  callbacks: StreamGenerationOptions = {}
): Promise<void> {
  const url = buildApiUrl('/api/generation-task');
  const authHeaders = getAuthHeaders();

  const body = {
    ...payload,
    options: {
      stream: true,
      ...(payload.options || {}),
    },
  };

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
    },
    body: JSON.stringify(body),
    signal: callbacks.signal,
  });

  if (!response.ok) {
    let errMsg = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errMsg = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {}
    if (callbacks.onError) callbacks.onError(errMsg);
    throw new Error(errMsg);
  }

  if (!response.body) {
    if (callbacks.onError) callbacks.onError('No response body from server');
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const event = parseGenerationTaskEventLine(line);
      if (!event) continue;

      if (event.type === 'thinking') {
        callbacks.onThinking?.(event.delta ?? '');
      } else if (event.type === 'content') {
        callbacks.onContent?.(event.delta ?? '');
      } else if (event.type === 'reset') {
        callbacks.onThinking?.(null);
        callbacks.onContent?.(null);
      } else if (event.type === 'status') {
        callbacks.onStatus?.(event.message || event.status || '');
      } else if (event.type === 'error') {
        callbacks.onError?.(event.message || 'Generation error');
      } else if (event.type === 'done') {
        callbacks.onDone?.(event);
      }
    }
  }
}

export interface AutoPipelineLogEntry {
  time: string;
  msg: string;
  level?: string;
}

export interface AutoPipelineStatusResponse {
  is_running?: boolean;
  running?: boolean;
  novel_id?: string;
  novel_title?: string;
  current_stage?: string;
  current_chapter?: number;
  total_chapters?: number;
  progress_percent?: number;
  status_message?: string;
  logs?: AutoPipelineLogEntry[];
  error?: string | null;
  stop_requested?: boolean;
  start_time?: string;
  last_heartbeat?: string;
  active_tasks_count?: number;
  active_tasks?: any[];
  step?: number;
  total_steps?: number;
}

export interface AutoPipelineStartResponse {
  status: string;
  success?: boolean;
  novel_id?: string;
  novel_title?: string;
  active_tasks_count?: number;
  message?: string;
}

export async function startAutoPipeline(
  novelId: string,
  prompt: string = '',
  maxChapters: number = 5
): Promise<AutoPipelineStartResponse> {
  return request('/api/pipeline/auto-run', {
    method: 'POST',
    body: JSON.stringify({
      novel_id: novelId,
      prompt,
      max_chapters: maxChapters,
    }),
  });
}

export async function getAutoPipelineStatus(novelId?: string): Promise<AutoPipelineStatusResponse> {
  const query = novelId ? `?novel_id=${novelId}` : '';
  return request(`/api/pipeline/auto-status${query}`);
}

export async function stopAutoPipeline(novelId?: string): Promise<{ status: string; success?: boolean; message: string }> {
  return request('/api/pipeline/auto-stop', {
    method: 'POST',
    body: JSON.stringify({ novel_id: novelId }),
  });
}
