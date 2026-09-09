import { request } from './client';
import { Novel, Chapter, Volume } from '../types';

export interface NovelDetailResponse {
  novel: Novel;
  worldbuilding: string;
  worldbuilding_version: number;
  characters: any;
  characters_raw: string;
  characters_version: number;
  plot: any;
  plot_raw: string;
  plot_version: number;
  chapters: Chapter[];
  chat_memory: any[];
  volumes: Volume[];
  worldview_patches: any[];
}

export async function listNovels(): Promise<Novel[]> {
  return request<Novel[]>('/api/novels');
}

export async function createNovel(
  title: string,
  genre: string = 'Fantasy',
  style: string = 'Classic Modernism',
  pipelinePrompt?: string
): Promise<{ status: string; novel_id: string }> {
  return request('/api/novels', {
    method: 'POST',
    body: JSON.stringify({
      title,
      genre,
      style,
      pipeline_prompt: pipelinePrompt,
    }),
  });
}

export async function getNovel(novelId: string): Promise<NovelDetailResponse> {
  return request<NovelDetailResponse>(`/api/novels/${novelId}`);
}

export async function deleteNovel(novelId: string): Promise<{ status: string }> {
  return request(`/api/novels/${novelId}`, {
    method: 'DELETE',
  });
}

export async function copyNovel(novelId: string, title?: string): Promise<{ status: string; novel_id: string; title: string }> {
  return request(`/api/novels/${novelId}/copy`, {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export async function saveChapter(novelId: string, chapterIndex: number, content: string): Promise<{ status: string; version: number }> {
  return request(`/api/novels/${novelId}/chapters/${chapterIndex}`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}

export async function saveWorldbuilding(novelId: string, content: string): Promise<{ status: string; version: number }> {
  return request(`/api/novels/${novelId}/worldbuilding`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}

export async function saveCharacters(novelId: string, jsonData: any): Promise<{ status: string; version: number }> {
  return request(`/api/novels/${novelId}/characters`, {
    method: 'POST',
    body: JSON.stringify({ json_data: jsonData }),
  });
}

export async function savePlot(novelId: string, outlineJson: any): Promise<{ status: string; version: number }> {
  return request(`/api/novels/${novelId}/plot`, {
    method: 'POST',
    body: JSON.stringify({ outline_json: outlineJson }),
  });
}

export async function saveVolumes(novelId: string, volumes: any[]): Promise<{ status: string }> {
  return request(`/api/novels/${novelId}/volumes`, {
    method: 'POST',
    body: JSON.stringify({ volumes }),
  });
}

export async function savePipelinePrompt(novelId: string, pipelinePrompt: string): Promise<{ status: string }> {
  return request(`/api/novels/${novelId}/pipeline-prompt`, {
    method: 'POST',
    body: JSON.stringify({ pipeline_prompt: pipelinePrompt }),
  });
}

export async function getPipelinePrompt(novelId: string): Promise<{ pipeline_prompt: string }> {
  return request(`/api/novels/${novelId}/pipeline-prompt`);
}

export async function getChatMemory(
  novelId: string,
  limit: number = 100,
  messageType?: string
): Promise<{ chat_memory: any[]; count: number }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (messageType) {
    params.set('message_type', messageType);
  }
  return request(`/api/novels/${novelId}/chat-memory?${params.toString()}`);
}

export async function clearChatMemory(novelId: string, messageType?: string): Promise<{ status: string; deleted_count?: number }> {
  const url = messageType && messageType !== 'all'
    ? `/api/novels/${novelId}/clear-chat?message_type=${encodeURIComponent(messageType)}`
    : `/api/novels/${novelId}/clear-chat`;
  return request(url, {
    method: 'POST',
  });
}

export async function deleteChatMessage(novelId: string, messageId: number): Promise<{ status: string; message_id: number }> {
  return request(`/api/novels/${novelId}/chat-memory/${messageId}`, {
    method: 'DELETE',
  });
}

export async function resetNovelContent(novelId: string): Promise<{ status: string; success: boolean; message: string }> {
  return request(`/api/novels/${novelId}/reset-content`, {
    method: 'POST',
  });
}

export function downloadNovelExport(novelId: string, format: 'html' | 'txt' = 'html'): void {
  const url = `/api/novels/${novelId}/export?format=${format}`;
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', '');
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

