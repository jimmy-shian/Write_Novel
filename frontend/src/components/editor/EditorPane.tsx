import React from 'react';
import { CopyCard } from '../common/CopyCard';
import { Button } from '../common/Button';
import { IconCopy, IconCheck } from '../common/Icons';
import { copyToClipboard } from '../../utils/clipboard';

interface EditorPaneProps {
  content: string;
  chapterIndex: number;
  isDirty: boolean;
  isSaving: boolean;
  fontSize?: number;
  onFontSizeChange?: (size: number) => void;
  onChangeContent: (text: string) => void;
  onSave: () => void;
}

export const EditorPane: React.FC<EditorPaneProps> = ({
  content,
  chapterIndex,
  isDirty,
  isSaving,
  fontSize = 16,
  onFontSizeChange,
  onChangeContent,
  onSave,
}) => {
  const [copied, setCopied] = React.useState(false);

  const wordCount = content ? content.length : 0;
  const lineCount = content ? content.split('\n').length : 0;

  const handleCopy = async () => {
    const ok = await copyToClipboard(content);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Ctrl+S or Cmd+S to save
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      onSave();
    }
  };

  return (
    <div className="editor-canvas-container">
      <div className="editor-toolbar">
        <div className="editor-toolbar-left">
          <span className="editor-chapter-tag">第 {chapterIndex} 章正文</span>
          <Button
            size="xs"
            variant="ghost"
            onClick={handleCopy}
            title="複製正文"
            icon={copied ? <IconCheck size={12} className="text-success" /> : <IconCopy size={12} />}
          >
            {copied ? '已複製' : '一鍵複製'}
          </Button>
        </div>

        <div className="editor-toolbar-right">
          {onFontSizeChange && (
            <div className="font-size-stepper" title="調整中間編輯區文字大小">
              <button
                type="button"
                className="stepper-btn"
                onClick={() => onFontSizeChange(Math.max(14, fontSize - 1))}
                disabled={fontSize <= 14}
                title="縮小文字 (A-)"
              >
                A-
              </button>
              <span className="stepper-val">{fontSize}px</span>
              <button
                type="button"
                className="stepper-btn"
                onClick={() => onFontSizeChange(Math.min(24, fontSize + 1))}
                disabled={fontSize >= 24}
                title="放大文字 (A+)"
              >
                A+
              </button>
            </div>
          )}
          <span className="stat-separator">·</span>
          <span className="stat-item">{wordCount} 字</span>
          <span className="stat-separator">·</span>
          <span className="stat-item">{lineCount} 行</span>
          {isDirty && <span className="stat-dirty-badge">未儲存 (Ctrl+S)</span>}
        </div>
      </div>

      <textarea
        className="editor-textarea"
        style={{ fontSize: `${fontSize}px` }}
        placeholder="在此開始手動創作，或透過右側 AI 導演協助生成章節段落..."
        value={content}
        onChange={(e) => onChangeContent(e.target.value)}
        onKeyDown={handleKeyDown}
        spellCheck={false}
      />
    </div>
  );
};
