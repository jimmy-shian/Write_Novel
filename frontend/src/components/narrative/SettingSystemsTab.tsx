import React, { useState } from 'react';
import { SettingSystem } from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { StatusDot } from '../common/StatusDot';
import {
  IconPlus,
  IconRefresh,
  IconShield,
  IconCheck,
  IconEdit,
  IconX,
} from '../common/Icons';
import { upsertSettingSystem } from '../../api/narrative';
import { CustomSelect } from '../common/CustomSelect';
import { showToast } from '../common/Toast';

interface SettingSystemsTabProps {
  novelId: string;
  systems: SettingSystem[];
  isLoading: boolean;
  isSyncing: boolean;
  onRefresh: () => void;
  onSyncFromWorldview: () => void;
}

export const SettingSystemsTab: React.FC<SettingSystemsTabProps> = ({
  novelId,
  systems,
  isLoading,
  isSyncing,
  onRefresh,
  onSyncFromWorldview,
}) => {
  const [filterType, setFilterType] = useState<string>('all');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingSystem, setEditingSystem] = useState<Partial<SettingSystem> | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Form states
  const [formName, setFormName] = useState('');
  const [formType, setFormType] = useState('power_mechanism');
  const [formMechanism, setFormMechanism] = useState('');
  const [formCost, setFormCost] = useState('');
  const [formBoundary, setFormBoundary] = useState('');
  const [formFailureCondition, setFormFailureCondition] = useState('');
  const [formStakeholder, setFormStakeholder] = useState('');
  const [formThemeLink, setFormThemeLink] = useState('');
  const [formState, setFormState] = useState('active');

  const openCreateModal = () => {
    setEditingSystem(null);
    setFormName('');
    setFormType('power_mechanism');
    setFormMechanism('');
    setFormCost('');
    setFormBoundary('');
    setFormFailureCondition('');
    setFormStakeholder('');
    setFormThemeLink('');
    setFormState('active');
    setIsAddModalOpen(true);
  };

  const openEditModal = (sys: SettingSystem) => {
    setEditingSystem(sys);
    setFormName(sys.name);
    setFormType(sys.type);
    setFormMechanism(sys.mechanism);
    setFormCost(sys.cost || '');
    setFormBoundary(sys.boundary || '');
    setFormFailureCondition(sys.failure_condition || '');
    setFormStakeholder(sys.stakeholder || '');
    setFormThemeLink(sys.theme_link || '');
    setFormState(sys.current_state || 'active');
    setIsAddModalOpen(true);
  };

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim() || !formMechanism.trim()) {
      showToast('名稱與運作機制為必填項目', 'warning');
      return;
    }
    setIsSubmitting(true);
    try {
      await upsertSettingSystem(novelId, {
        name: formName.trim(),
        type: formType,
        mechanism: formMechanism.trim(),
        cost: formCost.trim() || undefined,
        boundary: formBoundary.trim() || undefined,
        failure_condition: formFailureCondition.trim() || undefined,
        stakeholder: formStakeholder.trim() || undefined,
        theme_link: formThemeLink.trim() || undefined,
        current_state: formState,
      });
      showToast(editingSystem ? '設定系統已更新' : '設定系統已登錄', 'success');
      setIsAddModalOpen(false);
      onRefresh();
    } catch (err: any) {
      showToast(`儲存失敗: ${err.message}`, 'danger');
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredSystems = systems.filter((s) => {
    if (filterType === 'all') return true;
    if (filterType === 'active') return s.current_state === 'active';
    return s.type === filterType;
  });

  return (
    <div className="narrative-tab-content">
      {/* Action Toolbar */}
      <div className="narrative-toolbar">
        <div className="toolbar-left">
          <div className="tab-filters">
            <button
              type="button"
              className={`filter-chip ${filterType === 'all' ? 'active' : ''}`}
              onClick={() => setFilterType('all')}
            >
              全部 ({systems.length})
            </button>
            <button
              type="button"
              className={`filter-chip ${filterType === 'active' ? 'active' : ''}`}
              onClick={() => setFilterType('active')}
            >
              運行中 ({systems.filter((s) => s.current_state === 'active').length})
            </button>
            <button
              type="button"
              className={`filter-chip ${filterType === 'power_mechanism' ? 'active' : ''}`}
              onClick={() => setFilterType('power_mechanism')}
            >
              力量體系
            </button>
            <button
              type="button"
              className={`filter-chip ${filterType === 'ecological_law' ? 'active' : ''}`}
              onClick={() => setFilterType('ecological_law')}
            >
              生態法則
            </button>
            <button
              type="button"
              className={`filter-chip ${filterType === 'political_institution' ? 'active' : ''}`}
              onClick={() => setFilterType('political_institution')}
            >
              體制制度
            </button>
          </div>
        </div>

        <div className="toolbar-right">
          <Button
            size="sm"
            variant="secondary"
            onClick={onSyncFromWorldview}
            isLoading={isSyncing}
            icon={<IconRefresh size={14} />}
            title="從現有世界觀自動提煉力量體系、世界規則與陣營制度並登錄為運作態"
          >
            從世界觀一鍵提煉同步
          </Button>

          <Button
            size="sm"
            variant="primary"
            onClick={openCreateModal}
            icon={<IconPlus size={14} />}
          >
            登錄設定系統
          </Button>
        </div>
      </div>

      {/* 3. Systems Grid / Card List */}
      {filteredSystems.length === 0 ? (
        <div className="empty-state-card">
          <IconShield size={32} className="text-muted" />
          <p className="empty-title">尚未登錄任何運作態設定系統</p>
          <p className="empty-desc">
            設定不是裝飾性名詞，而是故事中推動因果的約束律。您可以點擊「從世界觀一鍵提煉同步」，或手動新增力量體系與制度邊界。
          </p>
          <Button size="sm" variant="primary" onClick={onSyncFromWorldview} isLoading={isSyncing}>
            立即提煉世界觀設定
          </Button>
        </div>
      ) : (
        <div className="setting-systems-grid">
          {filteredSystems.map((sys) => (
            <div key={sys.id} className="setting-system-card">
              <div className="system-card-header">
                <div className="system-title-group">
                  <span className="system-name">{sys.name}</span>
                  <Badge variant={sys.type === 'power_mechanism' ? 'accent' : 'neutral'} size="sm">
                    {sys.type === 'power_mechanism'
                      ? '力量體系'
                      : sys.type === 'ecological_law'
                      ? '生態法則'
                      : sys.type === 'political_institution'
                      ? '體制制度'
                      : sys.type}
                  </Badge>
                  <span className={`status-pill pill-${sys.current_state}`}>
                    <StatusDot status={sys.current_state === 'active' ? 'success' : 'warning'} size="sm" />
                    {sys.current_state === 'active' ? '運行態' : sys.current_state}
                  </span>
                </div>
                <div className="system-card-actions">
                  <button
                    type="button"
                    className="btn-action-icon"
                    onClick={() => openEditModal(sys)}
                    title="編輯此設定系統"
                  >
                    <IconEdit size={14} />
                  </button>
                </div>
              </div>

              <div className="system-card-body">
                <div className="prop-row">
                  <span className="prop-label">運作機制</span>
                  <p className="prop-content mechanism-text">{sys.mechanism}</p>
                </div>

                {sys.cost && (
                  <div className="prop-row cost-row">
                    <span className="prop-label">使用代價</span>
                    <p className="prop-content">{sys.cost}</p>
                  </div>
                )}

                {sys.boundary && (
                  <div className="prop-row boundary-row">
                    <span className="prop-label">不可突破邊界</span>
                    <p className="prop-content">{sys.boundary}</p>
                  </div>
                )}

                {sys.failure_condition && (
                  <div className="prop-row failure-row">
                    <span className="prop-label">崩潰/反噬條件</span>
                    <p className="prop-content">{sys.failure_condition}</p>
                  </div>
                )}

                {sys.stakeholder && (
                  <div className="prop-row">
                    <span className="prop-label">利益與對抗陣營</span>
                    <p className="prop-content">{sys.stakeholder}</p>
                  </div>
                )}
              </div>

              <div className="system-card-footer">
                <span className="usage-stats">
                  已引用 <strong>{sys.usage_count}</strong> 次
                  {sys.last_used_chapter > 0 && ` · 最後出現第 ${sys.last_used_chapter} 章`}
                </span>
                {sys.theme_link && (
                  <span className="theme-tag marquee-on-hover" title={`主題關聯: ${sys.theme_link}`}>
                    主題: {sys.theme_link}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 4. Add / Edit Modal */}
      {isAddModalOpen && (
        <div className="modal-backdrop">
          <div className="modal-dialog modal-md">
            <div className="modal-header">
              <h3 className="modal-title">
                {editingSystem ? `編輯設定系統：${editingSystem.name}` : '登錄新設定系統 (Setting System)'}
              </h3>
              <button type="button" className="btn-close" onClick={() => setIsAddModalOpen(false)}>
                <IconX size={16} />
              </button>
            </div>
            <form onSubmit={handleFormSubmit}>
              <div className="modal-body form-grid">
                <div className="form-group">
                  <label className="form-label">設定名稱 *</label>
                  <input
                    type="text"
                    className="form-input"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="例：九階靈能共振律、天啟審判庭特權規條"
                    required
                  />
                </div>

                <div className="form-row-2">
                  <div className="form-group">
                    <label className="form-label">設定類型</label>
                    <CustomSelect
                      value={formType}
                      onChange={(v) => setFormType(v)}
                      options={[
                        { value: 'power_mechanism', label: '力量能階體系', subLabel: 'Power Mechanism' },
                        { value: 'ecological_law', label: '生態/物理因果法則', subLabel: 'Ecological Law' },
                        { value: 'political_institution', label: '體制/陣營統治律', subLabel: 'Political Institution' },
                        { value: 'social_rule', label: '社會民俗禁忌', subLabel: 'Social Rule' },
                        { value: 'generic', label: '一般通用設定', subLabel: 'Generic' },
                      ]}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">運行狀態</label>
                    <CustomSelect
                      value={formState}
                      onChange={(v) => setFormState(v)}
                      options={[
                        { value: 'active', label: '運行中', subLabel: 'Active' },
                        { value: 'evolving', label: '演變中', subLabel: 'Evolving' },
                        { value: 'deprecated', label: '已失效/歷史廢棄', subLabel: 'Deprecated' },
                      ]}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">運作機制 (Mechanism) *</label>
                  <textarea
                    className="form-textarea"
                    rows={3}
                    value={formMechanism}
                    onChange={(e) => setFormMechanism(e.target.value)}
                    placeholder="寫清該設定的運作原理與因果規律，如何影響客觀現實..."
                    required
                  />
                </div>

                <div className="form-row-2">
                  <div className="form-group">
                    <label className="form-label">使用代價 (Cost)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={formCost}
                      onChange={(e) => setFormCost(e.target.value)}
                      placeholder="動用此能力或維持體制所需付出的實質代價..."
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">不可突破邊界 (Boundary)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={formBoundary}
                      onChange={(e) => setFormBoundary(e.target.value)}
                      placeholder="絕對無法辦到的限制（杜絕萬能解）..."
                    />
                  </div>
                </div>

                <div className="form-row-2">
                  <div className="form-group">
                    <label className="form-label">崩潰/反噬條件 (Failure Condition)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={formFailureCondition}
                      onChange={(e) => setFormFailureCondition(e.target.value)}
                      placeholder="何種情況下設定會被破除或導致失控..."
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">利益相關與對抗者 (Stakeholder)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={formStakeholder}
                      onChange={(e) => setFormStakeholder(e.target.value)}
                      placeholder="既得利益者與受壓迫者..."
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">主題象徵連結 (Theme Link)</label>
                  <input
                    type="text"
                    className="form-input"
                    value={formThemeLink}
                    onChange={(e) => setFormThemeLink(e.target.value)}
                    placeholder="與小說核心主題的隱喻關聯..."
                  />
                </div>
              </div>

              <div className="modal-footer">
                <Button type="button" variant="ghost" onClick={() => setIsAddModalOpen(false)}>
                  取消
                </Button>
                <Button type="submit" variant="primary" isLoading={isSubmitting}>
                  {editingSystem ? '儲存更新' : '確認登錄'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
