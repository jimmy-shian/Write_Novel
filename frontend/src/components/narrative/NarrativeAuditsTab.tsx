import React, { useState } from 'react';
import { NarrativeAudit, NarrativeAuditRunResult } from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { StatusDot } from '../common/StatusDot';
import {
  IconRefresh,
  IconCheck,
  IconAlertTriangle,
  IconSparkles,
  IconCompass,
  IconClock,
} from '../common/Icons';
import { resolveNarrativeAudit, runNarrativeAuditForChapter, fixChapterFromAudits } from '../../api/narrative';
import { CustomSelect } from '../common/CustomSelect';
import { emitChapterContentUpdated } from '../../utils/narrativeRefresh';
import { showToast } from '../common/Toast';

interface NarrativeAuditsTabProps {
  novelId: string;
  audits: NarrativeAudit[];
  activeChapterIndex: number;
  isLoading: boolean;
  onRefresh: () => void;
}

export const NarrativeAuditsTab: React.FC<NarrativeAuditsTabProps> = ({
  novelId,
  audits,
  activeChapterIndex,
  isLoading,
  onRefresh,
}) => {
  const [selectedChapter, setSelectedChapter] = useState<number>(activeChapterIndex || 1);
  const [unresolvedOnly, setUnresolvedOnly] = useState<boolean>(false);
  const [filterDimension, setFilterDimension] = useState<string>('all');
  const [isRunningAudit, setIsRunningAudit] = useState<boolean>(false);
  const [isFixingChapter, setIsFixingChapter] = useState<boolean>(false);
  const [lastAuditResult, setLastAuditResult] = useState<NarrativeAuditRunResult | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  // Run live audit for chapter
  const handleRunAudit = async () => {
    setIsRunningAudit(true);
    try {
      const res = await runNarrativeAuditForChapter(novelId, selectedChapter);
      setLastAuditResult(res);
      showToast(
        `第 ${selectedChapter} 章審計完成：[${res.overall_action}] 發現 ${res.findings_count} 項觀察點`,
        res.overall_action === 'CRITICAL' ? 'danger' : res.overall_action === 'REVISE' ? 'warning' : 'success'
      );
      onRefresh();
    } catch (err: any) {
      showToast(`審計執行失敗: ${err.message}`, 'danger');
    } finally {
      setIsRunningAudit(false);
    }
  };

  // Fix chapter prose via Editor using unresolved audits as instructions
  const handleFixChapter = async () => {
    setIsFixingChapter(true);
    try {
      const res = await fixChapterFromAudits(novelId, selectedChapter);
      if (res.status === 'success') {
        const remain = res.reaudit ? `，重審殘留 ${res.reaudit.findings_count} 項觀察點` : '';
        showToast(`第 ${selectedChapter} 章已由 Editor 按診斷重寫（處置 ${res.fixed_count} 筆）${remain}`, 'success');
        if (res.reaudit) setLastAuditResult(res.reaudit);
        // 正文已被 Editor 重寫：同步通知敘事引擎刷新（和前端正文一致）
        emitChapterContentUpdated(novelId, 'audit-fix', selectedChapter);
      } else {
        showToast(`Editor 認為第 ${selectedChapter} 章無需改動（原文保留）`, 'warning');
      }
      onRefresh();
    } catch (err: any) {
      showToast(`Editor 修正失敗: ${err.message}`, 'danger');
    } finally {
      setIsFixingChapter(false);
    }
  };

  // Resolve audit item
  const handleResolve = async (auditId: string) => {
    setResolvingId(auditId);
    try {
      const ok = await resolveNarrativeAudit(auditId);
      if (ok) {
        showToast('已標記為已處置/已修復', 'success');
        onRefresh();
      }
    } catch (err: any) {
      showToast(`處置失敗: ${err.message}`, 'danger');
    } finally {
      setResolvingId(null);
    }
  };

  const filteredAudits = audits.filter((a) => {
    if (unresolvedOnly && (a.resolved === 1 || a.resolved === true)) return false;
    if (filterDimension !== 'all' && a.dimension !== filterDimension) return false;
    return true;
  });

  const getDimensionLabel = (dim: string) => {
    switch (dim) {
      case 'voice_integrity':
        return '語言/口癖/動作重複';
      case 'conflict_novelty':
        return '長程因果套路重複';
      case 'ability_constraints':
        return '超常能力邊界/代價缺失';
      case 'pacing_balance':
        return '節奏呼吸與沉澱';
      default:
        return dim;
    }
  };

  const getSeverityBadge = (sev: string) => {
    const s = (sev || '').toLowerCase();
    if (s === 'critical') return <Badge variant="danger" size="sm">CRITICAL 嚴重</Badge>;
    if (s === 'warning' || s === 'revise') return <Badge variant="warning" size="sm">WARNING 需修改</Badge>;
    if (s === 'watch') return <Badge variant="accent" size="sm">WATCH 觀察</Badge>;
    if (s === 'no_action_required') return <Badge variant="neutral" size="sm">安靜呼吸章</Badge>;
    return <Badge variant="neutral" size="sm">{sev.toUpperCase()}</Badge>;
  };

  return (
    <div className="narrative-tab-content">
      {/* 1. Quick Audit Launcher */}
      <div className="audit-launcher-bar">
        <div className="launcher-left">
          <IconSparkles size={18} className="text-accent" />
          <span className="launcher-label">總監 2.0 敘事推理診斷引擎：</span>
          <span className="launcher-hint">
            審查語言動作模板化、60章長程因果公式重複、能力無代價萬能解與節奏呼吸
          </span>
        </div>
        <div className="launcher-right">
          <label className="ch-select-label">
            目標章節:
            <input
              type="number"
              className="form-input ch-input-sm"
              value={selectedChapter}
              onChange={(e) => setSelectedChapter(Number(e.target.value))}
              min={1}
            />
          </label>
          <Button
            size="sm"
            variant="primary"
            onClick={handleRunAudit}
            isLoading={isRunningAudit}
            icon={<IconSparkles size={14} />}
          >
            執行單章敘事審計
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={handleFixChapter}
            isLoading={isFixingChapter}
            icon={<IconCheck size={14} />}
            title="把該章未處置診斷拼成編輯指示，呼叫 Editor 重寫正文並自動標記處置"
          >
            呼叫 Editor 依診斷修正
          </Button>
        </div>
      </div>

      {/* 2. Last Audit Run Result Card */}
      {lastAuditResult && (
        <div
          className={`last-audit-card audit-result-${lastAuditResult.overall_action.toLowerCase()}`}
        >
          <div className="result-header">
            <span className="result-title">
              第 {lastAuditResult.chapter_index} 章診斷結論：
              <strong> [{lastAuditResult.overall_action}]</strong>
            </span>
            <span className="result-summary">{lastAuditResult.summary}</span>
          </div>

          {lastAuditResult.is_breathing_scene && (
            <div className="breathing-badge-bar">
              <IconCheck size={14} /> 本章判定為「節奏呼吸/過渡章」，允許情節沉澱，不強制盲目爆發衝突。
            </div>
          )}

          {lastAuditResult.findings && lastAuditResult.findings.length > 0 && (
            <div className="findings-inline-list">
              {lastAuditResult.findings.map((f, idx) => (
                <div key={idx} className="finding-inline-item">
                  <div className="finding-top">
                    {getSeverityBadge(f.severity)}
                    <span className="finding-dim">{getDimensionLabel(f.dimension)}</span>
                  </div>
                  <p className="finding-ev"><strong>佐證:</strong> {f.evidence}</p>
                  <p className="finding-rec"><strong>建議:</strong> {f.recommendation}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 3. Toolbar & Filters */}
      <div className="narrative-toolbar">
        <div className="toolbar-left">
          <div className="tab-filters">
            <button
              type="button"
              className={`filter-chip ${!unresolvedOnly ? 'active' : ''}`}
              onClick={() => setUnresolvedOnly(false)}
            >
              全部紀錄 ({audits.length})
            </button>
            <button
              type="button"
              className={`filter-chip ${unresolvedOnly ? 'active' : ''}`}
              onClick={() => setUnresolvedOnly(true)}
            >
              待處置 ({audits.filter((a) => !a.resolved).length})
            </button>
          </div>

          <CustomSelect
            className="select-sm ml-2"
            value={filterDimension}
            onChange={(v) => setFilterDimension(v)}
            options={[
              { value: 'all', label: '所有維度', subLabel: 'All Dimensions' },
              { value: 'voice_integrity', label: '語言/口癖/動作重複' },
              { value: 'conflict_novelty', label: '長程因果套路重複' },
              { value: 'ability_constraints', label: '超常能力邊界與代價' },
              { value: 'pacing_balance', label: '節奏呼吸與沉澱' },
            ]}
          />
        </div>

        <div className="toolbar-right">
          <Button
            size="sm"
            variant="ghost"
            onClick={onRefresh}
            isLoading={isLoading}
            icon={<IconRefresh size={14} />}
          >
            重新載入
          </Button>
        </div>
      </div>

      {/* 4. Audits List */}
      {filteredAudits.length === 0 ? (
        <div className="empty-state-card">
          <IconCheck size={32} className="text-success" />
          <p className="empty-title">目前無任何待處置的敘事審計問題</p>
          <p className="empty-desc">
            您可以點擊上方「執行單章敘事審計」，總監將即時診斷該章文本之動作重複、長程因果同質化與能力代價。
          </p>
        </div>
      ) : (
        <div className="narrative-audits-list">
          {filteredAudits.map((audit) => {
            const isResolved = audit.resolved === 1 || audit.resolved === true;
            return (
              <div
                key={audit.id}
                className={`audit-item-card ${isResolved ? 'audit-resolved' : 'audit-active'}`}
              >
                <div className="audit-card-top">
                  <div className="audit-badges">
                    <span className="ch-pill">第 {audit.chapter_index} 章</span>
                    {getSeverityBadge(audit.severity)}
                    <span className="dim-tag">{getDimensionLabel(audit.dimension)}</span>
                    {Boolean(audit.action_required) && !isResolved && (
                      <Badge variant="danger" size="sm">需修訂</Badge>
                    )}
                  </div>

                  <div className="audit-actions">
                    {isResolved ? (
                      <span className="resolved-tag">
                        <IconCheck size={13} /> 已處置
                      </span>
                    ) : (
                      <Button
                        size="xs"
                        variant="secondary"
                        onClick={() => handleResolve(audit.id)}
                        isLoading={resolvingId === audit.id}
                        icon={<IconCheck size={12} />}
                      >
                        標記已處置
                      </Button>
                    )}
                  </div>
                </div>

                <div className="audit-card-body">
                  <div className="audit-ev-row">
                    <span className="audit-row-label">診斷佐證</span>
                    <p className="audit-row-content ev-text">{audit.evidence}</p>
                  </div>
                  <div className="audit-rec-row">
                    <span className="audit-row-label">改進指引</span>
                    <p className="audit-row-content rec-text">{audit.recommendation}</p>
                  </div>
                </div>

                {audit.created_at && (
                  <div className="audit-card-footer">
                    <span className="audit-time">
                      <IconClock size={11} /> 記錄於 {new Date(audit.created_at).toLocaleString()}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
