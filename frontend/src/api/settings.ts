import { request } from './client';
import { AgentConfig } from '../types';

export interface SettingsSnapshot {
  agents: Record<string, AgentConfig>;
  [key: string]: any;
}

export async function getSettings(): Promise<SettingsSnapshot> {
  return request<SettingsSnapshot>('/api/settings');
}

export async function saveSettings(payload: any): Promise<{ status: string }> {
  return request('/api/settings', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchAvailableModels(baseUrl: string, apiKey: string): Promise<{ models: string[] }> {
  return request('/api/settings/fetch-models', {
    method: 'POST',
    body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }),
  });
}

export interface CloudSyncStatus {
  available: boolean;
  has_token: boolean;
  token?: string;
  storage_bucket: string;
  dataset_repo: string;
  db_path?: string;
  db_exists: boolean;
  db_size_mb: number;
  last_backup_time: string | null;
  last_backup_status: string;
  last_restore_time: string | null;
  last_restore_status: string;
  last_error: string;
}

export async function getCloudSyncStatus(): Promise<CloudSyncStatus> {
  return request<CloudSyncStatus>('/api/sync/status');
}

export async function saveCloudSyncConfig(config: {
  storage_bucket?: string;
  dataset_repo?: string;
  token?: string;
}): Promise<{ status: string; config: CloudSyncStatus }> {
  return request('/api/sync/config', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export async function triggerCloudBackup(force: boolean = false): Promise<{ status: string; message: string }> {
  return request(`/api/sync/backup?force=${force}`, {
    method: 'POST',
  });
}
