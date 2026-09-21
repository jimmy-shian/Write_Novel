import React, { useState } from 'react';
import { ConflictSignature, ConflictRepetitionDiagnosis } from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import {
  IconPlus,
  IconRefresh,
  IconAlertTriangle,
  IconCheck,
  IconCompass,
  IconSparkles,
  IconX,
} from '../common/Icons';
import { addConflictSignature, checkConflictRepetition } from '../../api/narrative';
import { CustomSelect } from '../common/CustomSelect';
import { showToast } from '../common/Toast';

interface ConflictSignaturesTabProps {
  novelId: string;
  signatures: ConflictSignature[];
  isLoading: boolean;
  onRefresh: () => void;
}

export const ConflictSignaturesTab: React.FC<ConflictSignaturesTabProps> = ({
  novelId,
  signatures,
  isLoading,
  onRefresh,
}) => {
  // Sandbox form states
  const [sandboxPressure, setSandboxPressure] = useState('');
  const [sandboxStrategy, setSandboxStrategy] = useState('play_dumb_or_weak');
  const [sandboxOutcome, setSandboxOutcome] = useState('public_shock');
  const [sandboxCost, setSandboxCost] = useState('無');
  const [sandboxPower, setSandboxPower] = useState('');
  const [isDiagnosing, setIsDiagnosing] = useState(false);
  const [diagnosisResult, setDiagnosisResult] = useState<ConflictRepetitionDiagnosis | null>(null);

  // Add signature modal states
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [modalChStart, setModalChStart] = useState<number>(1);
  const [modalChEnd, setModalChEnd] = useState<number>(1);
  const [modalInitiator, setModalInitiator] = useState('');
  const [modalPressure, setModalPressure] = useState('');
  const [modalStrategy, setModalStrategy] = useState('');
  const [modalPower, setModalPower] = useState('');
  const [modalOutcome, setModalOutcome] = useState('');
  const [modalCost, setModalCost] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Run anti-repetition check in sandbox
  const handleCheckRepetition = async () => {
    if (!sandboxPressure.trim()) {
      showToast('請輸入測試的施壓手段', 'warning');
      return;
    }
    setIsDiagnosing(true);
    try {
      const diag = await checkConflictRepetition(novelId, {
        pressure_type: sandboxPressure.trim(),
        protagonist_strategy: sandboxStrategy,
        outcome: sandboxOutcome,
        cost: sandboxCost.trim() || '無',
        power_used: sandboxPower.trim() || undefined,
      });
      setDiagnosisResult(diag);
      if (diag.has_repetition) {
        showToast(`偵測到長程因果重複！相似度 ${(diag.max_similarity * 100).toFixed(0)}%`, 'warning');
      } else {
        showToast('因果模式新穎，未檢測到套路同質化！', 'success');
      }
    } catch (err: any) {
      showToast(`檢驗失敗: ${err.message}`, 'danger');
    } finally {
      setIsDiagnosing(false);
    }
  };

  // Add directly from sandbox to ledger
  const handleAddFromSandbox = async () => {
    if (!sandboxPressure.trim() || !sandboxStrategy.trim()) {
      showToast('施壓手段與解題策略為必填', 'warning');
      return;
    }
    setIsSubmitting(true);
    try {
      await addConflictSignature(novelId, {
        chapter_start: signatures.length + 1,
        chapter_end: signatures.length + 1,
        pressure_type: sandboxPressure.trim(),
        protagonist_strategy: sandboxStrategy,
        outcome: sandboxOutcome,
        cost: sandboxCost.trim() || '無',
        power_used: sandboxPower.trim() || undefined,
      });
      showToast('因果特徵已登記至長程帳本', 'success');
      onRefresh();
    } catch (err: any) {
      showToast(`登記失敗: ${err.message}`, 'danger');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle modal submit
  const handleModalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!modalPressure.trim() || !modalStrategy.trim()) {
      showToast('施壓手段與解題策略為必填項目', 'warning');
      return;
    }
    setIsSubmitting(true);
    try {
      await addConflictSignature(novelId, {
        chapter_start: modalChStart,
        chapter_end: modalChEnd || modalChStart,
        initiator: modalInitiator.trim() || undefined,
        pressure_type: modalPressure.trim(),
        protagonist_strategy: modalStrategy.trim(),
        power_used: modalPower.trim() || undefined,
        outcome: modalOutcome.trim() || '解決',
        cost: modalCost.trim() || undefined,
      });
      showToast('因果特徵簽名已成功登記', 'success');
      setIsAddModalOpen(false);
      onRefresh();
    } catch (err: any) {
      showToast(`登記失敗: ${err.message}`, 'danger');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="narrative-tab-content">
      {/* 1. Sandbox: Anti-Repetition Guard */}
      <div className="sandbox-panel">
        <div className="sandbox-header">
          <div className="sandbox-title-group">
            <IconCompass size={18} className="text-accent" />
            <div className="sandbox-title-texts">
              <span className="sandbox-title">長程去套路化線上檢驗沙盒 (Conflict Novelty Guard)</span>
              <span className="sandbox-subtitle">
                在過去 60 章窗口內比對因果模式（壓迫方式 25% · 主角策略 35% · 結局 15% · 代價 10% · 破局機制 15%）
              </span>
            </div>
          </div>
          <Button
            size="sm"
            variant="primary"
            onClick={handleCheckRepetition}
            isLoading={isDiagnosing}
            icon={<IconSparkles size={14} />}
          >
            檢驗因果重複性
          </Button>
        </div>

        <div className="sandbox-form-grid">
          <div className="form-group">
            <label className="form-label">施壓手段 (Pressure Type)</label>
            <input
              type="text"
              className="form-input"
              value={sandboxPressure}
              onChange={(e) => setSandboxPressure(e.target.value)}
              placeholder="例：階層特權壓迫、宗門資源斷供、情報洩露遭圍捕"
            />
          </div>

          <div className="form-group">
            <label className="form-label">主角解題策略 (Protagonist Strategy)</label>
            <CustomSelect
              value={sandboxStrategy}
              onChange={(v) => setSandboxStrategy(v)}
              options={[
                { value: 'play_dumb_or_weak', label: '裝傻示弱 / 扮豬吃虎', subLabel: 'play_dumb_or_weak' },
                { value: 'rules_loophole', label: '體制規則漏洞反訴', subLabel: 'rules_loophole' },
                { value: 'asymmetric_wit', label: '非對稱情報智鬥', subLabel: 'asymmetric_wit' },
                { value: 'direct_clash', label: '正統實力硬撼亮劍', subLabel: 'direct_clash' },
                { value: 'faction_alliance', label: '合縱連橫利益博弈', subLabel: 'faction_alliance' },
                { value: 'strategic_retreat', label: '戰略隱忍與斷尾求生', subLabel: 'strategic_retreat' },
              ]}
            />
          </div>

          <div className="form-group">
            <label className="form-label">破局結局 (Outcome)</label>
            <CustomSelect
              value={sandboxOutcome}
              onChange={(v) => setSandboxOutcome(v)}
              options={[
                { value: 'public_shock', label: '全場震驚打臉', subLabel: 'public_shock' },
                { value: 'covert_settlement', label: '暗中合解與利益重組', subLabel: 'covert_settlement' },
                { value: 'institutional_reform', label: '逼迫體制妥協讓步', subLabel: 'institutional_reform' },
                { value: 'pyrrhic_victory', label: '慘勝但留存種子', subLabel: 'pyrrhic_victory' },
                { value: 'truth_exposed', label: '終極真相揭露', subLabel: 'truth_exposed' },
              ]}
            />
          </div>

          <div className="form-group">
            <label className="form-label">所付代價 (Cost)</label>
            <input
              type="text"
              className="form-input"
              value={sandboxCost}
              onChange={(e) => setSandboxCost(e.target.value)}
              placeholder="例：無 (零代價反殺) / 暴露一處安全屋 / 消耗底牌"
            />
          </div>
        </div>

        {/* Diagnosis Results Display */}
        {diagnosisResult && (
          <div
            className={`sandbox-diagnosis-result ${
              diagnosisResult.has_repetition ? 'diag-warning' : 'diag-success'
            }`}
          >
            <div className="diag-header">
              <span className="diag-status-badge">
                {diagnosisResult.has_repetition ? (
                  <>
                    <IconAlertTriangle size={14} /> [WARNING] 偵測到高度套路同質化 (相似度{' '}
                    {(diagnosisResult.max_similarity * 100).toFixed(0)}%)
                  </>
                ) : (
                  <>
                    <IconCheck size={14} /> [PASS] 因果結構新穎，未重複既有模式
                  </>
                )}
              </span>

              {diagnosisResult.has_repetition && (
                <span className="diag-action-tip">
                  建議：避開公式化「挑釁-裝傻-金手指-震驚」，嘗試體制博弈或付出情報代價。
                </span>
              )}
            </div>

            {diagnosisResult.matches && diagnosisResult.matches.length > 0 && (
              <div className="diag-matches-list">
                {diagnosisResult.matches.map((m, idx) => (
                  <div key={idx} className="diag-match-item">
                    <span className="match-range">{m.prior_chapter_range}</span>
                    <span className="match-sim">相似度: {(m.similarity * 100).toFixed(0)}%</span>
                    <div className="match-reasons">
                      {m.reasons.map((r, rIdx) => (
                        <span key={rIdx} className="match-reason-tag">
                          {r}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 2. Ledger Action Toolbar */}
      <div className="narrative-toolbar">
        <div className="toolbar-left">
          <span className="section-title">全書衝突因果簽名帳本 ({signatures.length} 筆已登記)</span>
        </div>
        <div className="toolbar-right">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setIsAddModalOpen(true)}
            icon={<IconPlus size={14} />}
          >
            手動登記因果簽名
          </Button>
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

      {/* 3. Signatures Timeline / Cards */}
      {signatures.length === 0 ? (
        <div className="empty-state-card">
          <IconCompass size={32} className="text-muted" />
          <p className="empty-title">尚未登記任何衝突因果簽名</p>
          <p className="empty-desc">
            每章寫作後，系統會自動提煉或手動登記衝突因果公式，用於在 400~500 章長程寫作中防止相同情節重複。
          </p>
        </div>
      ) : (
        <div className="signatures-timeline">
          {signatures.map((sig) => (
            <div key={sig.id} className="signature-timeline-card">
              <div className="sig-card-header">
                <div className="sig-chapter-badge">
                  第 {sig.chapter_start}
                  {sig.chapter_end !== sig.chapter_start && `-${sig.chapter_end}`} 章
                </div>
                {sig.initiator && <span className="sig-initiator">發起者: {sig.initiator}</span>}
                {sig.signature_hash && (
                  <span className="sig-hash-tag" title="因果模式特徵雜湊">
                    #{sig.signature_hash}
                  </span>
                )}
              </div>

              <div className="sig-card-flow">
                <div className="flow-step">
                  <span className="step-label">施壓手段</span>
                  <span className="step-val">{sig.pressure_type}</span>
                </div>
                <div className="flow-arrow">→</div>
                <div className="flow-step">
                  <span className="step-label">主角策略</span>
                  <span className="step-val strategy-val">{sig.protagonist_strategy}</span>
                </div>
                <div className="flow-arrow">→</div>
                <div className="flow-step">
                  <span className="step-label">破局結局</span>
                  <span className="step-val outcome-val">{sig.outcome}</span>
                </div>
              </div>

              <div className="sig-card-meta">
                {sig.power_used && (
                  <span className="meta-item">
                    <strong>動用力量:</strong> {sig.power_used}
                  </span>
                )}
                <span className="meta-item">
                  <strong>實質代價:</strong>{' '}
                  <span className={!sig.cost || sig.cost === '無' ? 'text-warning' : 'text-success'}>
                    {sig.cost || '零代價'}
                  </span>
                </span>
                {sig.emotional_effect && (
                  <span className="meta-item">
                    <strong>情緒反饋:</strong> {sig.emotional_effect}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 4. Add Signature Modal */}
      {isAddModalOpen && (
        <div className="modal-backdrop">
          <div className="modal-dialog modal-md">
            <div className="modal-header">
              <h3 className="modal-title">手動登記衝突因果簽名</h3>
              <button type="button" className="btn-close" onClick={() => setIsAddModalOpen(false)}>
                <IconX size={16} />
              </button>
            </div>
            <form onSubmit={handleModalSubmit}>
              <div className="modal-body form-grid">
                <div className="form-row-2">
                  <div className="form-group">
                    <label className="form-label">起始章節 *</label>
                    <input
                      type="number"
                      className="form-input"
                      value={modalChStart}
                      onChange={(e) => setModalChStart(Number(e.target.value))}
                      min={1}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">結束章節</label>
                    <input
                      type="number"
                      className="form-input"
                      value={modalChEnd}
                      onChange={(e) => setModalChEnd(Number(e.target.value))}
                      min={1}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">衝突發起者 (Initiator)</label>
                  <input
                    type="text"
                    className="form-input"
                    value={modalInitiator}
                    onChange={(e) => setModalInitiator(e.target.value)}
                    placeholder="例：巡城司統領、黑市拍賣行長老"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">施壓手段 (Pressure Type) *</label>
                  <input
                    type="text"
                    className="form-input"
                    value={modalPressure}
                    onChange={(e) => setModalPressure(e.target.value)}
                    placeholder="例：特權打壓、公然污衊、扣留親友"
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">主角解題策略 (Protagonist Strategy) *</label>
                  <input
                    type="text"
                    className="form-input"
                    value={modalStrategy}
                    onChange={(e) => setModalStrategy(e.target.value)}
                    placeholder="例：裝傻示弱、法規反殺、利益同盟、以力破巧"
                    required
                  />
                </div>

                <div className="form-row-2">
                  <div className="form-group">
                    <label className="form-label">破局結局 (Outcome) *</label>
                    <input
                      type="text"
                      className="form-input"
                      value={modalOutcome}
                      onChange={(e) => setModalOutcome(e.target.value)}
                      placeholder="例：敵方震驚退散、被迫達成秘密協議"
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">付出的實質代價 (Cost)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={modalCost}
                      onChange={(e) => setModalCost(e.target.value)}
                      placeholder="例：底牌暴露、法寶損毀、背負神魂契約"
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">動用力量或暗藏機制</label>
                  <input
                    type="text"
                    className="form-input"
                    value={modalPower}
                    onChange={(e) => setModalPower(e.target.value)}
                    placeholder="例：遠古古碑殘頁、暗影潛行法"
                  />
                </div>
              </div>

              <div className="modal-footer">
                <Button type="button" variant="ghost" onClick={() => setIsAddModalOpen(false)}>
                  取消
                </Button>
                <Button type="submit" variant="primary" isLoading={isSubmitting}>
                  登記簽名
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
