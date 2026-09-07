import React, { useState, useEffect, useCallback } from 'react';
import { StoryTerm } from '../../types';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { CustomSelect } from '../common/CustomSelect';
import { listTerms, createTerm, deleteTerm, updateTerm } from '../../api/terms';
import { IconTag, IconPlus, IconTrash, IconInfo } from '../common/Icons';

interface TermsModalProps {
  isOpen: boolean;
  onClose: () => void;
  novelId: string | null;
}

export const TermsModal: React.FC<TermsModalProps> = ({ isOpen, onClose, novelId }) => {
  const [terms, setTerms] = useState<StoryTerm[]>([]);
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [isLoading, setIsLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  // New term form state
  const [newTerm, setNewTerm] = useState('');
  const [newCategory, setNewCategory] = useState('通用術語');
  const [newDefinition, setNewDefinition] = useState('');
  const [newNotes, setNewNotes] = useState('');

  const fetchTermsList = useCallback(async () => {
    if (!novelId) return;
    setIsLoading(true);
    try {
      const res = await listTerms(novelId);
      setTerms(res.terms || []);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [novelId]);

  useEffect(() => {
    if (isOpen && novelId) {
      fetchTermsList();
    }
  }, [isOpen, novelId, fetchTermsList]);

  const handleCreateTerm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!novelId || !newTerm.trim() || !newDefinition.trim()) return;

    try {
      await createTerm(novelId, {
        term: newTerm.trim(),
        category: newCategory.trim(),
        definition: newDefinition.trim(),
        notes: newNotes.trim() || undefined,
      });
      setNewTerm('');
      setNewDefinition('');
      setNewNotes('');
      setShowAddForm(false);
      await fetchTermsList();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteTerm = async (termId: string) => {
    if (!novelId) return;
    try {
      await deleteTerm(novelId, termId);
      await fetchTermsList();
    } catch (err) {
      console.error(err);
    }
  };

  const categories = ['all', '通用術語', '修煉體系', '地理名詞', '功法法寶', '宗門勢力'];

  const filteredTerms = terms.filter((t) => {
    if (categoryFilter === 'all') return true;
    return t.category === categoryFilter;
  });

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="故事專用術語庫 (Glossary Constraints)"
      footer={
        <div className="modal-footer-actions">
          <Button variant="ghost" onClick={onClose}>
            關閉
          </Button>
        </div>
      }
    >
      <div className="terms-manager-container">
        <div className="terms-explainer-banner">
          <IconInfo size={16} className="text-accent" />
          <span>
            術語庫已自動對接後端 Prompt
            約束注入引擎，創作各階段均會強制 AI 嚴格遵循定義，避免名詞漂移與設定矛盾。
          </span>
        </div>

        <div className="terms-action-bar">
          <div className="terms-category-pills">
            {categories.map((cat) => (
              <button
                key={cat}
                type="button"
                className={`category-pill-btn ${categoryFilter === cat ? 'active' : ''}`}
                onClick={() => setCategoryFilter(cat)}
              >
                {cat === 'all' ? '全部類別' : cat}
              </button>
            ))}
          </div>

          <Button
            size="xs"
            variant="secondary"
            onClick={() => setShowAddForm(!showAddForm)}
            icon={<IconPlus size={12} />}
          >
            新增術語
          </Button>
        </div>

        {showAddForm && (
          <form className="add-term-inline-card" onSubmit={handleCreateTerm}>
            <div className="form-group">
              <label className="form-label">術語名稱</label>
              <input
                type="text"
                className="form-input"
                placeholder="例如: 乾坤九轉丹"
                value={newTerm}
                onChange={(e) => setNewTerm(e.target.value)}
                autoFocus
              />
            </div>

            <div className="form-group">
              <label className="form-label">分類</label>
              <CustomSelect
                value={newCategory}
                options={[
                  { value: '通用術語', label: '通用術語' },
                  { value: '修煉體系', label: '修煉體系' },
                  { value: '地理名詞', label: '地理名詞' },
                  { value: '功法法寶', label: '功法法寶' },
                  { value: '宗門勢力', label: '宗門勢力' },
                ]}
                onChange={(val) => setNewCategory(val)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">定義與嚴格約束規範</label>
              <textarea
                className="form-textarea"
                placeholder="明確敘述該術語之具體特質、限制與使用情境..."
                value={newDefinition}
                onChange={(e) => setNewDefinition(e.target.value)}
              />
            </div>

            <div className="inline-card-buttons">
              <Button size="xs" variant="primary" type="submit">
                儲存術語
              </Button>
              <Button
                size="xs"
                variant="ghost"
                type="button"
                onClick={() => setShowAddForm(false)}
              >
                取消
              </Button>
            </div>
          </form>
        )}

        <div className="terms-scroll-list">
          {filteredTerms.length === 0 ? (
            <div className="terms-empty-hint">暫無符合條件的專用術語</div>
          ) : (
            filteredTerms.map((item) => (
              <div key={item.id} className="term-card">
                <div className="term-card-header">
                  <div className="term-name-wrapper">
                    <IconTag size={13} className="text-accent" />
                    <span className="term-name">{item.term}</span>
                  </div>
                  <div className="term-header-actions">
                    <Badge variant="accent">{item.category}</Badge>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs text-muted"
                      onClick={() => handleDeleteTerm(item.id)}
                      title="刪除術語"
                    >
                      <IconTrash size={12} />
                    </button>
                  </div>
                </div>
                <div className="term-definition">{item.definition}</div>
                {item.notes && <div className="term-notes">備註：{item.notes}</div>}
              </div>
            ))
          )}
        </div>
      </div>
    </Modal>
  );
};
