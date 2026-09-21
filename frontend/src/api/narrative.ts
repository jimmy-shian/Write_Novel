import { request } from './client';
import {
  NarrativeProfile,
  SettingSystem,
  SettingHealthReport,
  ConflictSignature,
  ConflictRepetitionDiagnosis,
  NarrativeAudit,
  NarrativeAuditRunResult,
} from '../types';

// =============================================================================
// 1. Narrative Profile API
// =============================================================================

export async function getNarrativeProfile(novelId: string): Promise<NarrativeProfile> {
  const res = await request<{ novel_id: string; profile: NarrativeProfile }>(
    `/api/novels/${encodeURIComponent(novelId)}/narrative-profile`
  );
  return res.profile;
}

export async function updateNarrativeProfile(
  novelId: string,
  profile: Partial<NarrativeProfile>
): Promise<NarrativeProfile> {
  const res = await request<{ status: string; profile: NarrativeProfile }>(
    `/api/novels/${encodeURIComponent(novelId)}/narrative-profile`,
    {
      method: 'PUT',
      body: JSON.stringify(profile),
    }
  );
  return res.profile;
}

// =============================================================================
// 2. Setting Systems & Registry API
// =============================================================================

export async function getSettingSystems(
  novelId: string,
  activeOnly = false
): Promise<SettingSystem[]> {
  const q = activeOnly ? '?active_only=true' : '';
  const res = await request<{ novel_id: string; setting_systems: SettingSystem[]; total: number }>(
    `/api/novels/${encodeURIComponent(novelId)}/setting-systems${q}`
  );
  return res.setting_systems || [];
}

export async function upsertSettingSystem(
  novelId: string,
  systemData: Partial<SettingSystem>
): Promise<SettingSystem> {
  const res = await request<{ status: string; setting_system: SettingSystem }>(
    `/api/novels/${encodeURIComponent(novelId)}/setting-systems`,
    {
      method: 'POST',
      body: JSON.stringify(systemData),
    }
  );
  return res.setting_system;
}

export async function syncSettingSystemsFromWorldview(
  novelId: string
): Promise<{ synced_count: number; total_systems: number; setting_systems: SettingSystem[] }> {
  return await request(
    `/api/novels/${encodeURIComponent(novelId)}/setting-systems/sync`,
    {
      method: 'POST',
    }
  );
}

export async function getSettingSystemsHealth(
  novelId: string,
  currentChapter?: number
): Promise<SettingHealthReport> {
  const q = currentChapter ? `?current_chapter=${currentChapter}` : '';
  const res = await request<{ novel_id: string; health: SettingHealthReport }>(
    `/api/novels/${encodeURIComponent(novelId)}/setting-systems/health${q}`
  );
  return res.health;
}

// =============================================================================
// 3. Conflict Signatures & Anti-Repetition API
// =============================================================================

export async function getConflictSignatures(
  novelId: string,
  limit = 50
): Promise<ConflictSignature[]> {
  const res = await request<{ novel_id: string; signatures: ConflictSignature[]; total: number }>(
    `/api/novels/${encodeURIComponent(novelId)}/conflict-signatures?limit=${limit}`
  );
  return res.signatures || [];
}

export async function addConflictSignature(
  novelId: string,
  sigData: Partial<ConflictSignature>
): Promise<ConflictSignature> {
  const res = await request<{ status: string; signature: ConflictSignature }>(
    `/api/novels/${encodeURIComponent(novelId)}/conflict-signatures`,
    {
      method: 'POST',
      body: JSON.stringify(sigData),
    }
  );
  return res.signature;
}

export async function checkConflictRepetition(
  novelId: string,
  candidateSignature: Record<string, any>,
  window = 60,
  threshold = 0.70
): Promise<ConflictRepetitionDiagnosis> {
  const res = await request<{ novel_id: string; diagnosis: ConflictRepetitionDiagnosis }>(
    `/api/novels/${encodeURIComponent(novelId)}/conflict-signatures/check-repetition`,
    {
      method: 'POST',
      body: JSON.stringify({
        candidate_signature: candidateSignature,
        window,
        threshold,
      }),
    }
  );
  return res.diagnosis;
}

// =============================================================================
// 4. Narrative Audits API
// =============================================================================

export async function getNarrativeAudits(
  novelId: string,
  chapterIndex?: number,
  unresolvedOnly = false,
  limit = 50
): Promise<NarrativeAudit[]> {
  const params = new URLSearchParams();
  if (chapterIndex !== undefined && chapterIndex !== null) {
    params.append('chapter_index', String(chapterIndex));
  }
  if (unresolvedOnly) {
    params.append('unresolved_only', 'true');
  }
  params.append('limit', String(limit));

  const res = await request<{ novel_id: string; audits: NarrativeAudit[]; total: number }>(
    `/api/novels/${encodeURIComponent(novelId)}/narrative-audits?${params.toString()}`
  );
  return res.audits || [];
}

export async function createNarrativeAudit(
  novelId: string,
  auditData: Partial<NarrativeAudit>
): Promise<NarrativeAudit> {
  const res = await request<{ status: string; audit: NarrativeAudit }>(
    `/api/novels/${encodeURIComponent(novelId)}/narrative-audits`,
    {
      method: 'POST',
      body: JSON.stringify(auditData),
    }
  );
  return res.audit;
}

export async function runNarrativeAuditForChapter(
  novelId: string,
  chapterIndex: number,
  proseText?: string
): Promise<NarrativeAuditRunResult> {
  const res = await request<{ status: string; result: NarrativeAuditRunResult; audits: NarrativeAudit[] }>(
    `/api/novels/${encodeURIComponent(novelId)}/narrative-audits/run`,
    {
      method: 'POST',
      body: JSON.stringify({
        chapter_index: chapterIndex,
        prose_text: proseText,
      }),
    }
  );
  return res.result;
}
export async function resolveNarrativeAudit(auditId: string): Promise<boolean> {
  const res = await request<{ status: string; audit_id: string; resolved: boolean }>(
    `/api/narrative-audits/${encodeURIComponent(auditId)}/resolve`,
    {
      method: 'POST',
    }
  );
  return res.resolved ?? false;
}

export interface NarrativeFixChapterResult {
  status: string;
  novel_id: string;
  chapter_index: number;
  fixed_count: number;
  resolved_audit_ids: string[];
  reaudit: NarrativeAuditRunResult | null;
}

export async function fixChapterFromAudits(
  novelId: string,
  chapterIndex: number,
  auditIds?: string[]
): Promise<NarrativeFixChapterResult> {
  return await request<NarrativeFixChapterResult>(
    `/api/novels/${encodeURIComponent(novelId)}/narrative-audits/fix-chapter`,
    {
      method: 'POST',
      body: JSON.stringify({
        chapter_index: chapterIndex,
        audit_ids: auditIds ?? null,
      }),
    }
  );
}
