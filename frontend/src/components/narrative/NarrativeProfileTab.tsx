import React, { useState, useEffect } from 'react';
import { NarrativeProfile } from '../../types';
import { Button } from '../common/Button';
import { IconCompass, IconCheck } from '../common/Icons';
import { updateNarrativeProfile } from '../../api/narrative';
import { CustomSelect } from '../common/CustomSelect';
import { showToast } from '../common/Toast';

interface NarrativeProfileTabProps {
  novelId: string;
  profile: NarrativeProfile | null;
  isLoading: boolean;
  onRefresh: () => void;
}

export const NarrativeProfileTab: React.FC<NarrativeProfileTabProps> = ({
  novelId,
  profile,
  isLoading,
  onRefresh,
}) => {
  const [commercialPositioning, setCommercialPositioning] = useState('');
  const [dominantAppeal, setDominantAppeal] = useState('');
  const [tone, setTone] = useState('');
  const [pacingPreference, setPacingPreference] = useState('');
  const [powerFantasyLevel, setPowerFantasyLevel] = useState('medium_high');
  const [humorLevel, setHumorLevel] = useState('medium');
  const [emotionalIntensity, setEmotionalIntensity] = useState('medium');
  const [narrativeComplexity, setNarrativeComplexity] = useState('multi_faction');
  const [customNotes, setCustomNotes] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (profile) {
      setCommercialPositioning(profile.commercial_positioning || '');
      setDominantAppeal(profile.dominant_appeal || '');
      setTone(profile.tone || '');
      setPacingPreference(profile.pacing_preference || '');
      setPowerFantasyLevel(profile.power_fantasy_level || 'medium_high');
      setHumorLevel(profile.humor_level || 'medium');
      setEmotionalIntensity(profile.emotional_intensity || 'medium');
      setNarrativeComplexity(profile.narrative_complexity || 'multi_faction');
      setCustomNotes(profile.custom_notes || '');
    }
  }, [profile]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await updateNarrativeProfile(novelId, {
        commercial_positioning: commercialPositioning.trim(),
        dominant_appeal: dominantAppeal.trim(),
        tone: tone.trim(),
        pacing_preference: pacingPreference.trim(),
        power_fantasy_level: powerFantasyLevel,
        humor_level: humorLevel,
        emotional_intensity: emotionalIntensity,
        narrative_complexity: narrativeComplexity,
        custom_notes: customNotes.trim(),
      });
      showToast('作品敘事畫像已成功更新', 'success');
      onRefresh();
    } catch (err: any) {
      showToast(`儲存失敗: ${err.message}`, 'danger');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="narrative-tab-content">
      <div className="profile-guide-banner">
        <IconCompass size={20} className="text-accent" />
        <div className="guide-texts">
          <span className="guide-title">故事創作靈感羅盤 (Narrative Creative Compass)</span>
          <span className="guide-desc">
            此畫像向全體 Agent（架構師、編劇、潤色與總監）提供作品層級之文學調性約束，確保長篇寫作時基調穩定自洽。
          </span>
        </div>
      </div>

      <form onSubmit={handleSave} className="narrative-profile-form">
        <div className="form-card">
          <div className="form-card-title">1. 核心定位與讀者訴求</div>
          <div className="form-grid">
            <div className="form-group">
              <label className="form-label">商業小說定位 (Commercial Positioning)</label>
              <input
                type="text"
                className="form-input"
                value={commercialPositioning}
                onChange={(e) => setCommercialPositioning(e.target.value)}
                placeholder="例：400萬字史詩商業長篇、暗黑克蘇魯智鬥升級"
              />
            </div>

            <div className="form-group">
              <label className="form-label">主導爽點與吸引力 (Dominant Appeal)</label>
              <input
                type="text"
                className="form-input"
                value={dominantAppeal}
                onChange={(e) => setDominantAppeal(e.target.value)}
                placeholder="例：多維情報壓制、高智商反轉、勢力掌控感"
              />
            </div>

            <div className="form-group">
              <label className="form-label">故事語言基調 (Tone)</label>
              <input
                type="text"
                className="form-input"
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                placeholder="例：熱血、微諷、冷硬懸疑、沉浸寫實"
              />
            </div>

            <div className="form-group">
              <label className="form-label">節奏呼吸偏好 (Pacing Preference)</label>
              <input
                type="text"
                className="form-input"
                value={pacingPreference}
                onChange={(e) => setPacingPreference(e.target.value)}
                placeholder="例：緊湊推進、有張有弛、重視沉澱探索章"
              />
            </div>
          </div>
        </div>

        <div className="form-card">
          <div className="form-card-title">2. 創作刻度與機制約束</div>
          <div className="form-grid-4">
            <div className="form-group">
              <label className="form-label">金手指與爽感層級</label>
              <CustomSelect
                value={powerFantasyLevel}
                onChange={(v) => setPowerFantasyLevel(v)}
                options={[
                  { value: 'low', label: '低爽感 / 扎實硬核智鬥' },
                  { value: 'medium', label: '中等 / 伴隨代價的能力躍遷' },
                  { value: 'medium_high', label: '中高 / 關鍵危機強勢反殺' },
                  { value: 'high', label: '高爽感 / 絕對掌控與碾壓' },
                  { value: 'absolute', label: '極致 / 無敵流神明維度' },
                ]}
              />
            </div>

            <div className="form-group">
              <label className="form-label">幽默與諷刺層次</label>
              <CustomSelect
                value={humorLevel}
                onChange={(v) => setHumorLevel(v)}
                options={[
                  { value: 'low', label: '低 / 肅穆正劇風格' },
                  { value: 'medium', label: '中 / 適度黑色幽默與冷嘲' },
                  { value: 'high', label: '高 / 頻繁反諷與解構套路' },
                ]}
              />
            </div>

            <div className="form-group">
              <label className="form-label">情感衝突烈度</label>
              <CustomSelect
                value={emotionalIntensity}
                onChange={(v) => setEmotionalIntensity(v)}
                options={[
                  { value: 'low', label: '冷靜理智 / 客觀克制' },
                  { value: 'medium', label: '熱血激昂 / 生死羈絆' },
                  { value: 'high', label: '狂瀾劇烈 / 宿命悲壯抉擇' },
                ]}
              />
            </div>

            <div className="form-group">
              <label className="form-label">敘事結構複雜度</label>
              <CustomSelect
                value={narrativeComplexity}
                onChange={(v) => setNarrativeComplexity(v)}
                options={[
                  { value: 'single_track', label: '單線主軸直推' },
                  { value: 'multi_faction', label: '多陣營動態博弈網' },
                  { value: 'epic', label: '長程史詩多線並進' },
                ]}
              />
            </div>
          </div>
        </div>

        <div className="form-card">
          <div className="form-card-title">3. 長程不可突破紅線與備註</div>
          <div className="form-group">
            <label className="form-label">不可突破創作禁忌 (Hard Canon Guard)</label>
            <textarea
              className="form-textarea"
              rows={3}
              value={customNotes}
              onChange={(e) => setCustomNotes(e.target.value)}
              placeholder="例：嚴禁主角無腦聖母、反派絕不強行降智、動用禁忌法術必承擔道傷..."
            />
          </div>
        </div>

        <div className="form-actions-bottom">
          <Button type="submit" variant="primary" isLoading={isSaving} icon={<IconCheck size={14} />}>
            儲存敘事畫像
          </Button>
        </div>
      </form>
    </div>
  );
};
