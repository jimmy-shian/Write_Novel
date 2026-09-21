import React, { useState, useEffect } from 'react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { IconCheck, IconTrash } from '../common/Icons';

export interface ResetScopeOption {
  key: string;
  title: string;
  desc: string;
}

export const RESET_SCOPE_OPTIONS: ResetScopeOption[] = [
  { key: 'worldbuilding', title: '世界觀設定與力量體系', desc: '世界觀、轉折點、伏筆種子（含伏筆藍圖）' },
  { key: 'characters', title: '角色聖經與人物設定', desc: '全部人物卡' },
  { key: 'plot', title: '分卷規劃與章節骨架細綱', desc: '分卷 + 章綱（含連動清除幾何拓撲樹）' },
  { key: 'chapters', title: '所有章節正文初稿與精修', desc: '已生成的正文內容（含連動清除時序圖譜、幾何拓撲、草稿提案、自動術語與敘事引擎簽名/審計，手動術語保留）' },
  { key: 'chat', title: '對話記憶與流水線狀態', desc: '對話紀錄、導演指令、上下文記憶' },
];

interface ResetNovelModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (scopes: string[]) => Promise<void> | void;
  novelTitle: string;
  isLoading?: boolean;
}

export const ResetNovelModal: React.FC<ResetNovelModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  novelTitle,
  isLoading = false,
}) => {
  const [inputTitle, setInputTitle] = useState('');
  const [selected, setSelected] = useState<string[]>(RESET_SCOPE_OPTIONS.map((o) => o.key));

  // Reset input + selection when modal opens or target changes
  useEffect(() => {
    if (isOpen) {
      setInputTitle('');
      setSelected(RESET_SCOPE_OPTIONS.map((o) => o.key));
    }
  }, [isOpen, novelTitle]);

  const target = (novelTitle || '').trim();
  const currentInput = inputTitle.trim();
  const isMatch = currentInput.length > 0 && currentInput === target;
  const hasSelection = selected.length > 0;
  const canConfirm = isMatch && hasSelection && !isLoading;

  const toggleScope = (key: string) => {
    if (isLoading) return;
    setSelected((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  const handleSelectAll = () => {
    if (!isLoading) setSelected(RESET_SCOPE_OPTIONS.map((o) => o.key));
  };

  const handleClearAll = () => {
    if (!isLoading) setSelected([]);
  };

  const handleConfirm = () => {
    if (canConfirm) {
      onConfirm(selected);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && canConfirm) {
      e.preventDefault();
      handleConfirm();
    }
  };

  const handleFillTarget = () => {
    if (!isLoading) {
      setInputTitle(target);
    }
  };

  const confirmLabel = isLoading
    ? `正在清空所選 ${selected.length} 項...`
    : !hasSelection
      ? '請先勾選至少一個清除項目'
      : isMatch
        ? `確認清空所選 ${selected.length} 項`
        : '請輸入完整作品名稱確認';

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!isLoading) onClose();
      }}
      title="清空小說生成內容"
      maxWidth="md"
      closeOnOverlayClick={!isLoading}
      footer={
        <div className="modal-footer-actions flex items-center justify-end gap-2 w-full">
          <Button
            variant="ghost"
            onClick={onClose}
            disabled={isLoading}
          >
            取消
          </Button>
          <Button
            variant="danger"
            onClick={handleConfirm}
            isLoading={isLoading}
            disabled={!canConfirm}
            className={`btn-reset-confirm ${canConfirm ? 'is-danger-active' : ''}`}
          >
            {isLoading || (isMatch && hasSelection) ? (
              <>
                {!isLoading && hasSelection && <IconTrash size={13} className="mr-1 inline-block" />}
                <span>{confirmLabel}</span>
              </>
            ) : (
              confirmLabel
            )}
          </Button>
        </div>
      }
    >
      <div className="reset-modal-content">
        {/* 1. Danger Alert Banner */}
        <div className="reset-alert-banner">
          <div className="reset-alert-title">
            <span className="reset-alert-tag">[無法復原]</span>
            <span>危險操作警示</span>
          </div>
          <p className="reset-alert-desc">
            此操作將清空作品《<strong className="text-text-primary">{target}</strong>》勾選的生成資料
           （已選 <strong className="text-text-primary">{selected.length}</strong> / {RESET_SCOPE_OPTIONS.length} 項），未勾選的項目會完整保留。
          </p>
        </div>

        {/* 2. Selectable scopes + preserved settings */}
        <div className="reset-breakdown-grid">
          {/* Selectable items */}
          <div className="reset-breakdown-card cleared">
            <div className="reset-breakdown-header">
              <span className="status-dot danger" />
              <span>選擇清除範圍 (可勾選)</span>
            </div>
            <div className="reset-select-actions">
              <button type="button" className="reset-link-btn" onClick={handleSelectAll} disabled={isLoading}>
                全選
              </button>
              <span className="reset-link-sep">|</span>
              <button type="button" className="reset-link-btn" onClick={handleClearAll} disabled={isLoading}>
                全不選
              </button>
              <span className="reset-select-count">已選 {selected.length} 項</span>
            </div>
            <div className="reset-scope-list" role="group" aria-label="選擇要清空的資料範圍">
              {RESET_SCOPE_OPTIONS.map((opt) => {
                const checked = selected.includes(opt.key);
                return (
                  <label
                    key={opt.key}
                    className={`reset-scope-item ${checked ? 'is-checked' : 'is-unchecked'} ${isLoading ? 'is-disabled' : ''}`}
                  >
                    <input
                      type="checkbox"
                      className="reset-scope-checkbox"
                      checked={checked}
                      disabled={isLoading}
                      onChange={() => toggleScope(opt.key)}
                    />
                    <span className="reset-scope-text">
                      <span className="reset-scope-title">{opt.title}</span>
                      <span className="reset-scope-desc">{opt.desc}</span>
                    </span>
                  </label>
                );
              })}
            </div>
            {!hasSelection && (
              <div className="reset-breakdown-note text-danger">
                至少需要勾選一個項目才能執行清空。
              </div>
            )}
          </div>

          {/* Preserved items */}
          <div className="reset-breakdown-card preserved">
            <div className="reset-breakdown-header">
              <span className="status-dot success" />
              <span>會完整保留的設定</span>
            </div>
            <ul className="reset-breakdown-list">
              <li className="reset-breakdown-item">作品名稱與標題</li>
              <li className="reset-breakdown-item">題材類型與寫作風格</li>
              <li className="reset-breakdown-item">故事簡述 / 大綱靈感</li>
              <li className="reset-breakdown-item">上方未勾選的生成資料</li>
            </ul>
            <div className="reset-breakdown-note">
              保留了大綱靈感 (Pipeline Prompt)，清空後您隨時可按原始設定重新啟動全自動創作流水線。
            </div>
          </div>
        </div>

        {/* 3. Dedicated Verification Input Box */}
        <div className="reset-verification-box">
          <div className="reset-verify-label-row">
            <label htmlFor="reset-novel-title-input" className="reset-verify-label">
              安全確認：請輸入作品完整名稱
            </label>
            <button
              type="button"
              className="reset-target-badge"
              onClick={handleFillTarget}
              title="點擊直接代入作品完整名稱"
            >
              <span>《{target}》</span>
              <span className="reset-target-copy-hint">點擊代入</span>
            </button>
          </div>

          <input
            id="reset-novel-title-input"
            type="text"
            className={`reset-input-field ${isMatch ? 'is-match' : ''}`}
            value={inputTitle}
            onChange={(e) => setInputTitle(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`請輸入「${target}」`}
            autoFocus
            disabled={isLoading}
            autoComplete="off"
            spellCheck={false}
          />

          <div className="reset-feedback-row">
            {!currentInput ? (
              <span className="text-xs text-text-muted">
                勾選清除範圍並輸入完整名稱後，確認按鈕才會解鎖。
              </span>
            ) : isMatch ? (
              hasSelection ? (
                <span className="text-xs text-success flex items-center gap-1 font-medium">
                  <IconCheck size={13} />
                  名稱驗證完全吻合，可點擊下方按鈕執行清空。
                </span>
              ) : (
                <span className="text-xs text-danger">
                  名稱已吻合，但請先勾選至少一個清除項目。
                </span>
              )
            ) : (
              <span className="text-xs text-text-muted">
                名稱尚未吻合 ({currentInput.length} / {target.length} 字)
              </span>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
};
