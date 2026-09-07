import React, { useState } from 'react';
import { TemporalGraphSlice, TemporalFact, TemporalEntity } from '../../types';
import { StatusDot } from '../common/StatusDot';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';
import {
  IconGitBranch,
  IconPlus,
  IconRefresh,
  IconClock,
  IconAlertTriangle,
  IconTrash,
  IconUser,
  IconTag,
} from '../common/Icons';

interface TemporalGraphBoardProps {
  graphSlice: TemporalGraphSlice | null;
  chapterIndex: number;
  chapterContent: string;
  isLoading: boolean;
  isExtracting: boolean;
  onRefresh: () => void;
  onAddFact: (statement: string) => void;
  onInvalidateFact: (factId: string, supersededBy?: string) => void;
  onDeleteFact: (factId: string) => void;
  onExtractFromChapter: (content: string) => void;
}

export const TemporalGraphBoard: React.FC<TemporalGraphBoardProps> = ({
  graphSlice,
  chapterIndex,
  chapterContent,
  isLoading,
  isExtracting,
  onRefresh,
  onAddFact,
  onInvalidateFact,
  onDeleteFact,
  onExtractFromChapter,
}) => {
  const [newStatement, setNewStatement] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [filterActiveOnly, setFilterActiveOnly] = useState(true);

  const facts = graphSlice?.facts || [];
  const entities = graphSlice?.entities || [];

  const filteredFacts = filterActiveOnly ? facts.filter((f) => f.is_active) : facts;

  const handleAddFactSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newStatement.trim()) return;
    onAddFact(newStatement.trim());
    setNewStatement('');
    setShowAddForm(false);
  };

  return (
    <div className="temporal-graph-board">
      <div className="graph-board-header">
        <div className="graph-board-title-group">
          <IconGitBranch size={18} className="text-accent" />
          <div className="graph-title-texts">
            <span className="graph-board-title">時序動態記憶圖譜 (Graphiti)</span>
            <span className="graph-board-subtitle">
              第 {chapterIndex} 章時間切片 — 動態追蹤實體狀態變更與事實失效歷程
            </span>
          </div>
        </div>

        <div className="graph-board-actions">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onExtractFromChapter(chapterContent)}
            isLoading={isExtracting}
            disabled={!chapterContent.trim()}
            icon={<IconRefresh size={14} />}
            title="以 AI 分析當前章節正文並自動提取實體與時序事實"
          >
            本章事實自動提取
          </Button>

          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowAddForm(!showAddForm)}
            icon={<IconPlus size={14} />}
          >
            手動新增事實
          </Button>

          <Button
            size="sm"
            variant="ghost"
            onClick={onRefresh}
            isLoading={isLoading}
            icon={<IconRefresh size={14} />}
          >
            重新整理
          </Button>
        </div>
      </div>

      {showAddForm && (
        <form className="add-fact-inline-form" onSubmit={handleAddFactSubmit}>
          <div className="form-group">
            <label className="form-label">輸入時序事實陳述 (Valid from Ch.{chapterIndex})</label>
            <input
              type="text"
              className="form-input"
              placeholder="例如：林霄在天斷崖突破至築基中期，獲得了玄火令"
              value={newStatement}
              onChange={(e) => setNewStatement(e.target.value)}
              autoFocus
            />
          </div>
          <div className="inline-card-buttons">
            <Button size="xs" variant="primary" type="submit">
              儲存事實
            </Button>
            <Button size="xs" variant="ghost" type="button" onClick={() => setShowAddForm(false)}>
              取消
            </Button>
          </div>
        </form>
      )}

      <div className="graph-board-body">
        {/* Left column: Facts List */}
        <div className="graph-facts-pane">
          <div className="pane-sub-header">
            <div className="pane-sub-title">
              <span>時序事實命題 ({filteredFacts.length})</span>
              <div className="filter-pill-toggle">
                <button
                  type="button"
                  className={`pill-btn ${filterActiveOnly ? 'active' : ''}`}
                  onClick={() => setFilterActiveOnly(true)}
                >
                  當前有效
                </button>
                <button
                  type="button"
                  className={`pill-btn ${!filterActiveOnly ? 'active' : ''}`}
                  onClick={() => setFilterActiveOnly(false)}
                >
                  包含已作廢
                </button>
              </div>
            </div>
          </div>

          <div className="facts-scroll-list">
            {filteredFacts.length === 0 ? (
              <div className="facts-empty-hint">
                <IconClock size={20} className="text-muted" />
                <span>此切片目前無時序事實記錄。點擊右上角「本章事實自動提取」開始建立。</span>
              </div>
            ) : (
              filteredFacts.map((fact) => (
                <div
                  key={fact.id}
                  className={`fact-card ${fact.is_active ? 'active-fact' : 'invalid-fact'}`}
                >
                  <div className="fact-card-header">
                    <div className="fact-status-meta">
                      <StatusDot status={fact.is_active ? 'success' : 'neutral'} />
                      <span className="fact-valid-range">
                        第 {fact.valid_from_chapter} 章
                        {fact.invalid_from_chapter ? ` ~ 第 ${fact.invalid_from_chapter} 章` : '起有效'}
                      </span>
                    </div>

                    <div className="fact-actions">
                      {fact.is_active ? (
                        <Button
                          size="xs"
                          variant="ghost"
                          onClick={() => {
                            const reason = window.prompt('請輸入此事實作廢原因或被何者取代：');
                            if (reason !== null) {
                              onInvalidateFact(fact.id, reason || undefined);
                            }
                          }}
                          title="在當前章節將此事實作廢"
                        >
                          作廢
                        </Button>
                      ) : (
                        <Badge variant="neutral">已作廢</Badge>
                      )}
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs text-muted"
                        onClick={() => onDeleteFact(fact.id)}
                        title="永久刪除"
                      >
                        <IconTrash size={12} />
                      </button>
                    </div>
                  </div>

                  <div className="fact-statement-text">{fact.fact_statement}</div>

                  {fact.superseded_by && (
                    <div className="fact-superseded-hint">
                      <IconAlertTriangle size={12} className="text-warning" />
                      <span>取代資訊：{fact.superseded_by}</span>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right column: Entities Panel */}
        <div className="graph-entities-pane">
          <div className="pane-sub-header">
            <div className="pane-sub-title">
              <span>實體索引庫 ({entities.length})</span>
            </div>
          </div>

          <div className="entities-scroll-list">
            {entities.length === 0 ? (
              <div className="entities-empty-hint">尚未登錄實體</div>
            ) : (
              entities.map((ent) => (
                <div key={ent.id} className="entity-card">
                  <div className="entity-card-header">
                    <div className="entity-name-wrapper">
                      <IconUser size={13} className="text-accent" />
                      <span className="entity-name">{ent.name}</span>
                    </div>
                    <Badge variant="accent">{ent.entity_type}</Badge>
                  </div>
                  {ent.summary && <div className="entity-summary">{ent.summary}</div>}
                  <div className="entity-footer-meta">
                    登場：第 {ent.created_chapter} 章 · 更新：第 {ent.updated_chapter} 章
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
