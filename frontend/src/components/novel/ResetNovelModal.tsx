import React, { useState, useEffect } from 'react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { IconCheck, IconTrash } from '../common/Icons';

interface ResetNovelModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void> | void;
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

  // Reset input when modal opens or target changes
  useEffect(() => {
    if (isOpen) {
      setInputTitle('');
    }
  }, [isOpen, novelTitle]);

  const target = (novelTitle || '').trim();
  const currentInput = inputTitle.trim();
  const isMatch = currentInput.length > 0 && currentInput === target;

  const handleFillTarget = () => {
    if (!isLoading) {
      setInputTitle(target);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && isMatch && !isLoading) {
      e.preventDefault();
      onConfirm();
    }
  };

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
            onClick={onConfirm}
            isLoading={isLoading}
            disabled={!isMatch || isLoading}
            className={`btn-reset-confirm ${isMatch && !isLoading ? 'is-danger-active' : ''}`}
          >
            {isLoading ? (
              '正在清空內容...'
            ) : isMatch ? (
              <>
                <IconTrash size={13} className="mr-1 inline-block" />
                <span>確認清空生成內容</span>
              </>
            ) : (
              '請輸入完整作品名稱確認'
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
            此操作將清空作品《<strong className="text-text-primary">{target}</strong>》所有已生成的資料，將小說徹底重置回最初創建時的空白狀態。
          </p>
        </div>

        {/* 2. Structured Comparison Grid: What will be cleared vs preserved */}
        <div className="reset-breakdown-grid">
          {/* Cleared items */}
          <div className="reset-breakdown-card cleared">
            <div className="reset-breakdown-header">
              <span className="status-dot danger" />
              <span>會清除的資料 (不可逆)</span>
            </div>
            <ul className="reset-breakdown-list">
              <li className="reset-breakdown-item">世界觀設定與力量體系</li>
              <li className="reset-breakdown-item">角色聖經與人物設定</li>
              <li className="reset-breakdown-item">全書伏筆網絡與暗線</li>
              <li className="reset-breakdown-item">核心重大關鍵轉折點</li>
              <li className="reset-breakdown-item">分卷規劃與章節骨架細綱</li>
              <li className="reset-breakdown-item">所有章節正文初稿與精修</li>
              <li className="reset-breakdown-item">逐章上下文記憶與摘要</li>
            </ul>
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
            </ul>
            <div className="reset-breakdown-note">
              保留了大綱靈感 (Pipeline Prompt)，重置後您隨時可按原始設定重新啟動全自動創作流水線。
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
                輸入完整名稱後，下方的確認按鈕才會解鎖。
              </span>
            ) : isMatch ? (
              <span className="text-xs text-success flex items-center gap-1 font-medium">
                <IconCheck size={13} />
                名稱驗證完全吻合，可點擊下方按鈕執行清空。
              </span>
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
