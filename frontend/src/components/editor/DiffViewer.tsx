import React, { useMemo } from 'react';
import { computeLineDiff } from '../../utils/diff';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { IconCheck, IconX, IconColumns } from '../common/Icons';

interface DiffViewerProps {
  originalText: string;
  proposedText: string;
  proposalId?: string;
  isApplying?: boolean;
  onApply?: () => void;
  onReject?: () => void;
  onBackToEditor?: () => void;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({
  originalText,
  proposedText,
  proposalId,
  isApplying = false,
  onApply,
  onReject,
  onBackToEditor,
}) => {
  const diff = useMemo(() => {
    return computeLineDiff(originalText, proposedText);
  }, [originalText, proposedText]);

  return (
    <div className="diff-viewer-wrapper">
      <div className="diff-header-bar">
        <div className="diff-header-left">
          <IconColumns size={16} className="text-accent" />
          <span className="diff-title">AI 修改建議與差異對比</span>
          <div className="diff-stat-badges">
            <Badge variant="success">+{diff.addedCount} 行</Badge>
            <Badge variant="danger">-{diff.removedCount} 行</Badge>
            <Badge variant="neutral">{diff.unchangedCount} 行未變</Badge>
          </div>
        </div>

        <div className="diff-header-right">
          {onBackToEditor && (
            <Button size="sm" variant="ghost" onClick={onBackToEditor}>
              返回編輯
            </Button>
          )}
          {onReject && (
            <Button
              size="sm"
              variant="danger"
              onClick={onReject}
              disabled={isApplying}
              icon={<IconX size={14} />}
            >
              放棄建議
            </Button>
          )}
          {onApply && (
            <Button
              size="sm"
              variant="primary"
              onClick={onApply}
              isLoading={isApplying}
              icon={<IconCheck size={14} />}
            >
              一鍵套用
            </Button>
          )}
        </div>
      </div>

      <div className="diff-container">
        {diff.addedCount === 0 && diff.removedCount === 0 && !proposalId && (
          <div
            className="diff-empty-banner"
            style={{
              padding: '12px 16px',
              backgroundColor: 'var(--color-surface-hover, rgba(255,255,255,0.03))',
              borderBottom: '1px solid var(--color-border)',
              fontSize: '13px',
              color: 'var(--color-text-muted)',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <span>💡 目前此章節尚無待審閱的 AI 修訂案。您可在右側總控室切換至【AI 審閱精修】，點擊「送出」後將在此自動呈現行級對比與一鍵套用。</span>
          </div>
        )}
        {diff.lines.length === 0 ? (
          <div className="diff-empty-state">無任何文字差異</div>
        ) : (
          diff.lines.map((line, idx) => {
            const lineClass =
              line.type === 'added'
                ? 'diff-line-added'
                : line.type === 'removed'
                ? 'diff-line-removed'
                : 'diff-line-unchanged';

            const prefix = line.type === 'added' ? '+ ' : line.type === 'removed' ? '- ' : '  ';

            return (
              <div key={idx} className={`diff-line ${lineClass}`}>
                <span className="diff-gutter">
                  {line.type === 'removed' ? line.originalLine : line.proposedLine || ''}
                </span>
                <span className="diff-prefix">{prefix}</span>
                <span className="diff-content">{line.text || ' '}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
