import React, { useState } from 'react';
import { DraftProposal } from '../../types';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';
import { IconSparkles, IconCheck, IconX, IconInfo } from '../common/Icons';

interface ProposalInboxProps {
  proposals: DraftProposal[];
  selectedProposalId?: string;
  onSelectProposal: (proposal: DraftProposal) => void;
  onApplyProposal: (proposalId: string) => void;
  onRejectProposal: (proposalId: string) => void;
}

export const ProposalInbox: React.FC<ProposalInboxProps> = ({
  proposals,
  selectedProposalId,
  onSelectProposal,
  onApplyProposal,
  onRejectProposal,
}) => {
  const [filter, setFilter] = useState<'all' | 'pending'>('pending');

  const filteredProposals = proposals.filter((p) => {
    if (filter === 'pending') return p.status === 'pending';
    return true;
  });

  return (
    <div className="proposal-inbox-container">
      <div className="proposal-inbox-header">
        <div className="inbox-title-wrapper">
          <IconSparkles size={16} className="text-accent" />
          <span className="inbox-title">草稿建議收件箱 ({proposals.length})</span>
        </div>
        <div className="inbox-filter-group">
          <button
            type="button"
            className={`topbar-pill-btn ${filter === 'pending' ? 'active' : ''}`}
            onClick={() => setFilter('pending')}
          >
            待審閱
          </button>
          <button
            type="button"
            className={`topbar-pill-btn ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            全部
          </button>
        </div>
      </div>

      <div className="proposal-list">
        {filteredProposals.length === 0 ? (
          <div className="inbox-empty-hint">
            <IconInfo size={20} className="text-muted" />
            <span>目前沒有{filter === 'pending' ? '待審閱的' : ''}草稿建議。</span>
            <span className="inbox-sub-hint">可在右側 AI 導演面板點擊「審閱優化」或生成新章節來產生建議。</span>
          </div>
        ) : (
          filteredProposals.map((prop) => {
            const isSelected = prop.id === selectedProposalId;
            const statusVariant =
              prop.status === 'accepted'
                ? 'success'
                : prop.status === 'rejected'
                ? 'danger'
                : 'accent';

            return (
              <div
                key={prop.id}
                className={`proposal-card ${isSelected ? 'selected' : ''}`}
                onClick={() => onSelectProposal(prop)}
              >
                <div className="proposal-card-header">
                  <div className="proposal-card-title">
                    <span>第 {prop.chapter_index} 章修訂案</span>
                    <Badge variant={statusVariant}>
                      {prop.status === 'pending'
                        ? '待審閱'
                        : prop.status === 'accepted'
                        ? '已套用'
                        : '已放棄'}
                    </Badge>
                  </div>
                  <span className="proposal-date">
                    {prop.created_at ? new Date(prop.created_at).toLocaleTimeString() : ''}
                  </span>
                </div>

                {prop.review_comments && prop.review_comments.length > 0 && (
                  <div className="proposal-comments-preview">
                    {prop.review_comments.map((rc, idx) => (
                      <div key={idx} className="comment-preview-item">
                        <span className="comment-type-tag">{rc.type}</span>
                        <span className="comment-text">{rc.comment}</span>
                      </div>
                    ))}
                  </div>
                )}

                <div className="proposal-snippet">
                  {prop.proposed_text.slice(0, 100)}...
                </div>

                <div className="proposal-card-actions" onClick={(e) => e.stopPropagation()}>
                  {prop.status === 'pending' && (
                    <>
                      <Button
                        size="xs"
                        variant="primary"
                        onClick={() => onApplyProposal(prop.id)}
                        icon={<IconCheck size={12} />}
                      >
                        套用
                      </Button>
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => onRejectProposal(prop.id)}
                        icon={<IconX size={12} />}
                      >
                        放棄
                      </Button>
                    </>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
